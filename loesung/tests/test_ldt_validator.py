from copy import deepcopy
import hashlib
from pathlib import Path

from src.ldt_sparser import parse_dokument
from src.ldt_validator import validiere_ldt


def dokument(objekt, felder, attribut='8142', version='LDT3.2.15'):
    # Strukturfixture für die Teilprüfung, kein vollständiger Standardbefund.
    paare = [('8000', '8220'), ('0001', version), ('8001', '8220'),
             ('8000', '8205'), (attribut, 'Test'),
             ('8002', objekt), *felder, ('8003', objekt), ('8001', '8205'), ('8000', '8221')]
    daten = b''
    for fk, wert in paare:
        inhalt = wert.encode('iso8859-15')
        daten += f'{len(inhalt)+9:03}{fk}'.encode() + inhalt + b'\r\n'
    daten += b'0499300' + hashlib.sha1(daten).hexdigest().encode() + b'\r\n01380018221\r\n'
    return parse_dokument(daten)


def regeln(doc):
    # Diese Fixtures prüfen einzelne Objekte, keinen vollständigen Befundrahmen.
    return {m.regel for m in validiere_ldt(doc).meldungen
            if '/' in m.objektpfad or m.regel in {'E157', 'SATZFOLGE', 'VERSION'}}


NORMAL = [('8424', '20'), ('8461', '1'), ('8419', '2'), ('8421', 'mg/dl'),
          ('8462', '2'), ('8419', '2'), ('8421', 'mg/dl'), ('8422', 'N')]


def test_reference_units_can_repeat_without_duplicate_error():
    doc = dokument('Obj_0042', NORMAL)
    vorher = deepcopy(doc)
    assert not regeln(doc)
    assert doc == vorher
    assert not validiere_ldt(doc).vollstaendig


def test_unit_cannot_be_borrowed_from_next_reference_limit():
    felder = [x for i, x in enumerate(NORMAL) if i != 3]
    result = validiere_ldt(dokument('Obj_0042', felder))
    assert any(m.regel == 'K002' and m.feldkennung == '8419' for m in result.meldungen)


def test_dimensionless_value_does_not_require_unit():
    felder = [('8424', '20'), ('8461', '1'), ('8419', '9'), ('8422', 'N')]
    assert not regeln(dokument('Obj_0042', felder))
    felder.insert(3, ('8421', 'mg/dl'))
    assert 'K002' in regeln(dokument('Obj_0042', felder))


def test_wrong_position_missing_required_and_duplicate_fields():
    result = validiere_ldt(dokument('Obj_0060', [('8422', 'H'), ('7304', 'a'), ('7304', 'b')], '8160'))
    assert {'FELDPOSITION', 'PFLICHTFELD', 'VORKOMMEN'} <= {m.regel for m in result.meldungen}
    wrong = next(m for m in result.meldungen if m.regel == 'FELDPOSITION' and 'Obj_0060' in m.objektpfad)
    assert wrong.zeilennummer == 7
    assert 'Obj_0060' in wrong.objektpfad
    assert wrong.schwere == 'Fehler'


def test_flags_and_reference_content():
    assert 'E005' in regeln(dokument('Obj_0042', NORMAL[:-1] + [('8422', '???')]))
    assert 'K099' in regeln(dokument('Obj_0042', NORMAL[:-1] + [('8422', '!H')]))
    assert 'K055' in regeln(dokument('Obj_0042', [('8424', '20'), ('8422', 'N')]))


def test_attachment_source_and_base64_context():
    base = [('9970', '100'), ('6303', 'PDF')]
    assert 'K001' in regeln(dokument('Obj_0010', base, '8110'))
    content = [('8242', 'base64-kodierte_Anlage'), ('8002', 'Obj_0068'),
               ('6329', 'YWJj'), ('8003', 'Obj_0068')]
    assert not regeln(dokument('Obj_0010', base[:1] + content + base[1:], '8110'))
    wrong = [('3564', 'YWJj') if fk == '6329' else (fk, wert) for fk, wert in content]
    assert 'K100' in regeln(dokument('Obj_0010', base + wrong, '8110'))
    assert 'K001' in regeln(dokument('Obj_0010', base + content + [('6305', 'x.pdf')], '8110'))
    assert 'OBJEKTATTRIBUT' in regeln(dokument('Obj_0010', base + [('8242', 'base64-kodierte_Anlage')], '8110'))


