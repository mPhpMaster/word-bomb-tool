import os
import sys


def _app_base_dir() -> str:
    """Directory for config, logs, and bundled-app data (next to .exe when frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _app_base_dir()

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
    "definition_font_size": 14,
    "font_size": 10,
    "font_size_small": 9,
    "focused_alpha": 1.0,
    "unfocused_alpha": 0.85,
}

# File paths (alongside the executable when built with PyInstaller)
CONFIG_FILE = os.path.join(BASE_DIR, "ocr_config.json")
LOG_FILE = os.path.join(BASE_DIR, "ocr_helper.log")
METRICS_FILE = os.path.join(BASE_DIR, "ocr_metrics.json")
TESSERACT_INSTALLER_PATH = os.path.join(BASE_DIR, "tesseract_installer.exe")

# WBT Settings
OCR_INTERVAL = 0.5
OCR_INTERVAL_MIN = 0.1
OCR_INTERVAL_MAX = 10.0
OCR_TIMEOUT = 1
TYPING_DELAY = 0.1
TYPING_DELAY_MIN = 0.01
TYPING_DELAY_MAX = 2.0


def clamp_ocr_interval(value) -> float:
    """Seconds between auto-mode OCR polls; invalid values fall back to OCR_INTERVAL."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return OCR_INTERVAL
    if v != v:
        return OCR_INTERVAL
    return max(OCR_INTERVAL_MIN, min(OCR_INTERVAL_MAX, v))


def clamp_typing_delay(value) -> float:
    """Seconds between keystrokes for keyboard.write; invalid values fall back to TYPING_DELAY."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return TYPING_DELAY
    if v != v:  # NaN
        return TYPING_DELAY
    return max(TYPING_DELAY_MIN, min(TYPING_DELAY_MAX, v))


# API Settings
DATAMUSE_API = "https://api.datamuse.com/words"

# Cache Settings
CACHE_EXPIRY_MINUTES = 5
MAX_SUGGESTIONS_DISPLAY = 50
MAX_TYPED_HISTORY = 1000
UNDO_BUFFER_SIZE = 20

# Threading
MAX_WORKER_THREADS = 2

# Search and Sort Modes
SEARCH_MODES = ["Starts With", "Ends With", "Contains", "Rhymes", "Related Words"]
SORT_MODES = ["Shortest", "Longest", "Random", "Frequency"]

# Tesseract
TESSERACT_INSTALLER_URL = "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe"

# Logging
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'
MAX_LOG_QUEUE_SIZE = 500

# Status indicators (ASCII-safe for Windows console)
STATUS_ONLINE = "[OK] Online"
STATUS_OFFLINE = "[XX] Offline"
STATUS_TIMEOUT = "[--] Timeout"
STATUS_ERROR = "[!!] Error"
