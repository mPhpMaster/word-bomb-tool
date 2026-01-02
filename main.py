import sys
import os
import time
import keyboard
import logging
import shutil
import requests
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

# Import modules
from config import (
    SEARCH_MODES, SORT_MODES, MAX_WORKER_THREADS,
    TESSERACT_INSTALLER_URL, UNDO_BUFFER_SIZE, MAX_TYPED_HISTORY
)
from logging_utils import setup_logging, LogQueue
from state import StateManager
from ocr_processor import OCRProcessor
from api_client import DatamuseClient
from suggestion_manager import SuggestionManager
from ui_manager import RegionOverlay, RegionSelector, LogDisplay, HelpWindow
from tray_manager import TrayIcon
from tkinter import messagebox
import tkinter as tk

logger = logging.getLogger(__name__)

class OCRApplication:
    """Main application class."""
    
    def __init__(self):
        self.state_manager = StateManager()
        self.ocr_processor = OCRProcessor()
        self.api_client = DatamuseClient()
        self.log_queue = LogQueue()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS)
        
        self.region_overlay = None
        self.log_display = None
        self.help_win = None
        self.tray_icon = None
        
        # Load saved state
        self.state_manager.load_state()
        
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Setup UI callbacks."""
        self.callbacks = {
            'select_region': self.select_region,
            'set_search_mode': self.set_search_mode,
            'set_sort_mode': self.set_sort_mode,
            'clear_history': self.clear_typed_history,
            'undo_word': self.undo_last_word,
            'show_help': self.show_help_window,
            'toggle_window': lambda: self.log_display.toggle_visibility(),
            'exit': self.graceful_exit,
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log message to UI."""
        self.log_queue.add(message, level)
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
    
    def get_state_text(self) -> str:
        """Get current state display text."""
        state = self.state_manager.get_state()
        mode = SEARCH_MODES[state.current_mode_index]
        sort_mode = SORT_MODES[state.current_sort_mode_index]
        return f"""
Current Mode: {mode}
Current Sort: {sort_mode}
Auto Mode: {'On' if state.auto_mode_active else 'Off'}
Words Typed: {state.total_typed_count}
API Status: {state.api_status}
"""
    
    def get_help_text(self) -> str:
        """Get help window text."""
        return f"""{self.get_state_text()}
=====================================
HOTKEYS
=====================================
Fetch Suggestions:  SHIFT
Select Region:    TAB

Change Search Mode: Page Up
Change Sort Mode:   Page Down

Clear History:      Delete
Undo Last Word:     Ctrl+Z
Toggle This Log:    Caps Lock
Toggle Auto Mode:   F1

Show This Window:   . (period)
Quit Application:   Ctrl+C
"""
    
    def handle_shift_press(self):
        """WBT and fetch suggestions."""
        state = self.state_manager.get_state()
        if not state.region:
            self.log("Cannot perform WBT: No region selected.", "ERROR")
            self.select_region()
            return
        
        self.executor.submit(self._handle_shift_async)
    
    def _handle_shift_async(self):
        """Async WBT handler."""
        state = self.state_manager.get_state()
        region = state.region
        if not region:
            return
        
        self.log("Processing WBT...")
        letters = self.ocr_processor.perform_ocr(region)
        
        if not letters:
            self.log("WBT returned no characters.", "WARNING")
            return
        
        state = self.state_manager.get_state()
        mode = SEARCH_MODES[state.current_mode_index]
        
        if letters == state.last_ocr_text and state.suggestions:
            # Same text, type next word
            self.type_next_word()
        else:
            # New text, fetch suggestions
            self.state_manager.update_state(last_ocr_text=letters)
            self.log(f"--- WBT: {letters} ---")
            
            suggestions = self.api_client.get_suggestions(letters, mode)
            self.state_manager.update_state(api_status=self.api_client.status)
            
            if suggestions:
                suggestions = SuggestionManager.sort_suggestions(
                    suggestions,
                    SORT_MODES[state.current_sort_mode_index]
                )
                self.state_manager.update_state(suggestions=suggestions, suggestion_index=0)
                
                self.log(f"Found {len(suggestions)} suggestions.")
                self.log("\n".join(suggestions[:10]) +
                        (f"\n... and {len(suggestions) - 10} more"
                         if len(suggestions) > 10 else ""))
            else:
                self.state_manager.update_state(suggestions=[], suggestion_index=0)
        
        self.type_next_word()
    
    def type_next_word(self):
        """Type next untyped suggestion."""
        state = self.state_manager.get_state()
        if not state.suggestions:
            self.log("No suggestions loaded.", "WARNING")
            return
        
        word, next_idx = SuggestionManager.get_next_untyped_word(
            state.suggestions,
            state.suggestion_index,
            state.typed_words_history
        )
        
        if not word:
            self.log("All available suggestions have been typed.", "WARNING")
            return
        
        self.log(f"Typing: '{word}'")
        keyboard.write(word, delay=0.08)
        keyboard.press_and_release('enter')
        
        # Record typing
        state.typed_words_history.add(word)
        state.total_typed_count += 1
        if len(state.typed_words_history) > MAX_TYPED_HISTORY:
            state.typed_words_history.pop()
        
        self.state_manager.add_typing_record(word, state.last_ocr_text or "")
        self.state_manager.update_state(
            typed_words_history=state.typed_words_history,
            total_typed_count=state.total_typed_count,
            suggestion_index=next_idx
        )
    
    def select_region(self):
        """Select WBT region."""
        try:
            if self.region_overlay:
                self.region_overlay.show_region(None)
            new_region = RegionSelector.select_region()
            self.state_manager.update_state(region=new_region)
            self.log("New region selected.")
            if self.region_overlay:
                self.region_overlay.show_region(new_region)
            self.state_manager.save_state()
        except RuntimeError:
            self.log("Region selection cancelled.", "WARNING")
    
    def set_search_mode(self, mode_index: int):
        """Set search mode."""
        state = self.state_manager.get_state()
        if state.current_mode_index == mode_index:
            return
        
        self.state_manager.update_state(
            current_mode_index=mode_index,
            suggestions=[],
            suggestion_index=0,
            last_ocr_text=None
        )
        self.log(f"Current Mode: {SEARCH_MODES[mode_index]}")
        self.state_manager.save_state()
    
    def set_sort_mode(self, mode_index: int):
        """Set sort mode."""
        state = self.state_manager.get_state()
        if state.current_sort_mode_index == mode_index:
            return
        
        self.state_manager.update_state(current_sort_mode_index=mode_index)
        
        if state.suggestions:
            sorted_suggestions = SuggestionManager.sort_suggestions(
                state.suggestions,
                SORT_MODES[mode_index]
            )
            self.state_manager.update_state(
                suggestions=sorted_suggestions,
                suggestion_index=0
            )
        
        self.log(f"Current Sort: {SORT_MODES[mode_index]}")
        self.state_manager.save_state()
    
    def clear_typed_history(self):
        """Clear typed history."""
        self.state_manager.update_state(
            typed_words_history=set(),
            typing_records=[],
            total_typed_count=0
        )
        self.log("Cleared history of typed words.")
        self.state_manager.save_state()
    
    def undo_last_word(self):
        """Undo last typed word."""
        word = self.state_manager.undo_last_word()
        if word:
            self.log(f"Undone: '{word}'")
        else:
            self.log("Nothing to undo.", "WARNING")
    
    def toggle_auto_mode(self):
        """Toggle auto mode."""
        state = self.state_manager.get_state()
        new_state = not state.auto_mode_active
        self.state_manager.update_state(auto_mode_active=new_state)
        
        if new_state:
            self.log("Auto mode ENABLED.")
            self.executor.submit(self.auto_mode_watcher)
        else:
            self.log("Auto mode DISABLED.")
    
    def auto_mode_watcher(self):
        """Watch for region changes in auto mode."""
        last_text = None
        while True:
            state = self.state_manager.get_state()
            if not state.auto_mode_active:
                time.sleep(1)
                continue
            
            if not state.region:
                time.sleep(1)
                continue
            
            try:
                letters = self.ocr_processor.perform_ocr(state.region)
                if letters and letters != last_text:
                    self.log(f"Auto-detected: '{letters}'")
                    last_text = letters
                    self._handle_shift_async()
            except Exception as e:
                logger.error(f"Auto mode error: {e}", exc_info=True)
                self.log(f"[AUTO ERROR]: {str(e)}", "ERROR")
                time.sleep(2)
            
            time.sleep(1)
    
    def show_help_window(self):
        """Show help window."""
        if self.log_display and self.log_display.root:
            self.log_display.root.after(0, self._show_help_window_async)
    
    def _show_help_window_async(self):
        """Show help window on main thread."""
        if self.help_win and self.help_win.winfo_exists():
            self.help_win.lift()
            return
        
        self.help_win = HelpWindow.show(self.log_display.root, self.get_help_text())
    
    def _setup_tray_icon(self):
        """Setup system tray icon (optional)."""
        try:
            from tray_manager import PYSTRAY_AVAILABLE
            
            if not PYSTRAY_AVAILABLE:
                self.log("Tray icon disabled (pystray not installed)", "WARNING")
                return
            
            tray_callbacks = {
                'select_region': self.callbacks['select_region'],
                'toggle_window': self.callbacks['toggle_window'],
                # 'toggle_auto_mode': self.toggle_auto_mode,
                # 'show_help': self.callbacks['show_help'],
                # 'clear_history': self.callbacks['clear_history'],
                # '': None,
                'exit': self.callbacks['exit'],
            }
            
            self.tray_icon = TrayIcon("WBT", tray_callbacks)
            if not self.tray_icon.run_in_thread():
                self.log("Failed to initialize tray icon", "WARNING")
        except ImportError:
            self.log("Tray icon unavailable (optional dependency)", "WARNING")
        except Exception as e:
            logger.error(f"Tray initialization error: {e}", exc_info=True)
            self.log(f"Tray icon error: {str(e)}", "WARNING")
    
    def check_and_install_tesseract(self) -> bool:
        """Check for Tesseract and prompt installation."""
        import pytesseract
        
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

        if TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

        try:
            pytesseract.get_tesseract_version()
            return True
        except:
            pass
        
        self.log("Tesseract WBT not found.", "WARNING")
        
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        response = messagebox.askyesno(
            "Tesseract Not Found",
            "Tesseract WBT not found. Download and install?"
        )
        root.destroy()
        
        if not response:
            return False
        
        try:
            self.log("Downloading Tesseract...")
            with requests.get(TESSERACT_INSTALLER_URL, stream=True) as r:
                with open("tesseract_installer.exe", 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            self.log("Running installer...")
            subprocess.run(["tesseract_installer.exe"], check=True)
            self.log("Restarting...")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            self.log(f"Installation failed: {str(e)}", "ERROR")
            return False
    
    def run(self):
        """Start application."""
        logger.info("========== WBT STARTED ==========")
        
        # Check Tesseract
        if not self.check_and_install_tesseract():
            time.sleep(2)
            self.graceful_exit(1)
        
        # Initialize UI
        self.region_overlay = RegionOverlay()
        self.log_display = LogDisplay(self.log_queue, self.callbacks)
        time.sleep(0.5)  # Let UI initialize
        
        self.log("========== WBT STARTED ==========")
        self.log(self.get_state_text())
        # self.show_help_window()
        
        state = self.state_manager.get_state()
        if state.region is None:
            self.log("Press TAB to select a region", "WARNING")
        else:
            self.region_overlay.show_region(state.region)
        
        # Register hotkeys
        keyboard.add_hotkey('shift', self.handle_shift_press)
        keyboard.add_hotkey('tab', self.select_region)
        keyboard.add_hotkey('page up', lambda: self.set_search_mode(
            (state.current_mode_index + 1) % len(SEARCH_MODES)))
        keyboard.add_hotkey('page down', lambda: self.set_sort_mode(
            (state.current_sort_mode_index + 1) % len(SORT_MODES)))
        keyboard.add_hotkey('delete', self.clear_typed_history)
        keyboard.add_hotkey('caps lock', lambda: self.log_display.toggle_visibility())
        keyboard.add_hotkey('f1', self.toggle_auto_mode)
        keyboard.add_hotkey('.', self.show_help_window)
        keyboard.add_hotkey('ctrl+z', self.undo_last_word)
        keyboard.add_hotkey('ctrl+c', lambda: self.graceful_exit(0))
        
        self._setup_tray_icon()
        keyboard.wait()
    
    def graceful_exit(self, code: int = 0):
        """Gracefully exit application."""
        self.log("Shutting down...")
        self.state_manager.update_state(auto_mode_active=False)
        self.state_manager.save_state()
        self.state_manager.save_metrics()
        
        # Stop tray icon first
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception as e:
                logger.error(f"Error stopping tray icon: {e}")
        
        # Clean up keyboard hooks
        try:
            keyboard.unhook_all()
        except Exception as e:
            logger.error(f"Error cleaning up keyboard hooks: {e}")
        
        # If we have a tkinter root window, destroy it
        if hasattr(self, 'log_display') and self.log_display and hasattr(self.log_display, 'root'):
            try:
                self.log_display.root.after(100, self.log_display.root.destroy)
                self.log_display.root.update()
                time.sleep(0.2)  # Give it a moment to close
            except Exception as e:
                logger.error(f"Error closing window: {e}")
        
        # Exit the application
        os._exit(code)

if __name__ == "__main__":
    try:
        setup_logging()
        app = OCRApplication()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"FATAL ERROR: {e}")
        sys.exit(1)