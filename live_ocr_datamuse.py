import time
import threading
import os
import queue
import requests
import subprocess
import random
import keyboard
import pytesseract
import mss
from PIL import Image, ImageOps
import tkinter as tk
from tkinter import simpledialog

# ================= CONFIG =================
OCR_INTERVAL = 1
DATAMUSE_API = "https://api.datamuse.com/words?sp="
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_INSTALLER_URL = "https://github.com/tesseract-ocr/tesseract/releases/download/5.3.0/tesseract-ocr-w64-setup-v5.3.0.20221214.exe" # A known stable version
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
TYPING_DELAY = 0.08  # Seconds between each keystroke
# =========================================

region = None
log_queue = queue.Queue()
region_overlay = None

# ---------- SEARCH MODES ----------
SEARCH_MODES = ["Starts With", "Ends With", "Contains"]
current_mode_index = 2

# ---------- SORT MODES ----------
SORT_MODES = ["Shortest", "Longest", "Random"]
current_sort_mode_index = 2

# ---------- AUTO MODE ----------
auto_mode_active = False
auto_mode_thread = None

def get_current_sort_mode():
    return SORT_MODES[current_sort_mode_index]

def get_current_mode():
    return SEARCH_MODES[current_mode_index]



# ---------- LOGGING OVERLAY ----------
class LogOverlay(threading.Thread):
    def __init__(self, region_overlay_ref):
        super().__init__()
        self.daemon = True
        self.visible = True
        self.region_overlay = region_overlay_ref
        self.start()

    def run(self):
        self.root = tk.Tk()
        self.root.title("WBT v3 Log")
        self.root.geometry("360x128+10+10")  # Position top-left
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.8)
        self.root.overrideredirect(True)  # No window decorations

        self.text = tk.Text(self.root, bg="black", fg="darkgreen", font=("Consolas", 8), height=15)
        self.text.pack(fill=tk.BOTH, expand=True)

        self.check_queue()
        self.root.mainloop()

    def check_queue(self):
        while not log_queue.empty():
            message = log_queue.get_nowait()
            self.text.insert(tk.END, message + "\n")
            self.text.see(tk.END)  # Auto-scroll
        self.root.after(100, self.check_queue)

    def _toggle_visibility(self):
        """Internal method to run on the Tk thread."""
        self.visible = not self.visible
        if self.visible:
            self.root.deiconify()
            # Also show the region overlay if a region is selected
            if region:
                self.region_overlay.show_region(region)
        else:
            self.root.withdraw()
            # Also hide the region overlay
            self.region_overlay.show_region(None)

    def toggle_visibility(self):
        self.root.after(0, self._toggle_visibility)
def log(message):
    print(message)
    log_queue.put(message)


# ---------- REGION OVERLAY ----------
class RegionOverlay(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self._region = None
        self.ready = threading.Event()
        self.start()

    def run(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Start hidden
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.4)
        self.root.overrideredirect(True)

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_rectangle(0, 0, 0, 0, outline="red", width=2, tags="border")

        self.ready.set()  # Signal that the Tkinter root is ready
        self.root.mainloop()

    def show_region(self, new_region):
        self.ready.wait()  # Wait until the Tkinter root is initialized
        self._region = new_region
        if not self._region:
            self.root.withdraw()
            return

        x, y = self._region["left"], self._region["top"]
        w, h = self._region["width"], self._region["height"]
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.canvas.coords("border", 2, 2, w-2, h-2)
        self.root.deiconify()


# ---------- REGION SELECTION (FIXED) ----------
def select_region():
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.3)
    root.attributes("-topmost", True)
    root.title("Select Region")

    canvas = tk.Canvas(root, cursor="cross", bg="black")
    canvas.pack(fill=tk.BOTH, expand=True)

    start_x = start_y = 0
    rect = None
    result = {}

    def on_mouse_down(e):
        nonlocal start_x, start_y, rect
        start_x, start_y = e.x, e.y
        rect = canvas.create_rectangle(
            start_x, start_y, e.x, e.y,
            outline="red", width=1
        )

    def on_mouse_move(e):
        if rect:
            canvas.coords(rect, start_x, start_y, e.x, e.y)

    def on_mouse_up(e):
        x1, y1 = min(start_x, e.x), min(start_y, e.y)
        x2, y2 = max(start_x, e.x), max(start_y, e.y)

        result["region"] = {
            "left": x1,
            "top": y1,
            "width": x2 - x1,
            "height": y2 - y1
        }
        root.quit()   # IMPORTANT

    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)

    root.mainloop()
    root.destroy()

    if "region" not in result or result["region"]["width"] <= 0:
        raise RuntimeError("Region selection failed")

    return result["region"]


