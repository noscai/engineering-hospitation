from pathlib import Path

from src.pdf_vision_extractor import pdf_seiten_als_bilder


ROOT = Path(__file__).resolve().parents[1]


def test_pdf_seiten_als_bilder_rendert_scan_pdf_als_data_url():
    raw = (ROOT / 'data/synthetisch/SYN-004/befund_scan.pdf').read_bytes()
    pages = pdf_seiten_als_bilder(raw, dpi=72)
    assert pages
    assert pages[0]['seite'] == 1
    assert str(pages[0]['data_url']).startswith('data:image/png;base64,')
