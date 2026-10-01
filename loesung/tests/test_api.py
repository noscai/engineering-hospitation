from pathlib import Path

from fastapi.testclient import TestClient

from src.api import app


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_health():
    assert client.get('/health').json() == {'status': 'ok'}


def test_upload_ldt_returns_pdf_url_and_checked_values():
    raw = (ROOT / 'data/synthetisch/SYN-001/befund.ldt').read_bytes()
    response = client.post('/befunde/extrahieren', files={'file': ('befund.ldt', raw, 'application/octet-stream')})
    assert response.status_code == 200
    data = response.json()
    assert data['dateityp'] == 'LDT'
    assert data['pdf_url']
    assert len(data['laborwerte']) == 8
    assert data['normalisierte_laborwerte'][0]['loinc'] == '2160-0'
    assert not data['plausibilitaet']['review_erforderlich']


def test_upload_pdf_uses_rule_based_default_without_llm():
    raw = (ROOT / 'data/synthetisch/SYN-001/befund.pdf').read_bytes()
    response = client.post('/befunde/extrahieren', files={'file': ('befund.pdf', raw, 'application/pdf')})
    assert response.status_code == 200
    data = response.json()
    assert data['dateityp'] == 'PDF'
    assert data['pdf_url']
    assert len(data['laborwerte']) == 8


def test_save_review_case(tmp_path, monkeypatch):
    monkeypatch.setattr('src.api.REVIEW_CASES', tmp_path)
    payload = {
        'dateiname': 'befund.pdf',
        'dateityp': 'PDF',
        'laborwerte': [{'analyt': 'Glukose', 'wert': '90'}],
        'corrections': [{
            'index': 0,
            'original': {'analyt': 'Glukose', 'wert': '90'},
            'corrected': {'analyt': 'Glukose', 'wert': '91'},
            'status': 'corrected',
        }],
    }
    response = client.post('/review/faelle', json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['case_id']
    assert data['pfad'].endswith('review_case.json')


def test_rejects_unknown_file_type():
    response = client.post('/befunde/extrahieren', files={'file': ('x.txt', b'hello', 'text/plain')})
    assert response.status_code == 415
