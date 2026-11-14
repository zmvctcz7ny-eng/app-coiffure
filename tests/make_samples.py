"""Génère des documents d'exemple pour tester DocEdit (PDF, PDF scanné, Word, Excel, images)."""
from __future__ import annotations

import datetime as dt
import os
import sys

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from docedit.fonts import font_path  # noqa: E402

OUT = os.path.join(ROOT, "tests", "samples")


def make_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page()  # A4
    page.insert_font(fontname="LS", fontfile=font_path("sans"))
    page.insert_font(fontname="LSB", fontfile=font_path("sans", True))
    page.insert_font(fontname="LT", fontfile=font_path("serif"))
    page.insert_text((50, 70), "FACTURE N° 2024-117", fontname="LSB", fontsize=20, color=(0.1, 0.2, 0.6))
    page.insert_text((50, 100), "Date : 12/03/2024", fontname="LS", fontsize=11)
    page.insert_text((50, 116), "Client : Société Dupont & Fils", fontname="LS", fontsize=11)
    page.insert_text((50, 132), "12 rue des Lilas, 75011 Paris", fontname="LT", fontsize=11)
    page.draw_rect(pymupdf.Rect(45, 160, 550, 180), color=None, fill=(0.85, 0.9, 1))
    page.insert_text((50, 174), "Désignation", fontname="LSB", fontsize=10)
    rows = [("Conseil en organisation", "1 250,00 €"), ("Formation (2 jours)", "980,00 €"),
            ("Frais de déplacement", "145,50 €")]
    y = 200
    f = pymupdf.Font(fontfile=font_path("sans"))
    fb = pymupdf.Font(fontfile=font_path("sans", True))
    page.insert_text((540 - fb.text_length("Montant", 10), 174), "Montant", fontname="LSB", fontsize=10)
    for label, amount in rows:
        page.insert_text((50, y), label, fontname="LS", fontsize=10)
        page.insert_text((540 - f.text_length(amount, 10), y), amount, fontname="LS", fontsize=10)
        y += 18
    total = "2 375,50 €"
    page.insert_text((380, y + 12), "Total TTC :", fontname="LSB", fontsize=11)
    page.insert_text((540 - fb.text_length(total, 11), y + 12), total, fontname="LSB", fontsize=11, color=(0.7, 0, 0))
    page.insert_text((50, 760), "Paiement à 30 jours. Merci de votre confiance.", fontname="helv", fontsize=9,
                     color=(0.4, 0.4, 0.4))
    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)


def document_image(width=1240, height=1754) -> Image.Image:
    """Page de document blanche avec du texte, à ~150 dpi."""
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    from PIL import ImageFont

    big = ImageFont.truetype(font_path("sans", True), 52)
    reg = ImageFont.truetype(font_path("sans"), 34)
    ser = ImageFont.truetype(font_path("serif"), 34)
    d.text((100, 120), "ATTESTATION DE STAGE", font=big, fill=(20, 40, 120))
    lines = [
        (reg, "Je soussigné, Paul Martin, directeur de l'entreprise,"),
        (reg, "atteste que Mme Claire Durand a effectué un stage"),
        (reg, "du 02/09/2024 au 15/11/2024 inclus."),
        (ser, "Montant de la gratification : 1 830,00 euros."),
        (reg, "Fait à Lyon, le 18 novembre 2024."),
    ]
    y = 280
    for font, text in lines:
        d.text((100, y), text, font=font, fill=(25, 25, 25))
        y += 70
    d.rectangle((100, 760, 1140, 900), fill=(235, 240, 250))
    d.text((130, 805), "Référence dossier : ST-4471", font=reg, fill=(25, 25, 25))
    return img


def make_scan_pdf(path):
    img = document_image()
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    import io

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(path)


def make_photo(path):
    """Simule la photo d'une feuille posée sur une table, en perspective, avec une ombre."""
    paper = np.asarray(document_image())
    H, W = 2000, 1500
    bg = np.zeros((H, W, 3), np.uint8)
    bg[:] = (90, 70, 55)  # table en bois
    noise = np.random.default_rng(1).normal(0, 6, (H, W, 1))
    bg = np.clip(bg + noise, 0, 255).astype(np.uint8)
    src = np.float32([[0, 0], [paper.shape[1], 0], [paper.shape[1], paper.shape[0]], [0, paper.shape[0]]])
    dst = np.float32([[230, 180], [1290, 250], [1350, 1820], [140, 1760]])
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(paper, m, (W, H))
    mask = cv2.warpPerspective(np.full(paper.shape[:2], 255, np.uint8), m, (W, H))
    out = bg.copy()
    out[mask > 0] = warped[mask > 0]
    # ombre douce sur la moitié gauche
    shade = np.linspace(0.78, 1.0, W)[None, :, None]
    out = np.clip(out * shade, 0, 255).astype(np.uint8)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    Image.fromarray(out).save(path, quality=90)


def make_png(path):
    document_image().save(path)


def make_docx(path):
    from docx import Document
    from docx.shared import Pt, RGBColor

    d = Document()
    d.sections[0].header.paragraphs[0].text = "Association Les Amis du Quartier"
    d.add_heading("Compte rendu de réunion", level=1)
    p = d.add_paragraph("Réunion du ")
    r = p.add_run("14 mars 2024")
    r.bold = True
    p.add_run(" à 18h30, salle municipale.")
    p2 = d.add_paragraph()
    r = p2.add_run("Budget voté : ")
    r2 = p2.add_run("4 500 €")
    r2.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    r2.font.size = Pt(14)
    p2.add_run(" pour l'année 2024.")
    d.add_paragraph("Présents : Marie, Ahmed, Lucie et Jean.")
    t = d.add_table(rows=3, cols=2)
    t.style = "Table Grid"
    for i, (a, b) in enumerate([("Poste", "Montant"), ("Fête de quartier", "2 000 €"), ("Jardin partagé", "2 500 €")]):
        t.cell(i, 0).text = a
        t.cell(i, 1).text = b
    d.add_paragraph("Prochaine réunion : 11 avril 2024.")
    d.save(path)


def make_xlsx(path):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["Poste", "Date", "Montant", "Part"])
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    ws.append(["Loyer", dt.datetime(2024, 1, 5), 850, 0.5])
    ws.append(["Courses", dt.datetime(2024, 1, 12), 420.75, 0.25])
    ws.append(["Transport", dt.datetime(2024, 1, 20), 75.5, 0.05])
    ws.append(["Total", None, "=SUM(C2:C4)", None])
    for r in range(2, 5):
        ws.cell(r, 2).number_format = "DD/MM/YYYY"
        ws.cell(r, 3).number_format = "#,##0.00"
        ws.cell(r, 4).number_format = "0%"
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 14
    ws2 = wb.create_sheet("Notes")
    ws2["A1"] = "Mise à jour le 02/02/2024"
    wb.save(path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make_pdf(os.path.join(OUT, "facture.pdf"))
    make_scan_pdf(os.path.join(OUT, "attestation_scannee.pdf"))
    make_photo(os.path.join(OUT, "photo_document.jpg"))
    make_png(os.path.join(OUT, "attestation.png"))
    make_docx(os.path.join(OUT, "compte_rendu.docx"))
    make_xlsx(os.path.join(OUT, "budget.xlsx"))
    print("Exemples créés dans", OUT)
