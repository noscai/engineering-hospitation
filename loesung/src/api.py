"""FastAPI-Endpunkte fuer Review-UI und Uploads."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .eval_pdf import regel_text_pdf
from .ldt_extractor import extrahiere as extrahiere_ldt
from .ldt_sparser import LDTParseError
from .normalizer import normalisiere_laborwerte
from .pdf_llm_extractor import extrahiere_pdf_mit_llm, pdf_seitentexte
from .pdf_vision_extractor import extrahiere_pdf_bild_mit_llm
from .plausibility import pruefe_befund

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(tempfile.gettempdir()) / 'hospitation-review'
PDF_DIR = RUNTIME / 'pdfs'
REVIEW_CASES = ROOT / 'data/review_cases'


class UploadAntwort(BaseModel):
    document_id: str
    dateiname: str
    dateityp: Literal['LDT', 'PDF']
    pdf_url: str | None
    laborwerte: list[dict]
    normalisierte_laborwerte: list[dict]
    plausibilitaet: dict
    validierung: dict | None = None
    anhaenge: list[dict] = Field(default_factory=list)
    hinweise: list[dict | str] = Field(default_factory=list)
    review_erforderlich: bool


class ReviewCorrection(BaseModel):
    index: int
    original: dict
    corrected: dict
    status: Literal['confirmed', 'corrected']


class SaveReviewRequest(BaseModel):
    dateiname: str
    dateityp: Literal['LDT', 'PDF']
    laborwerte: list[dict]
    corrections: list[ReviewCorrection] = Field(default_factory=list)


app = FastAPI(title='Laborbefund Review API', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _typ(name: str, content_type: str | None, data: bytes):
    lower = name.lower()
    if data.startswith(b'%PDF-') or lower.endswith('.pdf') or content_type == 'application/pdf':
        return 'PDF'
    if lower.endswith(('.ldt', '.ldtx')) or data[:3].isdigit():
        return 'LDT'
    raise HTTPException(status_code=415, detail='Nur LDT- oder PDF-Dateien werden unterstuetzt.')


def _store_pdf(document_id: str, raw: bytes):
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = PDF_DIR / f'{document_id}.pdf'
    path.write_bytes(raw)
    return f'/befunde/{document_id}/pdf'


def _response(document_id, dateiname, dateityp, values, plaus, *, pdf_url=None, validierung=None, anhaenge=None, hinweise=None):
    return UploadAntwort(
        document_id=document_id,
        dateiname=dateiname,
        dateityp=dateityp,
        pdf_url=pdf_url,
        laborwerte=values,
        normalisierte_laborwerte=[x.model_dump() for x in normalisiere_laborwerte(values)],
        plausibilitaet=plaus,
        validierung=validierung,
        anhaenge=anhaenge or [],
        hinweise=hinweise or [],
        review_erforderlich=bool(plaus['review_erforderlich'] or (validierung and validierung.get('meldungen'))),
    )


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/befunde/{document_id}/pdf')
def pdf(document_id: str):
    path = PDF_DIR / f'{document_id}.pdf'
    if not path.exists():
        raise HTTPException(status_code=404, detail='PDF nicht gefunden.')
    return FileResponse(path, media_type='application/pdf', filename=f'{document_id}.pdf')


@app.post('/befunde/extrahieren', response_model=UploadAntwort)
async def befunde_extrahieren(
    file: UploadFile = File(...),
    use_llm: bool = Query(False, description='PDF per LLM Structured Output extrahieren. Bei Scan-PDFs automatisch als Vision/OCR-LLM.'),
    prompt: Literal['standard', 'kurz'] = 'kurz',
):
    raw = await file.read()
    dateiname = file.filename or 'upload'
    dateityp = _typ(dateiname, file.content_type, raw)
    document_id = uuid4().hex
    try:
        if dateityp == 'LDT':
            result, pdfs = extrahiere_ldt(raw)
            pdf_url = _store_pdf(document_id, next(iter(pdfs.values()))) if pdfs else None
            values = result['laborwerte']
            plaus = pruefe_befund(values).model_dump()
            return _response(
                document_id, dateiname, 'LDT', values, plaus, pdf_url=pdf_url,
                validierung=result['validierung'], anhaenge=result['anhaenge'], hinweise=result['hinweise'],
            )
        if use_llm:
            seiten = pdf_seitentexte(raw)
            hat_text = any(str(seite.get('text') or '').strip() for seite in seiten)
            extraction = extrahiere_pdf_mit_llm(raw, prompt_variante=prompt) if hat_text else extrahiere_pdf_bild_mit_llm(raw)
        else:
            with tempfile.NamedTemporaryFile(suffix='.pdf') as tmp:
                tmp.write(raw)
                tmp.flush()
                extraction = regel_text_pdf(Path(tmp.name))
        values = [x.model_dump() for x in extraction.laborwerte]
        plaus = pruefe_befund(values).model_dump()
        return _response(
            document_id, dateiname, 'PDF', values, plaus, pdf_url=_store_pdf(document_id, raw),
            hinweise=extraction.hinweise,
        )
    except LDTParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post('/review/faelle')
def save_review_case(payload: SaveReviewRequest):
    case_id = uuid4().hex
    target = REVIEW_CASES / case_id
    target.mkdir(parents=True, exist_ok=True)
    data = payload.model_dump()
    data['case_id'] = case_id
    data['quelle'] = 'review_ui'
    (target / 'review_case.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return {'case_id': case_id, 'pfad': str(target / 'review_case.json')}
