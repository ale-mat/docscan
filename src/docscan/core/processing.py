"""Procesamiento de imágenes (deskew, binarización, realce)."""

from __future__ import annotations

import numpy as np
import cv2
from PIL import Image, ImageFilter

from ..config import MAX_WIDTH


def deskew_image(pil_img: Image.Image, max_angle: float = 5.0) -> Image.Image:
    """Corrige inclinación leve usando HoughLines."""
    arr = np.array(pil_img.convert("L"))
    edges = cv2.Canny(arr, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)

    angle = 0.0
    if lines is not None:
        angles = [np.degrees(theta) for rho, theta in lines[:, 0]]
        median_angle = float(np.median(angles))
        if abs(median_angle) <= max_angle:
            angle = median_angle

    if abs(angle) > 0.1:
        pil_img = pil_img.rotate(
            -angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)
        )
    return pil_img


def enhance_scan(
    pil_img: Image.Image,
    binarize: bool = False,
    max_width: int | None = None,
) -> Image.Image:
    """Aplica ajustes de 'escaneo': resize, deskew, contraste, nitidez.

    max_width:
      - Si se pasa, limita el ancho máximo (en pixeles).
      - Si es None, usa el MAX_WIDTH global.
    """
    limit = int(max_width) if max_width else int(MAX_WIDTH)

    w, h = pil_img.size
    if w > limit:
        ratio = limit / float(w)
        pil_img = pil_img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    pil_img = deskew_image(pil_img)

    if binarize:
        gray = np.array(pil_img.convert("L"))
        bw = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            15,
        )
        pil_img = Image.fromarray(bw).convert("RGB")
    else:
        arr = np.array(pil_img.convert("RGB"))
        lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        lab = cv2.merge((cl, a, b))
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        pil_img = Image.fromarray(enhanced)
        pil_img = pil_img.filter(
            ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3)
        )

    return pil_img
