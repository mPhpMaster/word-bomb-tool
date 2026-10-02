# ocr_preprocess.py - image cleanup for the Windows OCR engine
#
# grayscale -> autocontrast -> Otsu binarize -> auto-invert -> drop noise ->
# crop to ink -> resize, then lay the prompt out as a line of text the engine
# reads reliably. Same steps as OcrPreprocess.cs in the C# version.

import logging
from functools import lru_cache
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

try:
    _BICUBIC = Image.Resampling.BICUBIC
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    _BICUBIC = Image.BICUBIC
    _LANCZOS = Image.LANCZOS


def to_gray(image: Image.Image) -> Image.Image:
    """8-bit grayscale (ITU-R 601-2 luma)."""
    return image.convert("L")


def auto_contrast(img: Image.Image, cutoff: int) -> Image.Image:
    """
    Stretches the gray histogram so the darkest kept pixel maps to 0 and the
    brightest to 255. cutoff is the percentage of pixels trimmed from each end of
    the histogram before computing the range.
    """
    hist = img.histogram()
    total = img.width * img.height
    if total == 0:
        return img
    if cutoff > 0:
        trim = total * cutoff // 100
        n = 0
        for lo in range(256):
            n += hist[lo]
            if n > trim:
                break
        n = 0
        for hi in range(255, -1, -1):
            n += hist[hi]
            if n > trim:
                break
    else:
        lo = next((i for i in range(256) if hist[i]), 256)
        hi = next((i for i in range(255, -1, -1) if hist[i]), -1)
    if hi <= lo:
        return img
    scale = 255.0 / (hi - lo)
    lut = [int(min(255.0, max(0.0, (i - lo) * scale)) + 0.5) for i in range(256)]
    return img.point(lut)


def otsu_level(img: Image.Image) -> int:
    """Optimal global threshold via Otsu's method."""
    hist = img.histogram()
    total = img.width * img.height
    if total == 0:
        return 128
    total_sum = sum(i * hist[i] for i in range(256))
    sum_b = 0.0
    w_b = 0
    max_var = -1.0
    first = last = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (total_sum - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) * (m_b - m_f)
        if between > max_var:
            max_var = between
            first = last = t
        elif between == max_var:
            last = t
    # The midpoint of the optimal plateau places the cut cleanly between the two
    # pixel clusters (matters for flat, bimodal histograms).
    return (first + last) // 2


def threshold(img: Image.Image, t: int) -> Image.Image:
    """Pixels below t become 0, others 255."""
    return img.point([0 if i < t else 255 for i in range(256)])


def majority_dark(img: Image.Image) -> bool:
    """True when most pixels are dark (a dark background)."""
    hist = img.histogram()
    return sum(hist[:128]) * 2 > img.width * img.height


def pad(img: Image.Image, border: int, fill: int = 255) -> Image.Image:
    """Adds a uniform margin around the image."""
    return ImageOps.expand(img, border=border, fill=fill)


def upscale_if_small(img: Image.Image, min_w: int = 140, min_h: int = 48) -> Image.Image:
    """Enlarges tiny crops while keeping the aspect ratio, capped at 4x."""
    w, h = img.size
    if w <= 0 or h <= 0:
        return img
    scale = min(4.0, max(max(1.0, min_w / w), max(1.0, min_h / h)))
    if scale <= 1.01:
        return img
    return img.resize((int(w * scale), int(h * scale)), _LANCZOS)


def resize_to_height(img: Image.Image, height: int) -> Image.Image:
    w = max(1, int(round(img.width * height / img.height)))
    return img.resize((w, height), _BICUBIC)


