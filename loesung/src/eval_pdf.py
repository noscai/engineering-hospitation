"""Evaluation der PDF-Extraktion und Normalisierung gegen Gold-Daten."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pypdf import PdfReader

from .laborwert_schema import LaborbefundExtraktion, Laborwert, Referenzbereich
from .normalizer import normalisiere_laborwert
from .pdf_llm_extractor import extrahiere_pdf_mit_llm, extrahiere_seitentexte_mit_llm
from .pdf_vision_extractor import extrahiere_pdf_bild_mit_llm
from .scan_ocr import ocr_scan_pdf


class FeldMetrik(BaseModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0


class BefundEval(BaseModel):
    id: str
    layout: str
    gold: int
    extrahiert: int
    felder: dict[str, FeldMetrik]
    normalisierung: dict[str, FeldMetrik]
    fehlerklassen: dict[str, int] = Field(default_factory=dict)


FIELDS = ['analyt', 'wert', 'einheit', 'referenz', 'flag', 'seite', 'wert_einheit_exact']
NORM_FIELDS = ['loinc', 'ziel_einheit']
VALUE_RE = r'[<>]?\d+(?:[,.]\d+)?'
PROSE_RE = re.compile(
    rf'(?P<analyt>[A-Za-zÄÖÜäöüßµ\- ]+):\s*(?P<wert>{VALUE_RE})\s+(?P<einheit>[%µA-Za-z/]+)\.\s+'
    rf'Referenz:\s*(?P<ref>.*?)(?:\.\s+Flag:\s*(?P<flag>[A-Za-z+!\-]+)\.)',
    re.DOTALL,
)


def _metric(tp=0, fp=0, fn=0):
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return FeldMetrik(tp=tp, fp=fp, fn=fn, precision=round(precision, 4), recall=round(recall, 4))


def _seiten(pdf_path: Path):
    return [(i, page.extract_text() or '') for i, page in enumerate(PdfReader(pdf_path).pages, start=1)]


def _ref(ref_text):
    ref_text = ref_text.strip()
    if ref_text in {'k.A.', 'nicht angegeben'}:
        return None
    match = re.search(rf'(?P<low>{VALUE_RE})\s*(?:-|bis)\s*(?P<high>{VALUE_RE})', ref_text)
    if not match:
        return None
    return {'untergrenze': match.group('low'), 'obergrenze': match.group('high')}


def regel_text_pdf(pdf_path: Path) -> LaborbefundExtraktion:
    werte = []
    for page_no, text in _seiten(pdf_path):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if 'Analyt' in lines and 'Ergebnis' in lines and 'Einheit' in lines:
            start = lines.index('Flag') + 1
            stop = next((i for i, line in enumerate(lines[start:], start) if line.startswith('Nur synthetische')), len(lines))
            rows = lines[start:stop]
            for i in range(0, len(rows) - 4, 5):
                werte.append(_laborwert(rows[i], rows[i + 1], rows[i + 2], _ref(rows[i + 3]), rows[i + 4], page_no))
            continue
        cleaned = ' '.join(lines)
        cleaned = re.sub(r'Nur synthetische Testdaten\..*$', '', cleaned)
        for match in PROSE_RE.finditer(cleaned):
            werte.append(_laborwert(match.group('analyt').strip(), match.group('wert'), match.group('einheit'),
                                    _ref(match.group('ref')), match.group('flag'), page_no))
    return LaborbefundExtraktion(laborwerte=werte, hinweise=[])


def _laborwert(analyt, wert, einheit, referenz, flag, seite):
    refs = []
    if referenz or flag:
        refs.append(Referenzbereich(
            spezifikation=None,
            untergrenze=referenz['untergrenze'] if referenz else None,
            obergrenze=referenz['obergrenze'] if referenz else None,
            untergrenze_einheit=einheit if referenz else None,
            obergrenze_einheit=einheit if referenz else None,
            text=[] if referenz else ['k.A.'],
            flag=flag,
        ))
    return Laborwert(
        befund_index=None, ergebnis_id=None, test_ident=None, analyt=analyt, wert=wert,
        einheit=einheit, einheitensystem=None, referenzen=refs, ergebnisstatus=None,
        quelle='PDF', seite=seite, confidence=None, begruendung='regel_text_pdf', zeile=None, objektpfad=None,
    )


def _gold_laborwert(row):
    refs = []
    ref = row.get('referenz')
    refs.append(Referenzbereich(
        spezifikation=None,
        untergrenze=ref['untergrenze'] if ref else None,
        obergrenze=ref['obergrenze'] if ref else None,
        untergrenze_einheit=row['einheit'] if ref else None,
        obergrenze_einheit=row['einheit'] if ref else None,
        text=[] if ref else ['k.A.'],
        flag=row['flag'],
    ))
    return Laborwert(
        befund_index=None, ergebnis_id=row['ergebnis_id'], test_ident=row['test_ident'],
        analyt=row['analyt'], wert=row['wert'], einheit=row['einheit'], einheitensystem=None,
        referenzen=refs, ergebnisstatus=None, quelle='PDF', seite=row['seite'], confidence=1.0,
        begruendung='gold', zeile=None, objektpfad=None,
    )


def _canon(text):
    return re.sub(r'\s+', ' ', str(text or '').strip().lower().replace('.', ','))


def _ref_key(wert):
    if not wert.referenzen:
        return None
    ref = wert.referenzen[0]
    if ref.untergrenze is None and ref.obergrenze is None:
        return 'k.A.'
    return (_canon(ref.untergrenze), _canon(ref.obergrenze))


def _match_gold(gold_values, pred_values):
    unmatched = list(pred_values)
    pairs, missing = [], []
    for gold in gold_values:
        gold_norm = normalisiere_laborwert(gold)
        found = None
        for pred in unmatched:
            pred_norm = normalisiere_laborwert(pred)
            if gold_norm.analyt_kanonisch and gold_norm.analyt_kanonisch == pred_norm.analyt_kanonisch:
                found = pred
                break
        if found is not None:
            unmatched.remove(found)
            pairs.append((gold, found))
        else:
            missing.append(gold)
    return pairs, missing, unmatched


def _flag_value(wert):
    if wert.referenzen and wert.referenzen[0].flag is not None:
        return wert.referenzen[0].flag
    return wert.ergebnisstatus


def _field_ok(field, gold, pred):
    if field == 'analyt':
        return normalisiere_laborwert(gold).analyt_kanonisch == normalisiere_laborwert(pred).analyt_kanonisch
    if field == 'referenz':
        return _ref_key(gold) == _ref_key(pred)
    if field == 'flag':
        return _canon(_flag_value(gold)) == _canon(_flag_value(pred))
    if field == 'wert_einheit_exact':
        return _canon(gold.wert) == _canon(pred.wert) and _canon(gold.einheit) == _canon(pred.einheit)
    return _canon(getattr(gold, field)) == _canon(getattr(pred, field))


def evaluiere_befund(gold, pred: LaborbefundExtraktion):
    gold_values = [_gold_laborwert(row) for row in gold['laborwerte']]
    pred_values = pred.laborwerte
    pairs, missing, extra = _match_gold(gold_values, pred_values)
    errors = Counter()
    fields = {}
    for field in FIELDS:
        ok = sum(1 for g, p in pairs if _field_ok(field, g, p))
        bad = len(pairs) - ok
        fields[field] = _metric(tp=ok, fp=bad + len(extra), fn=bad + len(missing))
        if bad:
            errors[f'{field}_falsch'] += bad
    if missing:
        errors['wert_fehlt'] += len(missing)
    if extra:
        errors['wert_zusaetzlich'] += len(extra)

    norm = {}
    for field in NORM_FIELDS:
        ok, bad = 0, 0
        for g, p in pairs:
            ng, np = normalisiere_laborwert(g), normalisiere_laborwert(p)
            if getattr(ng, field) == getattr(np, field):
                ok += 1
            else:
                bad += 1
                errors[f'normalisierung_{field}_falsch'] += 1
        norm[field] = _metric(tp=ok, fp=bad + len(extra), fn=bad + len(missing))
    return BefundEval(id=gold['id'], layout=gold['layout'], gold=len(gold_values), extrahiert=len(pred_values),
                      felder=fields, normalisierung=norm, fehlerklassen=dict(errors))


def _aggregate(items):
    result = {}
    for group in ('felder', 'normalisierung'):
        keys = FIELDS if group == 'felder' else NORM_FIELDS
        result[group] = {}
        for key in keys:
            tp = sum(getattr(item, group)[key].tp for item in items)
            fp = sum(getattr(item, group)[key].fp for item in items)
            fn = sum(getattr(item, group)[key].fn for item in items)
            result[group][key] = _metric(tp, fp, fn).model_dump()
    result['fehlerklassen'] = dict(sum((Counter(item.fehlerklassen) for item in items), Counter()))
    return result


def _load_or_run_llm_variant(folder, *, run_llm, output_name: str, model: str | None = None, prompt='kurz'):
    out = folder / output_name
    if out.exists():
        return LaborbefundExtraktion.model_validate_json(out.read_text())
    if not run_llm or not model:
        return None
    result = extrahiere_pdf_mit_llm((folder / 'befund.pdf').read_bytes(), model=model, prompt_variante=prompt)
    out.write_text(result.model_dump_json(indent=2) + '\n')
    return result


def _load_or_run_llm(folder, *, run_llm):
    return _load_or_run_llm_variant(folder, run_llm=run_llm, output_name='pdf_llm.json',
                                    model=os.getenv('LLM_MODEL'), prompt='kurz')


def _load_or_run_alt_llm(folder, *, run_llm):
    return _load_or_run_llm_variant(folder, run_llm=run_llm, output_name='pdf_llm_alt.json',
                                    model=os.getenv('LLM_ALT_MODEL'), prompt='kurz')


def _load_or_run_scan_vision_llm(folder, *, run_llm):
    scan = folder / 'befund_scan.pdf'
    if not scan.exists():
        return None
    out = folder / 'scan_vision_llm.json'
    if out.exists():
        return LaborbefundExtraktion.model_validate_json(out.read_text())
    if not run_llm:
        return None
    result = extrahiere_pdf_bild_mit_llm(scan.read_bytes())
    out.write_text(result.model_dump_json(indent=2) + '\n')
    return result


def _load_or_run_scan_llm(folder, *, run_llm):
    scan = folder / 'befund_scan.pdf'
    if not scan.exists():
        return None
    out = folder / 'scan_llm.json'
    if out.exists():
        return LaborbefundExtraktion.model_validate_json(out.read_text())
    ocr_out = folder / 'scan_ocr.json'
    ocr = ocr_scan_pdf(scan)
    ocr_out.write_text(json.dumps(ocr, ensure_ascii=False, indent=2) + '\n')
    if not run_llm:
        return None
    result = extrahiere_seitentexte_mit_llm(ocr['seiten'], prompt_variante='kurz')
    out.write_text(result.model_dump_json(indent=2) + '\n')
    return result


def evaluiere_dataset(root: Path, *, run_llm=False, limit: int | None = None):
    load_dotenv()
    variants = {'regel_text_pdf': [], 'llm_structured_text': [], 'llm_structured_alt_model': [], 'scan_ocr_llm': [], 'scan_vision_llm': []}
    run_errors = {'regel_text_pdf': [], 'llm_structured_text': [], 'llm_structured_alt_model': [], 'scan_ocr_llm': [], 'scan_vision_llm': []}
    skipped = {'regel_text_pdf': [], 'llm_structured_text': [], 'llm_structured_alt_model': [], 'scan_ocr_llm': [], 'scan_vision_llm': []}
    folders = sorted(path for path in root.glob('SYN-*') if path.is_dir())
    if limit:
        folders = folders[:limit]
    for folder in folders:
        gold = json.loads((folder / 'gold.json').read_text())
        try:
            variants['regel_text_pdf'].append(evaluiere_befund(gold, regel_text_pdf(folder / 'befund.pdf')))
        except Exception as exc:
            run_errors['regel_text_pdf'].append({'id': gold['id'], 'fehler': type(exc).__name__})
        try:
            llm = _load_or_run_llm(folder, run_llm=run_llm)
        except Exception as exc:
            run_errors['llm_structured_text'].append({'id': gold['id'], 'fehler': type(exc).__name__})
            llm = None
        if llm is not None:
            variants['llm_structured_text'].append(evaluiere_befund(gold, llm))
        else:
            skipped['llm_structured_text'].append(gold['id'])
        try:
            alt_llm = _load_or_run_alt_llm(folder, run_llm=run_llm)
        except Exception as exc:
            run_errors['llm_structured_alt_model'].append({'id': gold['id'], 'fehler': type(exc).__name__})
            alt_llm = None
        if alt_llm is not None:
            variants['llm_structured_alt_model'].append(evaluiere_befund(gold, alt_llm))
        else:
            skipped['llm_structured_alt_model'].append(gold['id'])
        try:
            scan_llm = _load_or_run_scan_llm(folder, run_llm=run_llm)
        except Exception as exc:
            run_errors['scan_ocr_llm'].append({'id': gold['id'], 'fehler': type(exc).__name__})
            scan_llm = None
        if scan_llm is not None:
            variants['scan_ocr_llm'].append(evaluiere_befund(gold, scan_llm))
        elif (folder / 'befund_scan.pdf').exists():
            skipped['scan_ocr_llm'].append(gold['id'])
        try:
            scan_vision = _load_or_run_scan_vision_llm(folder, run_llm=run_llm)
        except Exception as exc:
            run_errors['scan_vision_llm'].append({'id': gold['id'], 'fehler': type(exc).__name__})
            scan_vision = None
        if scan_vision is not None:
            variants['scan_vision_llm'].append(evaluiere_befund(gold, scan_vision))
        elif (folder / 'befund_scan.pdf').exists():
            skipped['scan_vision_llm'].append(gold['id'])
    report = {
        'modelle': {
            'llm_structured_text': os.getenv('LLM_MODEL'),
            'llm_structured_alt_model': os.getenv('LLM_ALT_MODEL'),
            'scan_vision_llm': os.getenv('LLM_VISION_MODEL') or os.getenv('LLM_MODEL'),
        },
        'varianten': {}, 'fehleranalyse': {}, 'lauf_fehler': run_errors, 'nicht_evaluiert': skipped,
    }
    for name, items in variants.items():
        report['varianten'][name] = {
            'befunde': len(items),
            'gesamt': _aggregate(items) if items else {},
            'pro_befund': [item.model_dump() for item in items],
        }
        report['fehleranalyse'][name] = report['varianten'][name]['gesamt'].get('fehlerklassen', {})
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path('data/synthetisch'))
    parser.add_argument('--output', type=Path, default=Path('reports/tag2-evaluation.json'))
    parser.add_argument('--run-llm', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    report = evaluiere_dataset(args.dataset, run_llm=args.run_llm, limit=args.limit)
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: {'befunde': v['befunde'], 'fehleranalyse': report['fehleranalyse'][k]}
                      for k, v in report['varianten'].items()}, ensure_ascii=False, indent=2))
