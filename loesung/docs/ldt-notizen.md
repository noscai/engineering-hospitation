# Lesenotizen zur LDT-Spezifikation

Quelle: [KBV LDT 3.2.15](../../docs/LDT_3.2.15_Spezifikation.pdf).
Seitenangaben beziehen sich auf die PDF-Seiten (entsprechen der gedruckten Nummerierung).
Dies ist eine Arbeitsgrundlage für unseren Parser und Generator, keine vollständige
Implementierung oder Konformitätsprüfung des Standards.

## 1. Zeilen und Zeichensatz (S. 24–27)

Eine Zeile enthält 3 Bytes Länge, 4 Bytes Feldkennung, den Inhalt und CRLF.
Die angegebene Länge ist die Byte-Länge des Inhalts plus neun. Ein Inhalt kann
höchstens 990 Bytes lang sein; feldspezifische Grenzen können kleiner sein.

Beispiel: `01380008220\r\n` enthält FK `8000` mit Inhalt `8220`.
Die 13 Bytes umfassen auch die zwei Bytes des Zeilenendes.

LDT 3.2.15 schreibt **ISO-8859-15** vor (Abschnitt 6.6, S. 27).
Für diese Version brauchen wir keine heuristische Encoding-Erkennung.
Erst Bytes und Längen prüfen, danach mit `iso8859-15` dekodieren.
Leere oder ausschließlich mit Leerzeichen gefüllte Felder sind grundsätzlich
verboten; Ausnahmen müssen ausdrücklich in Feld-/Regeltabellen stehen.

Der Typ `f` verlangt einen Dezimalpunkt (S. 26). FK `8420` ist dagegen
alphanumerisch (S. 69). Daher darf eine Dezimalkomma-Variation im Ergebnis
nicht pauschal auf numerisch typisierte Referenzgrenzen übertragen werden.

## 2. Sätze und Objekte (S. 22–24, 34–35)

Ein Labor-Befundpaket besteht aus `8220` (Header), mindestens einem `8205`
(Befund) und `8221` (Abschluss), in dieser Reihenfolge.

| Feldkennung | Bedeutung |
| --- | --- |
| `8000` | Satzbeginn; Inhalt ist die Satzart |
| `8001` | Satzende; Inhalt muss zur Satzart passen |
| `8002` | Objektbeginn; Inhalt ist die Objekt-ID |
| `8003` | Objektende; Inhalt muss zur Objekt-ID passen |
| `8100`–`8299` | Bereich für Objektattribute, die nachfolgende Objekte einleiten |

Die Satz-/Objekttabellen definieren erlaubte Felder, Anordnung, Häufigkeiten
und Abhängigkeiten. Die eingerückten Vorkommensstufen sind relevant, auch
innerhalb eines Objekts. Ein einfaches Dictionary pro Feldkennung verliert
Wiederholungen und Zuordnungen.

`M` bedeutet unbedingt erforderlich, `m` bedingt erforderlich, `K` optional
und `k` bedingt optional. Leere Objekte sind nicht erlaubt.

Implementierungsfolge: Satz-/Objektgrenzen mit einem Stack prüfen;
danach Feldpositionen, Vorkommen und Kontextregeln separat validieren.
Ein bekannter Feldcode an einer unzulässigen Stelle bleibt ein gemeldeter Fehler.

## 3. Laborwerte (S. 69–70, 152, 168–169)

Für klinisch-chemische Ergebnisse ist `Obj_0060` zuständig. Darin stehen
unter anderem Ergebnis-ID `7304`, Probengefäß-ID `7364` und Ergebnisstatus
`8418`. Mehrere Ergebnisse `8420` sind möglich: nicht einfach den letzten behalten.

