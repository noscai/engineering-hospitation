"""Deterministische Extraktion klinisch-chemischer Ergebnisse und Anhänge.

Aufruf: python -m src.ldt_extractor DATEI --output AUSGABEORDNER
Nicht unterstützte Ergebnisarten werden gemeldet, nicht aus Freitext erraten.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from .laborwert_schema import Laborwert, Referenzbereich
from .ldt_sparser import LDTFeld, LDTObjekt, parse_dokument
from .ldt_validator import validiere_ldt


def direkte_felder(objekt):
    return [x for x in objekt.inhalt if isinstance(x, LDTFeld)]


def erster(objekt, fk):
    return next((x.wert for x in direkte_felder(objekt) if x.feldkennung == fk), None)


def referenz(objekt):
    ref = Referenzbereich(spezifikation=erster(objekt, '8424'), untergrenze=None, obergrenze=None,
                          untergrenze_einheit=None, obergrenze_einheit=None, text=[],
                          flag=erster(objekt, '8422'))
    grenze = None
    for x in direkte_felder(objekt):
        if x.feldkennung == '8460':
            ref.text.append(x.wert)
        elif x.feldkennung in {'8461', '8462'}:
            grenze = 'untergrenze' if x.feldkennung == '8461' else 'obergrenze'
            setattr(ref, grenze, x.wert)
        elif x.feldkennung == '8421' and grenze:
            setattr(ref, grenze + '_einheit', x.wert)
        elif x.feldkennung != '8419':
            grenze = None
    return ref


def extrahiere(daten: bytes):
    """Gibt JSON-fähige Daten und getrennte, geprüfte PDF-Bytes zurück.

    Validierungsbefunde bleiben sichtbar. Unzuordenbare Inhalte werden nicht
    auf andere Werte übertragen. Externe Dateiverweise werden nicht geöffnet.
    """
    from dataclasses import asdict
    dokument = parse_dokument(daten)
    pruefung = validiere_ldt(dokument)
    werte, anhaenge, hinweise, pdfs = [], [], [], {}

    def besuche(objekt, pfad, befund_index):
        oid = objekt.beginn.wert
        if oid == 'Obj_0060':
            aktuell = None
            for i, x in enumerate(objekt.inhalt):
                if isinstance(x, LDTFeld) and x.feldkennung == '8420':
                    aktuell = Laborwert(
                        befund_index=befund_index, ergebnis_id=erster(objekt, '7304'),
                        test_ident=erster(objekt, '8410'),
                        analyt=erster(objekt, '8411') or erster(objekt, '7366'), wert=x.wert,
                        einheit=None, einheitensystem=None, referenzen=[],
                        ergebnisstatus=erster(objekt, '8418'), quelle='LDT', seite=None,
                        confidence=None, begruendung='Deterministisch aus LDT-Feld 8420 gelesen.',
                        zeile=x.zeilennummer, objektpfad=pfad,
                    )
                    werte.append(aktuell)
                    # Nur die direkt zu diesem Wert gehörige Einheit auslesen.
                    folgende = objekt.inhalt[i + 1:i + 3]
                    if folgende and isinstance(folgende[0], LDTFeld) and folgende[0].feldkennung == '8419':
                        aktuell.einheitensystem = folgende[0].wert
                        if len(folgende) == 2 and isinstance(folgende[1], LDTFeld) and folgende[1].feldkennung == '8421':
                            aktuell.einheit = folgende[1].wert
                elif isinstance(x, LDTObjekt) and x.beginn.wert == 'Obj_0042':
                    if aktuell is not None:
                        aktuell.referenzen.append(referenz(x))
                    else:
                        hinweise.append({'zeile': x.beginn.zeilennummer, 'code': 'NORMALWERT_OHNE_ERGEBNIS'})
                elif isinstance(x, LDTFeld) and x.feldkennung in {'7306', '8167', '8141', '8158', '8110'}:
                    aktuell = None
        elif oid in {'Obj_0061', 'Obj_0062', 'Obj_0063', 'Obj_0073', 'Obj_0055', 'Obj_0056', 'Obj_0072'}:
            hinweise.append({'zeile': objekt.beginn.zeilennummer, 'code': 'ERGEBNISTYP_NICHT_UNTERSTUETZT', 'objekt': oid})
        elif oid == 'Obj_0010':
            nr = len(anhaenge) + 1
            info = {'nummer': nr, 'befund_index': befund_index, 'zeile': objekt.beginn.zeilennummer,
                    'format': erster(objekt, '6303'), 'datei': None, 'fehler': None}
            anhaenge.append(info)
            if erster(objekt, '6305') is not None:
                info['fehler'] = 'EXTERNER_ANHANG_NICHT_GELESEN'
            else:
                bloecke = []
                for i, x in enumerate(objekt.inhalt):
                    if isinstance(x, LDTObjekt) and x.beginn.wert == 'Obj_0068' and i:
                        vorher = objekt.inhalt[i - 1]
                        if isinstance(vorher, LDTFeld) and vorher.feldkennung == '8242':
                            bloecke.append(x)
                try:
                    if len(bloecke) != 1:
                        raise ValueError('ANHANG_QUELLE_NICHT_EINDEUTIG')
                    felder = direkte_felder(bloecke[0])
                    if not felder or any(x.feldkennung != '6329' for x in felder):
                        raise ValueError('ANHANG_BASE64_KONTEXT_UNGUELTIG')
                    raw = base64.b64decode(b''.join(x.rohwert for x in felder), validate=True)
                    if info['format'] != 'PDF' or not raw.startswith(b'%PDF-'):
                        raise ValueError('ANHANG_KEIN_PDF')
                    reader = PdfReader(BytesIO(raw))
                    if reader.is_encrypted:
                        raise ValueError('PDF_VERSCHLUESSELT')
                    info.update(datei=f'anhang_{nr:03}.pdf', seiten=len(reader.pages),
                                sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
                    pdfs[info['datei']] = raw
                except (ValueError, binascii.Error) as exc:
                    info['fehler'] = str(exc)
                except Exception as exc:
                    # pypdf hat mehrere Fehlerklassen für beschädigte Strukturen.
                    info['fehler'] = f'PDF_UNLESBAR: {type(exc).__name__}'
        for x in objekt.inhalt:
            if isinstance(x, LDTObjekt):
                besuche(x, f'{pfad}/{x.beginn.wert}@{x.beginn.zeilennummer}', befund_index)

    befund_index = 0
    for satz in dokument.saetze:
        if satz.beginn.wert == '8205':
            befund_index += 1
        for objekt in satz.inhalt:
            if isinstance(objekt, LDTObjekt):
                besuche(objekt, f'{satz.beginn.wert}/{objekt.beginn.wert}@{objekt.beginn.zeilennummer}', befund_index)
    result = {'versionen': dokument.versionen, 'laborwerte': [w.model_dump() for w in werte],
              'anhaenge': anhaenge, 'validierung': asdict(pruefung), 'hinweise': hinweise,
              'review_erforderlich': bool(pruefung.meldungen or pruefung.ungepruefte_objekttypen or hinweise
                                         or any(a['fehler'] for a in anhaenge))}
    return result, pdfs


if __name__ == '__main__':
    import argparse
    import json
    from .ldt_sparser import LDTParseError
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('datei', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result, pdfs = extrahiere(args.datei.read_bytes())
        args.output.mkdir(parents=True, exist_ok=True)
        for name, raw in pdfs.items():
            (args.output / name).write_bytes(raw)
        (args.output / 'ergebnis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    except (OSError, LDTParseError) as exc:
        parser.exit(1, f'Fehler: {exc}\n')
    print(f"{len(result['laborwerte'])} Laborwerte, {len(pdfs)} PDFs; Ergebnis: {args.output / 'ergebnis.json'}")
