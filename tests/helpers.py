# Shared test setup: puts the project root on sys.path and draws synthetic prompts.

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

# Bold variants of common Windows fonts (file names under C:\Windows\Fonts).
FONTS = {
    "Arial": "arialbd.ttf",
    "Segoe UI": "segoeuib.ttf",
    "Verdana": "verdanab.ttf",
    "Tahoma": "tahomabd.ttf",
    "Trebuchet MS": "trebucbd.ttf",
}


def prompt(text, font_name, fg, bg, size):
    """Draws a prompt the way the game shows it: a short letter cluster in a bold
    font on a flat background, cropped like a user-picked region."""
    img = Image.new("RGB", (size * len(text) + 40, size * 2), bg)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONTS[font_name], size)
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    draw.text(((img.width - (x1 - x0)) / 2 - x0, (img.height - (y1 - y0)) / 2 - y0),
              text, fill=fg, font=font)
    return img
