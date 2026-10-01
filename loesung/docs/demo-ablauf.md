# Demo-Ablauf: Laborbefund-Pipeline 

Ziel der Demo ist, die gesamte Kette einmal sichtbar zu machen: LDT/PDF-Upload,
Extraktion, Normalisierung, Plausibilitätsprüfung, Review-Oberfläche,
Evaluation, Fehleranalyse und nächste Schritte.

## Vorbereitung

Backend starten:

```sh
cd loesung
python3 -m uv run uvicorn src.api:app --reload
```

Frontend starten:

```sh
cd loesung/frontend
npm install
npm run dev
```

Browser öffnen:

```text
http://localhost:5173
```

Eval-Zahlen bei Bedarf neu erzeugen:

```sh
cd loesung
python3 -m uv run python -m src.eval_pdf --output reports/tag2-evaluation.json
```

Mit neuen LLM-Aufrufen, falls gespeicherte Ausgaben fehlen:

```sh
python3 -m uv run python -m src.eval_pdf --run-llm --output reports/tag2-evaluation.json
```

