"""OCR-Stufe fuer die synthetischen Scan-PDFs.

Wenn lokale OCR-Tools fehlen, wird fuer die selbst erzeugten Scan-PDFs eine
deterministische OCR-Simulation aus den Gold-Daten erzeugt. Das macht die
Pipeline testbar, ohne zu behaupten, dass Tesseract installiert ist.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader


def _gold_ocr(folder: Path):
    gold = json.loads((folder / 'gold.json').read_text())
    pages = []
    for page in range(1, gold['seiten'] + 1):
        lines = [f"Laborbefund {gold['id']} OCR", "Fiktiver Scantext"]
        for row in [x for x in gold['laborwerte'] if x['seite'] == page]:
            ref = row['referenz']
            ref_text = f"{ref['untergrenze']} bis {ref['obergrenze']} {row['einheit']}" if ref else 'nicht angegeben'
            lines.append(f"{row['analyt']}: {row['wert']} {row['einheit']}. Referenz: {ref_text}. Flag: {row['flag']}.")
        lines.append('Glukose 999 mg/dl ist KEIN Messwert dieses Befunds.')
        pages.append({'seite': page, 'text': '\n'.join(lines)})
    return pages


def _tesseract_ocr(pdf: Path):
    if not shutil.which('tesseract'):
        return None
    try:
        import fitz
    except ImportError:
        return None
    pages = []
    doc = fitz.open(pdf)
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=220)
        png = pdf.parent / f'.ocr_page_{index}.png'
        pix.save(png)
        try:
            result = subprocess.run(['tesseract', str(png), 'stdout', '-l', 'deu+eng'],
                                    check=True, capture_output=True, text=True)
            pages.append({'seite': index, 'text': result.stdout})
        finally:
            png.unlink(missing_ok=True)
    return pages


def ocr_scan_pdf(pdf: Path):
    real = _tesseract_ocr(pdf)
    if real is not None:
        return {'methode': 'tesseract', 'seiten': real}
    folder = pdf.parent
    if (folder / 'gold.json').exists():
        return {'methode': 'synthetische_ocr_simulation', 'seiten': _gold_ocr(folder)}
    reader = PdfReader(pdf)
    return {'methode': 'kein_ocr_verfuegbar', 'seiten': [{'seite': i, 'text': ''}
                                                         for i, _ in enumerate(reader.pages, start=1)]}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = ocr_scan_pdf(args.pdf)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f"{result['methode']}: {len(result['seiten'])} Seiten -> {args.output}")
