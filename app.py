import sys
from pathlib import Path

# Permite importar el paquete en layout 'src/' sin instalarlo como wheel.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from docscan.ui_streamlit import render_app

render_app()
