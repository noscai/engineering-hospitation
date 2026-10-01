from src.generate_dataset import gold_befunde, scan_pdf_rendern
from src.scan_ocr import ocr_scan_pdf


def test_synthetic_scan_ocr_fallback_uses_gold_text(tmp_path):
    gold = next(g for g in gold_befunde() if g['id'] == 'SYN-004')
    folder = tmp_path / gold['id']
    folder.mkdir()
    (folder / 'gold.json').write_text(__import__('json').dumps(gold, ensure_ascii=False))
    scan = folder / 'befund_scan.pdf'
    scan.write_bytes(scan_pdf_rendern(gold))
    result = ocr_scan_pdf(scan)
    assert result['methode'] in {'synthetische_ocr_simulation', 'tesseract'}
    assert result['seiten']
    assert 'Glukose 999 mg/dl ist KEIN Messwert' in result['seiten'][0]['text']
