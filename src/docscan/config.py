"""Configuración global del proyecto.

Notas:
- En Linux/Mac (p.ej. Streamlit Cloud) poppler suele estar en PATH.
- En Windows, podés instalar Poppler y setear DOCSCAN_POPPLER_PATH.
"""

from __future__ import annotations
import os

DEFAULT_DPI: int = 250

# ~A4 @ 300dpi (se usa como límite para imágenes muy grandes; se recalcula en runtime cuando aplica)
MAX_WIDTH: int = 2480

# Calidad JPEG por defecto (modo "Balanceado")
JPEG_QUALITY: int = 80

# Poppler (para pdf2image). En Linux/Mac normalmente no hace falta.
POPPLER_PATH = os.getenv("DOCSCAN_POPPLER_PATH") or None
