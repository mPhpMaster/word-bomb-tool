import time
import threading
import os
import shutil
import sys
import requests
import subprocess
import random
import keyboard
import pytesseract
import mss
import json
import hashlib
import logging
from PIL import Image, ImageOps
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set
from dataclasses import dataclass, asdict
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ocr_helper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================= CONFIG =================
CONFIG_FILE = "ocr_config.json"
REGION_BACKUP_FILE = "region_backup.json"

THEME = {
    "bg": "#282c34",
    "fg": "#abb2bf",
    "log_bg": "#21252b",
    "log_fg": "#98c379",
    "select_bg": "#3e4452",
    "accent": "#61afef",
    "error": "#e06c75",
    "success": "#98c379",
    "warning": "#e5c07b",
    "font_family": "Consolas",
    "font_size": 10,
    "font_size_small": 9,
}

OCR_INTERVAL = 1
DATAMUSE_API = "https://api.datamuse.com/words?sp="
TYPING_DELAY = 0.08
MAX_SUGGESTIONS_DISPLAY = 50
MAX_TYPED_HISTORY = 1000
CACHE_EXPIRY_MINUTES = 5
OCR_TIMEOUT = 5

@dataclass
class AppState:
    region: Optional[Dict] = None
    suggestions: List[str] = None
    last_ocr_text: Optional[str] = None
    auto_mode_active: bool = False
    current_mode_index: int = 2
    current_sort_mode_index: int = 2
    suggestion_index: int = 0
    typed_words_history: Set[str] = None
    total_typed_count: int = 0
    
    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []
        if self.typed_words_history is None:
            self.typed_words_history = set()

def load_config():
    """Load configuration and saved state from file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info("Configuration loaded from file")
                return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    return {}

def save_config(state: AppState):
    """Save application state to configuration file."""
    try:
        config = {
            "region": state.region,
            "current_mode_index": state.current_mode_index,
            "current_sort_mode_index": state.current_sort_mode_index,
            "total_typed_count": state.total_typed_count,
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("Configuration saved")
    except Exception as e:
        logger.error(f"Error saving config: {e}")

def find_tesseract_path():
    """Find Tesseract installation path."""
    path_from_which = shutil.which("tesseract")
    if path_from_which:
        return path_from_which
    
    default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_path):
        return default_path
    return None

TESSERACT_PATH = find_tesseract_path()
TESSERACT_INSTALLER_URL = "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe"

if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ================= GLOBAL STATE =================
state = AppState()
log_queue = []
_log_lock = threading.Lock()
_state_lock = threading.Lock()
region_overlay = None
log_overlay = None
help_win = None

SEARCH_MODES = ["Starts With", "Ends With", "Contains"]
SORT_MODES = ["Shortest", "Longest", "Random"]

# OCR Caching and Threading
ocr_cache = {}
executor = ThreadPoolExecutor(max_workers=2)

# ================= STATE MANAGEMENT =================
def get_current_mode():
    with _state_lock:
        return SEARCH_MODES[state.current_mode_index]

def get_current_sort_mode():
    with _state_lock:
        return SORT_MODES[state.current_sort_mode_index]

def get_state_text():
    """Generates the current state text dynamically."""
    with _state_lock:
        return f"""
Current Mode: {get_current_mode()}
Current Sort: {get_current_sort_mode()}
Auto Mode: {'On' if state.auto_mode_active else 'Off'}
Words Typed: {state.total_typed_count}
"""

def get_help_text():
    """Generates the full help text dynamically."""
    return f"""
{get_state_text()}
=====================================
HOTKEYS
=====================================
Fetch Suggestions:  SHIFT
Select Region:    TAB

Change Search Mode: Page Up
Change Sort Mode:   Page Down

Clear History:      Delete
Toggle This Log:    Caps Lock
Toggle Auto Mode:   F1

