"""Pipeline principal: entrada → procesamiento → salida."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, List
import tempfile, shutil

from pdf2image import convert_from_path
from PIL import Image

from ..config import DEFAULT_DPI, POPPLER_PATH, JPEG_QUALITY
from .processing import enhance_scan
from ..utils.pdf import images_to_pdf_bytes


def pdf_to_processed_images(
    pdf_path: Path, dpi: int = DEFAULT_DPI, binarize: bool = False
) -> List[Image.Image]:
    pages = convert_from_path(str(pdf_path), dpi=int(dpi), poppler_path=POPPLER_PATH)
    # Las páginas renderizadas ya vienen en tamaño acorde al DPI; sólo aplicamos realce.
    return [enhance_scan(p, binarize=binarize) for p in pages]


def file_to_scanned_pdf(
    input_file: str,
    out_pdf: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    binarize: bool = False,
    quality: int = JPEG_QUALITY,
    a4: bool = True,
) -> Tuple[str, dict]:
    """Procesa un archivo PDF y genera un PDF 'escaneado'.

    Nota: el modo multi-archivo se implementa desde la UI simple (Streamlit).
    """
    inp = Path(input_file)
    tmpdir = Path(tempfile.mkdtemp())
    try:
        pdf = inp
        pages = pdf_to_processed_images(pdf, dpi=dpi, binarize=binarize)
        pdf_bytes = images_to_pdf_bytes(pages, quality=quality, a4=a4)
        out = Path(out_pdf) if out_pdf else inp.with_name(inp.stem + "_scanned.pdf")
        out.write_bytes(pdf_bytes)
        return str(out), {"pages": len(pages)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
