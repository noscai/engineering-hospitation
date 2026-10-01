from src.eval_pdf import evaluiere_befund, regel_text_pdf
from src.generate_dataset import gold_befunde, pdf_rendern
from src.laborwert_schema import LaborbefundExtraktion, Laborwert, Referenzbereich


def pred(analyt='Glukose', wert='90', einheit='mg/dl', flag='N'):
    return LaborbefundExtraktion(laborwerte=[
        Laborwert(
            befund_index=None, ergebnis_id=None, test_ident=None, analyt=analyt,
            wert=wert, einheit=einheit, einheitensystem=None,
            referenzen=[Referenzbereich(spezifikation=None, untergrenze='70', obergrenze='100',
                                        untergrenze_einheit=einheit, obergrenze_einheit=einheit,
                                        text=[], flag=flag)],
            ergebnisstatus=None, quelle='PDF', seite=1, confidence=1.0,
            begruendung=None, zeile=None, objektpfad=None,
        )
    ], hinweise=[])


def gold():
    return {'id': 'T', 'layout': 'test', 'laborwerte': [{
        'ergebnis_id': 'E1', 'test_ident': 'Glukose', 'analyt': 'Glukose',
        'wert': '90', 'einheit': 'mg/dl',
        'referenz': {'untergrenze': '70', 'obergrenze': '100'},
        'flag': 'N', 'seite': 1,
    }]}


def test_eval_exact_match_and_normalization_success():
    report = evaluiere_befund(gold(), pred())
    assert report.felder['wert_einheit_exact'].precision == 1
    assert report.felder['wert_einheit_exact'].recall == 1
    assert report.normalisierung['loinc'].precision == 1
    assert report.normalisierung['ziel_einheit'].recall == 1
    assert report.fehlerklassen == {}


def test_eval_counts_field_errors():
    report = evaluiere_befund(gold(), pred(wert='5.0', einheit='mmol/l'))
    assert report.felder['wert_einheit_exact'].precision == 0
    assert report.normalisierung['loinc'].precision == 1
    assert 'wert_einheit_exact_falsch' in report.fehlerklassen


def test_rule_text_pdf_reads_generated_pdf(tmp_path):
    fixture = next(gold_befunde())
    path = tmp_path / 'befund.pdf'
    path.write_bytes(pdf_rendern(fixture))
    result = regel_text_pdf(path)
    assert len(result.laborwerte) == 8
    assert result.laborwerte[0].analyt == fixture['laborwerte'][0]['analyt']
    assert result.laborwerte[0].wert == fixture['laborwerte'][0]['wert']