Show This Window:   . (period)
Quit Application:   Ctrl+C
"""

# ================= LOGGING =================
def log(message: str, level: str = "INFO"):
    """Log message with optional level (INFO, WARNING, ERROR)."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Choose color based on level
    if level == "ERROR":
        color_fg = THEME["error"]
    elif level == "WARNING":
        color_fg = THEME["warning"]
    else:
        color_fg = THEME["log_fg"]
    
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    
    with _log_lock:
        log_queue.append((formatted_msg, color_fg))
        # Keep log queue size manageable
        if len(log_queue) > 500:
            log_queue.pop(0)

# ================= REGION OVERLAY =================
class RegionOverlay(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self._region = None
        self.ready = threading.Event()
        self.start()

    def run(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.4)
        self.root.overrideredirect(True)

        self.canvas = tk.Canvas(self.root, bg=THEME["bg"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_rectangle(0, 0, 0, 0, outline=THEME["accent"], width=2, tags="border")

        self.ready.set()
        self.root.mainloop()

    def show_region(self, new_region):
        self.ready.wait()
        self._region = new_region
        if not self._region:
            self.root.withdraw()
            return

        x, y = self._region["left"], self._region["top"]
        w, h = self._region["width"], self._region["height"]
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.canvas.coords("border", 2, 2, w - 2, h - 2)
        self.root.deiconify()

# ================= REGION SELECTION =================
def show_select_region():
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.3)
    root.attributes("-topmost", True)
    root.wait_visibility(root)
    
    canvas = tk.Canvas(root, cursor="cross", bg="black")
    canvas.pack(fill=tk.BOTH, expand=True)

    start_x = start_y = 0
    rect = None
    result = {}

    def on_mouse_down(e):
        nonlocal start_x, start_y, rect
        start_x, start_y = e.x, e.y
        rect = canvas.create_rectangle(start_x, start_y, e.x, e.y, outline=THEME["accent"], width=2)

    def on_mouse_move(e):
        if rect:
            canvas.coords(rect, start_x, start_y, e.x, e.y)

    def on_mouse_up(e):
        x1, y1 = min(start_x, e.x), min(start_y, e.y)
        x2, y2 = max(start_x, e.x), max(start_y, e.y)

        result["region"] = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
        root.quit()

    def on_escape(e):
        root.quit()

    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)
    root.bind("<Escape>", on_escape)

    root.mainloop()
    root.destroy()

    if "region" not in result or result["region"]["width"] <= 0:
        log("Region selection cancelled.", "WARNING")
        raise RuntimeError("Region selection cancelled")

    return result["region"]

# ================= OCR PROCESSING =================
def get_image_hash(img_data: bytes) -> str:
    """Generate hash of image data for caching."""
    return hashlib.md5(img_data).hexdigest()

def preprocess_image(image: Image.Image) -> Image.Image:
    """Preprocess image for OCR."""
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = image.point(lambda x: 0 if x < 140 else 255)
    return image

def perform_ocr(region: Dict) -> Optional[str]:
    """Perform OCR on region with caching and error handling."""
    try:
        with mss.mss() as sct:
            img = sct.grab(region)
        
        img_hash = get_image_hash(img.rgb)
        
        # Check cache
        if img_hash in ocr_cache:
            cached_text, cached_time = ocr_cache[img_hash]
            age = datetime.now() - cached_time
            if age < timedelta(minutes=CACHE_EXPIRY_MINUTES):
                return cached_text
            else:
                del ocr_cache[img_hash]
        
        image = Image.frombytes("RGB", img.size, img.rgb)
        image = preprocess_image(image)
        
        raw_text = pytesseract.image_to_string(
            image,
            config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        )
        
        letters = "".join(c for c in raw_text if c.isalpha()).lower()
        
        # Cache result
        if letters:
            ocr_cache[img_hash] = (letters, datetime.now())
        
        return letters if letters else None
    
    except Exception as e:
        logger.error(f"WBT Error: {e}", exc_info=True)
        log(f"[WBT ERROR]: {str(e)}", "ERROR")
        return None

def fetch_suggestions(letters: str) -> List[str]:
    """Fetch suggestions from Datamuse API with error handling and retry."""
    if not letters or len(letters) < 1:
        return []
    
    try:
        mode = get_current_mode()
        if mode == "Starts With":
            url = DATAMUSE_API + letters + "*"
        elif mode == "Ends With":
            url = DATAMUSE_API + "*" + letters
        else:
            url = DATAMUSE_API + "*" + letters + "*"
        
        log(f"Fetching suggestions for '{letters}'...")
        r = requests.get(url, timeout=OCR_TIMEOUT)
        r.raise_for_status()
        
        data = r.json()
        if data:
            suggestions = [item["word"] for item in data if len(item["word"].split()) == 1]
            # Limit display
            suggestions = suggestions[:MAX_SUGGESTIONS_DISPLAY]
            log(f"Found {len(suggestions)} suggestions.")
            return suggestions
        else:
            log("No suggestions found.", "WARNING")
            return []
    
    except requests.exceptions.Timeout:
        log("[API ERROR]: Request timeout", "ERROR")
        return []
    except requests.exceptions.ConnectionError:
        log("[API ERROR]: Connection failed", "ERROR")
        return []
    except Exception as e:
        log(f"[API ERROR]: {str(e)}", "ERROR")
        logger.error(f"API Error: {e}", exc_info=True)
        return []

# ================= SUGGESTION MANAGEMENT =================
def resort_suggestions():
    """Re-sort suggestions based on current sort mode."""
    with _state_lock:
        if state.suggestions:
            sort_mode = get_current_sort_mode()
            if sort_mode == "Shortest":
                state.suggestions.sort(key=len)
            elif sort_mode == "Longest":
                state.suggestions.sort(key=len, reverse=True)
            elif sort_mode == "Random":
                random.shuffle(state.suggestions)
            state.suggestion_index = 0

def reset_suggestions():
    """Clear current suggestions and OCR text."""
    with _state_lock:
        state.suggestions = []
        state.suggestion_index = 0
        state.last_ocr_text = None

def type_next_word():
    """Type next untyped suggestion."""
    with _state_lock:
        if not state.suggestions:
            log("No suggestions loaded. Press SHIFT on text to get suggestions.", "WARNING")
            return
        
        original_index = state.suggestion_index
        for i in range(len(state.suggestions)):
            current_word_index = (original_index + i) % len(state.suggestions)
            word_to_type = state.suggestions[current_word_index]
            
            if ' ' in word_to_type:
                continue
            
            if word_to_type in state.typed_words_history:
                log(f"Skipping already-typed word: '{word_to_type}'")
                continue
            
            # Type the word
            log(f"Typing: '{word_to_type}'")
            keyboard.write(word_to_type, delay=TYPING_DELAY)
            keyboard.press_and_release('enter')
            
            state.typed_words_history.add(word_to_type)
            state.total_typed_count += 1
            state.suggestion_index = current_word_index + 1
            
            # Limit history size
            if len(state.typed_words_history) > MAX_TYPED_HISTORY:
                oldest = state.typed_words_history.pop()
                logger.info(f"Removed oldest word from history: {oldest}")
            
            return
        
        log("All available suggestions have been typed.", "WARNING")

def handle_shift_press():
    """OCR text and fetch/type suggestions."""
    with _state_lock:
        if not state.region:
            log("Cannot perform OCR: No region selected.", "ERROR")
            # Schedule region selection on main thread
            if log_overlay and log_overlay.root:
                log_overlay.root.after(0, select_region)
            return
    
    # Run OCR in thread to avoid blocking
    executor.submit(_handle_shift_async)

def _handle_shift_async():
    """Async OCR and suggestion handler."""
    with _state_lock:
        region_copy = state.region
    
    if not region_copy:
        return
    
    log("Processing OCR...")
    letters = perform_ocr(region_copy)
    
    if not letters:
        log("OCR returned no characters. Please try again.", "WARNING")
        return
    
    with _state_lock:
        if letters == state.last_ocr_text and state.suggestions:
            # Same text, type next word
            pass
        else:
            # New text, fetch suggestions
            state.last_ocr_text = letters
            log(f"--- OCR: {letters} ---")
            state.suggestions = fetch_suggestions(letters)
            resort_suggestions()
            if state.suggestions:
                log("\n".join(state.suggestions[:10]) + 
                    (f"\n... and {len(state.suggestions) - 10} more" 
                     if len(state.suggestions) > 10 else ""))
            state.suggestion_index = 0
    
    type_next_word()

def select_region():
    """Select new OCR region."""
    try:
        if region_overlay:
            region_overlay.show_region(None)
        new_region = show_select_region()
        with _state_lock:
            state.region = new_region
        log("New region selected.")
        if region_overlay:
            region_overlay.show_region(new_region)
        save_config(state)
    except RuntimeError:
        pass

def set_search_mode(mode_index: Optional[int] = None):
    """Set search mode."""
    with _state_lock:
        if mode_index is None:
            mode_index = (state.current_mode_index + 1) % len(SEARCH_MODES)
        if state.current_mode_index == mode_index:
            return
        state.current_mode_index = mode_index
        log(f"Current Mode: {get_current_mode()}")
        reset_suggestions()
    
    if log_overlay:
        log_overlay.update_menu_state()
    save_config(state)

def set_sort_mode(mode_index: Optional[int] = None):
    """Set sort mode."""
    with _state_lock:
        if mode_index is None:
            mode_index = (state.current_sort_mode_index + 1) % len(SORT_MODES)
        if state.current_sort_mode_index == mode_index:
            return
        state.current_sort_mode_index = mode_index
        log(f"Current Sort: {get_current_sort_mode()}")
        resort_suggestions()
    
    if log_overlay:
        log_overlay.update_menu_state()
    save_config(state)

def clear_typed_history():
    """Clear typed words history."""
    with _state_lock:
        state.typed_words_history.clear()
        state.total_typed_count = 0
    log("Cleared history of typed words.")
    save_config(state)

def toggle_auto_mode():
    """Toggle auto mode."""
    with _state_lock:
        state.auto_mode_active = not state.auto_mode_active
        if state.auto_mode_active:
            log("Auto mode ENABLED. Watching for changes...")
            executor.submit(auto_mode_watcher)
        else:
            log("Auto mode DISABLED.")
    
    if log_overlay:
        log_overlay.update_menu_state()
    save_config(state)

def auto_mode_watcher():
    """Watch region for text changes and auto-fetch suggestions."""
    last_auto_text = None
    while True:
        with _state_lock:
            if not state.auto_mode_active:
                time.sleep(1)
                continue
            region_copy = state.region
        
        if region_copy is None:
            time.sleep(1)
            continue
        
        try:
            letters = perform_ocr(region_copy)
            if letters and letters != last_auto_text:
                log(f"Auto-detected change: '{letters}'")
                last_auto_text = letters
                _handle_shift_async()
        except Exception as e:
            logger.error(f"Auto mode error: {e}", exc_info=True)
            log(f"[AUTO ERROR]: {str(e)}", "ERROR")
            time.sleep(2)
        
        time.sleep(OCR_INTERVAL)

# ================= LOGGING OVERLAY =================
class LogOverlay(threading.Thread):
    def __init__(self, region_overlay_ref):
        super().__init__()
        self.daemon = True
        self.visible = True
        self.region_overlay = region_overlay_ref
        self.root = None
        self.text_widget = None
        self.search_mode_var = None
        self.sort_mode_var = None
        self.auto_mode_var = None
        self.start()

    def run(self):
        self.root = tk.Tk()
        self.root.title("WBT v2 Log")
        self.root.geometry("500x400+10+10")
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.root.config(bg=THEME["bg"])

        # Style
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=THEME["bg"], foreground=THEME["fg"], 
                       font=(THEME["font_family"], THEME["font_size"]))
        style.configure("TButton", background=THEME["select_bg"], 
                       font=(THEME["font_family"], THEME["font_size_small"]))
        style.map("TButton", background=[("active", THEME["accent"])])

        # State Variables
        self.search_mode_var = tk.StringVar()
        self.sort_mode_var = tk.StringVar()
        self.auto_mode_var = tk.BooleanVar()

        # Menu
        menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        options_menu = tk.Menu(menubar, tearoff=0)
        help_menu = tk.Menu(menubar, tearoff=0)

        menubar.add_cascade(label="File", menu=file_menu)
        menubar.add_cascade(label="Options", menu=options_menu)
        menubar.add_cascade(label="Help", menu=help_menu)

        file_menu.add_command(label="Exit", command=graceful_exit, accelerator="Ctrl+C")
        
        options_menu.add_command(label="Select Region", command=select_region, accelerator="Tab")
        options_menu.add_separator()
        search_menu = tk.Menu(options_menu, tearoff=0)
        options_menu.add_cascade(label="Search Mode", menu=search_menu)
        for i, mode in enumerate(SEARCH_MODES):
            search_menu.add_radiobutton(label=mode, variable=self.search_mode_var, value=mode, 
                                       command=lambda i=i: set_search_mode(i))
        sort_menu = tk.Menu(options_menu, tearoff=0)
        options_menu.add_cascade(label="Sort Mode", menu=sort_menu)
        for i, mode in enumerate(SORT_MODES):
            sort_menu.add_radiobutton(label=mode, variable=self.sort_mode_var, value=mode, 
                                     command=lambda i=i: set_sort_mode(i))
        options_menu.add_separator()
        options_menu.add_checkbutton(label="Auto Mode", variable=self.auto_mode_var, 
                                    command=toggle_auto_mode, accelerator="F1")
        options_menu.add_separator()
        options_menu.add_command(label="Clear Typed History", command=clear_typed_history, 
                                accelerator="Delete")

        help_menu.add_command(label="Show Hotkeys", command=show_help_window, accelerator=".")

        # Text Widget
        self.text_widget = tk.Text(self.root, bg=THEME["log_bg"], fg=THEME["log_fg"], 
                                   font=(THEME["font_family"], THEME["font_size"]), 
                                   relief=tk.FLAT, bd=0, insertbackground=THEME["fg"])
        self.text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.root.protocol("WM_DELETE_WINDOW", graceful_exit)
        self.update_menu_state()
        self.check_queue()
        self.root.mainloop()

    def update_menu_state(self):
        if self.root:
            self.root.after(0, self._update_menu_vars)
    
    def _update_menu_vars(self):
        if self.search_mode_var:
            self.search_mode_var.set(get_current_mode())
        if self.sort_mode_var:
            self.sort_mode_var.set(get_current_sort_mode())
        if self.auto_mode_var:
            with _state_lock:
                self.auto_mode_var.set(state.auto_mode_active)

    def check_queue(self):
        with _log_lock:
            while log_queue:
                message, color = log_queue.pop(0)
                self.text_widget.insert(tk.END, message + "\n")
                self.text_widget.tag_config(color, foreground=color)
                self.text_widget.tag_add(color, f"{self.text_widget.index('end')}-1c linestart", 
                                        f"{self.text_widget.index('end')}-1c lineend")
                self.text_widget.see(tk.END)
        self.root.after(100, self.check_queue)

    def _toggle_visibility(self):
        self.visible = not self.visible
        if self.visible:
            self.root.deiconify()
            with _state_lock:
                if state.region and self.region_overlay:
                    self.region_overlay.show_region(state.region)
        else:
            self.root.withdraw()
            if self.region_overlay:
                self.region_overlay.show_region(None)

    def toggle_visibility(self):
        if self.root:
            self.root.after(0, self._toggle_visibility)

