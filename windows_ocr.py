# windows_ocr.py - in-process OCR through the engine built into Windows 10/11
#
# Windows.Media.Ocr through the pywinrt packages. Launching tesseract.exe costs
# ~0.4-0.6s per call and the letter pipeline ran it several times per read; the
# Windows engine stays loaded in this process and reads a short prompt in a few
# milliseconds.

import logging
import threading
from typing import Dict, Optional

from PIL import Image

logger = logging.getLogger(__name__)

try:
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
    from winrt.windows.storage.streams import DataWriter
    WINRT_AVAILABLE = True
    _IMPORT_ERROR = None
except Exception as e:  # not Windows 10+, or the winrt packages are missing
    WINRT_AVAILABLE = False
    _IMPORT_ERROR = e

_init_lock = threading.Lock()
_engines: Dict[str, Optional["OcrEngine"]] = {}


def _engine(lang: str):
    """
    The engine for a language prefix ("en", "ar"), or None when that OCR language
    isn't installed. English falls back to the user-profile languages.
    """
    with _init_lock:
        if lang in _engines:
            return _engines[lang]
        engine = None
        if not WINRT_AVAILABLE:
            logger.info(f"Windows OCR ({lang}): unavailable ({_IMPORT_ERROR})")
        else:
            try:
                for language in OcrEngine.available_recognizer_languages:
                    if language.language_tag.lower().startswith(lang):
                        engine = OcrEngine.try_create_from_language(language)
                        if engine is not None:
                            break
                if engine is None and lang == "en":
                    engine = OcrEngine.try_create_from_user_profile_languages()
                logger.info(
                    f"Windows OCR ({lang}): "
                    + (f"using {engine.recognizer_language.language_tag}" if engine
                       else "no OCR language installed")
                )
            except Exception as e:
                logger.error(f"Windows OCR ({lang}) unavailable: {e}")
                engine = None
        _engines[lang] = engine
        return engine


def available() -> bool:
    return _engine("en") is not None


def arabic_available() -> bool:
    return _engine("ar") is not None


def recognize(img: Image.Image, lang: str = "en") -> Optional[str]:
    """
    Recognises the text in an image with the engine for lang. Returns None when the
    engine is unavailable or recognition failed.
    """
    engine = _engine(lang)
    if engine is None or img is None or img.width <= 0 or img.height <= 0:
        return None
    # The engine rejects images larger than MaxImageDimension on either side.
    limit = OcrEngine.max_image_dimension
    if img.width > limit or img.height > limit:
        return None
    try:
        gray = img if img.mode == "L" else img.convert("L")
        writer = DataWriter()
        writer.write_bytes(gray.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.GRAY8, gray.width, gray.height
        )
        result = engine.recognize_async(bitmap).get()
        return result.text or ""
    except Exception as e:
        logger.error(f"Windows OCR error: {e}")
        return None
