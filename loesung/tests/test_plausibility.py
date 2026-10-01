from src.laborwert_schema import Laborwert, Referenzbereich
from src.plausibility import pruefe_befund, pruefe_laborwert, vergleiche_ldt_pdf


def laborwert(analyt, wert, einheit, flag='N', low=None, high=None, quelle='PDF', ergebnis_id=None):
    refs = []
    if flag is not None or low is not None or high is not None:
        refs.append(Referenzbereich(
            spezifikation=None, untergrenze=low, obergrenze=high,
            untergrenze_einheit=einheit if low is not None else None,
            obergrenze_einheit=einheit if high is not None else None,
            text=[], flag=flag,
        ))
    return Laborwert(
        befund_index=None, ergebnis_id=ergebnis_id, test_ident=None, analyt=analyt,
        wert=wert, einheit=einheit, einheitensystem=None, referenzen=refs,
        ergebnisstatus=None, quelle=quelle, seite=1 if quelle == 'PDF' else None,
        confidence=1.0 if quelle == 'PDF' else None, begruendung=None,
        zeile=1 if quelle == 'LDT' else None, objektpfad='test' if quelle == 'LDT' else None,
    )


def test_reference_flag_must_match_value_position():
    messages = pruefe_laborwert(laborwert('Glukose', '130', 'mg/dl', flag='N', low='70', high='100'))
    assert [m.regel for m in messages] == ['REFERENZ_FLAG_WIDERSPRUCH']
    assert messages[0].details['erwartung'] == 'high'


def test_physiologically_impossible_values_are_reported():
    high = pruefe_laborwert(laborwert('Natrium', '1400', 'mmol/l', flag='H', low='135', high='145'))
    negative = pruefe_laborwert(laborwert('CRP', '-1', 'mg/l', flag='L', low='0', high='5'))
    assert any(m.regel == 'PHYSIOLOGISCH_UNMOEGLICH' for m in high)
    assert any(m.regel == 'PHYSIOLOGISCH_UNMOEGLICH' for m in negative)


def test_unit_must_fit_analyte():
    messages = pruefe_laborwert(laborwert('Natrium', '140', 'mg/dl', flag='N'))
    assert [m.regel for m in messages] == ['EINHEIT_ANALYT']


def test_ldt_and_pdf_contradiction_after_normalization():
    ldt = [laborwert('Glukose', '90', 'mg/dl', flag='N', low='70', high='100', quelle='LDT', ergebnis_id='E1')]
    pdf = [laborwert('Glucose', '5.0', 'mmol/l', flag='N', low='3.9', high='5.6', quelle='PDF', ergebnis_id='E1')]
    assert vergleiche_ldt_pdf(ldt, pdf) == []

    pdf[0].wert = '7.0'
    messages = vergleiche_ldt_pdf(ldt, pdf)
    assert [m.regel for m in messages] == ['LDT_PDF_WIDERSPRUCH']
    assert messages[0].details['ldt_wert'] == '90'
    assert messages[0].details['pdf_wert'] == '126.11'


def test_report_collects_messages_and_review_flag():
    report = pruefe_befund([laborwert('LaborX', '7', 'mg/l')])
    assert report.review_erforderlich
    assert report.meldungen[0].regel == 'PLAUSIBILITAET_NICHT_PRUEFBAR'