def show_help_window():
    """Show help window."""
    if log_overlay and log_overlay.root:
        log_overlay.root.after(0, _create_help_window)

def _create_help_window():
    """Create help window (must run on Tk thread)."""
    global help_win
    
    if help_win and help_win.winfo_exists():
        help_win.lift()
        return
    
    help_win = tk.Toplevel(log_overlay.root)
    help_win.title("Help & Hotkeys")
    help_win.geometry("450x400")
    help_win.attributes("-topmost", True)
    help_win.config(bg=THEME["bg"])

    text_widget = tk.Text(help_win, font=(THEME["font_family"], THEME["font_size"]), 
                         relief=tk.FLAT, background=THEME["bg"], foreground=THEME["fg"], 
                         wrap=tk.WORD, padx=10, pady=10)
    text_widget.pack(fill=tk.BOTH, expand=True)
    text_widget.insert(tk.END, get_help_text().strip())
    text_widget.config(state=tk.DISABLED)

    close_button = ttk.Button(help_win, text="Close", command=help_win.destroy)
    close_button.pack(pady=10)
    help_win.bind("<Escape>", lambda e: help_win.destroy())

def graceful_exit(exit_code=0):
    """Gracefully exit application."""
    with _state_lock:
        state.auto_mode_active = False
    
    try:
        keyboard.unhook_all()
    except Exception as e:
        logger.error(f"Error unhooking keyboard: {e}")
    
    save_config(state)
    time.sleep(0.1)
    os._exit(exit_code)