# ---------- OCR AND TYPING LOGIC ----------
suggestion_list = []
suggestion_index = 0
last_ocr_text = None
typed_words_history = set()


def handle_shift_press():
    """On SHIFT press: OCR text. If text is new, fetch suggestions and type the first.
    If text is the same, type the next suggestion from the list."""
    global suggestion_list, suggestion_index, last_ocr_text
    with mss.mss() as sct:
        img = sct.grab(region)
    image = Image.frombytes("RGB", img.size, img.rgb)

    # ---- OCR preprocessing ----
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    image = image.point(lambda x: 0 if x < 140 else 255)

    raw_text = pytesseract.image_to_string(
        image,
        config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    )
    letters = "".join(c for c in raw_text if c.isalpha()).lower()
    
    # If OCR is empty, prompt for manual input
    if not letters:
        log("[INFO]        : Empty. Prompting.")
        # We need a temporary root for the dialog
        root = tk.Tk()
        root.withdraw() # Hide the main window
        root.attributes("-topmost", True) # Ensure dialog is on top
        manual_input = simpledialog.askstring("Manual Input", "OCR failed. Enter characters manually:", parent=root)
        root.destroy()

        if manual_input:
            letters = "".join(c for c in manual_input if c.isalpha()).lower()
        else:
            log("[INFO]        : Manual input cancelled.")
            return # Stop processing if user cancels

    # If OCR'd text is the same as last time, just type the next word
    if letters and letters == last_ocr_text:
        type_next_word()
        return

    # Otherwise, treat it as a new query
    last_ocr_text = letters
    log("-" * 45)
    log(f"[RAW OCR]     : {repr(raw_text.strip())}")
    log(f"[FILTERED]    : {letters}")

    # Reset and fetch new suggestions
    suggestion_list = []
    suggestion_index = 0

    if len(letters) >= 1:
        try:
            # Construct URL based on current search mode
            if get_current_mode() == "Starts With":
                url = DATAMUSE_API + letters + "*"
            elif get_current_mode() == "Ends With":
                url = DATAMUSE_API + "*" + letters
            else: # Contains
                url = DATAMUSE_API + "*" + letters + "*"
            r = requests.get(url, timeout=1)
            data = r.json()
            if data:
                # Sort suggestions based on the current sort mode
                new_suggestions = [item["word"] for item in data]
                sort_mode = get_current_sort_mode()
                if sort_mode == "Shortest":
                    new_suggestions.sort(key=len)
                elif sort_mode == "Longest":
                    new_suggestions.sort(key=len, reverse=True)
                elif sort_mode == "Random":
                    random.shuffle(new_suggestions)
                suggestion_list = new_suggestions
                log(f"[DATAMUSE]    : Found {len(suggestion_list)} suggestions")
        except Exception as e:
            log(f"[API ERROR]   : {e}")

    # If new suggestions were found, type the first one
    suggestion_index = 0 # Reset index for the new list
    type_next_word() # This will find and type the first available word

