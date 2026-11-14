"""Tests de bout en bout de l'API DocEdit (lancer : python -m pytest tests)."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile

import pymupdf
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DOCEDIT_DATA", tempfile.mkdtemp(prefix="docedit-test-"))

from fastapi.testclient import TestClient  # noqa: E402

from docedit import ocr  # noqa: E402
from docedit.server import app  # noqa: E402
from tests import make_samples  # noqa: E402

SAMPLES = os.path.join(ROOT, "tests", "samples")
needs_ocr = pytest.mark.skipif(not ocr.status()["available"], reason="Tesseract n'est pas installé")


@pytest.fixture(scope="session", autouse=True)
def samples():
    os.makedirs(SAMPLES, exist_ok=True)
    make_samples.make_pdf(os.path.join(SAMPLES, "facture.pdf"))
    make_samples.make_scan_pdf(os.path.join(SAMPLES, "attestation_scannee.pdf"))
    make_samples.make_photo(os.path.join(SAMPLES, "photo_document.jpg"))
    make_samples.make_png(os.path.join(SAMPLES, "attestation.png"))
    make_samples.make_docx(os.path.join(SAMPLES, "compte_rendu.docx"))
    make_samples.make_xlsx(os.path.join(SAMPLES, "budget.xlsx"))


@pytest.fixture()
def client():
    return TestClient(app)


def upload(client, name):
    with open(os.path.join(SAMPLES, name), "rb") as f:
        r = client.post("/api/upload", files={"file": (name, f.read())})
    assert r.status_code == 200, r.text
    return r.json()


def find(doc, needle):
    return next(it for it in doc["items"] if needle in it["text"])


def test_pdf_text_edit_replace_undo_export(client):
    doc = upload(client, "facture.pdf")
    did = doc["id"]
    amount = find(doc, "1 250,00")
    r = client.post(f"/api/doc/{did}/edit", json={"id": amount["id"], "text": "12 250,00 €"}).json()
    # montant aligné à droite : le bord droit ne bouge pas
    assert abs(r["items"][0]["bbox"][2] - amount["bbox"][2]) < 1
    date = find(doc, "12/03/2024")
    client.post(f"/api/doc/{did}/edit", json={"id": date["id"], "text": "Date : 28/11/2026"})
    r = client.post(f"/api/doc/{did}/replace", json={"q": "€", "r": "EUR"}).json()
    assert r["count"] == 4
    assert client.post(f"/api/doc/{did}/undo").json()["changed"] == 4
    assert client.post(f"/api/doc/{did}/redo").json()["changed"] == 4
    client.post(f"/api/doc/{did}/undo")
    out = client.get(f"/api/doc/{did}/export?fmt=original")
    assert out.status_code == 200 and "modifi" in out.headers["content-disposition"]
    text = pymupdf.open(stream=out.content)[0].get_text()
    assert "12 250,00 €" in text and "28/11/2026" in text
    assert "1 250,00" not in text.replace("12 250,00", "") and "12/03/2024" not in text
    # l'original n'est jamais modifié
    original = pymupdf.open(os.path.join(SAMPLES, "facture.pdf"))[0].get_text()
    assert "12/03/2024" in original


@needs_ocr
def test_image_ocr_edit_and_exports(client):
    doc = upload(client, "attestation.png")
    did = doc["id"]
    assert len(doc["items"]) >= 6
    line = find(doc, "1 830,00")
    client.post(f"/api/doc/{did}/edit", json={"id": line["id"], "text": line["text"].replace("1 830,00", "2 145,50")})
    assert client.get(f"/api/doc/{did}/page/0").headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/doc/{did}/export?fmt=original").headers["content-type"] == "image/png"
    pdf = client.get(f"/api/doc/{did}/export?fmt=pdf_ocr").content
    assert "2 145,50" in pymupdf.open(stream=pdf)[0].get_text()


@needs_ocr
def test_bold_override(client):
    doc = upload(client, "attestation.png")
    did = doc["id"]
    line = find(doc, "Lyon")
    assert client.get(f"/api/doc/{did}/item/{line['id']}/style").json()["bold"] is False
    r = client.post(f"/api/doc/{did}/edit", json={"id": line["id"], "text": "Fait à Paris", "bold": True}).json()
    assert r["changed"] == 1
    assert client.get(f"/api/doc/{did}/item/{line['id']}/style").json()["bold"] is True


@needs_ocr
def test_scanned_pdf(client):
    doc = upload(client, "attestation_scannee.pdf")
    did = doc["id"]
    assert doc["pages"][0]["mode"] == "image"
    ref = find(doc, "ST-4471")
    client.post(f"/api/doc/{did}/edit", json={"id": ref["id"], "text": ref["text"].replace("4471", "5582")})
    out = client.get(f"/api/doc/{did}/export?fmt=pdf_ocr").content
    assert "ST-5582" in pymupdf.open(stream=out)[0].get_text()


@needs_ocr
def test_scanner_flow(client):
    with open(os.path.join(SAMPLES, "photo_document.jpg"), "rb") as f:
        photo = f.read()
    det = client.post("/api/scan/detect", files={"file": ("p.jpg", photo)}).json()
    assert det["found"]
    expected = [[230 / 1500, 180 / 2000], [1290 / 1500, 250 / 2000], [1350 / 1500, 1820 / 2000], [140 / 1500, 1760 / 2000]]
    for (x, y), (ex, ey) in zip(det["corners"], expected):
        assert abs(x - ex) < 0.03 and abs(y - ey) < 0.03
    page = client.post("/api/scan/process", files={"file": ("p.jpg", photo)},
                       data={"corners": json.dumps(det["corners"]), "mode": "auto"})
    assert page.status_code == 200
    doc = client.post("/api/scan/finish", files=[("files", ("1.jpg", page.content, "image/jpeg"))] * 2).json()
    assert doc["kind"] == "scan" and len(doc["pages"]) == 2
    assert any("ATTESTATION" in it["text"] for it in doc["items"])
    zipped = client.get(f"/api/doc/{doc['id']}/export?fmt=jpg")
    assert zipped.headers["content-type"] == "application/zip"


def test_docx_keeps_formatting(client):
    from docx import Document

    doc = upload(client, "compte_rendu.docx")
    did = doc["id"]
    par = find(doc, "14 mars 2024")
    r = client.post(f"/api/doc/{did}/edit", json={"id": par["id"], "text": "Réunion du 21 mars 2025 à 19h00, salle municipale."}).json()
    assert "<b>21 mars 2025</b>" in r["items"][0]["html"]
    assert client.post(f"/api/doc/{did}/replace", json={"q": "2024", "r": "2025"}).json()["count"] == 2
    out = client.get(f"/api/doc/{did}/export?fmt=original").content
    d = Document(io.BytesIO(out))
    runs = [(r.text, r.bold) for r in d.paragraphs[1].runs]
    assert runs == [("Réunion du ", None), ("21 mars 2025", True), (" à 19h00, salle municipale.", None)]
    assert d.paragraphs[2].runs[1].font.color.rgb is not None  # couleur rouge conservée
    pdf = client.get(f"/api/doc/{did}/export?fmt=pdf")
    assert pdf.content[:4] == b"%PDF"


def test_xlsx_types(client):
    import openpyxl

    doc = upload(client, "budget.xlsx")
    did = doc["id"]
    for cell, text in [("x0-C2", "900,50"), ("x0-B3", "15/02/2025"), ("x0-D2", "55 %"), ("x0-A4", "Essence")]:
        assert client.post(f"/api/doc/{did}/edit", json={"id": cell, "text": text}).status_code == 200
    out = client.get(f"/api/doc/{did}/export?fmt=original").content
    ws = openpyxl.load_workbook(io.BytesIO(out))["Budget"]
    assert ws["C2"].value == 900.5 and ws["D2"].value == 0.55
    assert ws["B3"].value.year == 2025 and ws["A4"].value == "Essence"
    assert ws["C5"].value == "=SUM(C2:C4)"


def test_clear_errors(client):
    r = client.post("/api/upload", files={"file": ("vieux.doc", b"abc")})
    assert r.status_code == 400 and ".docx" in r.json()["detail"]
    r = client.post("/api/upload", files={"file": ("x.pdf", b"%PDF-1.4 abime")})
    assert "abîmé" in r.json()["detail"]
    assert client.get("/api/doc/0123456789abcdef").status_code == 404