def ink_bounds(img: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box (left, top, right, bottom) of the dark pixels, or None."""
    return img.point([255 if i < 128 else 0 for i in range(256)]).getbbox()


def keep_main_text(img: Image.Image) -> Image.Image:
    """
    Keeps only the prompt's own glyphs in a black-on-white image: drops thin lines
    spanning the region (box edges), then every blob less than half as tall as the
    tallest one unless it sits over or under a big glyph (dots of i/j and Arabic
    letters). That removes small corner text such as a "1K" counter and specks
    from animated backgrounds.
    """
    w, h = img.size
    dark = img.point([1 if i < 128 else 0 for i in range(256)]).tobytes()
    label = [0] * (w * h)
    boxes: List[Tuple[int, int, int, int]] = []
    counts: List[int] = []
    for start, v in enumerate(dark):
        if not v or label[start]:
            continue
        ident = len(boxes) + 1
        x0, y0, x1, y1, n = w, h, -1, -1, 0
        label[start] = ident
        stack = [start]
        while stack:
            p = stack.pop()
            n += 1
            py, px = divmod(p, w)
            if px < x0:
                x0 = px
            if px > x1:
                x1 = px
            if py < y0:
                y0 = py
            if py > y1:
                y1 = py
            for ny in (py - 1, py, py + 1):
                if ny < 0 or ny >= h:
                    continue
                row = ny * w
                for nx in (px - 1, px, px + 1):
                    if nx < 0 or nx >= w:
                        continue
                    q = row + nx
                    if dark[q] and not label[q]:
                        label[q] = ident
                        stack.append(q)
        boxes.append((x0, y0, x1, y1))
        counts.append(n)
    if not boxes:
        return img

    def is_line(i: int) -> bool:
        bx0, by0, bx1, by1 = boxes[i]
        bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
        return (
            (bh >= h * 0.9 and bw <= max(3, bh * 0.12))
            or (bw >= w * 0.9 and bh <= max(3, bw * 0.12))
            # A frame around the whole region: huge box, very little ink.
            or (bw >= w * 0.9 and bh >= h * 0.9 and counts[i] < bw * bh * 0.25)
        )

    lines = [is_line(i) for i in range(len(boxes))]
    max_h = max((b[3] - b[1] + 1 for i, b in enumerate(boxes) if not lines[i]), default=0)
    if max_h == 0:
        return img

    keep = [False] * (len(boxes) + 1)
    big = []
    for i, b in enumerate(boxes):
        if not lines[i] and b[3] - b[1] + 1 >= max_h * 0.5:
            big.append(b)
            keep[i + 1] = True

    reach = int(max_h * 0.7)
    for i, b in enumerate(boxes):
        if keep[i + 1] or lines[i]:
            continue
        for g in big:
            if b[2] >= g[0] and b[0] <= g[2] and b[3] >= g[1] - reach and b[1] <= g[3] + reach:
                keep[i + 1] = True
                break

    out = bytes(0 if keep[lb] and lb else 255 for lb in label)
    return Image.frombytes("L", (w, h), out)


def clean_prompt(src: Image.Image) -> Optional[Image.Image]:
    """
    Black-on-white prompt glyphs cropped to their ink: grayscale -> autocontrast ->
    Otsu binarize -> auto-invert (light text on dark UI) -> keep_main_text -> crop.
    Returns None when nothing is left.
    """
    g = auto_contrast(to_gray(src), 2)
    g = threshold(g, otsu_level(g))
    if majority_dark(g):
        g = ImageOps.invert(g)
    g = keep_main_text(g)
    box = ink_bounds(g)
    if box is None:
        return None
    return g.crop(box)


@lru_cache(maxsize=8)
def render_anchor(word: str, text_height: int) -> Image.Image:
    """Renders a known word (Arial bold), cropped to its ink and scaled to text_height."""
    img = Image.new("L", (text_height * (len(word) + 2) * 2, text_height * 3), 255)
    draw = ImageDraw.Draw(img)
    size = int(round(text_height * 1.4))
    try:
        font = ImageFont.truetype("arialbd.ttf", size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except OSError:
            font = ImageFont.load_default()
    draw.text((text_height / 2, text_height / 4), word, fill=0, font=font)
    box = ink_bounds(img)
    if box is None:
        return Image.new("L", (0, text_height), 255)
    return resize_to_height(img.crop(box), text_height)


def layout_for_windows_ocr(clean: Image.Image, anchor: str, text_height: int = 24,
                           copies: int = 3, gap: float = 1.2) -> Image.Image:
    """
    The Windows engine skips short, word-less clusters such as "AB" or "TR" when
    they stand alone, so the prompt is laid out as a normal line of text: a known
    anchor word followed by copies of the prompt, all black on white at
    text_height pixels with a wide margin. The caller drops the anchor and takes
    the majority reading of the copies.
    """
    g = resize_to_height(clean, text_height)
    a = render_anchor(anchor, text_height) if anchor else None
    gp = int(round(text_height * gap))
    lead = a.width + gp if a is not None and a.width > 0 else 0
    line = Image.new("L", (lead + copies * g.width + (copies - 1) * gp, text_height), 255)
    if lead:
        line.paste(a, (0, 0))
    for k in range(copies):
        line.paste(g, (lead + k * (g.width + gp), 0))
    return pad(line, text_height, 255)


def preprocess_for_windows_ocr(src: Image.Image, anchor: str, text_height: int = 24,
                               copies: int = 3, gap: float = 1.2) -> Optional[Image.Image]:
    """clean_prompt + layout_for_windows_ocr; None when the region has no text."""
    try:
        clean = clean_prompt(src)
        if clean is None:
            return None
        return layout_for_windows_ocr(clean, anchor, text_height, copies, gap)
    except Exception as e:
        logger.error(f"Preprocess error: {e}", exc_info=True)
        return None


def preprocess_turn_gate(src: Image.Image) -> Image.Image:
    """Softer pipeline for colored "YOUR TURN" UI: grayscale, autocontrast (cutoff 1), upscale."""
    g = to_gray(src)
    try:
        g = ImageOps.autocontrast(g, cutoff=1)
    except TypeError:
        g = ImageOps.autocontrast(g)
    return upscale_if_small(g)
