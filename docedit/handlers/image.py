"""Images importées (JPG, PNG, HEIC) et documents scannés avec la caméra."""
from __future__ import annotations

import io
import zipfile

import pymupdf

from .. import imaging
from . import common


def load_images(doc, images):
    doc.meta["pages"] = common.prepare_ocr_pages(doc, images)


def export_formats(doc) -> list[dict]:
    ext = doc.meta["ext"]
    if doc.kind == "scan":
        fmts = [{"id": "pdf_ocr", "label": "PDF avec texte sélectionnable (recommandé)"},
                {"id": "pdf", "label": "PDF (image seule)"},
                {"id": "jpg", "label": "Image(s) JPG" + (" (fichier .zip)" if len(doc.pages) > 1 else "")}]
        return fmts
    label = {".png": "PNG", ".heic": "HEIC", ".heif": "HEIC"}.get(ext, "JPG")
    fmts = [{"id": "original", "label": f"Format d'origine ({label})"}]
    if ext in (".heic", ".heif"):
        fmts.append({"id": "jpg", "label": "Image JPG (plus compatible)"})
    fmts += [{"id": "pdf", "label": "PDF"},
             {"id": "pdf_ocr", "label": "PDF avec texte sélectionnable"}]
    return fmts


def render_page(doc, pno: int, state):
    return common.image_page_png(doc, doc.pages[pno], state)


def boxes(doc, pno, state):
    return common.edited_page(doc, doc.pages[pno], state)[1]


def export(doc, fmt: str, state) -> tuple[bytes, str, str]:
    ext = doc.meta["ext"]
    if fmt in ("pdf", "pdf_ocr"):
        out = pymupdf.open()
        for page in doc.pages:
            img, bxs, _ = common.edited_page(doc, page, state)
            items = doc.page_items(page["index"])
            pdf_page = common.add_image_page_to_pdf(out, img, items, state, searchable=False)
            if fmt == "pdf_ocr":
                common.add_hidden_text(pdf_page, items, state, pdf_page.rect.width / img.shape[1], boxes=bxs)
        data = out.tobytes(garbage=3, deflate=True)
        return data, ".pdf", "application/pdf"

    if fmt == "original":
        target = {".png": "png", ".heic": "heic", ".heif": "heic"}.get(ext, "jpg")
    else:
        target = "jpg"
    if target == "heic" and not imaging.HEIF_OK:
        target = "jpg"
    mime = {"png": "image/png", "heic": "image/heic", "jpg": "image/jpeg"}[target]
    suffix = {"png": ".png", "heic": ".heic", "jpg": ".jpg"}[target]
    files = []
    for page in doc.pages:
        img, _, _ = common.edited_page(doc, page, state)
        files.append(common.jpeg_or_png_bytes(img, target))
    if len(files) == 1:
        return files[0], suffix, mime
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, data in enumerate(files, 1):
            z.writestr(f"page_{i:02d}{suffix}", data)
    return buf.getvalue(), ".zip", "application/zip"
