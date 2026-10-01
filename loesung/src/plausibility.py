"""Plausibilitaetsregeln fuer normalisierte Laborwerte."""
from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel

from .laborwert_schema import Laborwert, Referenzbereich
from .normalizer import NormalisierterLaborwert, normalisiere_laborwert


class Plausibilitaetsmeldung(BaseModel):
    regel: str
    schwere: str
    analyt: str | None
    quelle: str | None
    beschreibung: str
    details: dict[str, str | None] = {}


class Plausibilitaetsbericht(BaseModel):
    meldungen: list[Plausibilitaetsmeldung]
    review_erforderlich: bool


PHYSIOLOGISCHE_GRENZEN = {
    'Kreatinin': (Decimal('0'), Decimal('25')),
    'Glukose': (Decimal('0'), Decimal('1500')),
    'HbA1c': (Decimal('0'), Decimal('20')),
    'ALT': (Decimal('0'), Decimal('20000')),
    'Natrium': (Decimal('80'), Decimal('200')),
    'Kalium': (Decimal('0'), Decimal('15')),
    'CRP': (Decimal('0'), Decimal('1000')),
    'TSH': (Decimal('0'), Decimal('1000')),
}

HIGH_FLAGS = {'H', '+', 'HH', '++', '!H', '!+'}
LOW_FLAGS = {'L', '-', 'LL', '--', '!L', '!-'}
NORMAL_FLAGS = {'N', None, ''}


