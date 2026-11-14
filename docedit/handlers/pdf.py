"""PDF : pages avec du texte (PyMuPDF) et pages scannées (OCR)."""
from __future__ import annotations

import pymupdf
from PIL import Image

from .. import fonts, layout, imaging
from ..errors import UserError
from . import common

OCR_DPI = 200
MIN_TEXT_CHARS = 15
_font_cache: dict = {}


def open_pdf(path: str) -> pymupdf.Document:
    try:
        pdf = pymupdf.open(path)
    except Exception:
        raise UserError("Ce PDF n'a pas pu être ouvert. Le fichier est peut-être abîmé ou incomplet.")
    if pdf.needs_pass:
        raise UserError("Ce PDF est protégé par un mot de passe. Ouvrez-le avec votre lecteur PDF, "
                        "enregistrez-en une copie sans mot de passe, puis importez cette copie.")
    if pdf.page_count == 0:
        raise UserError("Ce PDF ne contient aucune page.")
    return pdf


def _classify(page: pymupdf.Page) -> str:
    visible = 0
    try:
        for span in page.get_texttrace():
            if span.get("type") != 3 and span.get("opacity", 1) > 0:
                visible += sum(1 for c in span["chars"] if c[0] > 32)
    except Exception:
        visible = len(page.get_text("text").strip())
    if visible < MIN_TEXT_CHARS:
        return "image"
    if visible < 60:
        area = abs(page.rect)
        covered = 0.0
        for info in page.get_image_info():
            covered += abs(pymupdf.Rect(info["bbox"]) & page.rect)
        if area and covered / area > 0.7:
            return "image"
    return "text"


def _font_lookup(page: pymupdf.Page) -> dict:
    table = {}
    for f in page.get_fonts(full=True):
        xref, ext, _ftype, basefont = f[0], f[1], f[2], f[3]
        clean = basefont.split("+", 1)[-1]
        table.setdefault(clean, (xref, ext))
        table.setdefault(clean.replace(" ", ""), (xref, ext))
    return table


