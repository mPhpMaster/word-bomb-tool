# WBT - Setup & Installation Guide

## Project Structure

```
ocr_helper/
├── config.py              # Configuration & constants
├── logging_utils.py       # Logging setup
├── state.py              # State management & metrics
├── ocr_processor.py      # WBT processing
├── api_client.py         # Datamuse API client
├── suggestion_manager.py # Suggestion logic
├── ui_manager.py         # UI windows & overlays
├── tray_manager.py       # System tray icon
├── main.py               # Application entry point
├── requirements.txt      # Python dependencies
└── README.md             # Documentation
```

## Installation

### 1. Prerequisites

- **Python 3.8+**
- **Tesseract WBT** (auto-installs on first run, or manually install from: https://github.com/tesseract-ocr/tesseract)

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Tesseract Setup (Optional - App will prompt for installation)

#### Windows
- Download installer: https://github.com/tesseract-ocr/tesseract/releases
- Or let the app auto-install on first run
- Recommended: Install for "All Users" and add to PATH

#### macOS
```bash
brew install tesseract
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get install tesseract-ocr
```

### 4. Run Application

```bash
python main.py
```

## Features

### 🎯 Core Features
- **WBT Text Recognition** - Extract text from screen regions
- **Word Suggestions** - Get word suggestions via Datamuse API
- **Auto-Type** - Automatically type suggestions
- **Undo** - Ctrl+Z to undo last typed word
- **Auto Mode** - Continuously monitor region for changes

### 🔍 Advanced Search (5 Modes)
1. **Starts With** - Words beginning with letters
2. **Ends With** - Words ending with letters
3. **Contains** - Words containing letters anywhere
4. **Rhymes** - Rhyming words
5. **Related Words** - Synonyms & conceptually related words

### 📊 Sorting Options
- **Shortest** - By word length (ascending)
- **Longest** - By word length (descending)
- **Random** - Shuffled
- **Frequency** - By word complexity/rarity

### 💾 System Tray Integration
- Minimize to system tray
- Quick-access context menu
- Start/stop from tray without opening main window
- Show/hide window from tray

### 📈 Telemetry & Metrics
- Tracks WBT attempts & success rate
- API request statistics
- Average processing times
- Saves metrics to `ocr_metrics.json`

## Hotkeys

| Key | Action |
|-----|--------|
| **SHIFT** | Fetch suggestions for WBT text |
| **TAB** | Select new WBT region |
| **Page Up** | Change search mode |
| **Page Down** | Change sort mode |
| **Delete** | Clear typed history |
| **Ctrl+Z** | Undo last word |
| **Caps Lock** | Toggle main window |
| **F1** | Toggle auto mode |
| **.** (Period) | Show help window |
| **Ctrl+C** | Exit application |

## Configuration Files

### `ocr_config.json`
Saves application state:
- Last selected region
- Current search/sort modes
- Total words typed

### `ocr_metrics.json`
Performance metrics:
- WBT success rate
- API response times
- Session statistics

### `ocr_helper.log`
Application logs with rotating file handlers (5MB per file, 3 backups)

## Troubleshooting

### Tesseract Not Found
- Run `python main.py` and accept the auto-installation prompt
- Or manually install from: https://github.com/tesseract-ocr/tesseract/releases

### Tray Icon Not Showing
- **Windows**: Install `pywin32`: `pip install pywin32`
- **Linux**: Install `PyGObject`: `pip install PyGObject`
- App will still work without tray icon

### Hotkeys Not Responding
- Ensure app has focus in taskbar
- Some apps (games) may capture hotkeys
- Try running as administrator

### Poor WBT Results
- Select larger region with better lighting
- Ensure text contrast is high
- Use monospace fonts if possible
- Adjust region to avoid shadows/reflections

## Usage Workflow

1. **Start App**: `python main.py`
2. **Select Region**: Press TAB to select WBT area
3. **Set Preferences**: Use Page Up/Down to set search/sort modes
4. **Recognize Text**: Press SHIFT on text in selected region
5. **Type Suggestions**: Press SHIFT repeatedly to cycle through suggestions
6. **Undo if Needed**: Press Ctrl+Z to undo
7. **Auto Mode** (Optional): Press F1 to auto-detect text changes

## Performance Tips

- **Smaller regions** = faster WBT
- **Higher contrast** = better accuracy
- **Auto Mode** = continuous monitoring (uses more CPU)
- **Cache** = results cached for 5 minutes

## Development

### Adding Tests
```python
# test_suggestion_manager.py
from suggestion_manager import SuggestionManager

def test_sort_shortest():
    words = ["elephant", "cat", "dog"]
    result = SuggestionManager.sort_suggestions(words, "Shortest")
    assert result == ["cat", "dog", "elephant"]
```

### Extending Functionality
Each module is designed to be independent:
- `ocr_processor.py` - Replace with different WBT engine
- `api_client.py` - Swap with different suggestion API
- `ui_manager.py` - Migrate to Qt/wxPython
- `tray_manager.py` - Add more tray features

## License

MIT License - Feel free to modify and distribute

## Support

For issues or feature requests, check:
- Application logs in `ocr_helper.log`
- Metrics in `ocr_metrics.json`
- Stack trace in console output