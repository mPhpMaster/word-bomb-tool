# Third-party notices

Word Bomb Tool is licensed under the MIT License (see `LICENSE`). It includes or
uses the following third-party components.

## Bundled data

- **ENABLE word list** (`data/enable1.txt.gz`) — the English word list.
  Public domain.
- **Arabic word list** (`data/arabic-words.txt.gz`) — adapted from the Arabic
  list of [FrequencyWords](https://github.com/hermitdave/FrequencyWords) by
  Hermit Dave (built from OpenSubtitles 2018) and filtered with the
  [Ayaspell](http://ayaspell.sourceforge.net/) Hunspell dictionary. Licensed
  under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); this
  licence covers that file only. Details in `data/ARABIC-WORDS-NOTICE.md`
  (installed next to the program as `ARABIC-WORDS-NOTICE.md`).

## Python runtime and libraries

The Windows executables are built with PyInstaller and contain the Python
runtime and these packages:

| Component | Licence |
| --- | --- |
| [Python](https://www.python.org/) runtime and standard library | PSF License 2.0 |
| [Tcl/Tk](https://www.tcl.tk/) (through tkinter) | Tcl/Tk License (BSD-style) |
| [pywinrt](https://github.com/pywinrt/pywinrt) (`winrt-runtime`, `winrt-Windows.*` — Windows OCR from Python) | MIT License |
| [keyboard](https://github.com/boppreh/keyboard) | MIT License |
| [mss](https://github.com/BoboTiG/python-mss) | MIT License |
| [Pillow](https://python-pillow.org/) | MIT-CMU (HPND) License |
| [requests](https://requests.readthedocs.io/) | Apache License 2.0 |
| [urllib3](https://github.com/urllib3/urllib3) (requests dependency) | MIT License |
| [idna](https://github.com/kjd/idna) (requests dependency) | BSD 3-Clause License |
| [charset-normalizer](https://github.com/jawah/charset_normalizer) (requests dependency) | MIT License |
| [certifi](https://github.com/certifi/python-certifi) (requests dependency) | Mozilla Public License 2.0 |
| [pytesseract](https://github.com/madmaze/pytesseract) | Apache License 2.0 |
| [PyInstaller](https://pyinstaller.org/) bootloader (build tool) | GPL 2.0 with the PyInstaller bootloader exception |

Optional, only used when installed: [pystray](https://github.com/moses-palmer/pystray)
(tray icon, LGPL 3.0) and [pywin32](https://github.com/mhammond/pywin32) (PSF 2.0).

## Services and optional tools

- **[Datamuse API](https://www.datamuse.com/api/)** — used for Rhymes / Related
  Words suggestions and definitions. Subject to Datamuse's terms of use.
- **Windows OCR** (`Windows.Media.Ocr`) — part of Windows; used through the
  Windows API.
- **[Tesseract OCR](https://github.com/tesseract-ocr/tesseract)** — Apache
  License 2.0. Not bundled; only used when Windows has no OCR language
  installed.
