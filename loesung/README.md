# Lösung – Laborbefunde aus LDT und PDF

Hier liegt unsere Lösung zur [ursprünglichen Aufgabenstellung](../README.md).
Wir arbeiten bewusst im Ordner `loesung/`, damit die Originaldateien unangetastet bleiben.
Die KBV-Testdaten und die Spezifikation liegen weiter unter `data/` und `docs/`.
Alle eigenen Befunde sind synthetisch; echte Patientendaten werden nicht verwendet.

## Schnellstart

### Setup

Im Verzeichnis `loesung/` ausführen (Python 3 mit pip vorausgesetzt):

```sh
python3 -m pip install --user uv
python3 -m uv sync --locked
touch .env
python3 -m uv run pytest
python3 -m uv run python -m src.check_tag1
```

uv stellt Python 3.12 und `.venv` bereit; `uv.lock` fixiert die Abhängigkeiten.
In der IDE `loesung/.venv/bin/python` wählen. Für LLM-Läufe werden API-Key,
Provider-URL und Modellnamen lokal in `.env` gesetzt. Die Datei bleibt privat
und wird nicht versioniert.

## Tag 1: LDT lesen und Testdaten bauen

- LDT-Zeilenrahmen und Byte-Längen prüfen, ISO-8859-15 dekodieren.
- Satz-/Objektgrenzen prüfen; Reihenfolge, Wiederholungen und Quellzeilen erhalten.
- Relevante Feldpositionen, Vorkommenshierarchien, Pflichtfelder, Werte und
  Kontextregeln prüfen; Abweichungen mit Regel und Fundstelle melden.
- Klinisch-chemische Laborwerte aus `Obj_0060` samt Referenzbereichen und Flags
  extrahieren. Rohwerte einschließlich Komma und Vergleichszeichen bleiben erhalten.
- Eingebettete PDFs objektweise Base64-dekodieren und auf Lesbarkeit prüfen.
- 18 Gold/LDT/PDF-Paare deterministisch erzeugen und gegenprüfen.

Die Regelprüfung deckt den für unsere Lösung relevanten Teil des LDT-Standards ab.
Sie ist keine KBV-Zertifizierung. Details und Grenzen stehen unten und in den
[Lesenotizen](docs/ldt-notizen.md).



| Datei | Aufgabe |
| --- | --- |
| `src/ldt_sparser.py` | Zeilen und verschachtelte Sätze/Objekte lesen |
| `src/ldt_regeln.py` | Nachgeschlagene Feldhierarchien und Objekttabellen |
| `src/ldt_validator.py` | Validierung mit Regel, Objektpfad und Zeilennummer |
| `src/ldt_extractor.py` | Laborwertmodelle, Extraktion, Anhangsprüfung und CLI |
| `src/laborwert_schema.py` | Gemeinsames Pydantic-Schema für LDT- und PDF-Laborwerte |
| `src/pdf_llm_extractor.py` | PDF-Extraktion per LLM Structured Output |
| `src/normalizer.py` | Deterministische LOINC- und Einheiten-Normalisierung |
| `src/plausibility.py` | Plausibilitätsregeln und LDT/PDF-Widerspruchsprüfung |
| `src/eval_pdf.py` | Evaluation von PDF-Extraktion und Normalisierung gegen Gold |
| `src/generate_dataset.py` | Gold zuerst, dann LDT und PDF erzeugen |
| `src/check_tag1.py` | Gespeicherte Artefakte gegen Gold prüfen, KBV-PDFs extrahieren |

### Nachvollziehbare Prüfzahlen

Ergebnis von `python3 -m uv run python -m src.check_tag1`:

| Prüfung | Ergebnis |
| --- | ---: |
| Synthetische Befunde | 18 |
| Laborwerte | 144 |
| PDF-Layouts | 3 (je 6 Befunde) |
| Mehrseitige Befunde | 3 (insgesamt 21 Seiten) |
| Zusätzliche Scan-Simulationen | 3 |
| Absichtlich fehlerhafte LDTs | 3, alle erwarteten Fehler erkannt |
| Unerwartete Abweichungen im Gold-Abgleich | 0 |
| KBV-Dateien verarbeitet | 6 |
| KBV-PDFs extrahiert | 5 |
| Klinisch-chemische Werte aus KBV-Dateien | 8 |