def _extract_text_items(doc, page: pymupdf.Page, pno: int):
    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_MEDIABOX_CLIP
    raw = page.get_text("rawdict", flags=flags)
    lookup = _font_lookup(page)
    n = 0
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            dx, dy = line["dir"]
            if abs(dy) > 0.02 or dx < 0:
                continue  # texte incliné ou vertical : non modifiable
            for span in line["spans"]:
                chars = span["chars"]
                size = span["size"]
                pieces, cur = [], []
                for ch in chars:
                    if cur and ch["bbox"][0] - cur[-1]["bbox"][2] > 1.6 * size:
                        pieces.append(cur)
                        cur = []
                    cur.append(ch)
                if cur:
                    pieces.append(cur)
                for piece in pieces:
                    while piece and piece[0]["c"].isspace():
                        piece = piece[1:]
                    while piece and piece[-1]["c"].isspace():
                        piece = piece[:-1]
                    if not piece:
                        continue
                    text = "".join(c["c"] for c in piece)
                    x0 = piece[0]["bbox"][0]
                    x1 = max(c["bbox"][2] for c in piece)
                    y0 = min(c["bbox"][1] for c in span["chars"])
                    y1 = max(c["bbox"][3] for c in span["chars"])
                    font_name = span["font"]
                    fx = lookup.get(font_name) or lookup.get(font_name.replace(" ", ""))
                    iid = f"p{pno}-{n}"
                    n += 1
                    c = span["color"]
                    doc.items[iid] = {
                        "id": iid, "page": pno, "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                        "orig": text, "src": "pdf",
                        "style": {
                            "font": font_name, "size": size, "flags": span["flags"],
                            "color": [((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255],
                            "origin": [piece[0]["origin"][0], piece[0]["origin"][1]],
                            "family": fonts.guess_family(font_name, span["flags"]),
                            "bold": fonts.guess_bold(font_name, span["flags"]),
                            "italic": fonts.guess_italic(font_name, span["flags"]),
                            "xref": fx[0] if fx else 0, "ext": fx[1] if fx else "",
                        },
                    }
                    doc.meta["order"].append(iid)


def load(doc):
    pdf = open_pdf(doc.original_path)
    pages, scans = [], []
    for pno, page in enumerate(pdf):
        mode = _classify(page)
        info = {"index": pno, "w": page.rect.width, "h": page.rect.height, "mode": "image" if mode == "image" else "pdf",
                "rotation": page.rotation}
        if page.rotation and mode == "text":
            info["rotmat"] = list(page.rotation_matrix)
        if mode == "text":
            _extract_text_items(doc, page, pno)
        else:
            pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            scans.append((pno, img))
        pages.append(info)
    for pno, img in scans:  # OCR des pages scannées
        infos = common.prepare_ocr_pages(doc, [img], page_offset=pno, auto_rotate=False)
        info = infos[0]
        info["pdf_w"], info["pdf_h"] = pages[pno]["w"], pages[pno]["h"]
        info["rotation"] = pages[pno]["rotation"]
        pages[pno] = info
    doc.meta["pages"] = pages
    if scans and len(scans) == len(pages):
        doc.meta["scanned_pdf"] = True


# ----------------------------------------------------------------------------- polices

def _font_for(pdf: pymupdf.Document, page: pymupdf.Page, it: dict, text: str, doc_id: str):
    """Renvoie (nom_interne, objet Font) : la police d'origine si possible, sinon la plus proche."""
    st = it["style"]
    xref, ext = st.get("xref"), (st.get("ext") or "").lower()
    if xref and ext in ("ttf", "otf", "cff"):
        key = (doc_id, xref)
        if key not in _font_cache:
            try:
                _name, _ext, _t, buf = pdf.extract_font(xref)
                _font_cache[key] = (pymupdf.Font(fontbuffer=buf), buf) if buf else None
            except Exception:
                _font_cache[key] = None
        entry = _font_cache[key]
        if entry:
            font, buf = entry
            needed = {ch for ch in (text + it["orig"]) if not ch.isspace()}
            if " " in text:
                needed.add(" ")
            if all(font.has_glyph(ord(ch)) for ch in needed):
                name = f"DEo{xref}"
                if name not in page.meta_fonts:
                    page.insert_font(fontname=name, fontbuffer=buf)
                    page.meta_fonts.add(name)
                return name, font
    fam, bold, italic = st["family"], st["bold"], st["italic"]
    path = fonts.font_path(fam, bold, italic)
    name = f"DEl{fam[:2]}{int(bold)}{int(italic)}"
    key = ("lib", path)
    if key not in _font_cache:
        _font_cache[key] = (pymupdf.Font(fontfile=path), None)
    if name not in page.meta_fonts:
        page.insert_font(fontname=name, fontfile=path)
        page.meta_fonts.add(name)
    return name, _font_cache[key][0]


def _apply_text_page(pdf, page: pymupdf.Page, items: list[dict], pstate: dict, doc_id: str) -> dict:
    edited = [it for it in items if it["id"] in pstate]
    if not edited:
        return {}
    page.meta_fonts = set()
    for it in edited:
        x0, y0, x1, y1 = it["bbox"]
        h = y1 - y0
        r = pymupdf.Rect(x0 + 0.25, y0 + h * 0.3, x1 - 0.25, y1 - h * 0.3)
        page.add_redact_annot(r)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    new_boxes = {}
    margin = max(18.0, min(it["bbox"][0] for it in items) if items else 36.0)
    page_w = page.rect.width if page.rotation in (0, 180) else page.rect.height
    for it in edited:
        text = " ".join(pstate[it["id"]].split())
        if not text:
            new_boxes[it["id"]] = [it["bbox"][0], it["bbox"][1], it["bbox"][0] + 2, it["bbox"][3]]
            continue
        st = it["style"]
        fname, font = _font_for(pdf, page, it, text, doc_id)
        size, left, _ = layout.place(it, items, page_w, margin, st["size"],
                                     lambda s, _t=text, _f=font: _f.text_length(_t, fontsize=s))
        ox, oy = st["origin"]
        if size < st["size"]:
            oy -= (st["size"] - size) * 0.15
        point = pymupdf.Point(left + (ox - it["bbox"][0]), oy)
        page.insert_text(point, text, fontsize=size, fontname=fname, color=st["color"])
        w = font.text_length(text, fontsize=size)
        new_boxes[it["id"]] = [left, it["bbox"][1], left + w, it["bbox"][3]]
    return new_boxes


# ----------------------------------------------------------------------------- rendu

def _text_page_result(doc, pno: int, state):
    ver = doc.page_version(pno, state)
    key = ("pdf", doc.id, pno, ver)
    hit = common.cache_get(key)
    if hit is not None:
        return hit
    pdf = open_pdf(doc.original_path)
    page = pdf[pno]
    boxes = _apply_text_page(pdf, page, doc.page_items(pno), doc.page_state(pno, state), doc.id)
    zoom = max(1.5, min(3.0, 1500 / max(1.0, page.rect.width)))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    res = (pix.tobytes("png"), boxes)
    common.cache_put(key, res)
    return res


def render_page(doc, pno: int, state):
    page = doc.pages[pno]
    if page["mode"] == "image":
        return common.image_page_png(doc, page, state)
    return _text_page_result(doc, pno, state)[0], "image/png"


def boxes(doc, pno: int, state) -> dict:
    page = doc.pages[pno]
    if page["mode"] == "image":
        return common.edited_page(doc, page, state)[1]
    return _text_page_result(doc, pno, state)[1]


def view_bbox(doc, pno: int, bbox):
    """Coordonnées d'affichage (page éventuellement tournée) d'une zone de texte."""
    mat = doc.pages[pno].get("rotmat")
    if not mat:
        return bbox
    r = pymupdf.Rect(bbox) * pymupdf.Matrix(*mat)
    return [r.x0, r.y0, r.x1, r.y1]


def export_formats(doc) -> list[dict]:
    fmts = [{"id": "original", "label": "PDF (format d'origine)"}]
    if any(p["mode"] == "image" for p in doc.pages):
        fmts.append({"id": "pdf_ocr", "label": "PDF avec texte sélectionnable"})
    return fmts


def export(doc, fmt: str, state) -> tuple[bytes, str, str]:
    pdf = open_pdf(doc.original_path)
    for info in doc.pages:
        pno = info["index"]
        page = pdf[pno]
        items = doc.page_items(pno)
        pstate = doc.page_state(pno, state)
        if info["mode"] != "image":
            _apply_text_page(pdf, page, items, pstate, doc.id)
            continue
        if not pstate and fmt != "pdf_ocr":
            continue
        img, bxs, rects = common.edited_page(doc, info, state)
        k = page.rect.width / img.shape[1]
        if page.rotation != 0 and pstate:
            # page tournée : on remplace l'image complète de la page
            page.add_redact_annot(page.rect)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
            page.insert_image(page.rect, stream=imaging.encode_jpeg(img, 90))
        elif rects:
            mat = page.derotation_matrix
            for r in rects:
                rr = pymupdf.Rect(r[0] * k, r[1] * k, r[2] * k, r[3] * k) * mat
                page.add_redact_annot(rr)
            # supprime une éventuelle ancienne couche de texte invisible, sans toucher à l'image
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
            for r in rects:
                crop = img[r[1]:r[3], r[0]:r[2]]
                if crop.size == 0:
                    continue
                rr = pymupdf.Rect(r[0] * k, r[1] * k, r[2] * k, r[3] * k) * mat
                page.insert_image(rr, stream=imaging.encode_jpeg(crop, 95))
        if fmt == "pdf_ocr":
            add_items = items
            has_text = len(page.get_text("text").strip()) > 0
            if has_text and not pstate:
                continue  # déjà sélectionnable
            common.add_hidden_text(page, add_items, state, k, boxes=bxs)
    try:
        pdf.subset_fonts()
    except Exception:
        pass
    data = pdf.tobytes(garbage=3, deflate=True)
    return data, ".pdf", "application/pdf"
