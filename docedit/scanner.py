"""Scanner : détection des bords de la feuille, recadrage, redressement et amélioration (OpenCV)."""
from __future__ import annotations

import cv2
import numpy as np


def _order(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def _candidates(gray: np.ndarray):
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    med = float(np.median(blur))
    yield cv2.dilate(cv2.Canny(blur, max(10, 0.66 * med * 0.5), min(255, 1.33 * med)), np.ones((3, 3), np.uint8), iterations=2)
    yield cv2.dilate(cv2.Canny(blur, 30, 100), np.ones((5, 5), np.uint8), iterations=1)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


def detect_corners(img_rgb: np.ndarray) -> tuple[list[list[float]], bool]:
    """Renvoie 4 coins normalisés (0..1) dans l'ordre haut-gauche, haut-droite, bas-droite, bas-gauche."""
    h, w = img_rgb.shape[:2]
    scale = 600.0 / max(h, w)
    small = cv2.resize(img_rgb, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    area_img = sh * sw
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    best, best_area = None, 0.0
    for channel in (gray, 255 - hsv[..., 1]):
        for edges in _candidates(channel):
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for c in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) != 4:
                    hull = cv2.convexHull(c)
                    approx = cv2.approxPolyDP(hull, 0.03 * cv2.arcLength(hull, True), True)
                if len(approx) != 4 or not cv2.isContourConvex(approx):
                    continue
                area = cv2.contourArea(approx)
                if area < 0.18 * area_img or area > 0.985 * area_img:
                    continue
                if area > best_area:
                    best, best_area = approx, area
        if best is not None:
            break
    if best is None:
        m = 0.03
        return [[m, m], [1 - m, m], [1 - m, 1 - m], [m, 1 - m]], False
    pts = _order(best)
    # on rentre légèrement les coins : le contour détecté inclut souvent l'ombre du bord de la feuille
    center = pts.mean(axis=0)
    pts = pts + (center - pts) * 0.012
    return [[float(x / sw), float(y / sh)] for x, y in pts], True


def warp(img_rgb: np.ndarray, corners_norm: list[list[float]]) -> np.ndarray:
    h, w = img_rgb.shape[:2]
    pts = _order(np.array([[x * w, y * h] for x, y in corners_norm], np.float32))
    tl, tr, br, bl = pts
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    width, height = max(width, 50), max(height, 50)
    # Résolution confortable pour l'OCR (env. 200 dpi pour un A4)
    target = 2300
    if max(width, height) < target:
        k = min(2.0, target / max(width, height))
        width, height = int(width * k), int(height * k)
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    m = cv2.getPerspectiveTransform(pts, dst)
    return cv2.warpPerspective(img_rgb, m, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _normalize_light(channel: np.ndarray) -> np.ndarray:
    """Supprime les ombres et le voile : divise par une estimation (à grande échelle) de l'éclairage du papier."""
    h, w = channel.shape[:2]
    k = 320.0 / max(h, w)
    small = cv2.resize(channel, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    size = max(9, (min(small.shape[:2]) // 5) | 1)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    bg = cv2.GaussianBlur(bg, (0, 0), size / 2)
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_CUBIC)
    bg = np.maximum(bg, 1)
    return cv2.divide(channel, bg, scale=245)


def enhance(img_rgb: np.ndarray, mode: str = "auto") -> np.ndarray:
    if mode == "original":
        return img_rgb
    if mode == "bw":
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        norm = _normalize_light(gray)
        bw = cv2.adaptiveThreshold(norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12)
        bw = cv2.medianBlur(bw, 3)
        return cv2.cvtColor(bw, cv2.COLOR_GRAY2RGB)
    if mode == "gray":
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        norm = _normalize_light(gray)
        norm = cv2.normalize(norm, None, 0, 255, cv2.NORM_MINMAX)
        return cv2.cvtColor(norm, cv2.COLOR_GRAY2RGB)
    # « auto » : couleur conservée, fond blanchi, ombres retirées, contraste renforcé
    chans = [_normalize_light(img_rgb[..., i]) for i in range(3)]
    out = cv2.merge(chans).astype(np.float32)
    # niveaux : point noir à 25, point blanc à 238 (le papier devient blanc, les couleurs claires restent)
    out = (out - 25.0) * (255.0 / (238.0 - 25.0))
    return np.clip(out, 0, 255).astype(np.uint8)