def type_next_word():
    """Finds the next untyped suggestion and types it."""
    global suggestion_list, suggestion_index, typed_words_history
    if not suggestion_list:
        log("[INFO]        : No suggestions loaded. Press SHIFT first.")
        return

    # Search for the next word that hasn't been typed yet
    original_index = suggestion_index
    for i in range(len(suggestion_list)):
        # Start searching from the current index and wrap around
        current_word_index = (original_index + i) % len(suggestion_list)
        word_to_type = suggestion_list[current_word_index]

        # If the word contains spaces, ignore it.
        if word_to_type.count(' ') > 0:
            typed_words_history.add(word_to_type) # Also add to history to avoid re-checking
            continue

        word_to_write = word_to_type.replace(' ', '-')

        if word_to_type not in typed_words_history:
            log(f"[TYPING]      : '{word_to_write}' (from: '{word_to_type}')")
            keyboard.write(word_to_write, delay=TYPING_DELAY)
            keyboard.press_and_release('enter')

            # Remember the word and set the index for the next search
            typed_words_history.add(word_to_type)
            suggestion_index = current_word_index + 1
            return

    log("[INFO]        : All available suggestions have been typed.")

def reselect_region():
    """Callback for Tab to re-run region selection."""
    global region
    log("Region reselection initiated...")
    if region_overlay:
        region_overlay.show_region(None)  # Hide overlay during selection

    try:
        new_region = select_region()
        region = new_region
        log(f"New region selected: {region}")
        if region_overlay:
            region_overlay.show_region(region)
    except RuntimeError as e:
        log(f"Region reselection cancelled or failed: {e}")
        if region_overlay:
            region_overlay.show_region(region) # Show old region again

def change_search_mode():
    """Callback for Page Up to cycle through search modes."""
    global current_mode_index
    current_mode_index = (current_mode_index + 1) % len(SEARCH_MODES)
    log(f"[MODE]        : Changed search mode to '{get_current_mode()}'")
    # Reset suggestions when mode changes, as they are now invalid
    global suggestion_list, suggestion_index, last_ocr_text
    suggestion_list = []
    suggestion_index = 0
    last_ocr_text = None # Force re-OCR on next SHIFT press

def change_sort_mode():
    """Callback for Page Down to cycle through sort modes."""
    global current_sort_mode_index, suggestion_list, suggestion_index
    current_sort_mode_index = (current_sort_mode_index + 1) % len(SORT_MODES)
    sort_mode = get_current_sort_mode()
    log(f"[SORT]        : Changed sort mode to '{sort_mode}'")

    # If there's an existing list of suggestions, re-sort it
    if suggestion_list:
        if sort_mode == "Shortest":
            suggestion_list.sort(key=len)
        elif sort_mode == "Longest":
            suggestion_list.sort(key=len, reverse=True)
        elif sort_mode == "Random":
            random.shuffle(suggestion_list)

        suggestion_index = 0 # Reset to the start of the re-sorted list
        log("[SORT]        : Re-sorted existing suggestions.")

def clear_typed_history():
    """Callback for Delete key to clear the typed words history."""
    global typed_words_history
    typed_words_history.clear()
    log("-" * 45)
    log("[INFO]        : Cleared history of typed words.")
    log("-" * 45)

def toggle_auto_mode():
    """Callback for F1 to toggle auto mode."""
    global auto_mode_active, auto_mode_thread
    auto_mode_active = not auto_mode_active
    if auto_mode_active:
        log("[AUTO]        : Auto mode ENABLED. Watching for changes...")
        # Start the auto mode thread if it's not already running
        if auto_mode_thread is None or not auto_mode_thread.is_alive():
            auto_mode_thread = threading.Thread(target=auto_mode_watcher, daemon=True)
            auto_mode_thread.start()
    else:
        log("[AUTO]        : Auto mode DISABLED.")