def check_and_install_tesseract():
    """Check for Tesseract and prompt installation if missing."""
    global TESSERACT_PATH
    if TESSERACT_PATH:
        return True

    log("Tesseract OCR not found on your system.", "WARNING")

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    response = messagebox.askyesno(
        "Tesseract OCR Not Found",
        "Tesseract OCR is required but was not found.\n\n"
        "Do you want to download and run the installer?"
    )
    root.destroy()

    if not response:
        log("User declined Tesseract installation.", "WARNING")
        return False

    try:
        installer_name = "tesseract_installer.exe"
        log(f"Downloading Tesseract installer...")
        
        with requests.get(TESSERACT_INSTALLER_URL, stream=True) as r:
            r.raise_for_status()
            with open(installer_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        log("Download complete. Running installer...")
        subprocess.run([installer_name], check=True)
        log("Restarting script to detect new installation...")
        os.execv(sys.executable, ['python'] + sys.argv)

    except Exception as e:
        log(f"Installation error: {str(e)}", "ERROR")
        logger.error(f"Installation error: {e}", exc_info=True)
    
    return False

# ================= MAIN =================
if __name__ == "__main__":
    try:
        # Load saved state
        config = load_config()
        state.region = config.get("region")
        state.current_mode_index = config.get("current_mode_index", 2)
        state.current_sort_mode_index = config.get("current_sort_mode_index", 2)
        state.total_typed_count = config.get("total_typed_count", 0)
        
        # Initialize overlays
        region_overlay = RegionOverlay()
        log_overlay = LogOverlay(region_overlay)

        log("========== WBT STARTED ==========")
        log(f"Tesseract: {'Found' if TESSERACT_PATH else 'Not Found'}")
        log(f"Saved region loaded: {state.region is not None}")
        
        show_help_window()
        log(get_state_text())

        # Check Tesseract
        if not check_and_install_tesseract():
            time.sleep(3)
            graceful_exit(1)
        
        # If no region saved, prompt selection
        if state.region is None:
            log("Press TAB to select a region to OCR", "WARNING")
        else:
            if region_overlay:
                region_overlay.show_region(state.region)
        
        # Register hotkeys
        keyboard.add_hotkey('f1', toggle_auto_mode)
        keyboard.add_hotkey('shift', handle_shift_press)
        keyboard.add_hotkey('tab', select_region)
        keyboard.add_hotkey('page up', set_search_mode)
        keyboard.add_hotkey('page down', set_sort_mode)
        keyboard.add_hotkey('delete', clear_typed_history)
        keyboard.add_hotkey('caps lock', lambda: log_overlay.toggle_visibility())
        keyboard.add_hotkey('.', show_help_window)
        keyboard.add_hotkey('ctrl+c', lambda: graceful_exit(0))

        keyboard.wait()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"FATAL ERROR: {e}")
        sys.exit(1)