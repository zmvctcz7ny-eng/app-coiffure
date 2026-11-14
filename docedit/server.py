"""Serveur FastAPI de DocEdit."""
from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import traceback
import urllib.parse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, imaging, ocr, scanner, store
from .errors import UserError
from .handlers import KIND_LABELS, handler_for
from .handlers.common import prepare_ocr_pages

log = logging.getLogger("docedit")
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
MAX_UPLOAD = 80 * 1024 * 1024

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff"}

@contextlib.asynccontextmanager
async def _lifespan(_app):
    store.cleanup_old()
    ocr.status()
    yield


app = FastAPI(title="DocEdit", version=__version__, docs_url=None, redoc_url=None, lifespan=_lifespan)


# ----------------------------------------------------------------------------- erreurs

@app.exception_handler(UserError)
async def _user_error(_req: Request, exc: UserError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def _validation_error(_req: Request, exc: RequestValidationError):
    return JSONResponse({"detail": "La demande est incomplète. Rechargez la page et réessayez."}, status_code=400)


@app.exception_handler(Exception)
async def _unexpected(_req: Request, exc: Exception):
    log.error("Erreur inattendue : %s\n%s", exc, traceback.format_exc())
    return JSONResponse({"detail": "Une erreur inattendue s'est produite. Réessayez ; si le problème continue, "
                                   "relancez DocEdit."}, status_code=500)


# ----------------------------------------------------------------------------- utilitaires

def _get_doc(doc_id: str):
    doc = store.get(doc_id)
    if doc is None:
        raise UserError("Ce document n'est plus disponible (il a peut-être été fermé ou supprimé). "
                        "Importez-le à nouveau.", 404)
    return doc


def _boxes(doc, state, pages: set[int]) -> dict:
    h = handler_for(doc)
    out = {}
    if hasattr(h, "boxes"):
        for p in pages:
            out[p] = h.boxes(doc, p, state)
    return out


def _item_views(doc, iids, state) -> list[dict]:
    h = handler_for(doc)
    pages = {doc.items[i]["page"] for i in iids if doc.items[i]["id"] in state}
    boxes = _boxes(doc, state, pages)
    htmls = h.items_html(doc, state, set(iids)) if hasattr(h, "items_html") and iids else {}
    views = []
    for iid in iids:
        it = doc.items[iid]
        v = {"id": iid, "page": it["page"], "text": state.get(iid, it["orig"]), "orig": it["orig"],
             "edited": iid in state, "multiline": it["src"] == "docx"}
        if it.get("bbox"):
            v["bbox"] = boxes.get(it["page"], {}).get(iid, it["bbox"])
            if hasattr(h, "view_bbox"):
                v["bbox"] = h.view_bbox(doc, it["page"], v["bbox"])
        if iid in htmls:
            v["html"] = htmls[iid]
        views.append(v)
    return views


def _page_views(doc, state) -> list[dict]:
    h = handler_for(doc)
    out = []
    for p in doc.pages:
        v = {"index": p["index"], "mode": "html" if p["mode"] == "html" else "image",
             "v": doc.page_version(p["index"], state)}
        if p["mode"] == "html":
            v["html"] = h.page_html(doc, p["index"], state)
            v["cls"] = p.get("html_class", "")
            v["title"] = p.get("title")
        else:
            v["w"], v["h"] = p["w"], p["h"]
        out.append(v)
    return out


def _summary(doc) -> dict:
    state = doc.state()
    h = handler_for(doc)
    st = ocr.status()
    return {
        "id": doc.id, "filename": doc.meta["filename"], "kind": doc.kind, "kind_label": KIND_LABELS[doc.kind],
        "pages": _page_views(doc, state),
        "items": _item_views(doc, list(doc.meta["order"]), state),
        "can_undo": doc.can_undo, "can_redo": doc.can_redo, "edited_count": len(state),
        "export_formats": h.export_formats(doc), "warnings": doc.meta["warnings"],
        "lang": doc.meta.get("lang"), "ocr_available": st["available"],
    }


def _update(doc, changed: list[str]) -> dict:
    state = doc.state()
    pages = sorted({doc.items[i]["page"] for i in changed})
    h = handler_for(doc)
    page_v = []
    for p in pages:
        pv = {"index": p, "v": doc.page_version(p, state)}
        page_v.append(pv)
    items = _item_views(doc, changed, state)
    # les autres éléments d'une page modifiée peuvent avoir bougé : on renvoie leur position
    del h
    return {"items": items, "pages": page_v, "can_undo": doc.can_undo, "can_redo": doc.can_redo,
            "edited_count": len(state), "changed": len(changed)}


def _pattern(q: str, case: bool, word: bool):
    if not q:
        raise UserError("Indiquez le texte à rechercher.")
    p = re.escape(q)
    if word:
        p = r"(?<!\w)" + p + r"(?!\w)"
    return re.compile(p, 0 if case else re.IGNORECASE)


# ----------------------------------------------------------------------------- pages

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"), media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ----------------------------------------------------------------------------- API

@app.get("/api/status")
def api_status(request: Request):
    st = ocr.status()
    return {"version": __version__, "ocr": {"available": st["available"], "message": st["message"],
                                            "lang": st["lang"]},
            "lan_url": os.environ.get("DOCEDIT_LAN_URL"), "lan_url_https": os.environ.get("DOCEDIT_LAN_URL_HTTPS")}


@app.get("/api/qr")
def api_qr(request: Request, https: int = 0):
    import io

    import qrcode
    import qrcode.image.svg

    url = os.environ.get("DOCEDIT_LAN_URL_HTTPS" if https else "DOCEDIT_LAN_URL") or str(request.base_url)
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"X-Url": urllib.parse.quote(url)})


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise UserError("Le fichier est vide.")
    if len(data) > MAX_UPLOAD:
        raise UserError("Ce fichier est trop volumineux (plus de 80 Mo).")
    return data


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    data = await _read_upload(file)
    name = file.filename or "document"
    ext = os.path.splitext(name)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if not ext:  # pas d'extension : on devine d'après le contenu
        ext = ".pdf" if data[:4] == b"%PDF" else (".png" if data[:4] == b"\x89PNG" else ".jpg")
    if ext in (".doc", ".xls", ".ppt", ".pptx", ".odt", ".ods"):
        raise UserError({".doc": "Les anciens fichiers Word (.doc) ne sont pas pris en charge : ouvrez-le dans Word "
                                 "et choisissez « Enregistrer sous… » au format .docx.",
                         ".xls": "Les anciens fichiers Excel (.xls) ne sont pas pris en charge : ouvrez-le dans "
                                 "Excel et enregistrez-le au format .xlsx."}.get(
            ext, "Ce type de fichier n'est pas pris en charge. Formats acceptés : PDF, Word (.docx), "
                 "Excel (.xlsx), images (JPG, PNG, HEIC)."))
    if ext == ".pdf":
        kind = "pdf"
    elif ext == ".docx":
        kind = "docx"
    elif ext == ".xlsx" or ext == ".xlsm":
        kind = "xlsx"
    elif ext in IMAGE_EXT:
        kind = "image"
    else:
        raise UserError("Ce type de fichier n'est pas pris en charge. Formats acceptés : PDF, Word (.docx), "
                        "Excel (.xlsx), images (JPG, PNG, HEIC).")
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(_create_doc, name, data, kind, ext)