def auto_mode_watcher():
    """
    A thread that runs in the background, watches the OCR region,
    and triggers the suggestion logic when the text changes.
    """
    log("[AUTO]        : Watcher thread started.")
    last_auto_text = None

    while True: # The loop will be controlled by auto_mode_active
        if not auto_mode_active:
            # If auto mode is turned off, wait a bit and check again.
            # This prevents the thread from exiting.
            time.sleep(1)
            continue

        if region is None:
            time.sleep(1) # Wait if no region is selected
            continue

        try:
            with mss.mss() as sct:
                img = sct.grab(region)

            image = Image.frombytes("RGB", img.size, img.rgb)
            # Apply the same preprocessing as the manual trigger
            image = image.convert("L")
            image = ImageOps.autocontrast(image)
            image = image.point(lambda x: 0 if x < 140 else 255)

            raw_text = pytesseract.image_to_string(
                image,
                config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            )
            current_text = "".join(c for c in raw_text if c.isalpha()).lower()

            # Trigger only if the text is new and not empty
            if current_text and current_text != last_auto_text:
                log(f"[AUTO]        : Change detected! ('{last_auto_text}' -> '{current_text}')")
                last_auto_text = current_text
                handle_shift_press() # Trigger the main logic

        except Exception as e:
            log(f"[AUTO ERROR]  : {e}")
            # Wait a bit longer after an error to avoid spamming
            time.sleep(2)

        # The interval for checking for changes in auto mode
        time.sleep(OCR_INTERVAL)

def show_help():
    """Logs the main help text to the overlay."""
    log("\n" + "="*45)
    log(f"Current Mode     : {get_current_mode()}")
    log(f"Current Sort     : {get_current_sort_mode()}")
    log("Press SHIFT      : Fetch")
    log("Press TAB        : Select region")
    log("Press Page Up    : Change mode")
    log("Press Page Down  : Change sort")
    log("Press Delete     : Clear history")
    log("Press Caps Lock  : Toggle Log")
    log("Press F1         : Toggle Auto Mode")
    log("Press .          : Show this help")
    log("Press CTRL+C     : Quit")
    log("="*45 + "\n")


# ---------- SETUP CHECKS ----------
def check_and_install_tesseract():
    """Checks for Tesseract OCR and prompts for installation if not found."""
    if os.path.exists(TESSERACT_PATH):
        log(f"Tesseract found: {TESSERACT_PATH}")
        return True

    log(f"Tesseract not found at {TESSERACT_PATH}")

    # Use Tkinter for a graphical confirmation dialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    response = tk.messagebox.askyesno(
        "Tesseract OCR Not Found",
        "Tesseract OCR is required but was not found.\n\n"
        "Do you want to download and run the official installer now?\n\n"
        "IMPORTANT: During installation, please ensure you install it to the default location:\n"
        f"C:\\Program Files\\Tesseract-OCR"
    )
    root.destroy()

    if not response:
        log("User declined Tesseract installation. Exiting.")
        return False

    try:
        installer_name = "tesseract_installer.exe"
        log(f"Downloading Tesseract installer...")
        
        with requests.get(TESSERACT_INSTALLER_URL, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            with open(installer_name, 'wb') as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        # Use carriage return to show progress on a single line in console
                        print(f"Downloading... {downloaded // 1024} KB / {total_size // 1024} KB", end='\r')
        print("\nDownload complete.")
        log("Download complete. Running installer...")
        subprocess.run([installer_name], check=True)
        log("Installer finished. Please restart this script.")
    except Exception as e:
        log(f"An error occurred during download/installation: {e}")
    return False

# ---------- MAIN ----------
if __name__ == "__main__":
    region_overlay = RegionOverlay()
    log_overlay = LogOverlay(region_overlay)

    reselect_region() # Initial region selection

    # Check for Tesseract after overlays are up, so we can show messages
    if not check_and_install_tesseract():
        time.sleep(5) # Give user time to read the message in the overlay
        os._exit(1)

    show_help()
    log("GitHub           : https://github.com/mPhpMaster") # Replace with your GitHub
    log("Discord          : alhlack") # Replace with your Discord
    log("="*45 + "\n")
    
    keyboard.add_hotkey('f1', toggle_auto_mode)
    keyboard.add_hotkey('shift', handle_shift_press)
    keyboard.add_hotkey('tab', reselect_region)
    keyboard.add_hotkey('page up', change_search_mode)
    keyboard.add_hotkey('page down', change_sort_mode)
    keyboard.add_hotkey('delete', clear_typed_history)
    keyboard.add_hotkey('caps lock', lambda: log_overlay.toggle_visibility())
    keyboard.add_hotkey('.', show_help)
    keyboard.add_hotkey('ctrl+c', lambda: os._exit(0))

    keyboard.wait()
