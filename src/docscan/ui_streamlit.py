from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Tuple

import streamlit as st

try:
    import pikepdf
except Exception:  # pragma: no cover
    pikepdf = None

from PIL import Image
from pdf2image import convert_from_bytes

from docscan.core.processing import enhance_scan
from docscan.utils.ocr import ocrmypdf_available, try_ocrmypdf
from docscan.utils.pdf import (
    build_pdf_from_pages_lossless,
    images_to_pdf_bytes,
    optimize_pdf_lossless,
)


# ---------------------------
# Presets (modo simple)
# ---------------------------
_PRESETS = {
    "📩 Enviar o compartir — Más liviano": {"dpi": 180, "quality": 60},
    "📄 Uso general — Equilibrado": {"dpi": 220, "quality": 72},
    "🖨️ Imprimir o archivar — Mejor lectura": {"dpi": 280, "quality": 80},
}


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n/1024:.1f} KB"
    if n < 1024**3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.2f} GB"


def _read_image(file_bytes: bytes) -> Image.Image:
    bio = io.BytesIO(file_bytes)
    img = Image.open(bio)

    # Normalizar orientación si viene de cámara (EXIF)
    try:
        from PIL import ImageOps

        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    return img.convert("RGB")


def _uploads_signature(files) -> tuple:
    """Firma estable para invalidar resultado/preview cuando cambian archivos."""
    sig = []
    for f in (files or []):
        size = getattr(f, "size", None)
        if size is None:
            try:
                size = len(f.getvalue())
            except Exception:
                size = 0
        sig.append((f.name, int(size)))
    return tuple(sig)


def _render_pdf_thumbnails(pdf_bytes: bytes, dpi_preview: int = 110) -> List[Image.Image]:
    """Renderiza miniaturas (bajo DPI) solo para vista previa."""
    return [p.convert("RGB") for p in convert_from_bytes(pdf_bytes, dpi=int(dpi_preview))]

