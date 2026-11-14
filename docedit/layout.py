"""Calculs de mise en page communs (PDF et images) : alignement, place disponible, réduction."""
from __future__ import annotations

MIN_SHRINK = 0.7  # on réduit au plus à 70 % de la taille d'origine


def _same_row(a, b) -> bool:
    top, bottom = max(a[1], b[1]), min(a[3], b[3])
    overlap = bottom - top
    return overlap > 0.5 * min(a[3] - a[1], b[3] - b[1])


def detect_alignment(item: dict, items: list[dict]) -> str:
    """Devine si le texte est aligné à gauche, à droite ou centré, à partir des voisins en colonne."""
    x0, y0, x1, y1 = item["bbox"]
    h = max(1.0, y1 - y0)
    tol = max(1.0, h * 0.15)
    left = right = center = 0
    cx = (x0 + x1) / 2
    for other in items:
        if other is item or other.get("page") != item.get("page"):
            continue
        ox0, oy0, ox1, oy1 = other["bbox"]
        if abs(oy0 - y0) < h * 0.5:  # même ligne : pas un voisin de colonne
            continue
        if abs(oy0 - y0) > h * 15:
            continue
        same_l = abs(ox0 - x0) < tol
        same_r = abs(ox1 - x1) < tol
        same_c = abs((ox0 + ox1) / 2 - cx) < tol
        if same_l and same_r:
            continue
        left += same_l
        right += same_r
        center += same_c and not same_l and not same_r
    if right > 0 and right > left and right >= center:
        return "right"
    if center > 1 and center > left and center > right:
        return "center"
    return "left"


def free_space(item: dict, items: list[dict], page_w: float, margin: float) -> tuple[float, float]:
    """Limites gauche/droite utilisables sur la même ligne sans toucher les voisins."""
    x0, y0, x1, y1 = item["bbox"]
    h = max(1.0, y1 - y0)
    gap = h * 0.4
    lim_l, lim_r = min(x0, margin), max(x1, page_w - margin)
    for other in items:
        if other is item or other.get("page") != item.get("page"):
            continue
        ob = other["bbox"]
        if not _same_row(item["bbox"], ob):
            continue
        if ob[0] >= x1 - 0.5:
            lim_r = min(lim_r, ob[0] - gap)
        elif ob[2] <= x0 + 0.5:
            lim_l = max(lim_l, ob[2] + gap)
    return min(lim_l, x0), max(lim_r, x1)


def place(item: dict, items: list[dict], page_w: float, margin: float, size: float, width_at, ) -> tuple[float, float, str]:
    """Retourne (taille, x_gauche, alignement) pour le nouveau texte.

    width_at(taille) donne la largeur du texte pour une taille.
    """
    x0, _, x1, _ = item["bbox"]
    align = item.get("align") or detect_alignment(item, items)
    lim_l, lim_r = free_space(item, items, page_w, margin)
    if align == "right":
        avail = x1 - lim_l
    elif align == "center":
        cx = (x0 + x1) / 2
        avail = 2 * min(cx - lim_l, lim_r - cx)
    else:
        avail = lim_r - x0
    avail = max(avail, x1 - x0)
    w = width_at(size)
    if w > avail and w > 0:
        size = max(size * avail / w * 0.995, size * MIN_SHRINK)
        w = width_at(size)
    if align == "right":
        left = x1 - w
    elif align == "center":
        left = (x0 + x1) / 2 - w / 2
    else:
        left = x0
    return size, left, align
