from src.laborwert_schema import Laborwert
from src.normalizer import normalisiere_laborwert, normalisiere_laborwerte


def laborwert(analyt, wert, einheit):
    return Laborwert(
        befund_index=None, ergebnis_id=None, test_ident=None, analyt=analyt,
        wert=wert, einheit=einheit, einheitensystem=None, referenzen=[],
        ergebnisstatus=None, quelle='PDF', seite=1, confidence=1.0,
        begruendung=None, zeile=None, objektpfad=None,
    )


def test_synonyme_map_to_loinc_and_target_units():
    cases = [
        ('Krea', '1,2', 'mg/dl', 'Kreatinin', '2160-0', 'mg/dl', '1.2'),
        ('Glucose', '5.5', 'mmol/l', 'Glukose', '2345-7', 'mg/dl', '99.09'),
        ('Hämoglobin A1c', '42', 'mmol/mol', 'HbA1c', '4548-4', '%', '5.992'),
        ('GPT', '22', 'U/l', 'ALT', '1742-6', 'U/l', '22'),
        ('Na', '141', 'mmol/l', 'Natrium', '2951-2', 'mmol/l', '141'),
        ('K', '4.2', 'mmol/l', 'Kalium', '2823-3', 'mmol/l', '4.2'),
        ('C-reaktives Protein', '0.7', 'mg/dl', 'CRP', '1988-5', 'mg/l', '7'),
        ('TSH', '1.5', 'mU/l', 'TSH', '3016-3', 'mU/l', '1.5'),
    ]
    for analyt, wert, einheit, kanonisch, loinc, ziel, normalisiert in cases:
        result = normalisiere_laborwert(laborwert(analyt, wert, einheit))
        assert result.status == 'ok'
        assert result.analyt_kanonisch == kanonisch
        assert result.loinc == loinc
        assert result.ziel_einheit == ziel
        assert result.wert_normalisiert == normalisiert


def test_comparator_and_missing_unit_are_not_repaired():
    comparator = normalisiere_laborwert(laborwert('CRP', '<0,5', 'mg/l'))
    assert comparator.status == 'ok'
    assert comparator.comparator == '<'
    assert comparator.wert_normalisiert == '0.5'

    missing = normalisiere_laborwert(laborwert('Krea', '1.2', None))
    assert missing.status == 'einheit_fehlt'
    assert missing.wert_normalisiert is None


def test_unknown_analyte_is_llm_fallback_candidate_only():
    result = normalisiere_laborwert(laborwert('LaborX-ABC', '7.0', 'mg/l'))
    assert result.status == 'unbekannter_analyt'
    assert result.methode == 'llm_fallback_erforderlich'
    assert result.loinc is None


def test_list_helper_accepts_dicts_from_json():
    values = [laborwert('Glukose', '90', 'mg/dl').model_dump()]
    result = normalisiere_laborwerte(values)
    assert result[0].loinc == '2345-7'
    assert result[0].wert_normalisiert == '90'
