import mss
import hashlib
import os
import logging
import shutil
import time
import threading
import unicodedata
from collections import Counter
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from PIL import Image, ImageOps
from config import CACHE_EXPIRY_MINUTES, OCR_STABLE_ATTEMPTS, OCR_STABLE_GAP
import ocr_preprocess
import windows_ocr
import word_list

def find_tesseract_path():
    """Find Tesseract installation path."""
    path_from_which = shutil.which("tesseract")
    if path_from_which:
        return path_from_which
    
    default_path = r"C:\Program Files\Tesseract-WBT\tesseract.exe"
    if os.path.exists(default_path):
        return default_path
    return None

TESSERACT_PATH = find_tesseract_path()

_pytesseract = None


def _tesseract():
    """pytesseract, imported on first use: it is only needed without Windows OCR,
    and importing it (it pulls in pandas when installed) takes seconds."""
    global _pytesseract
    if _pytesseract is None:
        import pytesseract
        if TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        _pytesseract = pytesseract
    return _pytesseract

logger = logging.getLogger(__name__)


def keep_letters(s: str) -> str:
    """Lowercase a-z only. Accents are stripped first ("ä" -> "a"), and anything
    that isn't a Latin letter is dropped."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s).lower() if "a" <= c <= "z"
    )


def keep_alnum(s: str) -> str:
    return "".join(c for c in s if c.isalnum()).lower()


def is_latin_prompt(letters: str) -> bool:
    """True when the letters are a Latin a-z prompt."""
    return bool(letters) and all("a" <= c <= "z" for c in letters)


def is_arabic_prompt(letters: str) -> bool:
    """True when the letters are an Arabic prompt."""
    return bool(letters) and all(word_list.is_arabic_letter(c) for c in letters)


def majority_token(text: str, anchor: str) -> str:
    """The most frequent letters-only token in the OCR text, ignoring the anchor
    word (the line holds several copies of the prompt). Ties go to the first seen."""
    skip = anchor.lower()
    tokens = [t for t in (keep_letters(x) for x in text.split()) if t and t != skip]
    if not tokens:
        return ""
    return Counter(tokens).most_common(1)[0][0]


# Two layouts (anchor, text height, gap) that each read the synthetic prompts in
# the tests; the second only runs when the first finds nothing.
_ENGLISH_LAYOUTS = (("WORD", 24, 1.2), ("THE", 32, 0.6))


def letters_from_windows_ocr(clean: Image.Image) -> Optional[str]:
    """English letters of a cleaned prompt (see ocr_preprocess.clean_prompt).
    Returns None when the engine is unavailable."""
    if not windows_ocr.available():
        return None
    for anchor, height, gap in _ENGLISH_LAYOUTS:
        line = ocr_preprocess.layout_for_windows_ocr(clean, anchor, height, 3, gap)
        text = windows_ocr.recognize(line)
        if text is None:
            return None
        letters = majority_token(text, anchor)
        if letters:
            return letters
    return ""


def arabic_reading(clean: Image.Image, anchor: str = "") -> Tuple[str, int, bool]:
    """Reads the prompt (three copies in a row, after the Latin anchor word if one
    is given) with the Windows Arabic engine. Returns the most common Arabic
    reading, how many copies gave it, and whether any copy came back with Latin
    letters instead."""
    if not windows_ocr.arabic_available():
        return "", 0, False
    line = ocr_preprocess.layout_for_windows_ocr(clean, anchor, 32, 3, 0.8)
    text = windows_ocr.recognize(line, "ar")
    if not text:
        return "", 0, False
    raw = [t for t in text.split() if not anchor or t.lower() != anchor.lower()]
    any_latin = any(("a" <= c <= "z") or ("A" <= c <= "Z") for t in raw for c in t)
    tokens = [t for t in ("".join(c for c in x if word_list.is_arabic_letter(c)) for x in raw) if t]
    if not tokens:
        return "", 0, any_latin
    best, votes = Counter(tokens).most_common(1)[0]
    return best, votes, any_latin


def read_prompt(image: Image.Image) -> str:
    """
    Reads the prompt and decides between English and Arabic. The English engine
    turns Arabic glyphs into plausible Latin letters ("يز" -> "cz"), and the Arabic
    engine sometimes turns Latin ones into Arabic ("QU" -> "لا"), so: an Arabic
    reading that all three copies agree on, with no Latin text, is Arabic;
    otherwise an English reading of 2+ letters that some word contains wins;
    otherwise a two-copy Arabic majority; otherwise nothing.
    Returns lowercase a-z for English, Arabic letters for Arabic, or "".
    """
    clean = ocr_preprocess.clean_prompt(image)
    if clean is None:
        return ""
    ar, votes, any_latin = arabic_reading(clean)
    if votes >= 3 and not any_latin:
        # Some fonts' "QU" reads as "لاه" three times out of three. Read the same
        # copies again after a Latin word: the Arabic engine then reads Latin
        # prompts as Latin, while real Arabic prompts stay Arabic.
        _, _, latin_after_anchor = arabic_reading(clean, "WORD")
        if not latin_after_anchor:
            return ar

    en = letters_from_windows_ocr(clean) or ""
    if len(en) >= 2 and word_list.search(en, "Contains"):
        return en

    return ar if votes >= 2 else ""


class OCRProcessor:
    """Handles WBT operations with caching."""
    
    def __init__(self):
        self.cache: Dict[str, tuple] = {}
        # One OCR at a time: a second caller (Shift, Alt+1, auto watcher, turn gate)
        # blocks here until the running OCR finishes.
        self._lock = threading.RLock()
    
    def get_image_hash(self, img_data: bytes) -> str:
        """Generate hash of image data for caching."""
        return hashlib.md5(img_data).hexdigest()
    
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for WBT."""
        image = image.convert("L")
        image = ImageOps.autocontrast(image)
        image = image.point(lambda x: 0 if x < 140 else 255)
        return image

    def preprocess_image_turn_gate(self, image: Image.Image) -> Image.Image:
        """
        Softer pipeline for YOUR TURN style UI (colored buttons, white text).
        The letter-OCR binarization often turns these regions into solid black/white.
        """
        return ocr_preprocess.preprocess_turn_gate(image)
    
    def clear_cache(self):
        """Clear WBT cache."""
        with self._lock:
            self.cache.clear()
        logger.info("WBT cache cleared")
    
    def perform_ocr(self, region: Dict) -> Optional[str]:
        """Letter OCR; waits for any OCR already in progress."""
        with self._lock:
            return self._perform_ocr(region)

    def perform_ocr_stable(self, region: Dict, attempts: int = OCR_STABLE_ATTEMPTS,
                           gap: float = OCR_STABLE_GAP) -> Optional[str]:
        """
        Letter OCR that only trusts a reading seen on two captures in a row.

        A single capture can land on a transition frame (letters animating in,
        the previous prompt fading out) and misread letters that are not really
        on screen. Returns None when no two consecutive readings agree.
        """
        prev = self.perform_ocr(region)
        for _ in range(max(1, attempts - 1)):
            time.sleep(gap)
            cur = self.perform_ocr(region)
            if cur and cur == prev:
                return cur
            prev = cur
        logger.debug("Letter OCR did not settle on a stable reading")
        return None

    def _perform_ocr(self, region: Dict) -> Optional[str]:
        """
        Perform WBT on region with caching and error handling.
        
        Args:
            region: Dictionary with 'left', 'top', 'width', 'height' keys
        
        Returns:
            Extracted text (lowercase letters only) or None if failed
        """
        start_time = time.time()
        
        try:
            # Capture region
            with mss.mss() as sct:
                img = sct.grab(region)
            
            img_hash = self.get_image_hash(img.rgb)
            
            # Check cache
            if img_hash in self.cache:
                cached_text, cached_time = self.cache[img_hash]
                age = datetime.now() - cached_time
                if age < timedelta(minutes=CACHE_EXPIRY_MINUTES):
                    duration = (time.time() - start_time) * 1000
                    return cached_text
                else:
                    del self.cache[img_hash]
            
            image = Image.frombytes("RGB", img.size, img.rgb)

            # Windows' built-in engine: in-process and a few ms. Tesseract (a new
            # process per run, ~0.5s each) is only used when Windows has no OCR
            # language at all.
            if windows_ocr.available():
                letters = read_prompt(image)
                if letters:
                    self.cache[img_hash] = (letters, datetime.now())
                duration = (time.time() - start_time) * 1000
                logger.info(f"WBT completed in {duration:.2f}ms ({letters!r}, Windows OCR)")
                return letters or None

            # Preprocess image
            image = self.preprocess_image(image)
            
            # Perform WBT
            raw_text = _tesseract().image_to_string(
                image,
                config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            )
            
            # Extract letters only
            letters = keep_letters(raw_text)
            
            # Cache result
            if letters:
                self.cache[img_hash] = (letters, datetime.now())
            
            duration = (time.time() - start_time) * 1000
            logger.debug(f"WBT completed in {duration:.2f}ms")
            
            return letters if letters else None
        
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"WBT Error: {e}", exc_info=True)
            return None

    def perform_ocr_turn_gate(self, region: Dict) -> Optional[str]:
        """Turn-gate OCR; waits for any OCR already in progress."""
        with self._lock:
            return self._perform_ocr_turn_gate(region)

    def _perform_ocr_turn_gate(self, region: Dict) -> Optional[str]:
        """
        OCR for auto-mode turn detection: letters and digits only, lowercase.
        Uses soft preprocessing + multiple PSM attempts (colored YOUR TURN UI).
        """
        start_time = time.time()

        def run_ocr(im: Image.Image, psm: int) -> str:
            try:
                raw = _tesseract().image_to_string(im, config=f"--psm {psm}")
            except Exception:
                return ""
            return "".join(c for c in raw if c.isalnum()).lower()

        try:
            with mss.mss() as sct:
                img = sct.grab(region)
            rgb = Image.frombytes("RGB", img.size, img.rgb)

            # 1) Soft path (best for purple/blue buttons + white text)
            soft = self.preprocess_image_turn_gate(rgb)

            # "YOUR TURN" is ordinary words, which the in-process Windows engine reads
            # directly. Tesseract's up-to-7 launches only run without that engine.
            if windows_ocr.available():
                best = keep_alnum(windows_ocr.recognize(soft) or "")
                duration = (time.time() - start_time) * 1000
                logger.debug(f"Turn gate WBT (Windows OCR) in {duration:.2f}ms: {best!r}")
                return best or None

            best = ""
            for psm in (6, 7, 8, 13):
                t = run_ocr(soft, psm)
                if len(t) > len(best):
                    best = t
            if best:
                duration = (time.time() - start_time) * 1000
                logger.debug(f"Turn gate WBT (soft) in {duration:.2f}ms: {best!r}")
                return best

            # 2) Harsh binarization (same as letter OCR) as fallback
            hard = self.preprocess_image(rgb)
            for psm in (7, 6, 8):
                t = run_ocr(hard, psm)
                if len(t) > len(best):
                    best = t
            duration = (time.time() - start_time) * 1000
            logger.debug(f"Turn gate WBT (hard fallback) in {duration:.2f}ms: {best!r}")
            return best if best else None
        except Exception as e:
            logger.error(f"Turn gate WBT error: {e}", exc_info=True)
            return None
