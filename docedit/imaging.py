"""Modification du texte dans les images (scans, photos, pages PDF scannées)."""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from . import layout
from .errors import UserError
from .fonts import pil_font

try:  # HEIC / HEIF (photos d'iPhone)
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover
    HEIF_OK = False

MAX_SIDE = 4000


def open_image(data: bytes | str) -> Image.Image:
    """Ouvre une image (JPG, PNG, HEIC…), applique l'orientation EXIF, convertit en RGB."""
    try:
        img = Image.open(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
        img.load()
    except Exception:
        raise UserError("Cette image n'a pas pu être ouverte. Le fichier est peut-être abîmé "
                        "ou dans un format non pris en charge (formats acceptés : JPG, PNG, HEIC).")
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return img


def to_np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB")).copy()


def encode_jpeg(arr: np.ndarray | Image.Image, quality: int = 88, max_side: int | None = None) -> bytes:
    img = Image.fromarray(arr) if isinstance(arr, np.ndarray) else arr
    if max_side and max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _luma(arr: np.ndarray) -> np.ndarray:
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def _clip(img: np.ndarray, x0, y0, x1, y1):
    h, w = img.shape[:2]
    return max(0, int(x0)), max(0, int(y0)), min(w, int(np.ceil(x1))), min(h, int(np.ceil(y1)))


def _stroke(mask: np.ndarray) -> float | None:
    """Épaisseur moyenne des traits d'un masque de texte (2 × aire / périmètre)."""
    m8 = mask.astype(np.uint8)
    perim = int((m8 - cv2.erode(m8, np.ones((3, 3), np.uint8))).sum())
    area = int(m8.sum())
    return 2.0 * area / perim if perim and area else None


def _rendered_stroke(text: str, family: str, bold: bool, size: float) -> float | None:
    font = pil_font(family, bold, False, size)
    l, t, r, b = font.getbbox(text, anchor="ls")
    w, h = int(r - l) + 6, int(b - t) + 6
    if w <= 6 or h <= 6:
        return None
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).text((3 - l, 3 - t), text, font=font, fill=255, anchor="ls")
    a = np.asarray(im)
    thr, _ = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return _stroke(a > max(thr, 35))


