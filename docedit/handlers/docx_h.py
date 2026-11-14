"""Documents Word (.docx) avec python-docx : chaque paragraphe est modifiable, la mise en forme est conservée."""
from __future__ import annotations

import base64
import difflib
import html
import io
import re

from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from ..errors import UserError
from . import htmlpdf

_RUN_XPATH = "./w:r | ./w:hyperlink/w:r | ./w:ins/w:r | ./w:smartTag/w:r | ./w:fldSimple/w:r"


def open_docx(path: str):
    try:
        return load_docx(path)
    except Exception:
        raise UserError("Ce fichier Word n'a pas pu être ouvert. Seuls les fichiers .docx sont pris en charge "
                        "(pour un ancien fichier .doc, ouvrez-le dans Word et enregistrez-le en .docx).")


def runs_of(par: Paragraph) -> list[Run]:
    return [Run(r, par) for r in par._p.xpath(_RUN_XPATH)]


def par_text(par: Paragraph) -> str:
    return "".join(r.text for r in runs_of(par))


def _word_opcodes(old: str, new: str):
    """Différences mot par mot (exprimées en positions de caractères) : « 14 » → « 21 » reste un seul bloc."""
    ta = re.findall(r"\w+|\s+|[^\w\s]", old)
    tb = re.findall(r"\w+|\s+|[^\w\s]", new)
    pa = [0]
    for t in ta:
        pa.append(pa[-1] + len(t))
    pb = [0]
    for t in tb:
        pb.append(pb[-1] + len(t))
    return [(tag, pa[a1], pa[a2], pb[b1], pb[b2])
            for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes()]


def set_par_text(par: Paragraph, new: str):
    """Remplace le texte du paragraphe en ne touchant que les caractères modifiés (garde la mise en forme)."""
    runs = runs_of(par)
    if not runs:
        if new:
            par.add_run(new)
        return
    texts = [r.text for r in runs]
    old = "".join(texts)
    if old == new:
        return
    ops = _word_opcodes(old, new)
    kept = sum(i2 - i1 for tag, i1, i2, _a, _b in ops if tag == "equal")
    if old and kept / max(len(old), len(new)) < 0.3:
        # texte presque entièrement réécrit : il prend le style du début du paragraphe
        first = next((k for k, t in enumerate(texts) if t), 0)
        for k, r in enumerate(runs):
            if r.text != (new if k == first else ""):
                r.text = new if k == first else ""
        return
    for tag, i1, i2, j1, j2 in reversed(ops):
        if tag == "equal":
            continue
        ins = new[j1:j2]
        # localise le run qui contient la position i1
        starts, pos = [], 0
        for t in texts:
            starts.append(pos)
            pos += len(t)
        pos_char = i1 - 1 if (tag == "insert" and i1 > 0) else i1
        target = len(texts) - 1
        for k, st in enumerate(starts):
            if st <= pos_char < st + len(texts[k]):
                target = k
                break
        # suppression de [i1, i2)
        for k in range(len(texts)):
            s, e = starts[k], starts[k] + len(texts[k])
            a, b = max(i1, s), min(i2, e)
            if a < b:
                texts[k] = texts[k][: a - s] + texts[k][b - s:]
        # insertion
        local = max(0, i1 - starts[target])
        texts[target] = texts[target][:local] + ins + texts[target][local:]
    for r, t in zip(runs, texts):
        if r.text != t:
            r.text = t


# ----------------------------------------------------------------------------- parcours

def _walk(element, parent, out: list):
    for child in element.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            out.append(("p", Paragraph(child, parent)))
        elif tag == qn("w:tbl"):
            rows = []
            for tr in child.findall(qn("w:tr")):
                cells = []
                for tc in tr.findall(qn("w:tc")):
                    cell_out: list = []
                    _walk(tc, _Cell(tc, parent), cell_out)
                    span = tc.find(qn("w:tcPr") + "/" + qn("w:gridSpan"))
                    cells.append((int(span.get(qn("w:val"))) if span is not None else 1, cell_out))
                rows.append(cells)
            out.append(("t", rows))
        elif tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                _walk(content, parent, out)


def structure(document) -> dict:
    """{'header': [...], 'body': [...], 'footer': [...]} dans un ordre stable."""
    res = {"header": [], "body": [], "footer": []}
    seen = set()
    for section in document.sections:
        for part_name, hf in (("header", section.header), ("footer", section.footer)):
            try:
                if hf.is_linked_to_previous:
                    continue
                el = hf._element
            except Exception:
                continue
            if id(el) in seen:
                continue
            seen.add(id(el))
            _walk(el, hf, res[part_name])
    _walk(document.element.body, document._body, res["body"])
    return res


def paragraphs(struct) -> list[Paragraph]:
    out = []

    def rec(nodes):
        for kind, val in nodes:
            if kind == "p":
                out.append(val)
            else:
                for row in val:
                    for _span, cell in row:
                        rec(cell)

    for key in ("header", "body", "footer"):
        rec(struct[key])
    return out


# ----------------------------------------------------------------------------- HTML

