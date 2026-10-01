"""Teilprüfung nach LDT 3.2.15; keine vollständige Konformitätsprüfung.

Objekttabellen: S. 127, 138, 152, 168–169. Regeln: S. 78, 93, 102, 108, 112.
Aufruf aus loesung/: python -m src.ldt_validator DATEI
"""
from dataclasses import dataclass
import hashlib
import re
from datetime import datetime

from .ldt_sparser import LDTDokument, LDTFeld, LDTObjekt, LDTSatz
from .ldt_regeln import SCHEMATA, METADATEN, BERICHT_ERGEBNISSE, BERICHT_REST, pruefe_reihenfolge


# Nur direkte Felder; untergeordnete Objekte werden separat geprüft.
ERLAUBT = {
    "Obj_0060": set("7304 7364 7260 7352 7251 7365 7366 8410 8411 7263 7264 8418 7302 7306 8420 8419 8421 8142 8225 8237 8236 8167 8220 8222 8223 8224 8126 8141 8158 7429 3473 8110".split()),
    "Obj_0042": set("8424 8167 8460 8461 8419 8421 8462 7316 7317 7363 7371 8422 8126".split()),
    "Obj_0010": set("9970 6221 6305 8242 6303 6328 6327 9908 9909 9980 9981".split()),
    "Obj_0068": {"3564", "6329"},
}
PFLICHT = {
    "Obj_0060": {"7304", "7364", "8418", "8141"},
    "Obj_0042": {"8424", "8422"},
    "Obj_0010": {"9970", "6303"},
    "Obj_0068": set(),
}
# Nur objektweit eindeutige Felder, keine wiederholbaren Untergruppen.
EINMAL = {
    "Obj_0060": set("7304 7260 8410 8418 8220 8222 8223 8224 8126 8141 8158 7429 3473".split()),
    "Obj_0042": set("8424 8461 8462 7316 7363 7371 8422 8126".split()),
    "Obj_0010": ERLAUBT["Obj_0010"] - {"9980"},
    "Obj_0068": set(),
}
ATTRIBUTE = {
    "8142": "Obj_0042", "8242": "Obj_0068", "8167": "Obj_0068",
    "8237": "Obj_0068", "8236": "Obj_0068", "8126": "Obj_0026",
    "8141": "Obj_0041", "8158": "Obj_0058", "8110": "Obj_0010",
    **{k: "Obj_0054" for k in ("8220", "8222", "8223", "8224", "8225")},
}
def ist_numerisch(wert):
    # E058 erlaubt auch Exponentialschreibweisen; Vergleichszeichen erhalten.
    return bool(re.fullmatch(
        r"\s*(?:[<>]=?\s*)?[+-]?[0-9]+(?:[.,][0-9]+)?(?:(?:[eE][+-]?[0-9]+)|(?:[x×]10\^[+-]?[0-9]+))?\s*",
        wert,
    ))


FLAGS = set("N H + HH ++ L - LL -- !H !+ !L !- A AA".split())


for _oid, (_felder, _pflicht, _mehrfach) in METADATEN.items():
    ERLAUBT[_oid] = set(_felder.split())
    PFLICHT[_oid] = set(_pflicht.split())
    EINMAL[_oid] = ERLAUBT[_oid] - set(_mehrfach.split())
ATTRIBUTE.update({
    '8132': 'Obj_0032', '8136': 'Obj_0036', '8119': 'Obj_0019',
    '8151': 'Obj_0051', '8218': 'Obj_0054', '8212': 'Obj_0043',
    '8239': 'Obj_0043', '8143': 'Obj_0043', '8147': 'Obj_0047',
    '8122': 'Obj_0022', '8145': 'Obj_0045', '8117': 'Obj_0017',
    '8137': 'Obj_0037', '8135': 'Obj_0035', '8160': 'Obj_0060',
    '8161': 'Obj_0061', '8162': 'Obj_0062', '8163': 'Obj_0063',
    '8155': 'Obj_0055', '8248': 'Obj_0073', '8156': 'Obj_0056',
    '8214': 'Obj_0054', '8215': 'Obj_0054', '8216': 'Obj_0054',
    '8219': 'Obj_0054', '8221': 'Obj_0054', '8154': 'Obj_0054',
    '8235': 'Obj_0047', '8247': 'Obj_0068', '8170': 'Obj_0070',
    '8114': 'Obj_0014', '8240': 'Obj_0014', '8241': 'Obj_0068',
    '8228': 'Obj_0007', '8229': 'Obj_0007', '8230': 'Obj_0007',
    '8131': 'Obj_0031', '8232': 'Obj_0031', '8233': 'Obj_0031',
    '8118': 'Obj_0031', '8169': 'Obj_0069', '8150': 'Obj_0050',
    '8140': 'Obj_0040', '8153': 'Obj_0053', '8127': 'Obj_0027',
})


