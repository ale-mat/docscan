"""CLI para usar DocScan desde la terminal."""

import argparse
from .core.pipeline import file_to_scanned_pdf

def main():
    p = argparse.ArgumentParser(description="Simula un escaneo: archivo -> PDF imagen")
    p.add_argument("input", help="Archivo de entrada")
    p.add_argument("-o", "--output", help="Archivo PDF de salida")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--binarize", action="store_true", help="Forzar blanco/negro (binarización adaptativa)")
    args = p.parse_args()

    out, info = file_to_scanned_pdf(args.input, out_pdf=args.output, dpi=args.dpi, binarize=args.binarize)
    print("✅ PDF generado:", out, info)

if __name__ == "__main__":
    main()