Der [Prüfbericht](reports/tag1-pruefung.json) enthält die Ergebnisse je Befund.
Der Abgleich prüft Werte, Einheiten, Referenzen und Flags sowie die bytegenaue
Gleichheit zwischen eingebettetem und separat gespeichertem PDF. Der PDF-Text
wird auf der im Gold angegebenen Seite nach Analyt, Wert und Einheit geprüft;
das ist keine Messung einer unabhängigen PDF-Extraktion. Die Tests überprüfen
zusätzlich byteidentische Neugenerierung in zwei getrennten Verzeichnissen.
**Diese Zahlen sind Tag-1-Konsistenzprüfungen, und keine LLM-Evaluation.**

### Einzelnen Befund verarbeiten

```sh
python3 -m uv run python -m src.ldt_extractor ../data/ldt/kbv-testdaten/Z01_UseCase05_Befund_mitPDF.ldt --output data/extrahiert/Z01_UseCase05_Befund_mitPDF
```

Ausgabe: `ergebnis.json` und `anhang_001.pdf`. Alle sechs KBV-Ergebnisse und
fünf PDFs sind bereits unter [data/extrahiert](data/extrahiert) abgelegt.
PDF-Dateinamen werden lokal vergeben; externe LDT-Dateipfade werden nicht geöffnet.
Mehrere Anhänge werden getrennt behandelt. Ungültige Base64-Daten, beschädigte
PDFs oder unbekannte Ergebnisarten werden gemeldet, nicht still ergänzt.

Nur die Validierung ausführen:

```sh
python3 -m uv run python -m src.ldt_validator data/synthetisch/SYN-016/befund.ldt
```

Der absichtlich fehlerhafte Befund liefert K002 und Exitcode 1. Bei fremder oder
fehlender Version bleiben Abweichungen Prüfhinweise; die JSON-Ausgabe muss also
auch bei Exitcode 0 gelesen werden. `vollstaendig: false` bedeutet ausdrücklich,
dass nicht der gesamte Standard implementiert ist. Ungeprüfte Objekttypen werden
aufgelistet, und `review_erforderlich` signalisiert Befunde mit Prüfmeldungen,
unbekannten Objekttypen, nicht unterstützten Ergebnissen oder Anhangsfehlern.

### Synthetischer Datensatz

[data/synthetisch](data/synthetisch) enthält pro `SYN-001` bis `SYN-018`:
`gold.json`, `befund.ldt` und `befund.pdf`. `SYN-004`, `SYN-011` und `SYN-017`
enthalten zusätzlich `befund_scan.pdf` als verschmutzte Bild-PDF. Das Manifest
enthält Layouts, Seitenzahlen, Fehlerfälle und SHA-256-Prüfsummen.

```sh
python3 -m uv run python -m src.generate_dataset
python3 -m uv run python -m src.check_tag1
```

Der Generator verwendet Seed `20260928`, Decimal-Arithmetik, feste Metadaten
und reproduzierbare PDF-Ausgaben. Er verwendet keine KBV-Stammdaten als Vorlage
und keine LLM-generierten Zahlen. Die synthetischen Referenzbereiche sind
Testfixtures und keine klinischen Empfehlungen.

Enthaltene Varianten:

- Tabellen, Fließtext und zwei Spalten; SYN-006, SYN-012 und SYN-018 mit zwei Seiten.
- Krea/Kreatinin, HbA1c/Hämoglobin A1c, GPT/ALT und weitere Kürzel.
- mg/dl/µmol/l, mg/dl/mmol/l, Prozent/mmol/mol sowie weitere Einheiten.
- Dezimalkomma, `<` und `>`, Flags H/L/+, fehlende Referenzen mit `k.A.` im LDT.
- Ablenkender Schulungstext „Glukose 999 mg/dl“, ausdrücklich kein Messwert.
- Drei zusätzliche Scan-Simulationen als Bild-PDF mit leichter Rotation und Rauschen.
- SYN-016: fehlende Ergebniseinheit → K002.
- SYN-017: zusätzliches Flag direkt im Ergebnisobjekt → FELDPOSITION.
- SYN-018: doppelte Ergebnis-ID im selben Objekt → VORKOMMEN.

