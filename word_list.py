# word_list.py - offline word search
#
# English from the ENABLE word list (public domain, ~173k words) and Arabic from a
# frequency-ordered list (see data/ARABIC-WORDS-NOTICE.md). Looking words up here
# takes a few milliseconds, where a Datamuse request took 0.5-2.5s per prompt.

import gzip
import logging
import os
import threading
from functools import lru_cache
from typing import List

from config import DATA_DIR

logger = logging.getLogger(__name__)

ENGLISH_FILE = os.path.join(DATA_DIR, "enable1.txt.gz")
ARABIC_FILE = os.path.join(DATA_DIR, "arabic-words.txt.gz")

# Modes answered from the local lists. Rhymes and Related Words need Datamuse.
LOCAL_MODES = ("Starts With", "Ends With", "Contains")

_lock = threading.Lock()
_lists = {}


def _load(path: str) -> List[str]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _words(arabic: bool) -> List[str]:
    key = "ar" if arabic else "en"
    words = _lists.get(key)
    if words is None:
        with _lock:
            words = _lists.get(key)
            if words is None:
                words = _load(ARABIC_FILE if arabic else ENGLISH_FILE)
                _lists[key] = words
                logger.info(f"Word list ({key}): {len(words)} words loaded")
    return words


def count() -> int:
    """Number of English words loaded (forces the load)."""
    return len(_words(False))


def arabic_count() -> int:
    """Number of Arabic words loaded (forces the load)."""
    return len(_words(True))


def preload() -> None:
    """Loads both lists in the background so the first prompt doesn't pay for it."""
    def run():
        try:
            _words(False)
            _words(True)
        except Exception as e:
            logger.error(f"Word list load failed: {e}", exc_info=True)

    threading.Thread(target=run, daemon=True, name="WordListLoad").start()


def is_arabic_letter(c: str) -> bool:
    return "ء" <= c <= "ي"


def is_arabic(s: str) -> bool:
    """True when the text contains Arabic letters."""
    return any(is_arabic_letter(c) for c in s)


def supports(mode: str) -> bool:
    """True for the search modes answered from the local list."""
    return mode in LOCAL_MODES


def search(letters: str, mode: str) -> List[str]:
    """
    All words matching the letters for the mode, never including the letters
    themselves. Arabic letters search the Arabic list (most common words first);
    anything else searches the English list (shortest first, then alphabetical).
    Returns an empty list for unsupported modes.
    """
    return list(_search(letters, mode))


@lru_cache(maxsize=256)
def _search(letters: str, mode: str) -> tuple:
    arabic = is_arabic(letters)
    p = letters.strip() if arabic else letters.strip().lower()
    if not p or not supports(mode):
        return ()

    n = len(p)
    words = _words(arabic)
    # The prompt itself is never a suggestion, so only longer words count.
    if mode == "Starts With":
        result = [w for w in words if len(w) > n and w.startswith(p)]
    elif mode == "Ends With":
        result = [w for w in words if len(w) > n and w.endswith(p)]
    else:
        result = [w for w in words if p in w and len(w) > n]
    # The Arabic list is already ordered by how common each word is. The English
    # list is alphabetical, so a stable sort by length keeps ties alphabetical.
    if not arabic:
        result.sort(key=len)
    return tuple(result)


def fix_il_confusion(letters: str, mode: str) -> str:
    """
    OCR often confuses a capital I with a lowercase l. Game prompts are common
    letter clusters, so when an I/L swap of the letters matches at least ten
    times as many words as the letters as read, the swap is returned; otherwise
    the letters are returned unchanged.
    """
    p = letters.lower()
    if not supports(mode) or is_arabic(p):
        return p

    positions = [i for i, c in enumerate(p) if c in "il"]
    if not positions or len(positions) > 4:
        return p

    original = len(_search(p, mode))
    best, best_count = p, original
    for mask in range(1, 1 << len(positions)):
        chars = list(p)
        for b, pos in enumerate(positions):
            if mask & (1 << b):
                chars[pos] = "l" if chars[pos] == "i" else "i"
        variant = "".join(chars)
        n = len(_search(variant, mode))
        if n > best_count:
            best, best_count = variant, n
    return best if best_count >= max(1, original) * 10 else p
