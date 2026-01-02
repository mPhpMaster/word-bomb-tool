# Word Bomb Tool - Setup Instructions

## Prerequisites

- Python 3.6 or higher
- [Tesseract Ocr for windows x64 5.5](https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/mPhpMaster/word-bomb-tool.git
```

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the script:

```bash
python main.py
```

or

```powershell
run.bat
```

or just double click on [run.vbs](run.vbs).

1. Go to `Options` -> `Select region` and select the block that shows the characters.

2. Press `SHIFT` to fetch a suggestion or `F1` to toggle auto mode.

3. Press `Ctrl+C` to exit the program.

## How It Works

- **OCR/Manual Input**: Simply enter/reads the letters from the Word Bomb game board/selected region.
- **Call Api**: Fetch word suggestions from [Datamuse API](https://api.datamuse.com/words).
- **Typing**: Automatically types the suggested word into the game.
- **Wait**: Waits for `the game to ask for a word` or `the user to press shift/f1` before repeating the process.

## Options

- **Select Region**: Press `TAB` to select a region.
- **Auto Mode**: Press `F1` to toggle auto mode.
- **Exit Program**: Press `Ctrl+C` to exit the program.
- **Show/Hide window**: Press `Caps Lock` to toggle the log window.
- **Show/Hide help**: Press `.` to toggle the help window.
- **Change Search Mode**: Press `Page Up` to change the search mode.
- **Change Sort Mode**: Press `Page Down` to change the sort mode.
- **Clear History**: Press `Delete` to clear the history.
- **Undo Last Word**: Press `Ctrl+Z` to undo the last word.
- **Fetch Suggestions**: Press `SHIFT` to fetch suggestions.

## Troubleshooting

- **No words found**: Make sure you entered the correct letters.

## Disclaimer

This is for educational purposes. Use responsibly and check Discord's terms of service.

Licensed under the MIT License. See [LICENSE](LICENSE) for details.