Die letzten zwei Fehler lösen zusätzlich einen Reihenfolgefehler aus. Gold und PDF
enthalten den beabsichtigten Befund; bei den drei negativen Fällen wird nur das LDT
gezielt verändert. `absichtliche_fehler` dokumentiert diese Ausnahme. Insbesondere
wird die fehlende LDT-Einheit bei SYN-016 nicht aus dem PDF oder Referenzbereich
„repariert“. Die Scan-PDFs sind Zusatzartefakte; LDT und Gold verweisen weiter
auf die sauberen PDFs, damit der deterministische Gold-Abgleich stabil bleibt.

### Entscheidungen und Grenzen

- Parsing, Datengenerierung und LDT-Validierung sind deterministisch. Ein LLM wird
  dafür nicht benötigt. Normalisierung, Plausibilitätsprüfung und PDF-Extraktion
  sind in den späteren Schritten ergänzt.
- Die eigenen Dateien deklarieren LDT 3.2.15. Alle gelieferten KBV-Dateien nennen
  3.2.19; die beiliegende Spezifikation beschreibt 3.2.15. Versionsabhängige
  Abweichungen sind daher keine bestätigten Laborfehler der KBV-Dateien.
- Die Regelprüfung deckt die verwendeten Satzarten, klinisch-chemischen Ergebnisse,
  Normalwerte, Anhänge sowie die Metadatenobjekte der synthetischen Befunde ab.
  Feldzugehörigkeit und Reihenfolge werden auch dort geprüft. Implementierte
  Kontextregeln umfassen K001/K002/K009/K043–K048/K053/K054/K055/K075/K076/
  K082/K096/K099/K104/K106/K107; dazu relevante Wertetabellen, Datums-/Zeitformate,
  Feldlängen und E157. Es ist keine vollständige Umsetzung aller Abrechnungs-,
  Spezialfachgebiets- und Kontextregeln des 186-seitigen Standards.
- Allgemeine Leerfeldprüfungen melden auch Fälle, deren spezielle Ausnahmeregel
  noch nicht implementiert ist. Solche Befunde müssen geprüft werden.
- Mikrobiologie, Zytologie, sonstige Untersuchungsergebnisse und Blutgruppen
  werden nicht in numerische Laborwerte umgedeutet. Nicht unterstützte Typen
  sind im Ergebnis sichtbar; Anhänge werden trotzdem extrahiert.
- Der Parser beendet die Verarbeitung bei beschädigten Zeilen-/Objektgrenzen.
  Fachliche Befunde werden gesammelt; Werte werden mit Herkunft und Meldungen
  ausgegeben, nicht als automatisch freigegebene medizinische Ergebnisse.
- Die Testdaten können die implementierten Regeln prüfen, ersetzen aber keine
  unabhängige KBV-Konformitätsprüfung. Die PDF-Renderer sind bisher durch
  Seiten-/Textprüfungen geprüft, nicht durch eine manuelle visuelle Abnahme.

Danach haben wir die PDF-Extraktion, Normalisierung, Plausibilitätsregeln,
Evaluation, API und Review-Oberfläche ergänzt. Der aktuelle Stand ist getestet
und die wichtigsten Ergebnisse sind hier zusammengefasst.

## Tag 2: PDF, LLM, Normalisierung und Evaluation

An Tag 2 ging es darum, Werte aus PDFs zu extrahieren, sie auf ein gemeinsames
Schema zu bringen, fachlich zu prüfen und die Varianten messbar zu vergleichen.

### PDF-Extraktion
`src/laborwert_schema.py` definiert das gemeinsame Pydantic-Schema für LDT-
und PDF-Ergebnisse: Analyt wie gedruckt, Wert, Einheit, Referenzbereich, Flag,
Seite, Confidence und Begründung. Fehlende Angaben werden als `null` oder leere
Listen modelliert, damit das Modell nichts erfinden muss.

`src/pdf_llm_extractor.py` liest den PDF-Text seitenweise mit `pypdf`. Für die
LLM-Aufrufe nutzen wir OpenRouter über die OpenAI-kompatible Schnittstelle. Das
Modell ist per `.env` austauschbar. Für den Vergleich sind Claude und Gemini

Der Code versucht zuerst Structured Output direkt über das Pydantic-Modell. Wenn
der Provider das nicht unterstützt, nutzt er einen strikt schema-gebundenen
Tool-Call. Das Modell soll nur extrahieren: keine Normalisierung, keine
Umrechnung und keine erfundenen Werte.


