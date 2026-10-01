import unittest
from pathlib import Path

from src.ldt_sparser import LDTParseError, lese_ldt, parse_ldt, parse_dokument


def ldt_bytes(*felder):
    zeilen = []
    for kennung, wert in felder:
        inhalt = wert.encode("iso8859-15")
        zeilen.append(f"{len(inhalt) + 9:03}{kennung}".encode("ascii") + inhalt + b"\r\n")
    return b"".join(zeilen)


class LDTParserTests(unittest.TestCase):
    def test_field_and_raw_non_ascii_value(self):
        feld = parse_ldt(b"0133101M\xfcll\r\n")[0]
        self.assertEqual(feld.feldkennung, "3101")
        self.assertEqual(feld.rohwert, b"M\xfcll")
        self.assertEqual(feld.zeilennummer, 1)

    def test_iso8859_15_preserves_raw_bytes(self):
        feld = parse_ldt(ldt_bytes(("3564", "Müller: 5 €")))[0]
        self.assertEqual(feld.wert, "Müller: 5 €")
        self.assertIn(b"\xa4", feld.rohwert)

    def test_nested_objects_keep_units_and_repeated_values_separate(self):
        daten = ldt_bytes(
            ("8000", "8205"), ("8160", "UE_Klinische_Chemie"),
            ("8002", "Obj_0060"), ("8420", "1.2"), ("8421", "mg/dl"),
            ("8142", "Normalwert"), ("8002", "Obj_0042"),
            ("8461", "40"), ("8421", "µmol/l"), ("8003", "Obj_0042"),
            ("8420", "1.3"), ("8003", "Obj_0060"), ("8001", "8205"),
        )
        dokument = parse_dokument(daten)
        satz = dokument.saetze[0]
        ergebnis = satz.inhalt[1]
        normalwert = ergebnis.inhalt[3]
        self.assertEqual(ergebnis.inhalt[1].wert, "mg/dl")
        self.assertEqual(normalwert.inhalt[1].wert, "µmol/l")
        self.assertEqual(ergebnis.inhalt[4].wert, "1.3")
        self.assertEqual(normalwert.beginn.zeilennummer, 7)
        self.assertEqual(satz.ende.zeilennummer, 13)

    def test_invalid_boundaries(self):
        cases = [
            ([("8410", "HB")], "Zeile 1.*außerhalb"),
            ([("8000", "8205"), ("8000", "8205")], "Zeile 2.*Neuer Satz"),
            ([("8000", "8205"), ("8001", "8221")], "Zeile 2.*erwartet 8205"),
            ([("8000", "8205"), ("8003", "Obj_0060")], "Zeile 2.*ohne Objektbeginn"),
            ([("8000", "8205"), ("8002", "Obj_0060"), ("8003", "Obj_0042")], "Zeile 3.*erwartet Obj_0060"),
            ([("8000", "8205"), ("8002", "Obj_0060"), ("8001", "8205")], "Zeile 3.*offenem Objekt"),
            ([("8000", "8205")], "Dateiende.*Satz.*Zeile 1"),
            ([("8000", "8205"), ("8002", "Obj_0060")], "Dateiende.*Objekt.*Zeile 2"),
        ]
        for felder, meldung in cases:
            with self.subTest(felder=felder), self.assertRaisesRegex(LDTParseError, meldung):
                parse_dokument(ldt_bytes(*felder))

    def test_version_difference_is_reported_separately(self):
        for version, anzahl in [("LDT3.2.15", 0), ("LDT3.2.19", 1)]:
            dokument = parse_dokument(ldt_bytes(
                ("8000", "8220"), ("8132", "Kopfdaten"),
                ("8002", "Obj_0032"), ("0001", version),
                ("8003", "Obj_0032"), ("8001", "8220"),
            ))
            self.assertEqual(dokument.versionen, [version])
            self.assertEqual(len(dokument.hinweise), anzahl)

    def test_invalid_records_are_rejected(self):
        for daten in (
            b"", b"01380008220\n", b"01480008220\r\n",
            b"abc80008220\r\n", b"0138x008220\r\n", b"\r\n",
        ):
            with self.subTest(daten=daten), self.assertRaises(LDTParseError):
                parse_ldt(daten)

    def test_error_identifies_line(self):
        with self.assertRaisesRegex(LDTParseError, "Zeile 2"):
            parse_ldt(b"01380008220\r\n0098000\n")

    def test_all_supplied_kbv_files(self):
        root = Path(__file__).resolve().parents[1]
        dateien = list((root.parent / "data/ldt/kbv-testdaten").glob("*.ldt"))
        self.assertEqual(len(dateien), 6)
        for pfad in dateien:
            with self.subTest(datei=pfad.name):
                felder = lese_ldt(pfad)
                self.assertEqual(felder[0].feldkennung, "8000")
                self.assertEqual(sum(f.laenge for f in felder), pfad.stat().st_size)
                dokument = parse_dokument(pfad.read_bytes())
                self.assertEqual(dokument.saetze[0].beginn.wert, "8220")
                self.assertEqual(dokument.saetze[-1].ende.wert, "8221")
                self.assertEqual(dokument.versionen, ["LDT3.2.19"])
                self.assertEqual(len(dokument.hinweise), 1)