def test_foreign_version_does_not_claim_confirmed_errors():
    result = validiere_ldt(dokument('Obj_0042', [], version='LDT3.2.19'))
    assert 'VERSION' in {m.regel for m in result.meldungen}
    assert all(m.schwere == 'Prüfhinweis' for m in result.meldungen)


def test_kbv_files_report_version_and_uncovered_objects():
    paths = list((Path(__file__).resolve().parents[2] / 'data/ldt/kbv-testdaten').glob('*.ldt'))
    assert len(paths) == 6
    for path in paths:
        result = validiere_ldt(parse_dokument(path.read_bytes()))
        assert not result.vollstaendig
        assert result.ungepruefte_objekttypen
        assert all(m.schwere == 'Prüfhinweis' for m in result.meldungen)
        assert 'VERSION' in {m.regel for m in result.meldungen}


def test_order_and_parent_dependencies():
    assert 'FELDREIHENFOLGE' in regeln(dokument('Obj_0042', list(reversed(NORMAL))))
    assert 'FELDREIHENFOLGE' in regeln(dokument('Obj_0042', [('8424', '20'), ('8419', '9'), ('8422', 'N')]))
    assert 'FELDREIHENFOLGE' in regeln(dokument('Obj_0042', NORMAL[:-1] + [('8419', '9'), NORMAL[-1]]))


def test_decimal_point_and_empty_fields():
    felder = [('8461', '1,5') if fk == '8461' else (fk, wert) for fk, wert in NORMAL]
    assert 'FORMAT_f' in regeln(dokument('Obj_0042', felder))
    assert 'LEERES_FELD' in regeln(dokument('Obj_0042', [('8424', ' '), ('8460', 'k.A.'), ('8422', 'N')]))


def test_conditional_requirements():
    assert 'K075' in regeln(dokument('Obj_0010', [('9970', '999'), ('6305', 'a.pdf'), ('6303', 'PDF')], '8110'))
    assert 'K075' not in regeln(dokument('Obj_0010', [('9970', '999'), ('6305', 'a.pdf'), ('6303', 'PDF'), ('6327', 'Sonstiges')], '8110'))
    result = regeln(dokument('Obj_0060', [('7260', '4'), ('8418', '06')], '8160'))
    assert {'K053', 'K076', 'BEDINGTES_PFLICHTFELD'} <= result
    assert 'K106' in regeln(dokument('Obj_0060', [], '8160'))


def test_checksum_detects_mutation_and_packet_order_is_checked():
    doc = dokument('Obj_0042', NORMAL)
    assert 'E157' not in regeln(doc)
    # Mutation ohne Neuberechnung der Prüfsumme.
    doc.saetze[1].inhalt.clear()
    assert 'E157' in regeln(doc)
    doc.saetze.reverse()
    assert 'SATZFOLGE' in regeln(doc)


def test_numeric_flag_and_duplicate_reference_specifications():
    normal = [('8142', 'Normalwert'), ('8002', 'Obj_0042'),
              ('8424', '20'), ('8460', 'k.A.'), ('8422', 'AA'), ('8003', 'Obj_0042')]
    felder = [('7304', 'x'), ('7364', 'p'), ('8410', 'Test'), ('8411', 'Test'),
              ('8418', '01'), ('7306', '01'), ('8420', '1.5'), ('8419', '9'), *normal, *normal]
    assert {'E005', 'K054'} <= regeln(dokument('Obj_0060', felder, '8160'))
    text = [('8420', 'positiv') if fk == '8420' else (fk, wert) for fk, wert in felder]
    assert 'E005' not in regeln(dokument('Obj_0060', text, '8160'))
