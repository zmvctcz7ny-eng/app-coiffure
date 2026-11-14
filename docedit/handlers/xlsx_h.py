"""Classeurs Excel (.xlsx) avec openpyxl : chaque cellule remplie est modifiable."""
from __future__ import annotations

import datetime as dt
import html
import io
import re

import openpyxl
from openpyxl.utils import get_column_letter

from ..errors import UserError
from . import htmlpdf

MAX_ROWS, MAX_COLS = 500, 60


def open_xlsx(path: str, data_only=False):
    try:
        return openpyxl.load_workbook(path, data_only=data_only)
    except Exception:
        raise UserError("Ce fichier Excel n'a pas pu être ouvert. Seuls les fichiers .xlsx sont pris en charge "
                        "(pour un ancien fichier .xls, ouvrez-le dans Excel et enregistrez-le en .xlsx).")


def _fmt_number(v, number_format: str) -> str:
    nf = number_format or "General"
    if "%" in nf:
        dec = len(re.search(r"0(?:\.(0+))?%", nf).group(1) or "") if re.search(r"0(?:\.(0+))?%", nf) else 0
        return f"{v * 100:.{dec}f}".replace(".", ",") + " %"
    m = re.search(r"0\.(0+)", nf)
    if m:
        s = f"{v:.{len(m.group(1))}f}"
    elif isinstance(v, int) or float(v).is_integer():
        s = str(int(v))
    else:
        s = repr(float(v))
        if "e" in s:
            s = f"{v:.10g}"
    return s.replace(".", ",")


def display(v, number_format="General") -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "VRAI" if v else "FAUX"
    if isinstance(v, dt.datetime):
        if v.hour or v.minute or v.second:
            return v.strftime("%d/%m/%Y %H:%M")
        return v.strftime("%d/%m/%Y")
    if isinstance(v, dt.date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, dt.time):
        return v.strftime("%H:%M")
    if isinstance(v, (int, float)):
        return _fmt_number(v, number_format)
    return str(v)


def parse_number(s: str):
    t = s.strip().replace(" ", "").replace("\xa0", "").replace(" ", "")
    pct = t.endswith("%")
    t = t.rstrip("%").strip("€$£").strip()
    if not re.fullmatch(r"[-+]?[\d.,]+", t) or not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        if t.count(",") > 1:
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    try:
        val = float(t)
    except ValueError:
        return None
    if pct:
        return val / 100
    return int(val) if val.is_integer() and "." not in t else val


def parse_date(s: str):
    m = re.fullmatch(r"\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:\s+(\d{1,2})[:h](\d{2}))?\s*", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return dt.datetime(y, mo, d, int(m.group(4) or 0), int(m.group(5) or 0))
        except ValueError:
            return None
    m = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", s)
    if m:
        try:
            return dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def convert(text: str, original):
    """Transforme le texte saisi dans le type de la cellule d'origine quand c'est possible."""
    if text.startswith("="):
        return text
    if text.strip() == "":
        return None
    if isinstance(original, bool):
        if text.strip().upper() in ("VRAI", "TRUE", "OUI"):
            return True
        if text.strip().upper() in ("FAUX", "FALSE", "NON"):
            return False
    if isinstance(original, (dt.datetime, dt.date)):
        d = parse_date(text)
        if d is not None:
            return d
    if isinstance(original, (int, float)) and not isinstance(original, bool):
        n = parse_number(text)
        if n is not None:
            return n
    if isinstance(original, str) or original is None:
        return text
    n = parse_number(text)
    return n if n is not None else text


def _iid(si: int, coord: str) -> str:
    return f"x{si}-{coord}"


def load(doc):
    wb = open_xlsx(doc.original_path)
    vals = open_xlsx(doc.original_path, data_only=True)
    pages = []
    for si, ws in enumerate(wb.worksheets):
        wv = vals.worksheets[si]
        truncated = ws.max_row > MAX_ROWS or ws.max_column > MAX_COLS
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, MAX_ROWS), max_col=min(ws.max_column, MAX_COLS)):
            for cell in row:
                if cell.value is None or isinstance(cell, openpyxl.cell.cell.MergedCell):
                    continue
                v = cell.value
                iid = _iid(si, cell.coordinate)
                if isinstance(v, str) and v.startswith("="):
                    text = v
                    disp = display(wv[cell.coordinate].value, cell.number_format) or text
                elif hasattr(v, "text") and not isinstance(v, str):  # formule de tableau, texte enrichi…
                    text = str(v)
                    disp = text
                else:
                    text = display(v, cell.number_format)
                    disp = text
                if not text.strip():
                    continue
                doc.items[iid] = {"id": iid, "page": si, "bbox": None, "orig": text, "src": "xlsx",
                                  "display": disp, "coord": cell.coordinate}
                doc.meta["order"].append(iid)
        pages.append({"index": si, "mode": "html", "html_class": "xlsx", "title": ws.title,
                      "truncated": truncated})
    doc.meta["pages"] = pages
    if any(p["truncated"] for p in pages):
        doc.meta["warnings"].append(f"Certaines feuilles sont très grandes : seules les {MAX_ROWS} premières lignes "
                                    f"et {MAX_COLS} premières colonnes sont affichées et modifiables. "
                                    "Le reste du fichier est conservé tel quel.")


