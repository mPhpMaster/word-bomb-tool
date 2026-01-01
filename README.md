# Word Bomb Tool - Setup Instructions

## Prerequisites

- Python 3.6 or higher
- [Tesseract Ocr for windows x64 5.5](https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe)

## Installation

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the script:

```bash
python main.py
```

1. Enter the letters you see in the Word Bomb game when prompted

2. The tool will suggest all valid words that can be made from those letters, ranked by length

3. Type `quit` to exit the program

## How It Works

- **Manual Input**: Simply enter the letters from the Word Bomb game board
- **Word Matching**: Compares entered letters against a dictionary of valid English words
- **Ranking**: Sorts words by length (longer words are prioritized in Word Bomb)
- **Suggestions**: Displays all valid words grouped by length

## Example

```
Enter letters: abcdef
Analyzing letters: abcdef
Unique letters: abcdef
Found 15 valid words

============================================================
WORD SUGGESTIONS
============================================================

6 letters (1 words):
  fecund

5 letters (3 words):
  acned, bated, caged
```

## Tips

- Enter all visible letters from the game board
- Longer words generally score more points in Word Bomb
- The tool downloads a full English dictionary on first run (saves locally for faster subsequent runs)

## Troubleshooting

- **No words found**: Make sure you entered the correct letters
- **Dictionary not loading**: Check your internet connection for the first run
- **Exit program**: Type 'quit' or press Ctrl+C

## Disclaimer

This is for educational purposes. Use responsibly and check Discord's terms of service.
