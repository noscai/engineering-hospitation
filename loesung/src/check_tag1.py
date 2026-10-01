"""Reproduzierbarer Tag-1-Abgleich; keine LLM-Evaluation.

python -m src.check_tag1
Prüft gespeicherte Gold/LDT/PDF-Paare und extrahiert alle KBV-Anhänge.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from pypdf import PdfReader
from .ldt_extractor import extrahiere

ROOT = Path(__file__).resolve().parents[1]


def check_tag1(root=ROOT):
    dataset = root / 'data/synthetisch'
    manifest = json.loads((dataset / 'manifest.json').read_text())
    if len(manifest['befunde']) != 18:
        raise ValueError('Genau 18 Befunde erwartet')
    summary = {'synthetische_befunde': [], 'kbv_befunde': [], 'llm_verwendet': False}
    for entry in manifest['befunde']:
        folder = dataset / entry['id']
        gold = json.loads((folder / 'gold.json').read_text())
        raw = (folder / 'befund.ldt').read_bytes()
        pdf = (folder / 'befund.pdf').read_bytes()
        result, attachments = extrahiere(raw)
        errors = []
        if hashlib.sha256(raw).hexdigest() != entry['sha256_ldt'] or hashlib.sha256(pdf).hexdigest() != entry['sha256_pdf']:
            errors.append('Manifest-Hash stimmt nicht')
        if list(attachments.values()) != [pdf]:
            errors.append('Eingebettetes PDF weicht ab')
        actual = result['laborwerte']
        if len(actual) != len(gold['laborwerte']):
            errors.append('Anzahl der Laborwerte weicht ab')
        pdf_pages = [p.extract_text() or '' for p in PdfReader(folder / 'befund.pdf').pages]
        if len(pdf_pages) != gold['seiten']:
            errors.append('PDF-Seitenzahl weicht ab')
        scan = entry.get('scan_pdf')
        if scan:
            scan_path = folder / scan['datei']
            if not scan_path.exists():
                errors.append('Scan-PDF fehlt')
            else:
                if hashlib.sha256(scan_path.read_bytes()).hexdigest() != scan['sha256']:
                    errors.append('Scan-PDF-Hash stimmt nicht')
                if len(PdfReader(scan_path).pages) != gold['seiten']:
                    errors.append('Scan-PDF-Seitenzahl weicht ab')
        for expected, observed in zip(gold['laborwerte'], actual):
            for key in ('ergebnis_id', 'test_ident', 'analyt', 'wert'):
                if observed[key] != expected[key]:
                    errors.append(f"{expected['ergebnis_id']}: {key} weicht ab")
            missing = any(e['typ'] == 'fehlende_einheit' and e['ergebnis_id'] == expected['ergebnis_id'] for e in gold['absichtliche_fehler'])
            if observed['einheit'] != (None if missing else expected['einheit']):
                errors.append(f"{expected['ergebnis_id']}: Einheit weicht ab")
            refs = observed['referenzen']
            if len(refs) != 1 or refs[0]['flag'] != expected['flag']:
                errors.append(f"{expected['ergebnis_id']}: Referenz/Flag weicht ab")
            elif expected['referenz']:
                for key in ('untergrenze', 'obergrenze'):
                    if refs[0][key] != expected['referenz'][key] or refs[0][key + '_einheit'] != expected['einheit']:
                        errors.append(f"{expected['ergebnis_id']}: {key} weicht ab")
            elif refs[0]['text'] != ['k.A.'] or refs[0]['untergrenze'] is not None or refs[0]['obergrenze'] is not None:
                errors.append('Fehlende Referenz wurde verändert')
            if expected['seite'] > len(pdf_pages):
                errors.append('Erwartete PDF-Seite fehlt')
            elif not all(expected[k] in pdf_pages[expected['seite'] - 1] for k in ('analyt', 'wert', 'einheit')):
                errors.append(f"{expected['ergebnis_id']}: PDF-Text fehlt")
        found = {m['regel'] for m in result['validierung']['meldungen']}
        expected_rules = {e['regel'] for e in gold['absichtliche_fehler']}
        allowed = expected_rules | ({'FELDREIHENFOLGE'} if expected_rules else set())
        if not expected_rules <= found or not found <= allowed:
            errors.append(f'Unerwartete Validierungsregeln: {sorted(found)}')
        if result['validierung']['ungepruefte_objekttypen']:
            errors.append('Nicht abgedeckter Objekttyp im synthetischen Befund')
        summary['synthetische_befunde'].append({
            'id': gold['id'], 'laborwerte': len(actual), 'pdf_seiten': len(pdf_pages),
            'scan_pdf': bool(scan),
            'layout': gold['layout'], 'erwartete_regeln': sorted(expected_rules),
            'gemeldete_regeln': sorted(found), 'abweichungen': errors,
        })
    for path in sorted((root.parent / 'data/ldt/kbv-testdaten').glob('*.ldt')):
        result, pdfs = extrahiere(path.read_bytes())
        target = root / 'data/extrahiert' / path.stem
        target.mkdir(parents=True, exist_ok=True)
        for name, raw in pdfs.items():
            (target / name).write_bytes(raw)
        (target / 'ergebnis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        summary['kbv_befunde'].append({
            'datei': path.name, 'laborwerte': len(result['laborwerte']), 'pdfs': len(pdfs),
            'anhaenge_fehler': [a['fehler'] for a in result['anhaenge'] if a['fehler']],
            'regeln': dict(Counter(m['regel'] for m in result['validierung']['meldungen'])),
            'nicht_unterstuetzte_ergebnistypen': sorted({h.get('objekt') for h in result['hinweise'] if h['code'] == 'ERGEBNISTYP_NICHT_UNTERSTUETZT'}),
        })
    summary['gesamt'] = {
        'befunde': len(summary['synthetische_befunde']),
        'laborwerte': sum(x['laborwerte'] for x in summary['synthetische_befunde']),
        'pdf_seiten': sum(x['pdf_seiten'] for x in summary['synthetische_befunde']),
        'scan_pdfs': sum(1 for x in summary['synthetische_befunde'] if x['scan_pdf']),
        'befunde_mit_absichtlichen_fehlern': sum(bool(x['erwartete_regeln']) for x in summary['synthetische_befunde']),
        'unerwartete_abweichungen': sum(len(x['abweichungen']) for x in summary['synthetische_befunde']),
        'kbv_dateien': len(summary['kbv_befunde']),
        'kbv_pdfs': sum(x['pdfs'] for x in summary['kbv_befunde']),
    }
    target = root / 'reports'
    target.mkdir(exist_ok=True)
    (target / 'tag1-pruefung.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    report = check_tag1()
    print(json.dumps(report['gesamt'], ensure_ascii=False, indent=2))
    if report['gesamt']['unerwartete_abweichungen'] or any(x['anhaenge_fehler'] for x in report['kbv_befunde']):
        raise SystemExit(1)
