"""Polices embarquées (Liberation, licence SIL OFL) et choix de la police la plus proche."""
from __future__ import annotations

import os
from functools import lru_cache

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

_FILES = {
    ("sans", False, False): "LiberationSans-Regular.ttf",
    ("sans", True, False): "LiberationSans-Bold.ttf",
    ("sans", False, True): "LiberationSans-Italic.ttf",
    ("sans", True, True): "LiberationSans-BoldItalic.ttf",
    ("serif", False, False): "LiberationSerif-Regular.ttf",
    ("serif", True, False): "LiberationSerif-Bold.ttf",
    ("serif", False, True): "LiberationSerif-Italic.ttf",
    ("serif", True, True): "LiberationSerif-BoldItalic.ttf",
    ("mono", False, False): "LiberationMono-Regular.ttf",
    ("mono", True, False): "LiberationMono-Bold.ttf",
    ("mono", False, True): "LiberationMono-Italic.ttf",
    ("mono", True, True): "LiberationMono-BoldItalic.ttf",
}

FAMILY_CSS = {
    "sans": "'Liberation Sans', Arial, Helvetica, sans-serif",
    "serif": "'Liberation Serif', 'Times New Roman', Times, serif",
    "mono": "'Liberation Mono', 'Courier New', monospace",
}

_SERIF_HINTS = ("times", "serif", "georgia", "garamond", "cambria", "roman", "minion",
                "book", "palatino", "baskerville", "caslon", "didot", "bodoni", "tiro")
_MONO_HINTS = ("courier", "mono", "consol", "cour", "typewriter", "menlo", "lucida console")
_BOLD_HINTS = ("bold", "black", "heavy", "semibold", "demi", "extrabold", "-bd", ",bold")
_ITALIC_HINTS = ("italic", "oblique", "-it", ",italic")


def font_path(family: str = "sans", bold: bool = False, italic: bool = False) -> str:
    return os.path.join(FONT_DIR, _FILES[(family, bool(bold), bool(italic))])


def guess_family(font_name: str, flags: int = 0) -> str:
    name = (font_name or "").lower()
    if flags & 8 or any(h in name for h in _MONO_HINTS):
        return "mono"
    if "sans" in name:
        return "sans"
    if flags & 4 or any(h in name for h in _SERIF_HINTS):
        return "serif"
    return "sans"


def guess_bold(font_name: str, flags: int = 0) -> bool:
    name = (font_name or "").lower()
    return bool(flags & 16) or any(h in name for h in _BOLD_HINTS)


def guess_italic(font_name: str, flags: int = 0) -> bool:
    name = (font_name or "").lower()
    return bool(flags & 2) or any(h in name for h in _ITALIC_HINTS)


@lru_cache(maxsize=64)
def pil_font(family: str, bold: bool, italic: bool, size: float):
    from PIL import ImageFont

    return ImageFont.truetype(font_path(family, bold, italic), max(1.0, round(size * 4) / 4))