def _create_doc(name, data, kind, ext):
    doc = store.create(name, data, kind, ext)
    try:
        with doc.lock:
            if kind == "image":
                img = imaging.open_image(data)
                handler_for(doc).load_images(doc, [img])
            else:
                handler_for(doc).load(doc)
            doc.save()
            return _summary(doc)
    except Exception:
        store.discard(doc)
        raise


@app.post("/api/scan/detect")
async def api_scan_detect(file: UploadFile = File(...)):
    data = await _read_upload(file)
    img = imaging.to_np(imaging.open_image(data))
    corners, found = scanner.detect_corners(img)
    return {"corners": corners, "found": found, "w": img.shape[1], "h": img.shape[0]}


@app.post("/api/scan/process")
async def api_scan_process(file: UploadFile = File(...), corners: str = Form(...), mode: str = Form("auto")):
    data = await _read_upload(file)
    try:
        pts = json.loads(corners)
        assert len(pts) == 4 and all(len(p) == 2 for p in pts)
        pts = [[min(1.0, max(0.0, float(x))), min(1.0, max(0.0, float(y)))] for x, y in pts]
    except Exception:
        raise UserError("Les coins de la feuille ne sont pas valides. Recommencez la photo.")
    from starlette.concurrency import run_in_threadpool

    def work():
        img = imaging.to_np(imaging.open_image(data))
        out = scanner.enhance(scanner.warp(img, pts), mode if mode in ("auto", "gray", "bw", "original") else "auto")
        return imaging.encode_jpeg(out, 92)

    return Response(await run_in_threadpool(work), media_type="image/jpeg")


@app.post("/api/scan/finish")
async def api_scan_finish(files: list[UploadFile] = File(...)):
    if not files:
        raise UserError("Aucune page scannée.")
    datas = [await _read_upload(f) for f in files]
    from starlette.concurrency import run_in_threadpool

    def work():
        import datetime

        name = "Scan " + datetime.datetime.now().strftime("%d-%m-%Y %Hh%M") + ".pdf"
        doc = store.create(name, None, "scan", ".jpg")
        try:
            with doc.lock:
                imgs = [imaging.open_image(d) for d in datas]
                doc.meta["pages"] = prepare_ocr_pages(doc, imgs)
                doc.save()
                return _summary(doc)
        except Exception:
            store.discard(doc)
            raise

    return await run_in_threadpool(work)