def _run_html(run: Run, images: dict | None) -> str:
    parts = []
    for blip in run._r.xpath(".//a:blip"):
        rid = blip.get(qn("r:embed"))
        try:
            part = run.part.related_parts[rid]
            blob, ctype = part.blob, part.content_type
        except Exception:
            continue
        width = ""
        ext = run._r.xpath(".//wp:extent")
        if ext:
            width = f' style="width:{int(ext[0].get("cx")) / 9525:.0f}px;max-width:100%"'
        if images is None:
            src = f"data:{ctype};base64,{base64.b64encode(blob).decode()}"
        else:
            name = f"img{len(images)}.{ctype.split('/')[-1]}"
            images[name] = blob
            src = name
        parts.append(f'<img src="{src}"{width} alt="">')
    text = run.text
    if text:
        t = html.escape(text).replace("\t", "&emsp;").replace("\n", "<br>")
        styles = []
        f = run.font
        if f.size:
            styles.append(f"font-size:{f.size.pt:.1f}pt")
        try:
            if f.color is not None and f.color.type is not None and f.color.rgb is not None:
                styles.append(f"color:#{f.color.rgb}")
        except Exception:
            pass
        if f.name:
            styles.append(f"font-family:'{html.escape(f.name)}'")
        if f.highlight_color:
            styles.append("background:#fff59d")
        if run.bold:
            t = f"<b>{t}</b>"
        if run.italic:
            t = f"<i>{t}</i>"
        if run.underline:
            t = f"<u>{t}</u>"
        if f.strike:
            t = f"<s>{t}</s>"
        parts.append(f'<span style="{";".join(styles)}">{t}</span>' if styles else t)
    return "".join(parts)


def paragraph_inner(par: Paragraph, images=None) -> str:
    inner = "".join(_run_html(r, images) for r in runs_of(par))
    return inner or "&#8203;"


def _par_tag(par: Paragraph) -> tuple[str, str]:
    name = ""
    try:
        name = (par.style.name or "").lower()
    except Exception:
        pass
    tag = "p"
    for n in range(1, 4):
        if f"heading {n}" in name or f"titre {n}" in name:
            tag = f"h{n}"
    if name in ("title", "titre"):
        tag = "h1"
    style = []
    al = par.alignment
    if al is not None:
        style.append("text-align:" + {0: "left", 1: "center", 2: "right", 3: "justify"}.get(int(al), "left"))
    try:
        ind = par.paragraph_format.left_indent
        if ind:
            style.append(f"margin-left:{ind.pt:.0f}pt")
    except Exception:
        pass
    if "list" in name or par._p.find(qn("w:pPr") + "/" + qn("w:numPr")) is not None:
        style.append("display:list-item;margin-left:1.4em")
    return tag, ";".join(style)


def to_html(struct, ids: dict, editable: bool = True, images=None) -> str:
    def rec(nodes) -> str:
        out = []
        for kind, val in nodes:
            if kind == "p":
                tag, style = _par_tag(val)
                iid = ids.get(id(val._p))
                attr = f' data-id="{iid}"' if (iid and editable) else ""
                cls = ' class="it"' if (iid and editable) else ""
                st = f' style="{style}"' if style else ""
                out.append(f"<{tag}{cls}{attr}{st}>{paragraph_inner(val, images)}</{tag}>")
            else:
                rows = []
                for row in val:
                    cells = "".join(
                        f'<td{f" colspan={span}" if span > 1 else ""}>{rec(cell)}</td>' for span, cell in row)
                    rows.append(f"<tr>{cells}</tr>")
                out.append(f'<table class="dt">{"".join(rows)}</table>')
        return "".join(out)

    parts = []
    if struct["header"]:
        parts.append(f'<div class="dhf">{rec(struct["header"])}</div>')
    parts.append(f'<div class="dbody">{rec(struct["body"])}</div>')
    if struct["footer"]:
        parts.append(f'<div class="dhf">{rec(struct["footer"])}</div>')
    return "".join(parts)


# ----------------------------------------------------------------------------- interface

def _modified(doc, state):
    document = open_docx(doc.original_path)
    struct = structure(document)
    pars = paragraphs(struct)
    ids = {}
    for n, par in enumerate(pars):
        iid = f"w{n}"
        if iid in doc.items:
            ids[id(par._p)] = iid
            if iid in state:
                set_par_text(par, state[iid])
    return document, struct, pars, ids


def load(doc):
    document = open_docx(doc.original_path)
    struct = structure(document)
    for n, par in enumerate(paragraphs(struct)):
        text = par_text(par)
        if text.strip():
            iid = f"w{n}"
            doc.items[iid] = {"id": iid, "page": 0, "bbox": None, "orig": text, "src": "docx"}
            doc.meta["order"].append(iid)
    doc.meta["pages"] = [{"index": 0, "mode": "html", "html_class": "docx"}]


def page_html(doc, pno, state) -> str:
    _d, struct, _p, ids = _modified(doc, state)
    return to_html(struct, ids)


def items_html(doc, state, iids) -> dict:
    _d, _s, pars, ids = _modified(doc, state)
    out = {}
    for par in pars:
        iid = ids.get(id(par._p))
        if iid in iids:
            out[iid] = paragraph_inner(par)
    return out


def export_formats(doc):
    return [{"id": "original", "label": "Word (.docx, format d'origine)"},
            {"id": "pdf", "label": "PDF"}]


def export(doc, fmt, state):
    document, struct, _p, ids = _modified(doc, state)
    buf = io.BytesIO()
    document.save(buf)
    data = buf.getvalue()
    if fmt == "pdf":
        pdf = htmlpdf.office_to_pdf(data, ".docx")
        if pdf is None:
            images: dict = {}
            body = to_html(struct, ids, editable=False, images=images)
            pdf = htmlpdf.html_to_pdf(body, images)
        return pdf, ".pdf", "application/pdf"
    return data, ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
