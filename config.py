# Application configuration and constants

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

# File paths
CONFIG_FILE = "ocr_config.json"
LOG_FILE = "ocr_helper.log"
METRICS_FILE = "ocr_metrics.json"

# WBT Settings
OCR_INTERVAL = 1
OCR_TIMEOUT = 5
TYPING_DELAY = 0.08

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
