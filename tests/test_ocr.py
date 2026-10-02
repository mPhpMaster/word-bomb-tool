import os
import unittest

from tests import helpers
from tests.helpers import SAMPLES, prompt
from PIL import Image, ImageDraw, ImageFont

import ocr_preprocess
import windows_ocr
from config import turn_gate_accepts
from ocr_processor import (
    is_arabic_prompt, is_latin_prompt, keep_letters, majority_token, read_prompt,
)

YZ = "يز"  # "يز", the prompt in samples/arabic-prompt-yz.png

TEXTS = ["HEA", "ING", "TR", "AB", "QU", "OMP", "ZY", "XE", "RIC", "WO", "ST", "ECT",
         "NN", "GH", "PH", "UNK", "CZ"]
STYLES = [
    ((255, 255, 255), (40, 44, 52)),
    ((0, 0, 0), (255, 255, 255)),
    ((255, 255, 255), (120, 70, 200)),
    ((180, 230, 60), (28, 28, 28)),
]
ARABIC_TEXTS = ["ست", "قل", "عين",
                "ما", "لا", "من"]  # ست قل عين ما لا من


class LetterTests(unittest.TestCase):
    def test_keep_letters(self):
        self.assertEqual("ab", keep_letters("ÄB"))  # "ÄB"
        self.assertEqual("cafe", keep_letters("Café"))
        self.assertEqual("hea", keep_letters("H-e.a 1"))
        self.assertEqual("", keep_letters(YZ))

    def test_majority_token_drops_anchor_and_votes(self):
        self.assertEqual("ab", majority_token("WORD AB AB A8", "WORD"))
        self.assertEqual("tr", majority_token("word TR TR", "WORD"))
        self.assertEqual("", majority_token("WORD", "WORD"))
        # Accents are stripped and non-Latin letters dropped.
        self.assertEqual("ab", majority_token("WORD ÄB ÄB", "WORD"))

    def test_prompt_kinds(self):
        self.assertTrue(is_latin_prompt("hea"))
        self.assertFalse(is_latin_prompt(YZ))
        self.assertFalse(is_latin_prompt(""))
        self.assertTrue(is_arabic_prompt(YZ))
        self.assertFalse(is_arabic_prompt("ab"))
        self.assertFalse(is_arabic_prompt(YZ + "1"))

    def test_turn_gate_accepts(self):
        self.assertTrue(turn_gate_accepts("yourturn"))
        self.assertTrue(turn_gate_accepts("itsyourturnnow"))
        self.assertFalse(turn_gate_accepts(""))
        self.assertFalse(turn_gate_accepts("turn"))


class KeepMainTextTests(unittest.TestCase):
    def test_drops_frame_and_small_corner_text(self):
        img = Image.new("L", (160, 64), 255)
        d = ImageDraw.Draw(img)
        d.rectangle([1, 1, 158, 62], outline=0, width=2)
        d.text((30, 8), "HEA", fill=0, font=ImageFont.truetype("arialbd.ttf", 40))
        d.text((135, 50), "1K", fill=0, font=ImageFont.truetype("arialbd.ttf", 9))
        left, top, right, bottom = ocr_preprocess.ink_bounds(ocr_preprocess.keep_main_text(img))
        # Only the big letters are left: no frame edge, nothing in the corner.
        self.assertGreater(left, 20)
        self.assertGreater(top, 5)
        self.assertLess(right, 130)
        self.assertLess(bottom, 55)

    def test_keeps_dots_over_letters(self):
        img = Image.new("L", (120, 80), 255)
        ImageDraw.Draw(img).text((20, 5), "ij", fill=0, font=ImageFont.truetype("arialbd.ttf", 56))
        self.assertEqual(ocr_preprocess.ink_bounds(img),
                         ocr_preprocess.ink_bounds(ocr_preprocess.keep_main_text(img)))


@unittest.skipUnless(windows_ocr.available(), "No Windows OCR language installed")
class WindowsOcrTests(unittest.TestCase):
    def test_reads_short_prompts_in_common_fonts_and_never_as_arabic(self):
        ok = n = 0
        misses, arabic = [], []
        for font in helpers.FONTS:
            for text in TEXTS:
                for fg, bg in STYLES:
                    for size in (18, 32, 56):
                        got = read_prompt(prompt(text, font, fg, bg, size))
                        n += 1
                        if got == text.lower():
                            ok += 1
                        else:
                            misses.append(f"{font}/{size}:{text}->{got!r}")
                        if got and not is_latin_prompt(got):
                            arabic.append(f"{font}/{size}:{text}->{got!r}")
        print(f"\nSynthetic English prompts: {ok}/{n} read correctly ({ok / n:.1%}); "
              f"misses: {misses[:20]}")
        self.assertGreaterEqual(ok, n * 0.97, f"{ok}/{n} read correctly; misses: {misses[:20]}")
        self.assertEqual([], arabic, "Latin prompts read as Arabic")

    def test_ignores_region_frame_and_small_corner_text(self):
        for text in ("HEA", "TR", "ING", "ST"):
            img = prompt(text, "Arial", (180, 230, 60), (28, 28, 28), 32)
            d = ImageDraw.Draw(img)
            d.rectangle([1, 1, img.width - 2, img.height - 2], outline=(97, 175, 239), width=2)
            d.text((img.width - 18, img.height - 14), "1K", fill=(150, 200, 60),
                   font=ImageFont.truetype("arialbd.ttf", 9))
            self.assertEqual(text.lower(), read_prompt(img))

    @unittest.skipUnless(windows_ocr.arabic_available(), "No Windows Arabic OCR language installed")
    def test_real_arabic_prompt_is_detected_and_not_read_as_latin(self):
        # Captured from the game (with the old on-region overlay border and the "1K"
        # counter in the corner). The English engine used to read it as "cz".
        img = Image.open(os.path.join(SAMPLES, "arabic-prompt-yz.png")).convert("RGB")
        self.assertEqual(YZ, read_prompt(img))

    @unittest.skipUnless(windows_ocr.arabic_available(), "No Windows Arabic OCR language installed")
    def test_arabic_prompts_are_recognised_as_arabic(self):
        # Whatever the engine reads, an Arabic prompt must never come back as Latin.
        # (Without libraqm Pillow draws Arabic letters unjoined and left to right, so
        # the exact letters are not checked here; the real capture test does that.)
        latin, arabic, n = [], 0, 0
        for font in ("Arial", "Segoe UI"):
            for text in ARABIC_TEXTS:
                for size in (32, 56):
                    got = read_prompt(prompt(text, font, (180, 230, 60), (28, 28, 28), size))
                    n += 1
                    if is_latin_prompt(got):
                        latin.append(f"{font}/{size}:{text}->{got!r}")
                    elif got:
                        arabic += 1
        print(f"\nSynthetic Arabic prompts: {arabic}/{n} recognised as Arabic")
        self.assertEqual([], latin, "Arabic prompts read as Latin")
        self.assertGreaterEqual(arabic, n * 0.8)

    def test_reads_real_your_turn_box(self):
        # Captured from the game: green "YOUR TURN" on a dark purple box.
        img = Image.open(os.path.join(SAMPLES, "your-turn.png")).convert("RGB")
        text = windows_ocr.recognize(ocr_preprocess.preprocess_turn_gate(img)) or ""
        alnum = "".join(c for c in text if c.isalnum()).lower()
        self.assertTrue(turn_gate_accepts(alnum), f"read {text!r}")


if __name__ == "__main__":
    unittest.main()
