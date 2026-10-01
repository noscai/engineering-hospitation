"""Scan-/Bild-PDFs per Vision-LLM Structured Output extrahieren.

Diese Variante ersetzt keine klassische OCR-Bibliothek. Sie rendert PDF-Seiten als
Bilder und laesst ein Vision-Modell die Laborwerte direkt in unser gemeinsames
Schema extrahieren. Damit bleibt die Downstream-Kette identisch:
Structured Extraction -> Normalisierung -> Plausibilitaet -> Eval.
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from pydantic import ValidationError

from .laborwert_schema import LaborbefundExtraktion, Laborwert, Referenzbereich
from .pdf_llm_extractor import _client


VISION_STRING_RE = re.compile(
    r'^(?P<analyt>.*?)\s+Wert\s+(?P<wert>\S+)'
    r'(?:\s+Einheit\s+(?P<einheit>.*?))?'
    r'\s+Referenz(?:bereich)?\s+(?P<referenz>.*?)\s+Flag\s+(?P<flag>\S*)\s+Seite\s+(?P<seite>\d+)\s*$',
    re.IGNORECASE,
)
VISION_COLON_RE = re.compile(
    r'^(?P<analyt>.*?):\s*(?P<wert>[<>]?\d+(?:[,.]\d+)?%?)\s*(?P<einheit>[^()]+?)?'
    r'\s*\(Ref:?\s*(?P<referenz>.*?)\)\s*Flag\s*(?P<flag>\S*)\s*\(Seite\s*(?P<seite>\d+)(?:/\d+)?\)\s*$',
    re.IGNORECASE,
)


def _referenz_aus_text(text: str, einheit: str | None, flag: str | None):
    text = text.strip().strip('.')
    if not text or text in {'k.A', 'k.A.', 'keine', 'nicht angegeben'}:
        return Referenzbereich(spezifikation=None, untergrenze=None, obergrenze=None,
                               untergrenze_einheit=None, obergrenze_einheit=None,
                               text=['k.A.'], flag=flag or None)
    match = re.search(r'(?P<low>[<>]?\d+(?:[,.]\d+)?)\s*(?:-|bis)\s*(?P<high>[<>]?\d+(?:[,.]\d+)?)', text)
    if not match:
        return Referenzbereich(spezifikation=None, untergrenze=None, obergrenze=None,
                               untergrenze_einheit=None, obergrenze_einheit=None,
                               text=[text], flag=flag or None)
    return Referenzbereich(spezifikation=None, untergrenze=match.group('low'), obergrenze=match.group('high'),
                           untergrenze_einheit=einheit, obergrenze_einheit=einheit, text=[], flag=flag or None)


def _laborwert_aus_vision_string(text: str):
    cleaned = text.strip()
    match = VISION_STRING_RE.match(cleaned) or VISION_COLON_RE.match(cleaned)
    if not match:
        raise ValueError(f'Vision-Zeile nicht parsebar: {text!r}')
    wert = match.group('wert')
    einheit = (match.group('einheit') or '').strip() or None
    if einheit:
        einheit = einheit.replace('Ref.', '').strip()
    if not einheit and wert.endswith('%'):
        wert, einheit = wert[:-1], '%'
    flag = (match.group('flag') or '').strip() or None
    return Laborwert(
        befund_index=None, ergebnis_id=None, test_ident=None, analyt=match.group('analyt').strip(),
        wert=wert, einheit=einheit, einheitensystem=None,
        referenzen=[_referenz_aus_text(match.group('referenz'), einheit, flag)],
        ergebnisstatus=flag, quelle='PDF', seite=int(match.group('seite')),
        confidence=None, begruendung='Gemini Vision Tool-Ausgabe aus Stringliste nachstrukturiert.',
        zeile=None, objektpfad=None,
    )


def _validate_vision_arguments(arguments: str):
    try:
        return LaborbefundExtraktion.model_validate_json(arguments)
    except ValidationError:
        data = json.loads(arguments)
        werte = data.get('laborwerte')
        if not isinstance(werte, list) or not all(isinstance(item, str) for item in werte):
            raise
        return LaborbefundExtraktion(
            laborwerte=[_laborwert_aus_vision_string(item) for item in werte],
            hinweise=[*data.get('hinweise', []), 'Vision-LLM lieferte Laborwerte als Strings; deterministisch nachstrukturiert.'],
        )

VISION_PROMPT = """Extrahiere echte Laborwerte aus den gescannten Befundseiten.
Die Seiten sind Bilder. Erfinde nichts: fehlende Angaben bleiben null oder leere Listen.
Ignoriere Freitext-Beispiele, die ausdruecklich keine Messwerte sind.
Wert, Einheit, Referenzbereich, Flag und Seite exakt wie sichtbar uebernehmen.
Keine Normalisierung, keine Umrechnung und keine medizinische Interpretation.
"""


def pdf_seiten_als_bilder(pdf: bytes, *, dpi: int = 180) -> list[dict[str, str | int]]:
    import fitz

    pages = []
    doc = fitz.open(stream=pdf, filetype='pdf')
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        png = pix.tobytes('png')
        encoded = base64.b64encode(png).decode('ascii')
        pages.append({'seite': index, 'mime_type': 'image/png', 'data_url': f'data:image/png;base64,{encoded}'})
    return pages


def _vision_messages(bilder, prompt=VISION_PROMPT):
    content = [{'type': 'text', 'text': prompt}]
    for bild in bilder:
        content.append({'type': 'text', 'text': f"Seite {bild['seite']}"})
        content.append({'type': 'image_url', 'image_url': {'url': bild['data_url']}})
    return [{'role': 'user', 'content': content}]


def _parse_vision_mit_tool(client, model, bilder, prompt):
    schema = LaborbefundExtraktion.model_json_schema()
    completion = client.chat.completions.create(
        model=model,
        messages=_vision_messages(bilder, prompt),
        tools=[{
            'type': 'function',
            'function': {
                'name': 'extrahiere_laborbefund_aus_bildern',
                'description': 'Extrahiert Laborwerte aus gescannten Befundseiten ohne Werte zu erfinden.',
                'parameters': schema,
                'strict': True,
            },
        }],
        tool_choice={'type': 'function', 'function': {'name': 'extrahiere_laborbefund_aus_bildern'}},
        temperature=0,
    )
    calls = completion.choices[0].message.tool_calls or []
    if not calls:
        raise RuntimeError('Vision Structured Output enthielt keinen Tool-Aufruf.')
    return _validate_vision_arguments(calls[0].function.arguments)


def extrahiere_pdf_bild_mit_llm(pdf: bytes, *, model: str | None = None, api_key: str | None = None,
                                base_url: str | None = None, client=None, load_env: bool = True,
                                dpi: int = 180):
    if load_env:
        load_dotenv()
    api_key = api_key or os.getenv('OPENAI_API_KEY') or os.getenv('LLM_API_KEY')
    base_url = base_url or os.getenv('OPENAI_BASE_URL') or os.getenv('LLM_BASE_URL')
    model = model or os.getenv('LLM_VISION_MODEL') or os.getenv('LLM_MODEL') or 'gpt-6-astra'
    if client is None:
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY oder LLM_API_KEY fehlt; Vision-LLM-Extraktion nicht gestartet.')
        client = _client(api_key, base_url)
    bilder = pdf_seiten_als_bilder(pdf, dpi=dpi)
    parsed = _parse_vision_mit_tool(client, model, bilder, VISION_PROMPT)
    for wert in parsed.laborwerte:
        wert.quelle = 'PDF'
        if wert.seite is None and len(bilder) == 1:
            wert.seite = 1
    return parsed


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model')
    parser.add_argument('--dpi', type=int, default=180)
    args = parser.parse_args()
    try:
        result = extrahiere_pdf_bild_mit_llm(args.pdf.read_bytes(), model=args.model, dpi=args.dpi)
    except Exception as exc:
        parser.exit(1, f'Fehler: {type(exc).__name__}: Vision-LLM-Extraktion fehlgeschlagen. Details bitte lokal mit Debugger/Logs pruefen.\n')
    args.output.write_text(result.model_dump_json(indent=2) + '\n')
    print(f"{len(result.laborwerte)} Bild-PDF-Laborwerte: {args.output}")
