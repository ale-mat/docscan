"""Funciones de entrada/salida de archivos."""

import shutil
import tempfile
from pathlib import Path

def unique_path(path: Path) -> Path:
    """
    Genera un Path único (archivo.pdf, archivo (1).pdf, ...).
    """
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        new_path = path.with_name(f"{stem} ({i}){suffix}")
        if not new_path.exists():
            return new_path
        i += 1

def temp_dir():
    """Crea un directorio temporal y lo devuelve."""
    return Path(tempfile.mkdtemp())
