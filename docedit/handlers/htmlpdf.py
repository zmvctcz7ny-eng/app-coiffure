"""Conversion en PDF : LibreOffice si présent (rendu fidèle), sinon mise en page HTML via PyMuPDF."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile

import pymupdf

CSS = """
body { font-family: sans-serif; font-size: 11pt; color: #000; }
h1 { font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }
p { margin: 0 0 6pt 0; }
table { border-collapse: collapse; margin: 6pt 0; }
td, th { border: 0.5pt solid #888; padding: 2pt 4pt; vertical-align: top; font-size: 9pt; }
th { background: #eee; }
.dhf { color: #555; font-size: 9pt; }
.sheet-title { font-size: 13pt; font-weight: bold; margin: 0 0 6pt 0; }
"""


def find_soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    cands = ["/Applications/LibreOffice.app/Contents/MacOS/soffice"]
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            cands.append(os.path.join(base, "LibreOffice", "program", "soffice.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def office_to_pdf(data: bytes, ext: str) -> bytes | None:
    soffice = find_soffice()
    if not soffice:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "document" + ext)
        with open(src, "wb") as f:
            f.write(data)
        profile = "file:///" + os.path.join(tmp, "profile").replace("\\", "/").lstrip("/")
        try:
            subprocess.run([soffice, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
                            "--outdir", tmp, src], capture_output=True, timeout=120)
        except Exception:
            return None
        out = glob.glob(os.path.join(tmp, "*.pdf"))
        if not out:
            return None
        with open(out[0], "rb") as f:
            return f.read()


def html_to_pdf(body_html: str, images: dict | None = None, landscape: bool = False) -> bytes:
    archive = pymupdf.Archive()
    for name, blob in (images or {}).items():
        archive.add(blob, name)
    story = pymupdf.Story(html=f"<html><body>{body_html}</body></html>", user_css=CSS, archive=archive)
    rect = pymupdf.paper_rect("a4-l" if landscape else "a4")
    where = rect + (40, 40, -40, -40)
    import io

    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()