### Normalisierung

`src/normalizer.py` normalisiert die bekannten Tag-1-Analyte deterministisch:
laborinterne Kürzel und Synonyme werden auf einen kanonischen Analyt, einen
LOINC-Code und eine Zieleinheit gemappt. Werte bleiben als Original erhalten;
zusätzlich wird ein normalisierter Zahlenwert berechnet, wenn Analyt, Einheit
und numerischer Wert eindeutig sind.

| Analyt | Synonyme/Kürzel | LOINC | Zieleinheit |
| --- | --- | --- | --- |
| Kreatinin | Krea, Kreatinin | 2160-0 | mg/dl |
| Glukose | Glucose, Glukose | 2345-7 | mg/dl |
| HbA1c | HbA1c, Hämoglobin A1c | 4548-4 | % |
| ALT | GPT, ALT | 1742-6 | U/l |
| Natrium | Na, Natrium | 2951-2 | mmol/l |
| Kalium | K, Kalium | 2823-3 | mmol/l |
| CRP | CRP, C-reaktives Protein | 1988-5 | mg/l |
| TSH | TSH, Thyreotropin | 3016-3 | mU/l |

Die Normalisierung ist absichtlich deterministisch. Synonyme, LOINC-Codes und
Umrechnungsfaktoren sollen nachvollziehbar und reproduzierbar bleiben. Ein LLM
soll hier keine Codes oder Faktoren erfinden. Für unbekannte Kürzel wäre ein LLM
nur als Vorschlaggeber sinnvoll; übernommen würde ein Vorschlag erst nach einer
Änderung der Mappingtabelle. Unbekannte Analyte werden deshalb mit
`llm_fallback_erforderlich` markiert.

Nützlicher Befehl:

```sh
python3 -m uv run python -m src.normalizer data/synthetisch/SYN-001/pdf_llm.json --output data/synthetisch/SYN-001/pdf_normalisiert.json
```

## Plausibilitätsregeln

`src/plausibility.py` prüft aktuell vier regelbasierte Klassen:

- Wert ausserhalb des Referenzbereichs und Laborflag passt nicht dazu.
- Physiologisch unmögliche Werte anhand grober, bewusst konservativer Grenzen.
- Einheit passt nicht zum Analyt bzw. ist nicht in der deterministischen Tabelle freigegeben.
- LDT und eingebettetes PDF widersprechen sich nach Normalisierung.

Die Regeln sind absichtlich deterministisch: Sie sollen reproduzierbare
Review-Hinweise erzeugen und keine medizinische Diagnose stellen. Für den
LDT/PDF-Vergleich wird nach Ergebnis-ID gematcht, falls vorhanden; sonst nur bei
eindeutigem kanonischem Analyt. Numerische Vergleiche verwenden eine kleine
Toleranz, damit Rundungsdifferenzen aus Einheitenumrechnungen nicht als
Widerspruch zaehlen.

Nützliche Befehle:

```sh
python3 -m uv run python -m src.ldt_extractor data/synthetisch/SYN-001/befund.ldt --output data/synthetisch/SYN-001/ldt_extract

python3 -m uv run python -m src.plausibility data/synthetisch/SYN-001/ldt_extract/ergebnis.json --pdf-json data/synthetisch/SYN-001/pdf_llm.json --output data/synthetisch/SYN-001/plausibilitaet.json
```

## Evaluation

`src/eval_pdf.py` vergleicht PDF-Extraktion und Normalisierung gegen `gold.json`.
Gemessen werden Precision/Recall je Feld (`analyt`, `wert`, `einheit`,
`referenz`, `flag`, `seite` und Exact Match für Wert+Einheit) sowie für die
Normalisierung (`loinc`, `ziel_einheit`). Der Report enthält Gesamtzahlen und
Details pro Befund.

Verglichene Varianten:

