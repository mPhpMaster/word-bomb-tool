# ocr_processor.py - WBT processing and image handling

import pytesseract
import mss
import hashlib
import os
import logging
import shutil
import time
from typing import Optional, Dict
from datetime import datetime, timedelta
from PIL import Image, ImageOps
from config import CACHE_EXPIRY_MINUTES
 
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

if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

logger = logging.getLogger(__name__)

class OCRProcessor:
    """Handles WBT operations with caching."""
    
    def __init__(self):
        self.cache: Dict[str, tuple] = {}
    
    def get_image_hash(self, img_data: bytes) -> str:
        """Generate hash of image data for caching."""
        return hashlib.md5(img_data).hexdigest()
    
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for WBT."""
        image = image.convert("L")
        image = ImageOps.autocontrast(image)
        image = image.point(lambda x: 0 if x < 140 else 255)
        return image
    
    def clear_cache(self):
        """Clear WBT cache."""
        self.cache.clear()
        logger.info("WBT cache cleared")
    
    def perform_ocr(self, region: Dict) -> Optional[str]:
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
            
            # Preprocess image
            image = Image.frombytes("RGB", img.size, img.rgb)
            image = self.preprocess_image(image)
            
            # Perform WBT
            raw_text = pytesseract.image_to_string(
                image,
                config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            )
            
            # Extract letters only
            letters = "".join(c for c in raw_text if c.isalpha()).lower()
            
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