def _decimal(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        return Decimal(text.replace(',', '.'))
    except InvalidOperation:
        return None


def _flag(refs: list[Referenzbereich]) -> str | None:
    return next((ref.flag for ref in refs if ref.flag), None)


def _reference(refs: list[Referenzbereich]):
    for ref in refs:
        low, high = _decimal(ref.untergrenze), _decimal(ref.obergrenze)
        if low is not None or high is not None:
            return low, high, ref.flag
    return None, None, _flag(refs)


def _expected_flag(value: Decimal, low: Decimal | None, high: Decimal | None, comparator: str | None):
    if comparator == '<' and high is not None and value <= high:
        return 'normal'
    if comparator == '>' and low is not None and value >= low:
        return 'high' if high is None or value > high else 'normal'
    if low is not None and value < low:
        return 'low'
    if high is not None and value > high:
        return 'high'
    return 'normal'


def _flag_class(flag: str | None):
    if flag in HIGH_FLAGS:
        return 'high'
    if flag in LOW_FLAGS:
        return 'low'
    if flag in NORMAL_FLAGS:
        return 'normal'
    return 'unknown'


def _add(meldungen, regel, schwere, wert, beschreibung, **details):
    meldungen.append(Plausibilitaetsmeldung(
        regel=regel, schwere=schwere, analyt=wert.analyt if isinstance(wert, Laborwert) else wert.analyt_kanonisch,
        quelle=wert.quelle, beschreibung=beschreibung, details={k: None if v is None else str(v) for k, v in details.items()},
    ))


def pruefe_laborwert(wert: Laborwert | dict) -> list[Plausibilitaetsmeldung]:
    wert = Laborwert.model_validate(wert) if isinstance(wert, dict) else wert
    norm = normalisiere_laborwert(wert)
    meldungen = []
    if norm.status == 'einheit_unbekannt':
        _add(meldungen, 'EINHEIT_ANALYT', 'Fehler', wert, 'Einheit passt nicht zum Analyt.', einheit=wert.einheit)
        return meldungen
    if norm.status in {'einheit_fehlt', 'wert_fehlt', 'wert_nicht_numerisch', 'unbekannter_analyt'}:
        _add(meldungen, 'PLAUSIBILITAET_NICHT_PRUEFBAR', 'Hinweis', wert, 'Wert ist nicht vollstaendig plausibilisierbar.',
             status=norm.status)
        return meldungen

    value = _decimal(norm.wert_normalisiert)
    if value is None:
        _add(meldungen, 'PLAUSIBILITAET_NICHT_PRUEFBAR', 'Hinweis', wert, 'Normalisierter Wert ist nicht numerisch.')
        return meldungen
    limits = PHYSIOLOGISCHE_GRENZEN.get(norm.analyt_kanonisch)
    if limits and not (limits[0] <= value <= limits[1]):
        _add(meldungen, 'PHYSIOLOGISCH_UNMOEGLICH', 'Fehler', wert,
             'Wert liegt ausserhalb der hinterlegten physiologischen Plausibilitaetsgrenzen.',
             messwert=value, untergrenze=limits[0], obergrenze=limits[1], einheit=norm.ziel_einheit)

    low, high, flag = _reference(wert.referenzen)
    if low is not None or high is not None:
        ref_norm = []
        for boundary in (low, high):
            if boundary is None:
                ref_norm.append(None)
            else:
                clone = wert.model_copy(update={'wert': str(boundary), 'einheit': wert.einheit, 'referenzen': []})
                ref_norm.append(_decimal(normalisiere_laborwert(clone).wert_normalisiert))
        expected = _expected_flag(value, ref_norm[0], ref_norm[1], norm.comparator)
        observed = _flag_class(flag)
        if observed != 'unknown' and expected != observed:
            _add(meldungen, 'REFERENZ_FLAG_WIDERSPRUCH', 'Fehler', wert,
                 'Laborflag passt nicht zur Lage des Werts gegenueber dem Referenzbereich.',
                 erwartung=expected, flag=flag, messwert=value, untergrenze=ref_norm[0], obergrenze=ref_norm[1])
    return meldungen


def vergleiche_ldt_pdf(ldt_werte: list[Laborwert | dict], pdf_werte: list[Laborwert | dict]) -> list[Plausibilitaetsmeldung]:
    ldt = [Laborwert.model_validate(x) if isinstance(x, dict) else x for x in ldt_werte]
    pdf = [Laborwert.model_validate(x) if isinstance(x, dict) else x for x in pdf_werte]
    pdf_by_id = {x.ergebnis_id: x for x in pdf if x.ergebnis_id}
    pdf_by_analyt = defaultdict(list)
    for x in pdf:
        norm = normalisiere_laborwert(x)
        if norm.analyt_kanonisch:
            pdf_by_analyt[norm.analyt_kanonisch].append(x)

    meldungen = []
    for ldt_wert in ldt:
        norm_ldt = normalisiere_laborwert(ldt_wert)
        candidate = pdf_by_id.get(ldt_wert.ergebnis_id)
        if candidate is None and norm_ldt.analyt_kanonisch:
            matches = pdf_by_analyt.get(norm_ldt.analyt_kanonisch, [])
            if len(matches) == 1:
                candidate = matches[0]
        if candidate is None:
            _add(meldungen, 'LDT_PDF_FEHLT', 'Hinweis', ldt_wert, 'Kein passender PDF-Wert gefunden.')
            continue
        norm_pdf = normalisiere_laborwert(candidate)
        if norm_ldt.status != 'ok' or norm_pdf.status != 'ok':
            continue
        ldt_value, pdf_value = _decimal(norm_ldt.wert_normalisiert), _decimal(norm_pdf.wert_normalisiert)
        differs = ldt_value is None or pdf_value is None or abs(ldt_value - pdf_value) > Decimal('0.1')
        if differs or norm_ldt.comparator != norm_pdf.comparator:
            _add(meldungen, 'LDT_PDF_WIDERSPRUCH', 'Fehler', ldt_wert,
                 'LDT-Wert und PDF-Wert widersprechen sich nach Normalisierung.',
                 ldt_wert=norm_ldt.wert_normalisiert, pdf_wert=norm_pdf.wert_normalisiert,
                 einheit=norm_ldt.ziel_einheit)
    return meldungen


def pruefe_befund(laborwerte: list[Laborwert | dict], pdf_laborwerte: list[Laborwert | dict] | None = None):
    meldungen = []
    for wert in laborwerte:
        meldungen.extend(pruefe_laborwert(wert))
    if pdf_laborwerte is not None:
        meldungen.extend(vergleiche_ldt_pdf(laborwerte, pdf_laborwerte))
    return Plausibilitaetsbericht(meldungen=meldungen, review_erforderlich=bool(meldungen))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ldt_json', type=Path, help='JSON mit laborwerte-Liste')
    parser.add_argument('--pdf-json', type=Path, help='Optionales PDF-Extraktionsergebnis')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ldt_data = json.loads(args.ldt_json.read_text())
    pdf_data = json.loads(args.pdf_json.read_text()) if args.pdf_json else None
    report = pruefe_befund(ldt_data['laborwerte'], pdf_data['laborwerte'] if pdf_data else None)
    text = report.model_dump_json(indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')