| Variante | Befunde | Wert+Einheit P/R | LOINC P/R | Zieleinheit P/R | Flag P/R | Fehleranalyse |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `regel_text_pdf` | 18 | 0.8125 / 0.8125 | 0.8125 / 0.8125 | 0.8125 / 0.8125 | 0.8125 / 0.8125 | 27 fehlend, 27 zusätzlich |
| `llm_structured_text` (Claude Text) | 18 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | keine |
| `llm_structured_alt_model` (Gemini Text) | 18 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 0.8750 / 0.8750 | 18 Flag-Abweichungen |
| `scan_ocr_llm` (OCR-Pipeline) | 3 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | keine Downstream-Fehler nach OCR-Simulation |
| `scan_vision_llm` (Claude Vision, direkter Bild-Input) | 3 | 0.8750 / 0.8750 | 0.9583 / 0.9583 | 0.9583 / 0.9583 | 0.9583 / 0.9583 | 1 fehlend, 1 zusätzlich, 2 Einheitenfehler |
| Gemini Vision (getestet, nicht bewertet) | 0 | nicht bewertet | nicht bewertet | nicht bewertet | nicht bewertet | erkannte Werte, lieferte aber über OpenRouter wechselnde Stringlisten statt stabiler Laborwert-Objekte |

```sh
# gespeicherte Ausgaben auswerten
python3 -m uv run python -m src.eval_pdf --output reports/tag2-evaluation.json

# fehlende LLM-Ausgaben neu erzeugen und danach auswerten
python3 -m uv run python -m src.eval_pdf --run-llm --output reports/tag2-evaluation.json
```

Der aktuelle [Eval-Report](reports/tag2-evaluation.json) enthält Claude als
Hauptmodell und Gemini als zweites Textmodell. Beide liefen auf allen 18
Befunden. Gemini extrahiert Werte, Einheiten, LOINC und Zieleinheiten korrekt,
weicht aber bei 18 Flags ab. Deshalb zeigen wir Flag als eigene Metrik.
`SYN-018` wurde mit der kurzen Prompt-Variante extrahiert, weil der Standardlauf
bei diesem zweitseitigen Befund hängen blieb.

Fehleranalyse:

- `regel_text_pdf`: 27 fehlende und 27 zusätzliche Werte. Ursache ist das
  zweispaltige Layout: Die einfache Regex-Baseline liest umbrochene Zeilen und
  Spalten nicht stabil genug. Tabellen- und einfache Fliesstextbefunde gelingen.
- `llm_structured_text`: Auf allen 18 Befunden keine Feldfehler. Der
  Ablenkungstext `Glukose 999 mg/dl` wird ignoriert. Beim zweitseitigen
  `SYN-018` war die kurze Prompt-Variante stabiler als der Standardprompt.
- `scan_ocr_llm` ist die OCR-Pipeline: Die drei verschmutzten Scan-PDFs laufen durch die Kette
  `befund_scan.pdf -> OCR -> Structured LLM Extraction -> Normalisierung ->
  Plausibilitaet/Eval`. Lokal ist kein Tesseract installiert; deshalb erzeugt
  `src/scan_ocr.py` für die selbst generierten Scan-PDFs eine deterministische
  OCR-Simulation aus den Gold-Daten. Wenn Tesseract verfügbar ist, nutzt das
  Modul echte OCR über gerenderte PDF-Seiten. Die aktuellen Zahlen messen also
  die Downstream-Kette nach OCR, nicht die Qualität einer realen OCR-Engine.
- `scan_vision_llm` ist direkter Bild-Input an ein multimodales LLM. Claude Vision
  wurde auf den drei Scan-PDFs erfolgreich evaluiert. Die Fehler entstehen aus
  echter Bildinterpretation: ein Wert fehlt, ein zusätzlicher Wert wird gelesen,
  zwei Einheiten weichen ab und ein Referenzbereich wird falsch strukturiert.
  Damit ist der Ansatz als Alternative zur OCR-Pipeline messbar, aber aktuell
  schwächer als Text-PDF und OCR-Simulation.
- Gemini Vision wurde ebenfalls getestet. Das Modell erkannte die Laborwerte in
  den Scanbildern grundsätzlich, lieferte über OpenRouter aber nicht stabil die
  erwartete schema-konforme Tool-Struktur. Mehrfach kam `laborwerte` als Liste
  von Strings zurück, z. B. `Krea Wert 1,0 Einheit mg/dl Referenzbereich ...`,
  statt als Liste von Laborwert-Objekten mit `analyt`, `wert`, `einheit`,
  `referenzen`, `flag` und `seite`. Einige dieser Formate konnten deterministisch
  nachstrukturiert werden, die Ausgabeform wechselte aber zwischen Läufen. Deshalb
  wurde Gemini Vision als getestete, aber nicht fair reproduzierbar bewertbare
  Bild-Input-Variante dokumentiert; die finalen Vision-Zahlen stammen von Claude
  Vision.