def _modified(doc, state):
    wb = open_xlsx(doc.original_path)
    for iid, text in state.items():
        it = doc.items.get(iid)
        if not it or it["src"] != "xlsx":
            continue
        ws = wb.worksheets[it["page"]]
        cell = ws[it["coord"]]
        cell.value = convert(text, cell.value)
    if state:
        try:
            wb.calculation.fullCalcOnLoad = True  # Excel recalcule les formules à l'ouverture
        except Exception:
            pass
    return wb


def _cell_display(doc, it, state, cell=None) -> str:
    if it["id"] not in state:
        return it["display"]
    text = state[it["id"]]
    if text.startswith("="):
        return text
    if cell is not None:
        return display(cell.value, cell.number_format)
    return text


def _color(c) -> str | None:
    try:
        if c is not None and c.type == "rgb" and isinstance(c.rgb, str) and len(c.rgb) == 8 and c.rgb != "00000000":
            return "#" + c.rgb[2:]
    except Exception:
        pass
    return None


def sheet_html(doc, wb, si: int, state, editable=True) -> str:
    ws = wb.worksheets[si]
    max_r, max_c = min(ws.max_row, MAX_ROWS), min(ws.max_column, MAX_COLS)
    spans, hidden = {}, set()
    for rng in ws.merged_cells.ranges:
        spans[(rng.min_row, rng.min_col)] = (rng.max_row - rng.min_row + 1, rng.max_col - rng.min_col + 1)
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    hidden.add((r, c))
    head = "".join(f"<th>{get_column_letter(c)}</th>" for c in range(1, max_c + 1))
    cols = "".join(
        f'<col style="width:{max(40, int((ws.column_dimensions[get_column_letter(c)].width or 10) * 7))}px">'
        for c in range(1, max_c + 1))
    rows = [f'<colgroup><col style="width:36px">{cols}</colgroup>' if editable else "",
            f"<tr><th></th>{head}</tr>" if editable else ""]
    for r in range(1, max_r + 1):
        tds = [f"<th>{r}</th>"] if editable else []
        for c in range(1, max_c + 1):
            if (r, c) in hidden:
                continue
            cell = ws.cell(row=r, column=c)
            iid = _iid(si, cell.coordinate)
            it = doc.items.get(iid)
            txt = html.escape(_cell_display(doc, it, state, cell)) if it else ""
            style = []
            if cell.font is not None:
                if cell.font.b:
                    style.append("font-weight:bold")
                if cell.font.i:
                    style.append("font-style:italic")
                fc = _color(cell.font.color)
                if fc:
                    style.append(f"color:{fc}")
            if cell.fill is not None and cell.fill.patternType == "solid":
                bg = _color(cell.fill.fgColor)
                if bg:
                    style.append(f"background:{bg}")
            al = cell.alignment.horizontal if cell.alignment is not None else None
            if al in ("center", "right", "left"):
                style.append(f"text-align:{al}")
            elif isinstance(cell.value, (int, float, dt.date)) and not isinstance(cell.value, bool):
                style.append("text-align:right")
            attrs = ""
            if (r, c) in spans:
                rs, cs = spans[(r, c)]
                attrs += (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
            if it and editable:
                attrs += f' class="it" data-id="{iid}"'
            if style:
                attrs += f' style="{";".join(style)}"'
            tds.append(f"<td{attrs}>{txt}</td>")
        rows.append(f"<tr>{''.join(tds)}</tr>")
    return f'<table class="xt">{"".join(rows)}</table>'


def page_html(doc, pno, state) -> str:
    wb = _modified(doc, state)
    return sheet_html(doc, wb, pno, state)


def items_html(doc, state, iids) -> dict:
    wb = _modified(doc, state)
    out = {}
    for iid in iids:
        it = doc.items[iid]
        cell = wb.worksheets[it["page"]][it["coord"]]
        out[iid] = html.escape(_cell_display(doc, it, state, cell))
    return out


def export_formats(doc):
    return [{"id": "original", "label": "Excel (.xlsx, format d'origine)"}, {"id": "pdf", "label": "PDF"}]


def export(doc, fmt, state):
    wb = _modified(doc, state)
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    if fmt == "pdf":
        pdf = htmlpdf.office_to_pdf(data, ".xlsx")
        if pdf is None:
            parts = []
            for si, ws in enumerate(wb.worksheets):
                parts.append(f'<p class="sheet-title">{html.escape(ws.title)}</p>')
                parts.append(sheet_html(doc, wb, si, state, editable=False))
            pdf = htmlpdf.html_to_pdf("".join(parts), landscape=True)
        return pdf, ".pdf", "application/pdf"
    return data, ".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
