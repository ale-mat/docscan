from PIL import Image
from src.docscan.core.processing import enhance_scan

def test_enhance_scan_runs():
    img = Image.new("RGB", (800, 600), "white")
    out = enhance_scan(img, binarize=False)
    assert out.size[0] <= 2480
