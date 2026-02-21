# 🖨️ DocScan Suite

Suite en Python para simular un escaneo digital:
- Convierte documentos (PDF, imágenes, DOCX/ODT) a PDF normalizado.
- Optimiza páginas: deskew, binarización, contraste.
- Normaliza a formato A4.
- Permite unión de múltiples archivos.
- OCR opcional para texto buscable.
- Interfaces: CLI y Streamlit.

## Estructura
- `src/docscan/core/` → lógica principal de procesamiento.
- `src/docscan/utils/` → utilidades de IO, OCR y PDF.
- `src/docscan/cli.py` → uso por línea de comandos.
- `src/docscan/ui_streamlit.py` → interfaz gráfica web.

## Instalación
```bash
pip install -r requirements.txt
