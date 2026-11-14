"""Reconnaissance de texte (OCR) avec Tesseract."""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading

from PIL import Image

# Tesseract lance plusieurs fils de calcul par défaut : avec plusieurs pages en parallèle,
# cela le ralentit énormément. Un fil par page est bien plus rapide.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

_lock = threading.Lock()
_status: dict | None = None

TESSERACT_HELP = (
    "La lecture du texte des images et des scans utilise le logiciel gratuit « Tesseract », "
    "qui n'est pas installé sur cet ordinateur. Le document s'affiche quand même, mais son texte "
    "ne peut pas être lu ni modifié. Pour l'installer, suivez la section « Installer Tesseract » "
    "du fichier README, puis relancez DocEdit."
)


def _candidates() -> list[str]:
    found = shutil.which("tesseract")
    paths = [found] if found else []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
            paths.append(os.path.join(base, "Tesseract-OCR", "tesseract.exe"))
    else:
        paths += ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract",
                  "/opt/local/bin/tesseract"]
    return [p for p in paths if p and os.path.isfile(p)]


def status(refresh: bool = False) -> dict:
    """{'available': bool, 'langs': [...], 'lang': 'fra+eng', 'message': str|None}"""
    global _status
    with _lock:
        if _status is not None and not refresh:
            return _status
        st = {"available": False, "langs": [], "lang": None, "message": TESSERACT_HELP, "version": None}
        try:
            import pytesseract
        except ImportError:
            _status = st
            return st
        for path in _candidates():
            pytesseract.pytesseract.tesseract_cmd = path
            try:
                st["version"] = str(pytesseract.get_tesseract_version())
                langs = pytesseract.get_languages(config="")
            except Exception:
                continue
            st["available"] = True
            st["langs"] = langs
            wanted = [lang for lang in ("fra", "eng") if lang in langs]
            if not wanted:
                wanted = [lang for lang in langs if lang not in ("osd", "equ")][:1]
            st["lang"] = "+".join(wanted) if wanted else None
            st["message"] = None
            if "fra" not in langs:
                st["message"] = (
                    "Tesseract est installé mais sans le français : les accents risquent d'être mal lus. "
                    "Voir la section « Installer Tesseract » du README pour ajouter la langue française.")
            if not st["lang"]:
                st["available"] = False
                st["message"] = TESSERACT_HELP
            break
        _status = st
        return st


def detect_rotation(img: Image.Image) -> int:
    """Angle (0/90/180/270) à appliquer pour remettre le texte à l'endroit, si Tesseract est sûr de lui."""
    st = status()
    if not st["available"] or "osd" not in st["langs"]:
        return 0
    import pytesseract

    try:
        small = img.copy()
        small.thumbnail((1800, 1800))
        osd = pytesseract.image_to_osd(small, config="--psm 0 -c min_characters_to_try=20")
    except Exception:
        return 0
    rot = re.search(r"Rotate:\s+(\d+)", osd)
    conf = re.search(r"Orientation confidence:\s+([\d.]+)", osd)
    if rot and conf and float(conf.group(1)) >= 3.0:
        return int(rot.group(1)) % 360
    return 0


def ocr_lines(img: Image.Image) -> list[dict]:
    """Lit le texte d'une image et renvoie des lignes {bbox:[x0,y0,x1,y1], text, conf} en pixels."""
    st = status()
    if not st["available"]:
        return []
    import pytesseract

    scale = 1.0
    work = img.convert("RGB")
    if work.width < 1400:
        scale = min(3.0, 1400 / max(1, work.width))
        work = work.resize((round(work.width * scale), round(work.height * scale)), Image.LANCZOS)
    try:
        data = pytesseract.image_to_data(work, lang=st["lang"], config="--psm 3",
                                         output_type=pytesseract.Output.DICT)
    except Exception:
        try:
            data = pytesseract.image_to_data(work, lang=st["lang"], config="--psm 6",
                                             output_type=pytesseract.Output.DICT)
        except Exception:
            return []

    groups: dict[tuple, list[dict]] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = (data[k][i] / scale for k in ("left", "top", "width", "height"))
        groups.setdefault(key, []).append({"text": word, "conf": conf, "bbox": [x, y, x + w, y + h]})

    lines = []
    for words in groups.values():
        words.sort(key=lambda w: w["bbox"][0])
        line_h = max(w["bbox"][3] - w["bbox"][1] for w in words)
        segment: list[dict] = []
        for w in words:
            if segment and w["bbox"][0] - segment[-1]["bbox"][2] > max(line_h * 1.6, 12):
                lines.append(_merge(segment))
                segment = []
            segment.append(w)
        if segment:
            lines.append(_merge(segment))
    lines = [ln for ln in lines if ln["conf"] >= 25 or len(ln["text"]) >= 4]
    lines = [ln for ln in lines if re.search(r"[\w€$£%]", ln["text"])]
    lines.sort(key=lambda ln: (round(ln["bbox"][1] / 8), ln["bbox"][0]))
    return lines


def _merge(words: list[dict]) -> dict:
    x0 = min(w["bbox"][0] for w in words)
    y0 = min(w["bbox"][1] for w in words)
    x1 = max(w["bbox"][2] for w in words)
    y1 = max(w["bbox"][3] for w in words)
    conf = sum(w["conf"] for w in words) / len(words)
    return {"bbox": [x0, y0, x1, y1], "text": " ".join(w["text"] for w in words), "conf": conf}


_FR = {"le", "la", "les", "des", "du", "de", "et", "un", "une", "est", "pour", "dans", "sur", "avec",
       "au", "aux", "par", "qui", "que", "pas", "ce", "cette", "vous", "nous", "date", "montant"}
_EN = {"the", "and", "of", "to", "in", "is", "for", "on", "with", "by", "this", "that", "you", "we",
       "are", "from", "amount", "total", "date"}


def guess_language(texts: list[str]) -> str | None:
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ]+", " ".join(texts).lower())
    if len(words) < 3:
        return None
    fr = sum(w in _FR for w in words) + 2 * sum(any(c in w for c in "éèêàçùœ") for w in words)
    en = sum(w in _EN for w in words)
    if fr == en == 0:
        return None
    return "français" if fr >= en else "anglais"