| Feldkennung | Bedeutung | Quelle |
| --- | --- | --- |
| `8410` | Test-Ident / lokales Kürzel | S. 69 |
| `8411` | Testbezeichnung | S. 69 |
| `8418` | Ergebnisstatus | S. 69, E007 ab S. 78 |
| `7306` | Darstellung der Ergebniswerte | Objektzuordnung S. 168 |
| `8420` | Ergebnis-Wert, alphanumerisch | S. 69 |
| `8419` | Einheitensystem | S. 69, E070 S. 93 |
| `8421` | Maßeinheit | S. 69 |
| `8142` | Leitet ein Normalwert-Objekt `Obj_0042` ein | S. 168 |
| `8424` | Normalwertspezifikation | S. 70, 152 |
| `8460` | Normalwert-Text | S. 70 |
| `8461` / `8462` | Untere / obere Normalwertgrenze | S. 70 |
| `8422` | Grenzwertindikator, bei diesem Ergebnistyp im Normalwert-Objekt | S. 152 |

Einheiten können auch an Referenzgrenzen stehen (S. 152). Sie dürfen nicht
versehentlich die Einheit des Messergebnisses überschreiben.
Andere Ergebnistypen besitzen andere Tabellen: beispielsweise steht `8422`
bei `Obj_0073` in einem anderen Kontext (S. 183).

### Relevante Regeln

- **K002, S. 102:** `8419=1` (SI) oder `2` (abweichend) verlangt `8421`.
  Bei `8419=9` (dimensionslos) ist `8421` verboten. Fehlende Einheit ist
  deshalb nicht bei jedem Ergebnis automatisch ein Fehler.
- **E005, S. 78:** Numerische Flags: `N`, `H`, `+`, `HH`, `++`, `L`, `-`,
  `LL`, `--`, `!H`, `!+`, `!L`, `!-`. Nichtnumerisch: `N`, `A`, `AA`.
  `H`, `L` und `+` aus der Aufgabe sind also ausdrücklich erlaubt.
- **K099, S. 112:** Bei extremen Flags (`!H`, `!+`, `!L`, `!-`) muss
  `8126` mit einem Fehlermeldung-/Aufmerksamkeitsobjekt folgen.
- **K055, S. 108:** Im Normalwert-Kontext muss mindestens eines der Felder
  `8460`, `8461`, `8462` oder `7316` vorhanden sein.
- **S. 70:** Wenn kein Normalbereich angegeben werden kann, ist `k.A.` in
  `8460` vorgesehen. Das gesamte Normalwert-Objekt ist in `Obj_0060` ein
  Kann-Objekt (S. 168); fehlendes Objekt und leeres Objekt unterscheiden.
- **K054, S. 108:** Mehrere Normalwert-Objekte unterliegen Regeln für die
  Wiederholung der Normalwertspezifikation; nicht blind zusammenführen.

## 4. Eingebettete PDFs (S. 102, 112, 127, 138)

Struktur eines eingebetteten Anhangs:

```text
8110 Anhang
  8002 Obj_0010
    9970 Dokumententyp
    8242 base64-kodierte_Anlage
      8002 Obj_0068
        6329 Base64-Teil 1
        6329 Base64-Teil 2 ...
      8003 Obj_0068
    6303 Dateiformat (z. B. PDF)
  8003 Obj_0010
```

Dies ist eine Strukturskizze ohne Längenpräfixe, keine vollständige LDT-Datei.

K001 verlangt entweder einen externen Dateiverweis `6305` oder `8242`.
K100 bestimmt: Unter `8242` enthält `Obj_0068` Base64-Felder `6329`, keine
Textfelder `3564`. Bei den in K100 genannten Freitextattributen gilt das
umgekehrte Verhältnis.

Für die Extraktion nur die `6329`-Inhalte des jeweiligen Anhangs in
Dateireihenfolge zusammenfügen, strikt Base64-dekodieren und anschließend
Dateiformat und tatsächlichen PDF-Inhalt prüfen. Mehrere Anhänge getrennt
behandeln; nicht alle Base64-Zeilen einer Datei global zusammenfügen.

## 5. Abgleich mit der gelieferten Beispieldatei

In `Z01_UseCase05_Befund_mitPDF.ldt`, Zeilen 240–258:

