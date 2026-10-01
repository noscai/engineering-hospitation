from types import SimpleNamespace

import pytest

from src.generate_dataset import gold_befunde, pdf_rendern
from src.laborwert_schema import LaborbefundExtraktion, Laborwert, Referenzbereich
from src.pdf_llm_extractor import extrahiere_pdf_mit_llm, pdf_seitentexte


class FakeCompletions:
    def __init__(self, parsed):
        self.parsed = parsed
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.parsed))])


class FakeFallbackCompletions:
    def __init__(self, arguments):
        self.arguments = arguments
        self.create_kwargs = None

    def parse(self, **kwargs):
        raise type('BadRequestError', (Exception,), {})('response_format unsupported')

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        call = SimpleNamespace(function=SimpleNamespace(arguments=self.arguments))
        message = SimpleNamespace(tool_calls=[call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, parsed):
        self.chat = SimpleNamespace(completions=FakeCompletions(parsed))


class FakeFallbackClient:
    def __init__(self, parsed):
        self.chat = SimpleNamespace(completions=FakeFallbackCompletions(parsed.model_dump_json()))


def test_pdf_text_pages_are_numbered():
    gold = next(gold_befunde())
    pages = pdf_seitentexte(pdf_rendern(gold))
    assert pages == [{'seite': 1, 'text': pages[0]['text']}]
    assert 'Laborbefund SYN-001' in pages[0]['text']
    assert 'Glukose 999 mg/dl ist KEIN Messwert' in pages[0]['text']


def test_llm_extraction_uses_structured_output_schema_and_keeps_missing_values(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    parsed = LaborbefundExtraktion(
        laborwerte=[
            Laborwert(
                befund_index=None, ergebnis_id=None, test_ident=None, analyt='Krea',
                wert='1,1', einheit='mg/dl', einheitensystem=None,
                referenzen=[
                    Referenzbereich(spezifikation=None, untergrenze='0.6', obergrenze='1.2',
                                    untergrenze_einheit='mg/dl', obergrenze_einheit='mg/dl',
                                    text=[], flag='N')
                ],
                ergebnisstatus=None, quelle='PDF', seite=1, confidence=0.86,
                begruendung='Tabellenzeile Krea auf Seite 1', zeile=None, objektpfad=None,
            )
        ],
        hinweise=['Ein zweiter Wert hatte keine Einheit.'],
    )
    client = FakeClient(parsed)
    result = extrahiere_pdf_mit_llm(pdf_rendern(next(gold_befunde())), model='test-model', client=client)
    kwargs = client.chat.completions.kwargs
    assert kwargs['model'] == 'test-model'
    assert kwargs['response_format'] is LaborbefundExtraktion
    assert 'Erfinde nichts' in kwargs['messages'][0]['content']
    assert result.laborwerte[0].quelle == 'PDF'
    assert result.laborwerte[0].ergebnis_id is None
    assert result.hinweise == ['Ein zweiter Wert hatte keine Einheit.']


def test_llm_extraction_falls_back_to_structured_tool_call(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    parsed = LaborbefundExtraktion(laborwerte=[], hinweise=['kein Laborwert gefunden'])
    client = FakeFallbackClient(parsed)
    result = extrahiere_pdf_mit_llm(pdf_rendern(next(gold_befunde())), model='anthropic/claude-sonnet-4', client=client)
    kwargs = client.chat.completions.create_kwargs
    assert kwargs['tools'][0]['function']['name'] == 'extrahiere_laborbefund'
    assert kwargs['tools'][0]['function']['strict'] is True
    assert result.hinweise == ['kein Laborwert gefunden']


def test_short_prompt_variant_is_used(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    parsed = LaborbefundExtraktion(laborwerte=[], hinweise=[])
    client = FakeClient(parsed)
    extrahiere_pdf_mit_llm(pdf_rendern(next(gold_befunde())), model='test-model', client=client, prompt_variante='kurz')
    assert 'Extrahiere nur echte Laborwerte' in client.chat.completions.kwargs['messages'][0]['content']


def test_llm_extraction_requires_api_key_without_injected_client(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('LLM_BASE_URL', raising=False)
    monkeypatch.delenv('LLM_MODEL', raising=False)
    with pytest.raises(RuntimeError, match='API_KEY'):
        extrahiere_pdf_mit_llm(pdf_rendern(next(gold_befunde())), load_env=False)