@dataclass(frozen=True)
class LDTMeldung:
    zeilennummer: int
    objektpfad: str
    feldkennung: str
    regel: str
    beschreibung: str
    schwere: str


@dataclass
class LDTPruefung:
    meldungen: list[LDTMeldung]
    ungepruefte_objekttypen: list[str]
    regelversion: str = "LDT3.2.15"
    vollstaendig: bool = False


def validiere_ldt(dokument: LDTDokument) -> LDTPruefung:
    """Prüft einen dokumentierten Regelausschnitt ohne Daten zu verändern.

    Fremde/fehlende Version: Befunde sind Prüfhinweise gegen 3.2.15,
    keine bestätigten Fehler der deklarierten Version.
    """
    meldungen = []
    ungeprueft = set()
    passend = bool(dokument.versionen) and all(v == "LDT3.2.15" for v in dokument.versionen)

    def melden(feld, pfad, regel, text, kennung=None):
        meldungen.append(LDTMeldung(
            feld.zeilennummer, pfad, kennung or feld.feldkennung, regel, text,
            "Fehler" if passend else "Prüfhinweis",
        ))

    if not passend:
        melden(dokument.saetze[0].beginn, "Dokument", "VERSION",
               "Deklarierte Version fehlt oder weicht von LDT3.2.15 ab; Regeln nur vergleichend angewendet.", "0001")

    satzarten = [s.beginn.wert for s in dokument.saetze]
    if not (len(satzarten) >= 3 and satzarten[0] == "8220"
            and satzarten[-1] == "8221" and all(s == "8205" for s in satzarten[1:-1])):
        melden(dokument.saetze[0].beginn, "Dokument", "SATZFOLGE",
               "Befundpaket erwartet 8220, mindestens einmal 8205, dann 8221 (S. 22).")

    def alle_felder(knoten):
        yield knoten.beginn
        for eintrag in knoten.inhalt:
            if isinstance(eintrag, LDTObjekt):
                yield from alle_felder(eintrag)
            else:
                yield eintrag
        if knoten.ende:
            yield knoten.ende

    sha1 = hashlib.sha1()
    for satz in dokument.saetze:
        for feld in alle_felder(satz):
            if feld.feldkennung == "9300" and feld.wert != sha1.hexdigest():
                melden(feld, "Dokument", "E157", "SHA-1-Prüfsumme stimmt nicht mit den Bytes vor dieser Zeile überein.")
            sha1.update(f"{feld.laenge:03}{feld.feldkennung}".encode("ascii") + feld.rohwert + b"\r\n")
    if satzarten[-1] == "8221":
        pruefsummen = [f for f in dokument.saetze[-1].inhalt if isinstance(f, LDTFeld) and f.feldkennung == "9300"]
        if len(pruefsummen) != 1:
            melden(dokument.saetze[-1].beginn, "8221", "PFLICHTFELD", "Abschluss benötigt genau eine Prüfsumme 9300.", "9300")

    def besuchen(knoten: LDTSatz | LDTObjekt, pfad: str, attribut=None, ergebniswert=None):
        oid = knoten.beginn.wert
        if isinstance(knoten, LDTObjekt) and oid not in ERLAUBT:
            ungeprueft.add(oid)
        if not knoten.inhalt:
            melden(knoten.beginn, pfad, "LEERES_OBJEKT", "Leeres Objekt bzw. leerer Satz ist nicht erlaubt (S. 22–24).")
        for x in knoten.inhalt:
            if isinstance(x, LDTFeld) and not x.wert.strip():
                melden(x, pfad, "LEERES_FELD", "Leerer Feldinhalt; eine zulässige Ausnahme ist nicht implementiert (S. 25).")
        if oid in ERLAUBT:
            felder = [x for x in knoten.inhalt if isinstance(x, LDTFeld)]
            vorhanden = {x.feldkennung for x in felder}
            falsche_folge = pruefe_reihenfolge(felder, SCHEMATA[oid]) if oid in SCHEMATA else []
            if oid == "Obj_0035":
                rest_start = next((i for i, x in enumerate(felder) if x.feldkennung not in BERICHT_ERGEBNISSE), len(felder))
                falsche_folge = pruefe_reihenfolge(felder[rest_start:], BERICHT_REST)
            if falsche_folge:
                melden(falsche_folge[0], pfad, "FELDREIHENFOLGE",
                       "Feld verletzt Reihenfolge, Elternabhängigkeit oder Häufigkeit der Objekttabelle; Folgefelder nicht neu zugeordnet.")
            werte = {x.feldkennung: x.wert for x in felder}
            if oid == "Obj_0060":
                if len(vorhanden & {"7260", "8410"}) != 1:
                    melden(knoten.beginn, pfad, "K106", "Genau ein Testbezug 7260 oder 8410 erforderlich.")
                for eltern, kind in [("8410", "8411"), ("7260", "7365")]:
                    if eltern in vorhanden and kind not in vorhanden:
                        melden(knoten.beginn, pfad, "BEDINGTES_PFLICHTFELD", f"{eltern} verlangt {kind}.", kind)
                if werte.get("7260") == "4" and "7352" not in vorhanden:
                    melden(knoten.beginn, pfad, "K053", "Katalog 4 verlangt URL 7352.", "7352")
                status = werte.get("8418")
                if status and status not in {f"{i:02}" for i in range(1, 13)}:
                    melden(knoten.beginn, pfad, "E007", "Ergebnisstatus muss 01 bis 12 sein.", "8418")
                if status and status not in {"01", "02", "09", "11", "12"} and "8225" not in vorhanden:
                    melden(knoten.beginn, pfad, "K076", "Ergebnisstatus verlangt mindestens einen Messzeitpunkt 8225.", "8225")
                normalwerte = [x for x in knoten.inhalt if isinstance(x, LDTObjekt) and x.beginn.wert == "Obj_0042"]
                spezifikationen = set()
                for normal in normalwerte:
                    for x in normal.inhalt:
                        if isinstance(x, LDTFeld) and x.feldkennung == "8424":
                            if x.wert != "13" and x.wert in spezifikationen:
                                melden(x, pfad, "K054", "Normalwertspezifikation darf hier nur einmal vorkommen (Ausnahme: 13).")
                            spezifikationen.add(x.wert)
            if oid == "Obj_0010" and werte.get("9970") == "999" and "6327" not in vorhanden:
                melden(knoten.beginn, pfad, "K075", "Dokumententyp 999 verlangt Beschreibung 6327.", "6327")
            if oid == "Obj_0019":
                status = [x.wert for x in felder if x.feldkennung == "0204"]
                if not (len(status) in {1, 2} and sum(v in {"1", "2", "3", "4"} for v in status) == 1
                        and (len(status) == 1 or sum(v in {"5", "6"} for v in status) == 1)):
                    melden(knoten.beginn, pfad, "K043", "Ungültige Kombination von Betriebsstättenstatus.", "0204")
                if not vorhanden & {"0200", "0201"}:
                    melden(knoten.beginn, pfad, "K044", "Betriebsstätten-ID oder BSNR fehlt.")
            if oid == "Obj_0022":
                status = {x.wert for x in felder if x.feldkennung == "7321"}
                for regel, trigger, fk in [
                    ("K045", {"03", "04", "05", "06", "08", "11", "12", "14", "16"}, "8147"),
                    ("K046", {"01", "02", "07", "08", "14", "17"}, "8119"),
                    ("K048", {"03", "15", "16"}, "8143"),
                    ("K107", {"01", "02", "07"}, "8114"),
                ]:
                    if status & trigger and fk not in vorhanden:
                        melden(knoten.beginn, pfad, regel, f"Einsenderstatus verlangt {fk}.", fk)
                if status & {"03", "15", "16"} and "8119" in vorhanden:
                    melden(knoten.beginn, pfad, "K047", "Betriebsstätte bei diesem Einsenderstatus nicht erlaubt.", "8119")
            if oid == "Obj_0045":
                for person in knoten.inhalt:
                    if isinstance(person, LDTObjekt) and person.beginn.wert == "Obj_0047":
                        status = [x.wert for x in person.inhalt if isinstance(x, LDTFeld) and x.feldkennung == "7420"]
                        if status != ["12"]:
                            melden(person.beginn, pfad, "K104", "Patient benötigt Personenstatus 12.", "7420")
            if oid == "Obj_0054" and "7279" in vorhanden and "7273" not in vorhanden:
                melden(knoten.beginn, pfad, "BEDINGTES_PFLICHTFELD", "Uhrzeit erfordert Zeitzone.", "7273")
            if oid == "Obj_0035" and not any(isinstance(x, LDTObjekt) and x.beginn.wert in
                    {"Obj_0060", "Obj_0061", "Obj_0062", "Obj_0063", "Obj_0073", "Obj_0055"} for x in knoten.inhalt):
                melden(knoten.beginn, pfad, "K009", "Laborergebnisbericht enthält kein Untersuchungsergebnis.")
            for fk in sorted(PFLICHT[oid] - vorhanden):
                melden(knoten.beginn, pfad, "PFLICHTFELD", f"Pflichtfeld {fk} fehlt.", fk)
            gesehen = set()
            for i, x in enumerate(knoten.inhalt):
                vorher = knoten.inhalt[i - 1] if i else None
                nachher = knoten.inhalt[i + 1] if i + 1 < len(knoten.inhalt) else None
                if isinstance(x, LDTObjekt):
                    if not isinstance(vorher, LDTFeld) or ATTRIBUTE.get(vorher.feldkennung) != x.beginn.wert:
                        melden(x.beginn, pfad, "OBJEKTATTRIBUT", "Objekt ohne passendes unmittelbar vorangehendes Attribut.")
                    continue
                fk = x.feldkennung
                grenzen = {"8410": 20, "8411": 60, "8420": 60, "8421": 60, "8460": 990,
                           "8461": 60, "8462": 60, "7304": 60, "7364": 60, "7358": 60,
                           "6303": 60, "6327": 60, "6329": 990, "3564": 990, "3101": 45, "3102": 45}
                if fk in grenzen and len(x.rohwert) > grenzen[fk]:
                    melden(x, pfad, "FELDLAENGE", f"Feldinhalt überschreitet {grenzen[fk]} Bytes.")
                feste = {"8418": 2, "8419": 1, "8424": 2, "9970": 3, "7278": 8, "7306": 2}
                if fk in feste and len(x.rohwert) != feste[fk]:
                    melden(x, pfad, "FELDLAENGE", f"Feldinhalt muss {feste[fk]} Bytes lang sein.")
                erlaubte_werte = {
                    "8424": ("E052", set("10 11 12 13 20 21 22 23 24 25 26 27 28 30".split())),
                    "9970": ("E053", set("006 010 10A 039 090 091 092 093 094 100 101 102 103 110 120 150 160 200 250 251 252 253 254 255 256 257 258 300 301 400 500 900 999".split())),
                    "8401": ("E006", {"1", "2"}),
                    "7306": ("E058", set("01 02 03 04 05 06 07 08 99".split())),
                }
                if fk in erlaubte_werte:
                    regel, erlaubt = erlaubte_werte[fk]
                    if x.wert not in erlaubt:
                        melden(x, pfad, regel, "Wert ist in der Wertetabelle nicht vorgesehen.")
                if fk == "7278":
                    try:
                        datetime.strptime(x.wert, "%Y%m%d")
                    except ValueError:
                        melden(x, pfad, "F002", "Ungültiges Datum des Timestamp.")
                if fk == "7279":
                    try:
                        if len(x.wert) not in {6, 9} or not x.wert.isascii() or not x.wert.isdigit():
                            raise ValueError()
                        datetime.strptime(x.wert[:6], "%H%M%S")
                    except ValueError:
                        melden(x, pfad, "F016", "Ungültige Uhrzeit des Timestamp.")
                if oid == "Obj_0042" and fk in {"8461", "8462", "7363", "7371"}:
                    if not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", x.wert):
                        melden(x, pfad, "FORMAT_f", "Numerische Grenze benötigt Ganzzahl oder Dezimalzahl mit Punkt (S. 26).")
                if fk not in ERLAUBT[oid]:
                    melden(x, pfad, "FELDPOSITION", f"Feld {fk} ist in {oid} nicht vorgesehen.")
                if fk in EINMAL[oid] and fk in gesehen:
                    melden(x, pfad, "VORKOMMEN", "Feld darf hier objektweit nur einmal vorkommen.")
                gesehen.add(fk)
                if fk in ERLAUBT[oid] and fk in ATTRIBUTE:
                    if not isinstance(nachher, LDTObjekt) or nachher.beginn.wert != ATTRIBUTE[fk]:
                        melden(x, pfad, "OBJEKTATTRIBUT", f"Erwartetes Folgeobjekt {ATTRIBUTE[fk]} fehlt.")
                if oid in {"Obj_0060", "Obj_0042"}:
                    if fk == "8419":
                        hat_einheit = isinstance(nachher, LDTFeld) and nachher.feldkennung == "8421"
                        if x.wert not in {"1", "2", "9"}:
                            melden(x, pfad, "E070", "Einheitensystem muss 1, 2 oder 9 sein.")
                        if (x.wert in {"1", "2"} and not hat_einheit) or (x.wert == "9" and hat_einheit):
                            melden(x, pfad, "K002", "Einheit fehlt für System 1/2 oder ist bei dimensionslosem System 9 vorhanden.")
                    if fk == "8421" and (not isinstance(vorher, LDTFeld) or vorher.feldkennung != "8419"):
                        melden(x, pfad, "K002", "Einheit ohne unmittelbar zugeordnetes Einheitensystem.")
                    if fk in ({"8420"} if oid == "Obj_0060" else {"8461", "8462", "7363", "7371"}):
                        if not isinstance(nachher, LDTFeld) or nachher.feldkennung != "8419":
                            melden(x, pfad, "EINHEITENSYSTEM", "Zum Wert fehlt das bedingt erforderliche Einheitensystem.", "8419")
                if oid == "Obj_0042" and fk == "8422":
                    if x.wert not in FLAGS:
                        melden(x, pfad, "E005", "Unbekannter Grenzwertindikator.")
                    elif ergebniswert is not None:
                        numerisch = ist_numerisch(ergebniswert)
                        erlaubt = FLAGS - {"A", "AA"} if numerisch else {"N", "A", "AA"}
                        if x.wert not in erlaubt:
                            melden(x, pfad, "E005", "Flag passt nicht zum numerischen/nichtnumerischen Ergebniswert.")
                    if x.wert in {"!H", "!+", "!L", "!-"}:
                        if not isinstance(nachher, LDTFeld) or nachher.feldkennung != "8126":
                            melden(x, pfad, "K099", "Extremflag erfordert nachfolgendes Attribut 8126.")
            if oid == "Obj_0042" and not vorhanden & {"8460", "8461", "8462", "7316"}:
                melden(knoten.beginn, pfad, "K055", "Normalwert benötigt Text, Grenze oder Listenbezeichnung.")
            if oid == "Obj_0010" and len(vorhanden & {"6305", "8242"}) != 1:
                melden(knoten.beginn, pfad, "K001", "Genau eine Anhangsquelle 6305 oder 8242 erforderlich.")
            if oid == "Obj_0068" and attribut in {"8242", "8167", "8217", "8236", "8237", "8238"}:
                erwartet, verboten = ("6329", "3564") if attribut == "8242" else ("3564", "6329")
                if erwartet not in vorhanden or verboten in vorhanden:
                    melden(knoten.beginn, pfad, "K100", f"Kontext {attribut} verlangt {erwartet} und verbietet {verboten}.")
        aktueller_wert = None
        for i, x in enumerate(knoten.inhalt):
            if isinstance(x, LDTFeld) and x.feldkennung == "8420":
                aktueller_wert = x.wert
            if isinstance(x, LDTObjekt):
                vorher = knoten.inhalt[i - 1] if i else None
                fk = vorher.feldkennung if isinstance(vorher, LDTFeld) else None
                besuchen(x, f"{pfad}/{x.beginn.wert}@{x.beginn.zeilennummer}", fk,
                         aktueller_wert if x.beginn.wert == "Obj_0042" else None)

    for satz in dokument.saetze:
        if satz.beginn.wert == "8205":
            felder = list(alle_felder(satz))
            if any(x.feldkennung == "8401" and x.wert == "2" for x in felder):
                for x in felder:
                    if x.feldkennung == "8418" and x.wert in {"02", "05", "10"}:
                        melden(x, "8205", "K096", "Abgeschlossener Befund enthält ein vorläufiges/fehlendes Ergebnis.")
            if any(x.feldkennung == "8418" and x.wert == "11" or x.feldkennung == "7368" for x in felder):
                materialien = [x for x in satz.inhalt if isinstance(x, LDTObjekt) and x.beginn.wert == "Obj_0037"]
                if not any(any(isinstance(f, LDTFeld) and f.feldkennung == "8126" for f in m.inhalt) for m in materialien):
                    melden(satz.beginn, "8205", "K082", "Fehlendes/unverwertbares Material verlangt Aufmerksamkeit im Materialobjekt.")
        besuchen(satz, f"{satz.beginn.wert}@{satz.beginn.zeilennummer}")
    return LDTPruefung(meldungen, sorted(ungeprueft))


if __name__ == "__main__":
    import argparse
    import json
    from dataclasses import asdict
    from pathlib import Path
    from .ldt_sparser import LDTParseError, parse_dokument

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datei", type=Path)
    args = parser.parse_args()
    try:
        ergebnis = validiere_ldt(parse_dokument(args.datei.read_bytes()))
    except (OSError, LDTParseError) as exc:
        parser.exit(1, f"Fehler: {exc}\n")
    print(json.dumps(asdict(ergebnis), ensure_ascii=False, indent=2))
    if any(m.schwere == "Fehler" for m in ergebnis.meldungen):
        parser.exit(1)
