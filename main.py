import sys
import os
import time
import random
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
    TESSERACT_INSTALLER_URL, TESSERACT_INSTALLER_PATH,
    TYPING_DELAY_MIN, TYPING_DELAY_MAX,
    OCR_INTERVAL_MIN, OCR_INTERVAL_MAX,
    MAX_TYPED_HISTORY,
    TURN_GATE_NEED_YOUR,
    TURN_GATE_NEED_TURN,
)
from logging_utils import setup_logging, LogQueue
from state import StateManager
from ocr_processor import OCRProcessor
from api_client import DatamuseClient
from suggestion_manager import SuggestionManager
from ui_manager import RegionOverlay, RegionSelector, LogDisplay, HelpWindow, DefinitionPopup
from tray_manager import TrayIcon
from tkinter import messagebox, simpledialog
import tkinter as tk

logger = logging.getLogger(__name__)


def _type_word_human_like(word: str, base_delay: float, inter_key_scale: float = 1.0) -> None:
    """
    Type a word with variable gaps between keys so rhythm is not perfectly metronomic.
    base_delay is the typical seconds between keystrokes (from settings).
    inter_key_scale nudges speed without changing the saved setting (Shift vs auto).
    """
    if not word:
        return
    if base_delay <= 0:
        keyboard.write(word, delay=0)
        return

    base = max(TYPING_DELAY_MIN, base_delay * inter_key_scale)
    # Wider spread reads less robotic than a tight band around base.
    low = max(0.03, base * 0.52)
    high = min(TYPING_DELAY_MAX, base * 2.45)
    mode = min(max(base, low), high)

    for i, ch in enumerate(word):
        keyboard.write(ch)
        if i >= len(word) - 1:
            break
        # Hesitation / micro-pauses (more frequent than before so rhythm varies)
        r = random.random()
        if r < 0.34:
            time.sleep(random.uniform(0.1, 0.34))
        elif r < 0.42:
            time.sleep(random.uniform(0.16, 0.45))
        dt = random.triangular(low, high, mode)
        time.sleep(dt)


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

        self.state_manager.load_state()

        # When True, auto_mode_watcher clears its last-seen letters (fix F1 re-enable with same prompt).
        self._auto_watcher_reset = False

        self._setup_callbacks()

    def _setup_callbacks(self):
        """Setup UI callbacks."""
        self.callbacks = {
            'select_region': self.select_region,
            'clear_turn_region': self.clear_turn_region,
            'set_search_mode': self.set_search_mode,
            'set_sort_mode': self.set_sort_mode,
            'clear_history': self.clear_typed_history,
            'undo_word': self.undo_last_word,
            'show_help': self.show_help_window,
            'toggle_window': lambda: self.log_display.toggle_visibility(),
            'fetch_suggestions': self.handle_shift_press,
            'fetch_definitions': self.handle_alt_1_press,
            'set_typing_delay': self.set_typing_delay,
            'set_ocr_interval': self.set_ocr_interval,
            'exit': self.graceful_exit,
        }

    def _turn_gate_accepts(self, text: str) -> bool:
        """YOUR TURN → yourturn; tolerate partial / noisy OCR."""
        if not text:
            return False
        return (
            (TURN_GATE_NEED_YOUR in text and TURN_GATE_NEED_TURN in text)
            or ("yourturn" in text)
            or (TURN_GATE_NEED_YOUR in text and len(text) >= 4)
        )

    def _auto_mode_turn_ok(self):
        """
        If turn_region is set, auto mode only types when OCR shows YOUR TURN.
        Returns (ok, turn_ocr_text_or_none) so the watcher can log without double OCR.
        """
        state = self.state_manager.get_state()
        tr = state.turn_region
        if not tr:
            return True, None
        text = self.ocr_processor.perform_ocr_turn_gate(dict(tr))
        if not text:
            return False, ""
        return self._turn_gate_accepts(text), text

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
        if state.turn_region:
            tg = 'On (turn region must OCR as YOUR TURN)'
        else:
            tg = "Off (no second region — auto types on any letter change)"
        return f"""
Current Mode: {mode}
Current Sort: {sort_mode}
Typing delay: {state.typing_delay}s (~avg between keys)
OCR interval: {state.ocr_interval}s (auto mode poll)
Auto mode only on your turn: {tg}
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
Fetch Definitions:  Alt+1
Select Regions:     TAB — letters, then YOUR TURN box (Esc to skip second)
Clear turn region:  Ctrl+F2

Change Search Mode: Page Up
Change Sort Mode:   Page Down

Clear History:      Delete
Undo Last Word:     Ctrl+Z
Toggle Log + Region: Caps Lock
Toggle Auto Mode:   F1

Show This Window:   . (period)
Quit Application:   Ctrl+C
"""

    def handle_shift_press(self):
        """WBT and fetch suggestions."""
        state = self.state_manager.get_state()
        resume_auto = False
        if state.auto_mode_active:
            self.state_manager.update_state(auto_mode_active=False)
            resume_auto = True

        if not state.region:
            self.log("Cannot perform WBT: No region selected.", "ERROR")
            self.select_region()
            if resume_auto:
                self.state_manager.update_state(auto_mode_active=True)
            return

        self.executor.submit(self._handle_shift_async_with_auto_resume, resume_auto)

    def _handle_shift_async_with_auto_resume(self, resume_auto: bool):
        try:
            self._handle_shift_async("shift")
        finally:
            if resume_auto:
                self.state_manager.update_state(auto_mode_active=True)

    def _handle_shift_async(self, typing_source: str = "shift"):
        """Fetch letters from region, get suggestions, type first/next word and Enter (Shift or auto)."""
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
            self.type_next_word(typing_source)
            return

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
            for i, suggestion in enumerate(suggestions[:3]):
                self.log(f"\t{i+1}. {suggestion}")
            self.log((f"\n... and {len(suggestions) - 3} more"
                     if len(suggestions) > 3 else ""))
        else:
            self.state_manager.update_state(suggestions=[], suggestion_index=0)

        self.type_next_word(typing_source)

    def handle_alt_1_press(self):
        """WBT and fetch definitions."""
        state = self.state_manager.get_state()
        if not state.region:
            self.log("Cannot perform WBT: No region selected.", "ERROR")
            self.select_region()
            return

        self.executor.submit(self._handle_alt_1_async)

    def _handle_alt_1_async(self):
        """Async WBT handler."""
        state = self.state_manager.get_state()
        region = state.region
        if not region:
            return

        self.log("Processing WBT...")
        word = self.ocr_processor.perform_ocr(region)

        if not word:
            self.log("WBT returned no definitions.", "WARNING")
            return

        definitions = self.api_client.get_definitions(word)
        self.state_manager.update_state(api_status=self.api_client.status)

        if definitions:
            self.state_manager.update_state(definitions=definitions, definition_index=0)
            self.log(f"Found {len(definitions)} definitions.")
        else:
            self.state_manager.update_state(definitions=[], definition_index=0)
            self.log("No definitions found.", "WARNING")

        self.log(f"Showing definition for: '{word}'")

        def_popup = DefinitionPopup.show(self.log_display.root, word, definitions)
        def_popup.wait_window(def_popup)

    def type_next_word(self, typing_source: str = "shift"):
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

        # "Thinking" before hands move (same path for Shift and auto; auto slightly longer).
        if typing_source == "auto":
            time.sleep(random.uniform(0.52, 1.12))
        else:
            time.sleep(random.uniform(0.3, 0.72))

        delay = state.typing_delay
        self.log(f"Typing: '{word}'")
        # Slower inter-key timing than raw setting (auto a bit slower than Shift).
        scale = 1.32 if typing_source == "auto" else 1.22
        _type_word_human_like(word, delay, inter_key_scale=scale)
        time.sleep(random.uniform(0.26, 0.62))
        keyboard.press_and_release('enter')

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
        """Select letter region, then a second fullscreen picker for YOUR TURN (Esc skips)."""
        parent = self.log_display.root if self.log_display and self.log_display.root else None
        try:
            if self.region_overlay:
                self.region_overlay.show_region(None)
            new_region = RegionSelector.select_region()
        except RuntimeError:
            self.log("Region selection cancelled.", "WARNING")
            return

        messagebox.showinfo(
            "Your turn region",
            "Select the box around **YOUR TURN** for auto mode (F1).\n\n"
            "Press Esc in the next screen to skip — then auto mode will not wait for your turn.",
            parent=parent,
        )
        turn_region = None
        try:
            turn_region = RegionSelector.select_region()
        except RuntimeError:
            self.log("Turn region skipped — letters only.", "WARNING")

        self.state_manager.update_state(region=new_region, turn_region=turn_region)
        self.log("Regions saved (letters" + (" + your turn)." if turn_region else ")."))
        if self.region_overlay:
            self.region_overlay.show_region(new_region, turn_region)
        self.state_manager.save_state()

    def clear_turn_region(self):
        """Remove second region; auto mode no longer gates on YOUR TURN."""
        self.state_manager.update_state(turn_region=None)
        self.log("Turn region cleared — auto mode no longer waits for your turn.")
        if self.region_overlay:
            st = self.state_manager.get_state()
            self.region_overlay.show_region(st.region, None)
        self.state_manager.save_state()

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

    def set_typing_delay(self):
        """Prompt for typing delay (seconds per character) and save to ocr_config.json."""
        if not self.log_display or not self.log_display.root:
            return
        parent = self.log_display.root
        state = self.state_manager.get_state()
        val = simpledialog.askfloat(
            "Typing delay",
            f"Typical delay between keystrokes in seconds (timing varies slightly).\n"
            f"Slower, more human-like values are often ~0.25–0.45.\n"
            f"Allowed range: {TYPING_DELAY_MIN} to {TYPING_DELAY_MAX}",
            minvalue=TYPING_DELAY_MIN,
            maxvalue=TYPING_DELAY_MAX,
            initialvalue=round(state.typing_delay, 4),
            parent=parent,
        )
        if val is None:
            return
        self.state_manager.update_state(typing_delay=val)
        self.state_manager.save_state()
        self.log(f"Typing delay set to {val} s per character.")

    def set_ocr_interval(self):
        """Prompt for auto-mode OCR poll interval and save to ocr_config.json."""
        if not self.log_display or not self.log_display.root:
            return
        parent = self.log_display.root
        state = self.state_manager.get_state()
        val = simpledialog.askfloat(
            "OCR interval",
            "Seconds between OCR checks in auto mode (F1).\n"
            f"Allowed range: {OCR_INTERVAL_MIN} to {OCR_INTERVAL_MAX}",
            minvalue=OCR_INTERVAL_MIN,
            maxvalue=OCR_INTERVAL_MAX,
            initialvalue=round(state.ocr_interval, 4),
            parent=parent,
        )
        if val is None:
            return
        self.state_manager.update_state(ocr_interval=val)
        self.state_manager.save_state()
        self.log(f"OCR interval set to {val} s.")

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
            self._auto_watcher_reset = True
            self.ocr_processor.clear_cache()
            self.log("Auto mode ENABLED (fresh OCR scan).")
        else:
            self.log("Auto mode DISABLED.")

    def auto_mode_watcher(self):
        """Watch for region changes in auto mode (background thread)."""
        last_text = None
        last_warn_empty = 0.0
        last_warn_gate = 0.0
        while True:
            state = self.state_manager.get_state()
            poll = state.ocr_interval
            if not state.auto_mode_active:
                time.sleep(poll)
                continue

            if not state.region:
                time.sleep(poll)
                continue

            if self._auto_watcher_reset:
                self._auto_watcher_reset = False
                last_text = None

            try:
                region = dict(state.region)
                letters = self.ocr_processor.perform_ocr(region)
                now = time.monotonic()
                if not letters:
                    if now - last_warn_empty > 8.0:
                        self.log(
                            "Auto mode: letter OCR is empty — check the letter region (TAB).",
                            "WARNING",
                        )
                        last_warn_empty = now
                    time.sleep(poll)
                    continue

                if letters != last_text:
                    gate_ok, turn_ocr = self._auto_mode_turn_ok()
                    if not gate_ok:
                        if state.turn_region and now - last_warn_gate > 8.0:
                            self.log(
                                f"Auto mode: waiting for YOUR TURN (turn OCR: {turn_ocr!r})",
                                "WARNING",
                            )
                            last_warn_gate = now
                        time.sleep(poll)
                        continue
                    self.log(f"Auto-detected: '{letters}'")
                    last_text = letters
                    self._handle_shift_async("auto")
            except Exception as e:
                logger.error(f"Auto mode error: {e}", exc_info=True)
                self.log(f"[AUTO ERROR]: {str(e)}", "ERROR")
                time.sleep(2)
                continue

            time.sleep(poll)

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
                '-2': None,
                'fetch_suggestions': self.callbacks['fetch_suggestions'],
                'fetch_definitions': self.callbacks['fetch_definitions'],
                '-1': None,
                'toggle_window': self.callbacks['toggle_window'],
                '-0': None,
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
        except Exception:
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
                with open(TESSERACT_INSTALLER_PATH, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            self.log("Running installer...")
            subprocess.run([TESSERACT_INSTALLER_PATH], check=True)
            self.log("Restarting...")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            self.log(f"Installation failed: {str(e)}", "ERROR")
            return False

    def run(self):
        """Start application."""
        logger.info("========== WBT STARTED ==========")

        if not self.check_and_install_tesseract():
            time.sleep(2)
            self.graceful_exit(1)

        self.region_overlay = RegionOverlay()
        self.log_display = LogDisplay(
            self.log_queue,
            self.callbacks,
            on_visibility_changed=lambda vis: self.region_overlay.set_bundle_visible(vis)
            if self.region_overlay
            else None,
        )
        time.sleep(0.5)

        self.log("========== WBT STARTED ==========")
        for i, line in enumerate(self.get_state_text().split("\n")):
            self.log(f"{line}")

        state = self.state_manager.get_state()
        if state.region is None:
            self.log("Press TAB to select regions", "WARNING")
        else:
            self.region_overlay.show_region(state.region, state.turn_region)

        keyboard.add_hotkey('shift', self.handle_shift_press)
        keyboard.add_hotkey('alt+1', self.handle_alt_1_press)
        keyboard.add_hotkey('tab', self.select_region)
        keyboard.add_hotkey('page up', lambda: self.set_search_mode(
            (self.state_manager.get_state().current_mode_index + 1) % len(SEARCH_MODES)))
        keyboard.add_hotkey('page down', lambda: self.set_sort_mode(
            (self.state_manager.get_state().current_sort_mode_index + 1) % len(SORT_MODES)))
        keyboard.add_hotkey('delete', self.clear_typed_history)
        keyboard.add_hotkey('caps lock', lambda: self.log_display.toggle_visibility())
        keyboard.add_hotkey('f1', self.toggle_auto_mode)
        keyboard.add_hotkey('ctrl+f2', self.clear_turn_region)
        keyboard.add_hotkey('.', self.show_help_window)
        keyboard.add_hotkey('ctrl+z', self.undo_last_word)
        keyboard.add_hotkey('ctrl+c', lambda: self.graceful_exit(0))

        threading.Thread(target=self.auto_mode_watcher, daemon=True, name="AutoOCR").start()

        self._setup_tray_icon()
        keyboard.wait()

    def graceful_exit(self, code: int = 0):
        """Gracefully exit application."""
        self.log("Shutting down...")
        self.state_manager.update_state(auto_mode_active=False)
        self.state_manager.save_state()
        self.state_manager.save_metrics()

        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception as e:
                logger.error(f"Error stopping tray icon: {e}")

        try:
            keyboard.unhook_all()
        except Exception as e:
            logger.error(f"Error cleaning up keyboard hooks: {e}")

        if hasattr(self, 'log_display') and self.log_display and hasattr(self.log_display, 'root'):
            try:
                self.log_display.root.after(100, self.log_display.root.destroy)
                self.log_display.root.update()
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"Error closing window: {e}")

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
