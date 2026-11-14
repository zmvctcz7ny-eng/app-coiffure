"""Fonctions partagées par les types de documents qui passent par l'OCR (images, scans, PDF scannés)."""
from __future__ import annotations

import io
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pymupdf
from PIL import Image

from .. import imaging, ocr

_render_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
_CACHE_MAX = 24


def cache_get(key):
    if key in _render_cache:
        _render_cache.move_to_end(key)
        return _render_cache[key]
    return None


def cache_put(key, value):
    _render_cache[key] = value
    _render_cache.move_to_end(key)
    while len(_render_cache) > _CACHE_MAX:
        _render_cache.popitem(last=False)


def prepare_ocr_pages(doc, images: list[Image.Image], page_offset: int = 0, auto_rotate: bool = True,
                      names: list[str] | None = None) -> list[dict]:
    """Enregistre les images de travail, lance l'OCR (en parallèle) et ajoute les lignes comme éléments."""
    st = ocr.status()
    if not st["available"]:
        if st["message"] and st["message"] not in doc.meta["warnings"]:
            doc.meta["warnings"].append(st["message"])
    elif st["message"] and st["message"] not in doc.meta["warnings"]:
        doc.meta["warnings"].append(st["message"])

    def work(args):
        idx, img = args
        if auto_rotate and st["available"]:
            rot = ocr.detect_rotation(img)
            if rot:
                img = img.rotate(-rot, expand=True)
        lines = ocr.ocr_lines(img) if st["available"] else []
        return idx, img, lines

    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as pool:
        results = list(pool.map(work, list(enumerate(images))))

    infos = []
    texts = []
    for idx, img, lines in results:
        pno = page_offset + idx
        name = (names[idx] if names else f"page_{pno}.png")
        img.save(doc.path(name), "PNG", optimize=False, compress_level=3)
        infos.append({"index": pno, "w": img.width, "h": img.height, "mode": "image", "image": name})
        for n, ln in enumerate(lines):
            iid = f"p{pno}-{n}"
            doc.items[iid] = {"id": iid, "page": pno, "bbox": [round(v, 2) for v in ln["bbox"]],
                              "orig": ln["text"], "src": "ocr"}
            doc.meta["order"].append(iid)
            texts.append(ln["text"])
    if texts:
        doc.meta["lang"] = doc.meta.get("lang") or ocr.guess_language(texts)
    return infos


def load_page_array(doc, page: dict) -> np.ndarray:
    key = ("src", doc.id, page["index"])
    hit = cache_get(key)
    if hit is not None:
        return hit
    arr = imaging.to_np(Image.open(doc.path(page["image"])))
    cache_put(key, arr)
    return arr


def edited_page(doc, page: dict, state: dict):
    """Image de la page avec les modifications, + nouvelles bbox + zones modifiées (avec cache)."""
    pno = page["index"]
    ver = doc.page_version(pno, state)
    key = ("img", doc.id, pno, ver)
    hit = cache_get(key)
    if hit is not None:
        return hit
    src = load_page_array(doc, page)
    items = doc.page_items(pno)
    out, boxes, rects = imaging.apply_edits(src, items, doc.page_state(pno, state))
    if any(it["id"] in state for it in items):
        doc.save()  # mémorise les styles estimés
    res = (out, boxes, rects)
    cache_put(key, res)
    return res


def item_bold(doc, item: dict) -> bool:
    page = doc.pages[item["page"]]
    src = load_page_array(doc, page)
    had = "style" in item
    st = imaging.item_style(src, doc.page_items(item["page"]), item)
    if not had:
        doc.save()
    return bool(st["bold"])


def image_page_png(doc, page: dict, state: dict) -> tuple[bytes, str]:
    out, _, _ = edited_page(doc, page, state)
    return imaging.encode_jpeg(out, 85, max_side=2200), "image/jpeg"


def add_image_page_to_pdf(out_pdf: pymupdf.Document, img: np.ndarray, items: list[dict], state: dict,
                          searchable: bool, width_pt: float | None = None, height_pt: float | None = None):
    h, w = img.shape[:2]
    if width_pt is None:
        k = 842.0 / max(w, h) if max(w, h) > 0 else 1
        width_pt, height_pt = w * k, h * k
    page = out_pdf.new_page(width=width_pt, height=height_pt)
    page.insert_image(page.rect, stream=imaging.encode_jpeg(img, 90))
    if searchable:
        add_hidden_text(page, items, state, width_pt / w)
    return page


def add_hidden_text(page: pymupdf.Page, items: list[dict], state: dict, k: float, offset=(0.0, 0.0),
                    boxes: dict | None = None):
    """Ajoute une couche de texte invisible (sélectionnable / recherchable) au-dessus d'une image."""
    font = pymupdf.Font("helv")
    for it in items:
        text = " ".join(state.get(it["id"], it["orig"]).split())
        if not text:
            continue
        x0, y0, x1, y1 = (boxes or {}).get(it["id"], it["bbox"])
        x0, x1 = x0 * k + offset[0], x1 * k + offset[0]
        y0, y1 = y0 * k + offset[1], y1 * k + offset[1]
        hgt = max(1.0, y1 - y0)
        size = hgt * 0.95
        tl = font.text_length(text, fontsize=size)
        if tl <= 0:
            continue
        sx = (x1 - x0) / tl
        point = pymupdf.Point(x0, y1 - hgt * 0.2)
        try:
            page.insert_text(point, text, fontsize=size, fontname="helv", render_mode=3,
                             morph=(point, pymupdf.Matrix(sx, 1)))
        except Exception:
            pass


def pil_from_bytes(data: bytes) -> Image.Image:
    return imaging.open_image(data)


def jpeg_or_png_bytes(arr: np.ndarray, fmt: str) -> bytes:
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    if fmt == "png":
        img.save(buf, "PNG", optimize=True)
    elif fmt == "heic":
        img.save(buf, "HEIF", quality=92)
    else:
        img.save(buf, "JPEG", quality=93)
    return buf.getvalue()
