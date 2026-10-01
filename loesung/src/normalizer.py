"""Deterministische Normalisierung von Laborwerten.

Die Tabelle deckt die synthetischen Tag-1-Analyte ab. Unbekannte Kuerzel werden
nicht geraten; ein LLM darf spaeter nur fuer den Fallback Vorschlaege liefern.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field

from .laborwert_schema import Laborwert


class NormalisierterLaborwert(BaseModel):
    quelle: str | None
    ergebnis_id: str | None
    original_analyt: str | None
    original_wert: str | None
    original_einheit: str | None
    analyt_kanonisch: str | None
    loinc: str | None
    loinc_name: str | None
    ziel_einheit: str | None
    wert_normalisiert: str | None
    comparator: str | None
    status: str
    methode: str
    hinweise: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AnalytRegel:
    kanonisch: str
    loinc: str
    loinc_name: str
    ziel_einheit: str
    synonyme: tuple[str, ...]
    faktoren: dict[str, Decimal]
    offsets: dict[str, Decimal] | None = None


REGELN = [
    AnalytRegel('Kreatinin', '2160-0', 'Creatinine [Mass/volume] in Serum or Plasma', 'mg/dl',
                ('krea', 'kreatinin', 'creatinine'), {'mg/dl': Decimal('1'), 'µmol/l': Decimal('0.011312217')}),
    AnalytRegel('Glukose', '2345-7', 'Glucose [Mass/volume] in Serum or Plasma', 'mg/dl',
                ('glukose', 'glucose'), {'mg/dl': Decimal('1'), 'mmol/l': Decimal('18.01559')}),
    AnalytRegel('HbA1c', '4548-4', 'Hemoglobin A1c/Hemoglobin.total in Blood', '%',
                ('hba1c', 'haemoglobin a1c', 'hamoglobin a1c', 'hämoglobin a1c'),
                {'%': Decimal('1'), 'mmol/mol': Decimal('0.091491308')},
                {'mmol/mol': Decimal('2.149130832')}),
    AnalytRegel('ALT', '1742-6', 'Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma', 'U/l',
                ('alt', 'gpt', 'alat'), {'u/l': Decimal('1')}),
    AnalytRegel('Natrium', '2951-2', 'Sodium [Moles/volume] in Serum or Plasma', 'mmol/l',
                ('natrium', 'na', 'sodium'), {'mmol/l': Decimal('1')}),
    AnalytRegel('Kalium', '2823-3', 'Potassium [Moles/volume] in Serum or Plasma', 'mmol/l',
                ('kalium', 'k', 'potassium'), {'mmol/l': Decimal('1')}),
    AnalytRegel('CRP', '1988-5', 'C reactive protein [Mass/volume] in Serum or Plasma', 'mg/l',
                ('crp', 'c-reaktives protein', 'c reaktives protein', 'c reactive protein'),
                {'mg/l': Decimal('1'), 'mg/dl': Decimal('10')}),
    AnalytRegel('TSH', '3016-3', 'Thyrotropin [Units/volume] in Serum or Plasma', 'mU/l',
                ('tsh', 'thyreotropin', 'thyrotropin'), {'mu/l': Decimal('1'), 'mU/l': Decimal('1')}),
]

SYNONYME = {synonym: regel for regel in REGELN for synonym in regel.synonyme}
VALUE_RE = re.compile(r'^\s*(?P<comparator>[<>])?\s*(?P<value>[+-]?\d+(?:[.,]\d+)?)\s*$')


def _key(text: str | None) -> str:
    if not text:
        return ''
    value = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', value.lower().replace('_', ' ').strip())


def _unit_key(text: str | None) -> str:
    if not text:
        return ''
    return text.strip().replace('μ', 'µ')


def _decimal_text(value: Decimal) -> str:
    quantized = value.quantize(Decimal('0.01')) if value.copy_abs() >= Decimal('10') else value.quantize(Decimal('0.001'))
    return format(quantized.normalize(), 'f')


def normalisiere_laborwert(wert: Laborwert | dict) -> NormalisierterLaborwert:
    if isinstance(wert, dict):
        wert = Laborwert.model_validate(wert)
    analyt = wert.analyt or wert.test_ident
    regel = SYNONYME.get(_key(analyt))
    result = NormalisierterLaborwert(
        quelle=wert.quelle, ergebnis_id=wert.ergebnis_id,
        original_analyt=analyt, original_wert=wert.wert, original_einheit=wert.einheit,
        analyt_kanonisch=None, loinc=None, loinc_name=None, ziel_einheit=None,
        wert_normalisiert=None, comparator=None, status='unbekannter_analyt',
        methode='deterministisch', hinweise=[],
    )
    if regel is None:
        result.methode = 'llm_fallback_erforderlich'
        result.hinweise.append('Analyt/Kuerzel ist nicht in der deterministischen Mappingtabelle.')
        return result

    result.analyt_kanonisch = regel.kanonisch
    result.loinc = regel.loinc
    result.loinc_name = regel.loinc_name
    result.ziel_einheit = regel.ziel_einheit

    if wert.wert is None:
        result.status = 'wert_fehlt'
        result.hinweise.append('Kein Wert vorhanden.')
        return result
    if wert.einheit is None:
        result.status = 'einheit_fehlt'
        result.hinweise.append('Keine Einheit vorhanden; Wert wird nicht umgerechnet.')
        return result

    match = VALUE_RE.match(wert.wert)
    if not match:
        result.status = 'wert_nicht_numerisch'
        result.hinweise.append('Wert ist nicht numerisch parsebar.')
        return result
    try:
        raw_value = Decimal(match.group('value').replace(',', '.'))
    except InvalidOperation:
        result.status = 'wert_nicht_numerisch'
        result.hinweise.append('Wert ist nicht als Decimal parsebar.')
        return result
    unit = _unit_key(wert.einheit)
    faktor = regel.faktoren.get(unit) or regel.faktoren.get(unit.lower())
    if faktor is None:
        result.status = 'einheit_unbekannt'
        result.hinweise.append(f'Einheit {wert.einheit!r} ist fuer {regel.kanonisch} nicht freigegeben.')
        return result

    result.comparator = match.group('comparator')
    result.wert_normalisiert = _decimal_text(raw_value * faktor + (regel.offsets or {}).get(unit, Decimal('0')))
    result.status = 'ok'
    if unit != regel.ziel_einheit:
        result.hinweise.append(f'Einheit von {wert.einheit} nach {regel.ziel_einheit} umgerechnet.')
    return result


def normalisiere_laborwerte(werte: list[Laborwert | dict]) -> list[NormalisierterLaborwert]:
    return [normalisiere_laborwert(wert) for wert in werte]


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('eingabe', type=Path, help='JSON mit laborwerte-Liste oder LaborbefundExtraktion')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.eingabe.read_text())
    normalized = [x.model_dump() for x in normalisiere_laborwerte(data['laborwerte'])]
    text = json.dumps({'normalisierte_laborwerte': normalized}, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')
