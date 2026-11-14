"""Génère les icônes de l'application (PWA)."""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "icons")


def icon(size: int, maskable: bool = False) -> Image.Image:
    s = size * 4  # dessin en grand puis réduction (anticrénelage)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top, bot = (37, 99, 235), (29, 78, 216)
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / s
        gd.line([(0, y), (s, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
    mask = Image.new("L", (s, s), 0)
    if maskable:
        ImageDraw.Draw(mask).rectangle((0, 0, s, s), fill=255)
    else:
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)
    k = 0.72 if maskable else 1.0  # zone de sécurité des icônes « maskable »
    c = s / 2

    def P(x, y):
        return (c + (x - 0.5) * s * k, c + (y - 0.5) * s * k)

    # feuille
    x0, y0 = P(0.26, 0.17)
    x1, y1 = P(0.70, 0.83)
    fold = s * k * 0.12
    d.polygon([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)], fill=(255, 255, 255, 255))
    d.polygon([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], fill=(191, 219, 254, 255))
    # lignes de texte
    for i, w in enumerate((0.30, 0.34, 0.22, 0.30)):
        lx0, ly = P(0.33, 0.36 + i * 0.1)
        lx1, _ = P(0.33 + w, 0)
        d.rounded_rectangle((lx0, ly, lx1, ly + s * k * 0.035), radius=int(s * k * 0.017), fill=(148, 163, 184, 255))
    # crayon
    pen = [P(0.50, 0.80), P(0.80, 0.50), P(0.88, 0.58), P(0.58, 0.88)]
    d.polygon(pen, fill=(250, 204, 21, 255))
    tip = [P(0.50, 0.80), P(0.58, 0.88), P(0.46, 0.92)]
    d.polygon(tip, fill=(30, 41, 59, 255))
    cap = [P(0.80, 0.50), P(0.84, 0.46), P(0.92, 0.54), P(0.88, 0.58)]
    d.polygon(cap, fill=(244, 114, 182, 255))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    icon(192).save(os.path.join(OUT, "icon-192.png"))
    icon(512).save(os.path.join(OUT, "icon-512.png"))
    icon(512, maskable=True).save(os.path.join(OUT, "icon-maskable-512.png"))
    full = icon(180, maskable=True).convert("RGB")
    full.save(os.path.join(OUT, "apple-touch-icon.png"))
    print("Icônes créées dans", OUT)
