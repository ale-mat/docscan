"""Utilidades para manipulación de PDFs."""

from __future__ import annotations

import io
from typing import Dict, Iterable, List, Tuple

import img2pdf
from PIL import Image

try:
    import pikepdf
except Exception:  # pragma: no cover
    pikepdf = None  # type: ignore


_A4_MM: Tuple[float, float] = (210.0, 297.0)


def images_to_pdf_bytes(
    images: List[Image.Image],
    quality: int = 80,
    a4: bool = True,
    scanner: bool = False,
) -> bytes:
    """Convierte una lista de imágenes (PIL) en un PDF.

    - scanner=False: salida liviana tipo foto (JPEG) controlada por quality
    - scanner=True: salida tipo escáner real (1-bit + CCITT Group4) ideal para texto
    """
    if not images:
        return b""

    # Layout A4 (en puntos PDF)
    layout_fun = None
    if a4:
        a4_pt = (img2pdf.mm_to_pt(_A4_MM[0]), img2pdf.mm_to_pt(_A4_MM[1]))
        layout_fun = img2pdf.get_layout_fun(a4_pt)

    # IMPORTANT: algunas versiones de img2pdf fallan si layout_fun=None
    convert_kwargs = {}
    if layout_fun is not None:
        convert_kwargs["layout_fun"] = layout_fun

    if scanner:
        # --- NIVEL 2: CCITT Group4 ---
        tiff_pages: List[bytes] = []
        for im in images:
            im1 = im if im.mode == "1" else im.convert("L").convert("1")
            bio = io.BytesIO()
            im1.save(bio, format="TIFF", compression="group4")
            tiff_pages.append(bio.getvalue())
        return img2pdf.convert(tiff_pages, **convert_kwargs)

    # --- Modo normal (JPEG) ---
    jpeg_pages: List[bytes] = []
    q = max(1, min(95, int(quality)))

    for im in images:
        im_rgb = im.convert("RGB") if im.mode != "RGB" else im
        bio = io.BytesIO()

        # Mejor compresión sin pérdida visible típica:
        # - progressive=True suele bajar tamaño
        # - subsampling 4:2:0 reduce bastante (en docs suele ser imperceptible)
        try:
            im_rgb.save(
                bio,
                format="JPEG",
                quality=q,
                optimize=True,
                progressive=True,
                subsampling="4:2:0",
            )
        except TypeError:
            im_rgb.save(
                bio,
                format="JPEG",
                quality=q,
                optimize=True,
                progressive=True,
            )

        jpeg_pages.append(bio.getvalue())

    return img2pdf.convert(jpeg_pages, **convert_kwargs)


def optimize_pdf_lossless(pdf_bytes: bytes) -> bytes:
    """Optimiza un PDF de forma *lossless* cuando es posible.

    - Re-comprime streams
    - Genera object streams
    - Limpia estructura

    Si pikepdf no está disponible, devuelve el PDF tal cual.
    """
    if not pdf_bytes:
        return b""
    if pikepdf is None:
        return pdf_bytes

    out = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(pdf_bytes)) as pdf:
        pdf.save(
            out,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            linearize=False,
        )
    return out.getvalue()


def merge_pdfs_lossless(pdf_bytes_list: List[bytes]) -> bytes:
    """Une PDFs sin rasterizar (preserva texto/vectores).

    Si pikepdf no está disponible, lanza RuntimeError.
    """
    if not pdf_bytes_list:
        return b""
    if pikepdf is None:
        raise RuntimeError("pikepdf no está disponible para unir PDFs.")

    out = io.BytesIO()
    with pikepdf.Pdf.new() as dst:
        for b in pdf_bytes_list:
            with pikepdf.Pdf.open(io.BytesIO(b)) as src:
                dst.pages.extend(src.pages)
        dst.save(out)
    return out.getvalue()


def merge_and_optimize_pdfs_lossless(pdf_bytes_list: List[bytes]) -> bytes:
    merged = merge_pdfs_lossless(pdf_bytes_list)
    return optimize_pdf_lossless(merged)


def _single_image_to_pdf_page_bytes(img: Image.Image, a4: bool = True, quality: int = 80) -> bytes:
    """Convierte una única imagen a un PDF de 1 página."""
    return images_to_pdf_bytes([img], quality=quality, a4=a4, scanner=False)


def build_pdf_from_pages_lossless(
    pages: List[dict],
    a4: bool = True,
    quality_for_images: int = 75,
    optimize: bool = True,
) -> bytes:
    """Construye un PDF preservando páginas PDF como PDF y embebiendo imágenes como páginas.

    pages: lista de dicts con:
      - kind: "pdf" | "image"
      - pdf_bytes + page_index (para kind pdf)
      - image (PIL.Image) (para kind image)
      - rotate: int (grados, múltiplos de 90) opcional

    Requiere pikepdf.
    """
    if not pages:
        return b""
    if pikepdf is None:
        raise RuntimeError("pikepdf no está disponible para construir el PDF sin rasterizar.")

    # Abrimos PDFs fuente una sola vez por contenido (bytes) para evitar re-trabajo.
    pdf_cache: Dict[int, pikepdf.Pdf] = {}
    opened: List[pikepdf.Pdf] = []

    def _open_pdf_cached(b: bytes) -> "pikepdf.Pdf":
        key = hash(b)
        pdf = pdf_cache.get(key)
        if pdf is None:
            pdf = pikepdf.Pdf.open(io.BytesIO(b))
            pdf_cache[key] = pdf
            opened.append(pdf)
        return pdf

    try:
        out = io.BytesIO()
        with pikepdf.Pdf.new() as dst:
            for p in pages:
                kind = p.get("kind")
                rotate = int(p.get("rotate", 0)) % 360

                if kind == "pdf":
                    src = _open_pdf_cached(p["pdf_bytes"])
                    src_page = src.pages[int(p["page_index"])]
                    dst.pages.append(src_page)
                    if rotate:
                        cur = int(dst.pages[-1].get("/Rotate", 0))
                        dst.pages[-1]["/Rotate"] = (cur + rotate) % 360

                elif kind == "image":
                    img: Image.Image = p["image"]
                    if rotate:
                        img = img.rotate(-rotate, expand=True, fillcolor=(255, 255, 255))
                    one_pdf = _single_image_to_pdf_page_bytes(img, a4=a4, quality=quality_for_images)
                    with pikepdf.Pdf.open(io.BytesIO(one_pdf)) as img_pdf:
                        dst.pages.extend(img_pdf.pages)
                else:
                    raise ValueError(f"Página desconocida: {kind}")

            dst.save(out)

        result = out.getvalue()
        return optimize_pdf_lossless(result) if optimize else result
    finally:
        for pdf in opened:
            try:
                pdf.close()
            except Exception:
                pass
