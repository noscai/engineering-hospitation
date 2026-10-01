from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LDTFeld:
    zeilennummer: int
    laenge: int
    feldkennung: str
    rohwert: bytes

    @property
    def wert(self) -> str:
        """Text gemäß LDT 3.2.15, Abschnitt 6.6; Rohbytes bleiben erhalten."""
        return self.rohwert.decode("iso8859-15")


@dataclass
class LDTObjekt:
    beginn: LDTFeld
    inhalt: list[LDTFeld | LDTObjekt] = field(default_factory=list)
    ende: LDTFeld | None = None


@dataclass
class LDTSatz:
    beginn: LDTFeld
    inhalt: list[LDTFeld | LDTObjekt] = field(default_factory=list)
    ende: LDTFeld | None = None


@dataclass
class LDTDokument:
    saetze: list[LDTSatz]
    versionen: list[str]
    hinweise: list[str]


class LDTParseError(ValueError):
    pass

def parse_ldt(daten: bytes) -> list[LDTFeld]:
    """Prüft den Zeilenrahmen, noch keine fachlichen Feld-/Objektregeln.

    Die dreistellige Länge zählt Bytes einschließlich Header und CRLF.
    Werte bleiben bis zur expliziten Zeichensatzauswertung als Bytes erhalten.
    """
    if not daten:
        raise LDTParseError("Leere LDT-Datei")

    felder = []
    for nummer, zeile in enumerate(daten.splitlines(keepends=True), start=1):
        prefix = f"Zeile {nummer}: "
        if not zeile.endswith(b"\r\n"):
            raise LDTParseError(prefix + "Zeilenende CRLF fehlt")
        if len(zeile) < 9:
            raise LDTParseError(prefix + "Zeile kürzer als Header und CRLF")
        if not zeile[:3].isdigit():
            raise LDTParseError(prefix + "Länge muss aus drei Ziffern bestehen")
        laenge = int(zeile[:3])
        if laenge != len(zeile):
            raise LDTParseError(
                prefix + f"Länge deklariert {laenge}, tatsächlich {len(zeile)} Bytes"
            )
        if not zeile[3:7].isdigit():
            raise LDTParseError(prefix + "Feldkennung muss aus vier Ziffern bestehen")
        felder.append(LDTFeld(nummer, laenge, zeile[3:7].decode("ascii"), zeile[7:-2]))
    return felder


def lese_ldt(pfad: str | Path) -> list[LDTFeld]:
    return parse_ldt(Path(pfad).read_bytes())


def parse_dokument(daten: bytes) -> LDTDokument:
    """Erhält Reihenfolge und Wiederholungen und prüft Satz-/Objektgrenzen.

    Noch keine Prüfung von Satzfolge, Pflichtfeldern, Objektattributen oder
    erlaubten Feldpositionen. Abweichende Versionen werden nur ausgewiesen.
    """
    felder = parse_ldt(daten)
    saetze: list[LDTSatz] = []
    stapel: list[LDTObjekt] = []
    satz: LDTSatz | None = None
    versionen: list[str] = []
    hinweise: list[str] = []

    for feld in felder:
        kennung, wert = feld.feldkennung, feld.wert
        prefix = f"Zeile {feld.zeilennummer}: "
        if kennung == "8000":
            if satz is not None:
                raise LDTParseError(prefix + "Neuer Satz vor Abschluss des vorherigen Satzes")
            satz = LDTSatz(feld)
            saetze.append(satz)
            continue
        if satz is None:
            raise LDTParseError(prefix + f"Feld {kennung} außerhalb eines Satzes")

        if kennung == "8001":
            if stapel:
                raise LDTParseError(prefix + f"Satzende bei offenem Objekt {stapel[-1].beginn.wert}")
            if wert != satz.beginn.wert:
                raise LDTParseError(prefix + f"Satzende {wert}, erwartet {satz.beginn.wert}")
            satz.ende = feld
            satz = None
        elif kennung == "8002":
            objekt = LDTObjekt(feld)
            eltern = stapel[-1] if stapel else satz
            eltern.inhalt.append(objekt)
            stapel.append(objekt)
        elif kennung == "8003":
            if not stapel:
                raise LDTParseError(prefix + "Objektende ohne Objektbeginn")
            objekt = stapel[-1]
            if wert != objekt.beginn.wert:
                raise LDTParseError(prefix + f"Objektende {wert}, erwartet {objekt.beginn.wert}")
            objekt.ende = feld
            stapel.pop()
        else:
            eltern = stapel[-1] if stapel else satz
            eltern.inhalt.append(feld)
            if kennung == "0001":
                versionen.append(wert)
                if wert != "LDT3.2.15":
                    hinweise.append(
                        prefix + f"Version {wert}; vorliegende Spezifikation: LDT3.2.15. "
                        "Versionskonformität nicht geprüft."
                    )

    if stapel:
        beginn = stapel[-1].beginn
        raise LDTParseError(f"Dateiende: Objekt {beginn.wert} aus Zeile {beginn.zeilennummer} nicht geschlossen")
    if satz is not None:
        raise LDTParseError(f"Dateiende: Satz {satz.beginn.wert} aus Zeile {satz.beginn.zeilennummer} nicht geschlossen")
    return LDTDokument(saetze, versionen, hinweise)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datei", type=Path)
    args = parser.parse_args()
    try:
        dokument = parse_dokument(args.datei.read_bytes())
    except (OSError, LDTParseError) as exc:
        parser.exit(1, f"Fehler: {exc}\n")
    print(f"{args.datei.name}: {len(dokument.saetze)} Sätze; Zeilen und Satz-/Objektgrenzen geprüft")
    for hinweis in dokument.hinweise:
        print(f"Hinweis: {hinweis}")