- `8410`: `HBs-Ag`, `8411`: `Hepatitis B Antigen`
- `8420`: `247.6`, `8419`: `2`, `8421`: `Einheit`
- Normalwert-Objekt: Grenzen `30.0` und `100.0`, Flag `++`

`Einheit` ist der tatsächliche Platzhalter aus der Testdatei. Daraus dürfen
wir keine konkrete medizinische Einheit erfinden.
Ab Zeile 363 steht ein Anhang mit `Obj_0010`, `8242`, `Obj_0068` und vielen
`6329`-Zeilen; am Ende folgt `6303=PDF`.
Das wird inzwischen durch `src/ldt_extractor.py` objektbezogen extrahiert:
die `6329`-Zeilen werden pro Anhang zusammengefuehrt, Base64-dekodiert und
als PDF auf Lesbarkeit geprueft.

**Versionsabweichung:** Alle sechs gelieferten LDT-Dateien deklarieren in
`0001` die Version `LDT3.2.19`. Die beigefügte Spezifikation beschreibt
3.2.15; E001 auf S. 78 nennt entsprechend `LDT3.2.15`.
Eine Abweichung von unseren 3.2.15-Regeln beweist bei diesen Dateien noch
keinen Laborfehler. Versionskonflikte separat melden; keine vollstaendige
3.2.19-Konformitaet behaupten. Die KBV-Beispiele werden deshalb verarbeitet
und mit 3.2.15-Hinweisen versehen, aber nicht als 3.2.19-konform bewertet.

## 6. Umsetzung fuer Tag 1

Die gelesenen Spezifikationsstellen wurden fuer Tag 1 in vier Bausteine
ueberfuehrt:

1. `src/ldt_sparser.py` prueft den Zeilenrahmen, dekodiert ISO-8859-15 unter
   Erhalt der Rohbytes und baut die Satz-/Objekthierarchie mit Zeilennummern.
2. `src/ldt_validator.py` meldet Feldpositionen, Pflichtfelder, Vorkommen,
   Wertebereiche, Datums-/Zeitformate, Satzfolge und die SHA-1-Pruefsumme `9300`.
3. `src/ldt_extractor.py` liest klinisch-chemische Werte aus `Obj_0060` mit
   Einheiten, Referenzbereichen, Flags und Herkunftspfad aus und extrahiert
   eingebettete PDFs.
4. `src/generate_dataset.py` erzeugt 18 synthetische Gold/LDT/PDF-Paare mit
   festem Seed; `src/check_tag1.py` gleicht die gespeicherten Artefakte gegen
   Gold und gegen die eingebetteten PDFs ab.

Der synthetische Datensatz enthaelt 18 Befunde, 144 Laborwerte, drei PDF-Layouts,
drei mehrseitige PDFs und drei absichtlich fehlerhafte LDT-Dateien. Die Fehler
werden gemeldet und nicht automatisch repariert. Der Generator nutzt keine echten
Patientendaten, keine LLM-generierten Messwerte und keine KBV-Dateien als Vorlage.

Nicht abgedeckte Objekttypen werden ausgewiesen; `vollstaendig` bleibt `false`.
Bei fehlender oder abweichender Version werden Regelverletzungen nur als
Pruefhinweise gegen 3.2.15 gemeldet. Die aktuelle Grenze der Umsetzung steht
in `loesung/README.md`.


### Erweiterte Validierung

Implementiert sind geordnete Vorkommenshierarchien fuer die verwendeten
klinischen, Anhangs- und Metadatenobjekte in `src/ldt_regeln.py`, Satzfolge
fuer Befundpakete (S. 22), SHA-1 ueber die Originalbytes vor 9300 (E157,
S. 98), K053/K054 (S. 108), K075 (S. 109), K076 (S. 110), K106 (S. 113),
numerische Grenzformate und E005 mit Bezug zum jeweiligen Ergebniswert.
Weitere implementierte Kontextregeln sind in der eigenen README aufgefuehrt.
Vollstaendige Standardkonformitaet wird weiterhin nicht behauptet.