def analyze(img: np.ndarray, item: dict, items: list[dict]) -> dict:
    """Estime couleur du fond, couleur du texte, graisse, police et taille d'une ligne de texte."""
    x0, y0, x1, y1 = item["bbox"]
    h = max(2.0, y1 - y0)
    pad = max(2, int(round(h * 0.12)))
    ring = max(2, int(round(h * 0.18)))
    ex0, ey0, ex1, ey1 = _clip(img, x0 - pad - ring, y0 - pad - ring, x1 + pad + ring, y1 + pad + ring)
    region = img[ey0:ey1, ex0:ex1].astype(np.float32)
    mask_ring = np.ones(region.shape[:2], bool)
    ix0, iy0, ix1, iy1 = _clip(img, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    mask_ring[iy0 - ey0:iy1 - ey0, ix0 - ex0:ix1 - ex0] = False
    ring_px = region[mask_ring]
    if len(ring_px) < 10:
        ring_px = region.reshape(-1, 3)
    bg = np.median(ring_px, axis=0)
    ring_std = float(np.std(_luma(ring_px)))

    bx0, by0, bx1, by1 = _clip(img, x0, y0, x1, y1)
    inner = img[by0:by1, bx0:bx1].astype(np.float32)
    fg = np.array([20, 20, 20], np.float32) if bg.mean() > 128 else np.array([235, 235, 235], np.float32)
    measured = None
    if inner.size:
        dist = np.linalg.norm(inner - bg, axis=2)
        d8 = np.clip(dist, 0, 255).astype(np.uint8)
        thr, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thr = max(thr, 35)
        mask = d8 > thr
        if mask.sum() > 5:
            strong = dist >= np.percentile(dist[mask], 60)
            sel = mask & strong
            fg = np.median(inner[sel if sel.sum() > 3 else mask], axis=0)
            measured = _stroke(mask)

    text = item["orig"]
    best = None
    for family in ("sans", "serif", "mono"):
        f100 = pil_font(family, False, False, 100)
        l, t, r, b = f100.getbbox(text, anchor="ls")
        if r - l <= 0 or b - t <= 0:
            continue
        size = 100 * h / (b - t)
        width = (r - l) * size / 100
        err = abs(width - (x1 - x0)) / max(1.0, x1 - x0)
        if family == "mono":
            err += 0.08  # on préfère sans/serif en cas d'hésitation
        if best is None or err < best[0]:
            best = (err, family, size)
    family, size = ("sans", h) if best is None else (best[1], best[2])

    # graisse : épaisseur des traits comparée au même texte rendu en normal (t=0) et en gras (t=1)
    weight = None
    if measured:
        ref_regular = _rendered_stroke(text, family, False, size)
        ref_bold = _rendered_stroke(text, family, True, size)
        if ref_regular and ref_bold and ref_bold > ref_regular:
            weight = float(np.log(measured / ref_regular) / np.log(ref_bold / ref_regular))
    # indice complémentaire : le gras est plus large que le normal à hauteur égale
    width_says_bold = False
    fb = pil_font(family, True, False, 100)
    fr = pil_font(family, False, False, 100)
    lb, tb, rb, bb = fb.getbbox(text, anchor="ls")
    lr, tr_, rr, br = fr.getbbox(text, anchor="ls")
    if bb - tb > 0 and br - tr_ > 0:
        wb = (rb - lb) * h / (bb - tb)
        wr = (rr - lr) * h / (br - tr_)
        width_says_bold = abs(wb - (x1 - x0)) < abs(wr - (x1 - x0))
    return {
        "bg": [int(v) for v in bg], "fg": [int(v) for v in fg], "uniform": ring_std < 22,
        "family": family, "size_regular": float(size), "weight": weight, "pad": pad, "h": float(h),
        "wide": bool(width_says_bold),
    }


def finalize_style(item: dict, m: dict, page_weight: float | None) -> dict:
    """Décide normal/gras en comparant la ligne aux autres lignes de la page, puis calcule taille et ligne de base."""
    w = m.get("weight")
    if item.get("bold_override") is not None:
        bold = bool(item["bold_override"])
    elif w is None:
        bold = False
    elif page_weight is None:
        bold = w > 0.75
    else:
        z = w - page_weight
        bold = (z > 0.55 and w > 0.6) or (z > 0.25 and m.get("wide", False))
    family, size, h = m["family"], m["size_regular"], m["h"]
    text = item["orig"]
    x0, y0, x1, y1 = item["bbox"]
    if bold:
        f100 = pil_font(family, True, False, 100)
        l, t, r, b = f100.getbbox(text, anchor="ls")
        if b - t > 0:
            size = 100 * h / (b - t)
    font = pil_font(family, bold, False, size)
    l, t, r, b = font.getbbox(text, anchor="ls")
    baseline = ((y0 - t) + (y1 - b)) / 2

    st = dict(m)
    st.update({"bold": bool(bold), "size": float(size), "baseline": float(baseline)})
    return st


def _erase(out: np.ndarray, src: np.ndarray, item: dict, st: dict):
    x0, y0, x1, y1 = item["bbox"]
    pad = st["pad"]
    rx0, ry0, rx1, ry1 = _clip(out, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    if rx1 <= rx0 or ry1 <= ry0:
        return (rx0, ry0, rx1, ry1)
    if st["uniform"]:
        out[ry0:ry1, rx0:rx1] = np.array(st["bg"], np.uint8)
    else:
        m = 3 * pad + 4
        cx0, cy0, cx1, cy1 = _clip(out, rx0 - m, ry0 - m, rx1 + m, ry1 + m)
        crop = out[cy0:cy1, cx0:cx1].copy()
        reg = src[ry0:ry1, rx0:rx1].astype(np.float32)
        dist = np.linalg.norm(reg - np.array(st["bg"], np.float32), axis=2)
        mask_local = (dist > 30).astype(np.uint8) * 255
        mask_local = cv2.dilate(mask_local, np.ones((5, 5), np.uint8), iterations=2)
        mask = np.zeros(crop.shape[:2], np.uint8)
        mask[ry0 - cy0:ry1 - cy0, rx0 - cx0:rx1 - cx0] = mask_local
        if mask.any():
            fixed = cv2.inpaint(crop, mask, max(3, pad), cv2.INPAINT_TELEA)
            out[cy0:cy1, cx0:cx1] = fixed
    return (rx0, ry0, rx1, ry1)


def _stale(it: dict) -> bool:
    st = it.get("style")
    return not st or (it.get("bold_override") is not None and st.get("bold") != bool(it["bold_override"]))


def item_style(src: np.ndarray, page_items: list[dict], item: dict) -> dict:
    """Style estimé d'une ligne (mis en cache dans l'élément)."""
    if _stale(item):
        # on mesure toutes les lignes pour connaître la graisse « normale » de la page
        weights = []
        for it in page_items:
            if "measure" not in it:
                it["measure"] = analyze(src, it, page_items)
            if it["measure"].get("weight") is not None and len(it["orig"]) >= 4:
                weights.append(it["measure"]["weight"])
        page_weight = float(np.median(weights)) if len(weights) >= 3 else None
        item["style"] = finalize_style(item, item["measure"], page_weight)
    return item["style"]


def apply_edits(src: np.ndarray, page_items: list[dict], state: dict) -> tuple[np.ndarray, dict, list]:
    """Applique les modifications d'une page. Renvoie (image, nouvelles bbox, zones modifiées)."""
    edited = [it for it in page_items if it["id"] in state]
    if not edited:
        return src, {}, []
    out = src.copy()
    h_img, w_img = src.shape[:2]
    styles = {it["id"]: item_style(src, page_items, it) for it in edited}
    dirty = {}
    for it in edited:
        dirty[it["id"]] = list(_erase(out, src, it, styles[it["id"]]))

    pil = Image.fromarray(out)
    draw = ImageDraw.Draw(pil)
    new_boxes = {}
    margin = max(8.0, w_img * 0.02)
    for it in edited:
        st = styles[it["id"]]
        text = " ".join(state[it["id"]].split())
        if not text:
            new_boxes[it["id"]] = it["bbox"]
            continue

        def width_at(size, _t=text, _st=st):
            f = pil_font(_st["family"], _st["bold"], False, size)
            l, _, r, _ = f.getbbox(_t, anchor="ls")
            return r - l

        size, left, _ = layout.place(it, page_items, w_img, margin, st["size"], width_at)
        font = pil_font(st["family"], st["bold"], False, size)
        l, t, r, b = font.getbbox(text, anchor="ls")
        # on garde la ligne de base ; si la taille a été réduite, on reste centré verticalement
        baseline = st["baseline"]
        if size < st["size"]:
            x0, y0, x1, y1 = it["bbox"]
            baseline = baseline - (st["size"] - size) * 0.15
        draw.text((left - l, baseline), text, font=font, fill=tuple(st["fg"]), anchor="ls")
        box = [left, baseline + t, left + (r - l), baseline + b]
        new_boxes[it["id"]] = [box[0], min(box[1], it["bbox"][1]), box[2], max(box[3], it["bbox"][3])]
        d = dirty[it["id"]]
        dirty[it["id"]] = [min(d[0], box[0] - 2), min(d[1], box[1] - 2), max(d[2], box[2] + 2), max(d[3], box[3] + 2)]
    rects = [list(_clip(src, *r)) for r in dirty.values()]
    return np.asarray(pil).copy(), new_boxes, rects