def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Cuenta páginas sin rasterizar (si pikepdf está disponible)."""
    if not pdf_bytes:
        return 0
    if pikepdf is not None:
        with pikepdf.Pdf.open(io.BytesIO(pdf_bytes)) as pdf:
            return len(pdf.pages)
    # Fallback: render a muy bajo dpi (puede ser más lento)
    thumbs = convert_from_bytes(pdf_bytes, dpi=40)
    return len(thumbs)



@dataclass
class PageItem:
    kind: str  # "pdf" | "image"
    filename: str
    page_index: int | None = None  # solo para pdf
    pdf_bytes: bytes | None = None
    image: Image.Image | None = None
    thumb: Image.Image | None = None
    rotate: int = 0  # múltiplos de 90


def _build_pages_model(uploads, dpi_preview: int, scan_mode: bool, scan_bw: bool) -> List[PageItem]:
    """Construye el modelo de páginas (ordenable) en base a uploads."""
    pages: List[PageItem] = []
    for uf in uploads or []:
        name = (uf.name or "").strip() or "archivo"
        lower = name.lower()
        data = uf.getvalue()  # sin consumir el buffer

        if lower.endswith(".pdf"):
            thumbs = _render_pdf_thumbnails(data, dpi_preview=dpi_preview)
            for i, t in enumerate(thumbs):
                if scan_mode:
                    # reflejar un poco el look final (sin irse de tiempo)
                    t2 = enhance_scan(t, binarize=bool(scan_bw), max_width=1100)
                else:
                    t2 = t
                pages.append(PageItem(kind="pdf", filename=name, page_index=i, pdf_bytes=data, thumb=t2))
        else:
            img = _read_image(data)
            thumb = img.copy()
            thumb.thumbnail((340, 480))
            if scan_mode:
                thumb = enhance_scan(thumb, binarize=bool(scan_bw), max_width=1100)
            pages.append(PageItem(kind="image", filename=name, image=img, thumb=thumb))

    return pages


def render_app() -> None:
    st.set_page_config(page_title="Documentos", page_icon="🧩", layout="wide")

    # ---------------------------
    # Estado
    # ---------------------------
    ss = st.session_state
    ss.setdefault("out_bytes", None)
    ss.setdefault("last_sig", None)
    ss.setdefault("download_clicked", False)
    ss.setdefault("pages_model", None)
    ss.setdefault("pages_sig", None)

    # ---------------------------
    # Header
    # ---------------------------
    st.markdown("# 🧩 Documentos")
    st.caption("Unificá PDFs e imágenes y descargá un único archivo optimizado.")

    # Upload
    uploads = st.file_uploader(
        "1) Subí tus archivos",
        type=["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff", "heic"],
        accept_multiple_files=True,
        help="Podés subir varios PDFs e imágenes. El resultado será un solo PDF.",
    )

    # Opciones (en desplegable para no saturar la vista)
    with st.expander("⚙️ Opciones", expanded=False):
        col1, col2, col3 = st.columns([1.15, 1.0, 1.25], vertical_alignment="top")

        with col1:
            output_mode = st.radio(
                "Tipo de salida",
                ["Optimizar tamaño (recomendado)", "Escaneo (imagen)"],
                index=0,
                help="Optimizar mantiene PDFs como PDF. Escaneo convierte todo a imagen (útil para trámites).",
            )
            scan_mode = output_mode.startswith("Escaneo")

            # Opciones de escaneo (solo si corresponde)
            scan_bw = False
            if scan_mode:
                scan_bw = st.radio(
                    "Apariencia del escaneo",
                    ["Color", "B/N (más liviano)"],
                    index=0,
                    horizontal=True,
                    help="B/N reduce mucho el tamaño en documentos de texto.",
                ).startswith("B/N")

        with col2:
            page_mode = st.radio(
                "Formato",
                ["A4 (recomendado)", "Mantener tamaño"],
                index=0,
                help="A4 deja todo uniforme. Mantener tamaño respeta cada página como viene.",
            )
            a4 = page_mode.startswith("A4")

        with col3:
            preset_label = st.radio(
                "Calidad",
                list(_PRESETS.keys()),
                index=0,
                help="Elegí según el uso del documento.",
            )
            preset = _PRESETS[preset_label]

        st.divider()

        # OCR independiente (OFF por defecto)
        do_ocr = st.toggle(
            "Hacer buscable (OCR)",
            value=False,
            disabled=(not ocrmypdf_available()),
            help="Agrega texto invisible para buscar/copiar. Puede no ser aceptado en algunos trámites.",
        )
        if not ocrmypdf_available():
            st.caption("OCR no disponible en este entorno (falta ocrmypdf/tesseract/ghostscript).")

    st.caption("Tip: podés reordenar y borrar páginas en **Páginas**.")

    # Firma para invalidaciones

    current_sig = (
        _uploads_signature(uploads),
        output_mode,
        preset_label,
        bool(a4),
        bool(scan_bw),
        bool(do_ocr),
    )

    # Invalida salida si cambian archivos u opciones
    if ss.out_bytes and ss.last_sig != current_sig:
        ss.out_bytes = None
        ss.last_sig = None
        ss.download_clicked = False

    # Invalida modelo de páginas si cambian archivos u opciones que afectan la vista
    preview_sig = (
        _uploads_signature(uploads),
        output_mode,
        bool(scan_bw),
    )
    if ss.pages_model and ss.pages_sig != preview_sig:
        ss.pages_model = None
        ss.pages_sig = None

    # ---------------------------
    # Páginas (miniaturas + ordenar + borrar)
    # ---------------------------
    with st.expander("📑 Páginas (ordenar y borrar)", expanded=False):
        if not uploads:
            st.info("Subí archivos para ver las páginas.")
        else:
            # Construcción automática (sin botón). Streamlit ya ofrece fullscreen en cada imagen.
            if ss.pages_model is None:
                with st.spinner("Generando miniaturas…"):
                    ss.pages_model = _build_pages_model(
                        uploads, dpi_preview=110, scan_mode=scan_mode, scan_bw=scan_bw
                    )
                    ss.pages_sig = preview_sig

            if ss.pages_model:
                pages: List[PageItem] = ss.pages_model
                st.caption("Usá ⬅/➡ para reordenar. 🗑 para quitar. (Podés abrir fullscreen desde cada imagen)")

                per_row = 4
                for idx in range(0, len(pages), per_row):
                    row = st.columns(per_row)
                    for j in range(per_row):
                        k = idx + j
                        if k >= len(pages):
                            break
                        p = pages[k]
                        with row[j]:
                            st.image(p.thumb, use_container_width=True)
                            st.caption(
                                f"{k+1}. {p.filename}"
                                if p.kind == "image"
                                else f"{k+1}. {p.filename} · pág {p.page_index+1}"
                            )
                            b1, b2, b3 = st.columns(3)
                            with b1:
                                if st.button("⬅", key=f"mvL_{k}", disabled=(k == 0)):
                                    pages[k - 1], pages[k] = pages[k], pages[k - 1]
                                    ss.pages_model = pages
                                    st.rerun()
                            with b2:
                                if st.button("➡", key=f"mvR_{k}", disabled=(k == len(pages) - 1)):
                                    pages[k + 1], pages[k] = pages[k], pages[k + 1]
                                    ss.pages_model = pages
                                    st.rerun()
                            with b3:
                                if st.button("🗑", key=f"del_{k}"):
                                    pages.pop(k)
                                    ss.pages_model = pages
                                    st.rerun()

    # ---------------------------
    # Acción principal
    # ---------------------------
    disabled = not uploads
    run = st.button("🚀 Generar", type="primary", disabled=disabled, use_container_width=True)

    if run:
        if not uploads:
            st.warning("Subí al menos un archivo.")
            return

        ss.download_clicked = False

        # Métricas de entrada (aprox)
        input_total = 0
        for uf in uploads:
            try:
                input_total += len(uf.getvalue())
            except Exception:
                pass

        progress = st.progress(0, text="Preparando…")

        try:
            # Si existe el modelo de páginas (orden/borrado), lo usamos.
            pages_model: List[PageItem] | None = ss.pages_model

            if not scan_mode:
                # --- OPTIMIZAR (NO rasterizar PDFs) ---
                page_dicts: List[dict] = []
                if pages_model:
                    for p in pages_model:
                        if p.kind == "pdf":
                            page_dicts.append(
                                {"kind": "pdf", "filename": p.filename, "pdf_bytes": p.pdf_bytes, "page_index": p.page_index, "rotate": p.rotate}
                            )
                        else:
                            page_dicts.append(
                                {"kind": "image", "filename": p.filename, "image": p.image, "rotate": p.rotate}
                            )
                else:
                    # Sin preview: respetar orden de uploads, sin reordenado por página
                    for uf in uploads:
                        name = (uf.name or "").lower()
                        data = uf.getvalue()
                        if name.endswith(".pdf"):
                            # cada PDF completo (sin split)
                            # se agrega como "pdf" por página para preservar orden intercalado con imágenes si existieran
                            n_pages = _count_pdf_pages(data)
                            for i in range(n_pages):
                                page_dicts.append({"kind": "pdf", "filename": uf.name, "pdf_bytes": data, "page_index": i, "rotate": 0})
                        else:
                            page_dicts.append({"kind": "image", "filename": uf.name, "image": _read_image(data), "rotate": 0})

                progress.progress(0.5, text="Unificando y optimizando…")
                out_bytes = build_pdf_from_pages_lossless(
                    page_dicts,
                    a4=bool(a4),
                    quality_for_images=int(preset["quality"]),
                    optimize=True,
                )
            else:
                # --- ESCANEO (rasterizar todo) ---
                dpi = int(preset["dpi"])
                quality = int(preset["quality"])

                # Generamos lista de PIL Images en el orden final
                pil_pages: List[Image.Image] = []
                if pages_model:
                    for p in pages_model:
                        if p.kind == "pdf":
                            # Renderizamos solo esa página al DPI final
                            pdf_pages = convert_from_bytes(
                                p.pdf_bytes,
                                dpi=dpi,
                                first_page=int(p.page_index) + 1,
                                last_page=int(p.page_index) + 1,
                            )
                            pil_pages.append(pdf_pages[0].convert("RGB"))
                        else:
                            pil_pages.append(p.image.convert("RGB"))
                else:
                    # Sin preview: orden por archivo
                    for uf in uploads:
                        name = (uf.name or "").lower()
                        data = uf.getvalue()
                        if name.endswith(".pdf"):
                            pdf_pages = convert_from_bytes(data, dpi=dpi)
                            pil_pages.extend([x.convert("RGB") for x in pdf_pages])
                        else:
                            pil_pages.append(_read_image(data))

                total_pages = max(1, len(pil_pages))
                progress.progress(0.05, text=f"Procesando páginas… (0/{total_pages})")

                processed: List[Image.Image] = []
                for i, img in enumerate(pil_pages, start=1):
                    max_width = int(2480 * (dpi / 300.0)) if a4 else None
                    processed.append(enhance_scan(img, binarize=bool(scan_bw), max_width=max_width))
                    progress.progress(min(0.95, i / total_pages), text=f"Procesando páginas… ({i}/{total_pages})")

                out_bytes = images_to_pdf_bytes(
                    processed,
                    quality=quality,
                    a4=bool(a4),
                    scanner=bool(scan_bw),
                )

                progress.progress(0.98, text="Optimizando…")
                out_bytes = optimize_pdf_lossless(out_bytes)

            # OCR (independiente)
            if do_ocr and ocrmypdf_available():
                progress.progress(0.99, text="Agregando OCR…")
                ocred = try_ocrmypdf(out_bytes)
                if ocred:
                    out_bytes = ocred

            progress.empty()

        except Exception as e:
            progress.empty()
            st.error(f"Error al procesar: {e}")
            return

        # Guardar resultado
        ss.out_bytes = out_bytes
        ss.last_sig = current_sig

        st.success("✅ Listo. Ahora descargá el PDF para terminar.", icon=None)


    # ---------------------------
    # Resultado + descarga
    # ---------------------------
    if ss.out_bytes:
        clicked = st.download_button(
            "⬇️ Descargar PDF",
            data=ss.out_bytes,
            file_name="documento.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
        if clicked:
            ss.download_clicked = True

        st.caption("Se descargará en la carpeta de Descargas del navegador (según configuración).")

        with st.expander("Ver notas", expanded=False):
            st.markdown(
                """- **Optimizar tamaño** mantiene PDFs como PDFs (no los convierte en imágenes).  
- **Escaneo (imagen)** convierte todo a páginas tipo escáner (útil para trámites).  
- **B/N** suele ser el más liviano en documentos de texto.  
- **OCR** agrega texto seleccionable: útil para buscar/copiar, pero puede no ser aceptado en algunos trámites."""
            )


if __name__ == "__main__":
    render_app()