"""PDF-Laborwerte per LLM Structured Output extrahieren.

Aufruf:
    python -m src.pdf_llm_extractor data/synthetisch/SYN-001/befund.pdf --output out.json

Ohne OPENAI_API_KEY oder LLM_API_KEY wird kein API-Aufruf gestartet.
"""
from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader

from .laborwert_schema import LaborbefundExtraktion


SYSTEM_PROMPT = """Du extrahierst Laborwerte aus PDF-Text.
Gib ausschliesslich Werte aus dem Text zurueck. Erfinde nichts.
Fehlende Angaben muessen null oder eine leere Liste bleiben.
Ignoriere Freitext-Beispiele, die ausdruecklich keine Messwerte sind.
Nutze Analyt, Wert, Einheit, Referenzbereich, Flag, Seite, Confidence und Begruendung.
Wert und Einheit bleiben exakt wie gedruckt; keine Normalisierung und keine Umrechnung.
"""

KURZ_PROMPT = """Extrahiere nur echte Laborwerte aus dem PDF-Text.
Gib keine Beispielwerte aus Freitext zurueck.
Fehlende Angaben bleiben null oder leere Listen.
Wert, Einheit, Referenz, Flag und Seite exakt aus dem Text uebernehmen.
"""


def pdf_seitentexte(pdf: bytes) -> list[dict[str, str | int]]:
    reader = PdfReader(BytesIO(pdf))
    return [{'seite': index, 'text': page.extract_text() or ''} for index, page in enumerate(reader.pages, start=1)]


def _client(api_key: str | None, base_url: str | None):
    from openai import OpenAI
    kwargs = {'api_key': api_key, 'timeout': 90}
    if base_url:
        kwargs['base_url'] = base_url
    return OpenAI(**kwargs)


def _messages(seiten, prompt=SYSTEM_PROMPT):
    return [
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': json.dumps({'seiten': seiten}, ensure_ascii=False)},
    ]


def _parse_mit_response_format(client, model, seiten, prompt):
    completion = client.chat.completions.parse(
        model=model,
        messages=_messages(seiten, prompt),
        response_format=LaborbefundExtraktion,
        temperature=0,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError('Structured Output enthielt kein geparstes Ergebnis.')
    return parsed


def _parse_mit_tool(client, model, seiten, prompt):
    schema = LaborbefundExtraktion.model_json_schema()
    completion = client.chat.completions.create(
        model=model,
        messages=_messages(seiten, prompt),
        tools=[{
            'type': 'function',
            'function': {
                'name': 'extrahiere_laborbefund',
                'description': 'Extrahiert Laborwerte aus PDF-Text ohne Werte zu erfinden.',
                'parameters': schema,
                'strict': True,
            },
        }],
        tool_choice={'type': 'function', 'function': {'name': 'extrahiere_laborbefund'}},
        temperature=0,
    )
    calls = completion.choices[0].message.tool_calls or []
    if not calls:
        raise RuntimeError('Structured Output enthielt keinen Tool-Aufruf.')
    return LaborbefundExtraktion.model_validate_json(calls[0].function.arguments)


def extrahiere_pdf_mit_llm(pdf: bytes, *, model: str | None = None, api_key: str | None = None,
                           base_url: str | None = None, client=None, load_env: bool = True,
                           prompt_variante: str = 'standard'):
    return extrahiere_seitentexte_mit_llm(
        pdf_seitentexte(pdf), model=model, api_key=api_key, base_url=base_url,
        client=client, load_env=load_env, prompt_variante=prompt_variante,
    )


def extrahiere_seitentexte_mit_llm(seiten, *, model: str | None = None, api_key: str | None = None,
                                  base_url: str | None = None, client=None, load_env: bool = True,
                                  prompt_variante: str = 'standard'):
    if load_env:
        load_dotenv()
    api_key = api_key or os.getenv('OPENAI_API_KEY') or os.getenv('LLM_API_KEY')
    base_url = base_url or os.getenv('OPENAI_BASE_URL') or os.getenv('LLM_BASE_URL')
    model = model or os.getenv('LLM_MODEL') or 'gpt-6-astra'
    if client is None:
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY oder LLM_API_KEY fehlt; PDF-LLM-Extraktion nicht gestartet.')
        client = _client(api_key, base_url)
    prompt = KURZ_PROMPT if prompt_variante == 'kurz' else SYSTEM_PROMPT
    try:
        parsed = _parse_mit_response_format(client, model, seiten, prompt)
    except Exception as exc:
        if exc.__class__.__name__ != 'BadRequestError':
            raise
        parsed = _parse_mit_tool(client, model, seiten, prompt)
    for wert in parsed.laborwerte:
        wert.quelle = 'PDF'
        if wert.seite is None and len(seiten) == 1:
            wert.seite = 1
    return parsed


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model')
    parser.add_argument('--prompt', choices=['standard', 'kurz'], default='standard')
    args = parser.parse_args()
    try:
        result = extrahiere_pdf_mit_llm(args.pdf.read_bytes(), model=args.model, prompt_variante=args.prompt)
    except Exception as exc:
        parser.exit(1, f'Fehler: {type(exc).__name__}: LLM-Extraktion fehlgeschlagen. Details bitte lokal mit Debugger/Logs pruefen.\n')
    args.output.write_text(result.model_dump_json(indent=2) + '\n')
    print(f"{len(result.laborwerte)} PDF-Laborwerte: {args.output}")