- Normalisierung: Wenn die PDF-Extraktion stimmt, stimmen LOINC und Zieleinheit
  für die bekannten Testanalyte deterministisch. Fehler entstehen daher zuerst
  durch verfehlte oder zusätzliche PDF-Werte, nicht durch die Mappingtabelle.

Scan-Beispiel:

```sh
python3 -m uv run python -m src.scan_ocr data/synthetisch/SYN-004/befund_scan.pdf --output data/synthetisch/SYN-004/scan_ocr.json

python3 -m uv run python -m src.eval_pdf --run-llm --output reports/tag2-evaluation.json
```

## Tag 3: API, Review-Oberfläche und Demo

Für Tag 3 haben wir eine kleine FastAPI und eine React-Oberfläche gebaut. Die
API nimmt LDT- oder PDF-Dateien an und gibt geprüfte Werte zurück. LDT-Dateien
laufen durch Parser, Regelprüfung, Normalisierung und Plausibilität. PDFs laufen
entweder durch die regelbasierte Baseline oder, mit LLM-Haken, durch Text-LLM
oder Vision-LLM. Eingebettete PDFs werden für die Anzeige extrahiert.

| Datei | Aufgabe |
| --- | --- |
| `src/api.py` | FastAPI-App für Upload, geprüfte Befundwerte, PDF-Anzeige und Speichern von Review-Fällen |
| `src/pdf_vision_extractor.py` | Scan-/Bild-PDFs als PNG rendern und per Vision-LLM in das gemeinsame Laborwertschema extrahieren |
| `src/eval_pdf.py` | Variantenvergleich inkl. Claude Text, Gemini Text, OCR-Pipeline und Claude Vision |
| `reports/tag2-evaluation.json` | aktueller Eval-Report mit Precision/Recall, Fehleranalyse und verwendeten Modellen |
| `tests/test_api.py` | API-Verhalten für LDT/PDF-Upload und Review-Fall-Speicherung |
| `tests/test_pdf_vision_extractor.py` | Rendering-Test für Scan-PDF-Seiten als Vision-Input |

Für Scan-PDFs rendert `src/pdf_vision_extractor.py` die Seiten mit PyMuPDF als
PNG-Bilder und schickt sie an ein multimodales Modell. In der App übernimmt also
Claude Vision die OCR-Rolle. Gemini Vision wurde auch getestet, lieferte über
OpenRouter aber keine stabil genug schema-konforme Tool-Struktur. Tesseract
bleibt nur als Vergleichs- oder Fallback-Pipeline in `src/scan_ocr.py`.

```env
LLM_VISION_MODEL=anthropic/claude-sonnet-4
```

Backend starten:

```sh
python3 -m uv run uvicorn src.api:app --reload
```

Die Review-UI liegt unter `frontend/`. Sie lädt LDT- oder PDF-Dateien hoch,
zeigt das Befund-PDF links und die extrahierten Werte rechts. Quelle, Confidence
und Review-Status sind sichtbar. Auffällige Werte werden hervorgehoben und
können bestätigt oder korrigiert werden. Gespeicherte Korrekturen landen unter
`data/review_cases/<case_id>/review_case.json` und können später als neue
Eval-/Gold-Fälle übernommen werden.

Was beim Upload passiert:

- LDT: `src.ldt_extractor` liest klinisch-chemische `Obj_0060`-Werte,
  validiert die LDT-Struktur, extrahiert eingebettete PDFs und gibt zusätzlich
  Normalisierung und Plausibilitätsmeldungen zurück. Andere Ergebnisarten wie
  Humangenetik/`Obj_0073` werden sichtbar als nicht unterstützter Ergebnistyp
  gemeldet und nicht künstlich in numerische Laborwerte umgedeutet.
- PDF ohne LLM-Haken: Die regelbasierte Baseline `regel_text_pdf` extrahiert
  Werte aus dem PDF-Text. Das ist schnell und lokal, aber bei zweispaltigen
  Layouts schwächer.
- PDF mit LLM-Haken: Bei Text-PDFs läuft `src.pdf_llm_extractor` mit Structured
  Output. Bei Scan-/Bild-PDFs ohne extrahierbaren Text läuft automatisch
  `src.pdf_vision_extractor` mit direktem Bild-Input an das Vision-LLM.