@app.get("/api/doc/{doc_id}")
def api_doc(doc_id: str):
    doc = _get_doc(doc_id)
    with doc.lock:
        return _summary(doc)


@app.get("/api/doc/{doc_id}/page/{pno}")
def api_page(doc_id: str, pno: int, v: str = ""):
    doc = _get_doc(doc_id)
    if pno < 0 or pno >= len(doc.pages):
        raise UserError("Cette page n'existe pas.", 404)
    with doc.lock:
        data, mime = handler_for(doc).render_page(doc, pno, doc.state())
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})


class EditIn(BaseModel):
    id: str
    text: str
    bold: bool | None = None


@app.get("/api/doc/{doc_id}/item/{iid}/style")
def api_item_style(doc_id: str, iid: str):
    """Graisse détectée d'une ligne de scan (pour pré-cocher la case « Gras »)."""
    doc = _get_doc(doc_id)
    with doc.lock:
        it = doc.items.get(iid)
        if not it:
            raise UserError("Ce texte n'existe plus dans le document. Rechargez la page.")
        if it["src"] != "ocr":
            return {"bold": None}
        from .handlers.common import item_bold

        return {"bold": item_bold(doc, it)}


@app.post("/api/doc/{doc_id}/edit")
def api_edit(doc_id: str, body: EditIn):
    doc = _get_doc(doc_id)
    with doc.lock:
        if body.id not in doc.items:
            raise UserError("Ce texte n'existe plus dans le document. Rechargez la page.")
        it = doc.items[body.id]
        text = body.text if it["src"] == "docx" else " ".join(body.text.split())
        style_changed = False
        if body.bold is not None and it["src"] == "ocr" and it.get("style", {}).get("bold") != body.bold:
            it["bold_override"] = body.bold
            style_changed = True
        changed = doc.apply({body.id: text})
        if style_changed and not changed:
            doc.save()
            changed = [body.id] if body.id in doc.state() else []
        return _update(doc, changed)


class ResetIn(BaseModel):
    id: str


@app.post("/api/doc/{doc_id}/reset")
def api_reset(doc_id: str, body: ResetIn):
    doc = _get_doc(doc_id)
    with doc.lock:
        if body.id not in doc.items:
            raise UserError("Ce texte n'existe plus dans le document.")
        return _update(doc, doc.apply({body.id: doc.items[body.id]["orig"]}))


class SearchIn(BaseModel):
    q: str
    r: str = ""
    case: bool = False
    word: bool = False


@app.post("/api/doc/{doc_id}/search")
def api_search(doc_id: str, body: SearchIn):
    doc = _get_doc(doc_id)
    pat = _pattern(body.q, body.case, body.word)
    with doc.lock:
        state = doc.state()
        hits, count = [], 0
        for iid in doc.meta["order"]:
            n = len(pat.findall(state.get(iid, doc.items[iid]["orig"])))
            if n:
                hits.append(iid)
                count += n
        return {"ids": hits, "count": count}


@app.post("/api/doc/{doc_id}/replace")
def api_replace(doc_id: str, body: SearchIn):
    doc = _get_doc(doc_id)
    pat = _pattern(body.q, body.case, body.word)
    with doc.lock:
        state = doc.state()
        changes, count = {}, 0
        for iid in doc.meta["order"]:
            cur = state.get(iid, doc.items[iid]["orig"])
            new, n = pat.subn(lambda _m: body.r, cur)
            if n:
                changes[iid] = new
                count += n
        if not changes:
            raise UserError(f"« {body.q} » n'a été trouvé nulle part dans le document.")
        res = _update(doc, doc.apply(changes))
        res["count"] = count
        return res


@app.post("/api/doc/{doc_id}/undo")
def api_undo(doc_id: str):
    doc = _get_doc(doc_id)
    with doc.lock:
        return _update(doc, doc.undo())


@app.post("/api/doc/{doc_id}/redo")
def api_redo(doc_id: str):
    doc = _get_doc(doc_id)
    with doc.lock:
        return _update(doc, doc.redo())


@app.get("/api/doc/{doc_id}/export")
def api_export(doc_id: str, fmt: str = "original"):
    doc = _get_doc(doc_id)
    h = handler_for(doc)
    allowed = [f["id"] for f in h.export_formats(doc)]
    if fmt not in allowed:
        fmt = allowed[0]
    with doc.lock:
        data, ext, mime = h.export(doc, fmt, doc.state())
    stem = os.path.splitext(doc.meta["filename"])[0]
    name = f"{stem} (modifié){ext}"
    ascii_name = re.sub(r"[^A-Za-z0-9._ ()-]", "_", name)
    disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name)}"
    return Response(data, media_type=mime, headers={"Content-Disposition": disp, "Cache-Control": "no-store"})


@app.delete("/api/doc/{doc_id}")
def api_close(doc_id: str):
    doc = store.get(doc_id)
    if doc:
        store.discard(doc)
    return {"ok": True}
