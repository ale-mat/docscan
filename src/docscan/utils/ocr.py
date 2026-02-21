"""Módulo para OCR (ocrmypdf o pytesseract)."""

import shutil
import tempfile
from pathlib import Path
from typing import List, Optional
from PIL import Image

def ocrmypdf_available() -> bool:
    return shutil.which("ocrmypdf") is not None

def try_ocrmypdf(input_pdf_bytes: bytes) -> Optional[bytes]:
    """Si hay ocrmypdf instalado, intenta aplicar OCR a un PDF."""
    if not ocrmypdf_available():
        return None
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "in.pdf"
        out_path = Path(td) / "out.pdf"
        in_path.write_bytes(input_pdf_bytes)
        cmd = ["ocrmypdf", "--skip-text", str(in_path), str(out_path)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and out_path.exists():
            return out_path.read_bytes()
    return None

def try_pytesseract_text(pages: List[Image.Image], lang: str = "spa+eng") -> str:
    """Extrae texto plano con pytesseract (fallback)."""
    try:
        import pytesseract
    except ImportError:
        return ""
    out = []
    for i, img in enumerate(pages, 1):
        txt = pytesseract.image_to_string(img, lang=lang)
        out.append(f"--- Página {i} ---\n{txt.strip()}\n")
    return "\n".join(out)
