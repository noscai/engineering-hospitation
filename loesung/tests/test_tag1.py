"""Integrationstests: Gold -> getrennte Renderer -> Parser und PDF-Leser."""
import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.generate_dataset import SCAN_IDS, gold_befunde, pdf_rendern, ldt_rendern, generieren, scan_pdf_rendern
from src.ldt_extractor import extrahiere
from src.ldt_sparser import parse_dokument
from src.ldt_validator import validiere_ldt


@pytest.mark.parametrize('gold', list(gold_befunde()), ids=lambda g: g['id'])
def test_gold_roundtrip(gold):
    pdf = pdf_rendern(gold)
    result, attachments = extrahiere(ldt_rendern(gold, pdf))
    assert list(attachments.values()) == [pdf]
    assert len(result['laborwerte']) == len(gold['laborwerte']) == 8
    assert result['validierung']['ungepruefte_objekttypen'] == []
    expected_rules = {e['regel'] for e in gold['absichtliche_fehler']}
    found_rules = {m['regel'] for m in result['validierung']['meldungen']}
    assert expected_rules <= found_rules
    assert found_rules <= expected_rules | ({'FELDREIHENFOLGE'} if expected_rules else set())
    pdf_pages = [p.extract_text() for p in PdfReader(BytesIO(pdf)).pages]
    assert len(pdf_pages) == gold['seiten']
    for wanted, actual in zip(gold['laborwerte'], result['laborwerte']):
        assert actual['ergebnis_id'] == wanted['ergebnis_id']
        assert actual['analyt'] == wanted['analyt']
        assert actual['test_ident'] == wanted['test_ident']
        assert actual['wert'] == wanted['wert']
        missing = any(e['typ'] == 'fehlende_einheit' and e['ergebnis_id'] == wanted['ergebnis_id'] for e in gold['absichtliche_fehler'])
        assert actual['einheit'] == (None if missing else wanted['einheit'])
        assert len(actual['referenzen']) == 1
        ref = actual['referenzen'][0]
        assert ref['flag'] == wanted['flag']
        if wanted['referenz']:
            assert ref['untergrenze'] == wanted['referenz']['untergrenze']
            assert ref['obergrenze'] == wanted['referenz']['obergrenze']
            assert ref['untergrenze_einheit'] == wanted['einheit']
            assert ref['obergrenze_einheit'] == wanted['einheit']
        else:
            assert ref['untergrenze'] is None and ref['obergrenze'] is None
            assert ref['text'] == ['k.A.']
        page = pdf_pages[wanted['seite'] - 1]
        assert wanted['analyt'] in page
        assert wanted['wert'] in page
        assert wanted['einheit'] in page
    assert not any(v['wert'] == '999' for v in result['laborwerte'])


def test_reproducible_generation(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    assert generieren(first) == generieren(second)
    for a in first.rglob('*'):
        if a.is_file():
            assert a.read_bytes() == (second / a.relative_to(first)).read_bytes()


def test_committed_artifacts_match_generator():
    root = Path(__file__).resolve().parents[1] / 'data/synthetisch'
    manifest = json.loads((root / 'manifest.json').read_text())
    assert len(manifest['befunde']) == 18
    assert manifest['scan_simulationen'] == 3
    for gold in gold_befunde():
        path = root / gold['id']
        assert json.loads((path / 'gold.json').read_text()) == gold
        pdf = pdf_rendern(gold)
        assert (path / 'befund.pdf').read_bytes() == pdf
        assert (path / 'befund.ldt').read_bytes() == ldt_rendern(gold, pdf)
        if gold['id'] in SCAN_IDS:
            scan = scan_pdf_rendern(gold)
            assert (path / 'befund_scan.pdf').read_bytes() == scan
            assert len(PdfReader(BytesIO(scan)).pages) == gold['seiten']
        else:
            assert not (path / 'befund_scan.pdf').exists()


def test_broken_attachment_is_reported_without_crashing_or_repair():
    gold = next(gold_befunde())
    raw = ldt_rendern(gold, pdf_rendern(gold))
    raw = raw.replace(b'JVBER', b'!VBER', 1)
    result, pdfs = extrahiere(raw)
    assert not pdfs
    assert result['anhaenge'][0]['fehler']
    assert any(m['regel'] == 'E157' for m in result['validierung']['meldungen'])
    assert result['review_erforderlich']


def test_multiple_attachments_are_not_concatenated():
    gold = next(gold_befunde())
    pdf = pdf_rendern(gold)
    raw = ldt_rendern(gold, pdf)
    start = raw.index(b'0158110Anhang\r\n')
    end = raw.index(b'0178003Obj_0010\r\n', start) + len(b'0178003Obj_0010\r\n')
    raw = raw[:end] + raw[start:end] + raw[end:]
    result, pdfs = extrahiere(raw)
    assert len(pdfs) == 2
    assert all(value == pdf for value in pdfs.values())


def test_all_kbv_examples_extract_without_inventing_units():
    root = Path(__file__).resolve().parents[2] / 'data/ldt/kbv-testdaten'
    for path in root.glob('*.ldt'):
        result, attachments = extrahiere(path.read_bytes())
        assert result['review_erforderlich']
        assert result['versionen'] == ['LDT3.2.19']
        for meta in result['anhaenge']:
            if meta['datei']:
                assert hashlib.sha256(attachments[meta['datei']]).hexdigest() == meta['sha256']
        if path.name.startswith('Z01_UseCase05'):
            assert result['laborwerte'][0]['wert'] == '247.6'
            assert result['laborwerte'][0]['einheit'] == 'Einheit'
            assert len(attachments) == 1


def test_empty_and_unsupported_version_never_pass_silently():
    gold = next(gold_befunde())
    raw = ldt_rendern(gold, pdf_rendern(gold)).replace(b'LDT3.2.15', b'LDT3.2.19')
    result = validiere_ldt(parse_dokument(raw))
    assert any(m.regel == 'VERSION' for m in result.meldungen)
    assert not result.vollstaendig