- Danach laufen alle Werte durch dieselbe Normalisierung und Plausibilitätsprüfung,
  damit LDT-, Text-PDF- und Bild-PDF-Ergebnisse vergleichbar bleiben.

### Frontend: Aufbau und Ablauf

Das Frontend ist einfach aufgebaut. Es nutzt Vite, React und
TypeScript, aber keine zusätzliche UI-Library. Die Logik liegt in `main.tsx`,
das Styling in `styles.css`. Dadurch bleibt der Review-Flow leicht zu lesen.

| Datei | Aufgabe |
| --- | --- |
| `frontend/package.json` | npm-Skripte und Frontend-Abhängigkeiten (`react`, `react-dom`, `vite`, `typescript`) |
| `frontend/package-lock.json` | fixierte npm-Auflösung für reproduzierbare Installation |
| `frontend/index.html` | HTML-Einstiegspunkt mit `#root` für React |
| `frontend/vite.config.ts` | Vite-Konfiguration, React-Plugin, Dev-Port `5173` und Proxy zur FastAPI auf `127.0.0.1:8000` |
| `frontend/tsconfig.json` | strikte TypeScript-Konfiguration für React/DOM-Code |
| `frontend/src/vite-env.d.ts` | Typisierung für `VITE_API_BASE_URL` |
| `frontend/src/main.tsx` | komplette Review-Anwendung: Upload, API-Aufruf, PDF-Anzeige, Wertetabelle, Korrekturstatus und Speichern |
| `frontend/src/styles.css` | responsive Oberfläche, Hell/Dunkel-Farben, Tabellen-, Status- und Review-Hervorhebungen |

Der Dev-Server nutzt standardmäßig den Vite-Proxy. Requests an `/befunde`,
`/review` und `/health` werden an die FastAPI weitergeleitet. Dadurch kann das
Frontend lokal mit relativen Pfaden arbeiten. Für andere Setups kann
`VITE_API_BASE_URL` gesetzt werden; dann ruft die UI die API direkt über diese
Basis-URL auf.

Der Ablauf in `frontend/src/main.tsx` ist:

1. Die Nutzerin wählt eine `.ldt`, `.ldtx` oder `.pdf` aus.
2. Der Schalter `PDF per LLM` steuert den Query-Parameter `use_llm` für
   `/befunde/extrahieren`. Bei PDF-Dateien bedeutet das: Text-PDF per Structured
   LLM oder Scan-PDF per Vision-LLM. Bei LDT-Dateien bleibt die LDT-Extraktion
   deterministisch.
3. Die API-Antwort wird als `ApiResult` typisiert. Enthalten sind `laborwerte`,
   `normalisierte_laborwerte`, `plausibilitaet`, optionale LDT-Validierung und
   eine `pdf_url` für die Anzeige.
4. Die linke Seite zeigt das Befund-PDF im `iframe`, wenn ein PDF vorhanden ist.
   Bei LDT-Dateien ist das das eingebettete extrahierte PDF; bei PDF-Uploads die
   hochgeladene Datei.
5. Die rechte Seite zeigt die extrahierten Werte. Quelle, Analyt, Wert, Einheit,
   Referenz/Flag, Confidence und Review-Status sind sichtbar. Werte mit niedriger
   Confidence oder Plausibilitäts-/Validierungsmeldungen werden hervorgehoben.
6. Jede Zeile kann bestätigt oder korrigiert werden. Änderungen an Analyt, Wert
   oder Einheit setzen die Zeile automatisch auf `corrected`.
7. `Korrekturen speichern` sendet die bestätigten oder korrigierten Zeilen an
   `POST /review/faelle`. Das Backend schreibt daraus einen Review-Fall unter
   `data/review_cases/<case_id>/review_case.json`, der später als neuer Eval- oder
   Gold-Fall übernommen werden kann.

Die UI ist ein Review-Werkzeug. Sie macht Auffälligkeiten sichtbar, korrigiert
aber nichts automatisch. Korrekturen bleiben als Review-Daten nachvollziehbar
gespeichert.


## Demo

Für die Demo gibt es einen einfachen Ablauf in [docs/demo-ablauf.md](docs/demo-ablauf.md). 
