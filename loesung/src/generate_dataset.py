"""18 deterministische Gold/LDT/PDF-Paare; keine LLM-Aufrufe.

python -m src.generate_dataset --output data/synthetisch
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from textwrap import wrap

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from PIL import Image, ImageDraw, ImageFont

SEED = 20260928
SCAN_IDS = {'SYN-004': -1.6, 'SYN-011': 1.2, 'SYN-017': -0.9}
ANALYTE = [
    ('Kreatinin', ['Krea', 'Kreatinin'], [('mg/dl', '0.6', '1.2'), ('µmol/l', '53', '106')]),
    ('Glukose', ['Glucose', 'Glukose'], [('mg/dl', '70', '100'), ('mmol/l', '3.9', '5.6')]),
    ('HbA1c', ['HbA1c', 'Hämoglobin A1c'], [('%', '4.0', '5.7'), ('mmol/mol', '20', '39')]),
    ('ALT', ['GPT', 'ALT'], [('U/l', '10', '50')]),
    ('Natrium', ['Na', 'Natrium'], [('mmol/l', '135', '145')]),
    ('Kalium', ['K', 'Kalium'], [('mmol/l', '3.5', '5.1')]),
    ('CRP', ['CRP', 'C-reaktives Protein'], [('mg/l', '0', '5')]),
    ('TSH', ['TSH', 'Thyreotropin'], [('mU/l', '0.4', '4.0')]),
]


def gold_befunde():
    rng = random.Random(SEED)
    for n in range(1, 19):
        gold = {'id': f'SYN-{n:03}', 'synthetisch': True, 'seed': SEED,
                'ldt_version': 'LDT3.2.15', 'datum': '20260928',
                'patient': {'nachname': f'Musterpatient-{n:03}', 'vorname': 'Synthetisch', 'geburt': '19800101'},
                'layout': ['tabelle', 'fliesstext', 'zweispaltig'][(n - 1) % 3],
                'seiten': 2 if n % 6 == 0 else 1,
                'kommentar': 'Nur synthetische Testdaten. Beispiel im Schulungstext: Glukose 999 mg/dl ist KEIN Messwert dieses Befunds.',
                'laborwerte': [], 'absichtliche_fehler': []}
        for i, (kanonisch, namen, einheiten) in enumerate(ANALYTE):
            unit, low, high = einheiten[(n + i) % len(einheiten)]
            lo, hi = Decimal(low), Decimal(high)
            factor = Decimal(rng.randint(-3, 14)) / Decimal(10)
            value = max(Decimal('0.1'), lo + (hi - lo) * factor).quantize(Decimal('0.1'))
            flag = ('+' if n % 2 == 0 else 'H') if value > hi else ('L' if value < lo else 'N')
            comparator = '<' if i == 6 and n % 2 == 0 else ('>' if i == 7 and n % 3 == 0 else '')
            if comparator == '<':
                value, flag = Decimal('0.5'), 'N'
            elif comparator == '>':
                value, flag = Decimal('10.0'), 'H'
            value_text = str(value)
            if n % 2 == 0:
                value_text = value_text.replace('.', ',')
            gold['laborwerte'].append({
                'ergebnis_id': f'SYN-{n:03}-E{i+1:02}', 'analyt_kanonisch': kanonisch,
                'test_ident': namen[(n + i) % len(namen)], 'analyt': namen[(n + i) % len(namen)],
                'wert': comparator + value_text, 'einheit': unit,
                'referenz': None if (n + i) % 5 == 0 else {'untergrenze': low, 'obergrenze': high},
                'flag': flag, 'material': 'EDTA-Blut' if kanonisch == 'HbA1c' else 'Serum', 'seite': 2 if gold['seiten'] == 2 and i >= 4 else 1,
            })
        # Absichtliche Fehler
        if n == 16:
            gold['absichtliche_fehler'] = [{'typ': 'fehlende_einheit', 'ergebnis_id': gold['laborwerte'][0]['ergebnis_id'], 'regel': 'K002'}]  # Einheit fehlt
        elif n == 17:
            gold['absichtliche_fehler'] = [{'typ': 'flag_an_falscher_stelle', 'ergebnis_id': gold['laborwerte'][0]['ergebnis_id'], 'regel': 'FELDPOSITION'}]  # Flag steht falsch
        elif n == 18:
            gold['absichtliche_fehler'] = [{'typ': 'doppelte_ergebnis_id', 'ergebnis_id': gold['laborwerte'][0]['ergebnis_id'], 'regel': 'VORKOMMEN'}]  # Ergebnis-ID doppelt
        yield gold


def pdf_rendern(gold):
    stream = BytesIO()
    c = Canvas(stream, pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle(f"Synthetischer Laborbefund {gold['id']}")
    width, height = A4
    for seite in range(1, gold['seiten'] + 1):
        c.setFont('Helvetica-Bold', 16)
        c.drawString(40, height - 45, f"Laborbefund {gold['id']}")
        c.setFont('Helvetica', 10)
        c.drawString(40, height - 65, f"{gold['patient']['vorname']} {gold['patient']['nachname']} | 28.09.2026")
        c.drawString(40, height - 82, 'Fiktiver Testbefund - nicht zur medizinischen Verwendung')
        rows = [x for x in gold['laborwerte'] if x['seite'] == seite]
        if gold['layout'] == 'tabelle':
            y = height - 120
            c.setFont('Helvetica-Bold', 10)
            for x, label in [(40, 'Analyt'), (210, 'Ergebnis'), (290, 'Einheit'), (370, 'Referenz'), (520, 'Flag')]:
                c.drawString(x, y, label)
            c.setFont('Helvetica', 10)
            for row in rows:
                y -= 35
                ref = row['referenz']
                ref_text = f"{ref['untergrenze']} - {ref['obergrenze']}" if ref else 'k.A.'
                for x, label in [(40, row['analyt']), (210, row['wert']), (290, row['einheit']), (370, ref_text), (520, row['flag'])]:
                    c.drawString(x, y, label)
                c.line(40, y - 8, width - 40, y - 8)
        else:
            for i, row in enumerate(rows):
                zweispaltig = gold['layout'] == 'zweispaltig'
                x = 40 + (i % 2) * 265 if zweispaltig else 40
                y = height - 125 - (i // 2 if zweispaltig else i) * (105 if zweispaltig else 65)
                ref = row['referenz']
                ref_text = f"{ref['untergrenze']} bis {ref['obergrenze']} {row['einheit']}" if ref else 'nicht angegeben'
                text = f"{row['analyt']}: {row['wert']} {row['einheit']}. Referenz: {ref_text}. Flag: {row['flag']}."
                c.setFont('Helvetica', 11)
                for j, line in enumerate(wrap(text, 34 if zweispaltig else 83)):
                    c.drawString(x, y - j * 15, line)
        c.setFont('Helvetica-Oblique', 9)
        for j, line in enumerate(wrap(gold['kommentar'], 98)):
            c.drawString(40, 85 - j * 12, line)
        c.drawRightString(width - 40, 35, f"Seite {seite} / {gold['seiten']}")
        c.showPage()
    c.save()
    return stream.getvalue()


def _font(size, bold=False):
    name = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def scan_pdf_rendern(gold):
    """Zusaetzliche Scan-Simulation: Bild-PDF mit Rotation und Rauschen."""
    rng = random.Random(f"{SEED}:{gold['id']}:scan")
    pages = []
    width, height = 1240, 1754
    for seite in range(1, gold['seiten'] + 1):
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        draw.text((75, 70), f"Laborbefund {gold['id']}", fill=(20, 20, 20), font=_font(34, True))
        draw.text((75, 125), f"{gold['patient']['vorname']} {gold['patient']['nachname']} | 28.09.2026",
                  fill=(35, 35, 35), font=_font(22))
        draw.text((75, 165), 'Fiktiver Testbefund - Scan-Simulation', fill=(65, 65, 65), font=_font(20))
        y = 245
        for row in [x for x in gold['laborwerte'] if x['seite'] == seite]:
            ref = row['referenz']
            ref_text = f"{ref['untergrenze']} - {ref['obergrenze']} {row['einheit']}" if ref else 'k.A.'
            draw.text((80, y), row['analyt'], fill=(15, 15, 15), font=_font(24, True))
            draw.text((390, y), f"{row['wert']} {row['einheit']}", fill=(15, 15, 15), font=_font(24))
            draw.text((650, y), f"Ref: {ref_text}", fill=(35, 35, 35), font=_font(21))
            draw.text((1030, y), f"Flag {row['flag']}", fill=(35, 35, 35), font=_font(21))
            y += 92
        draw.text((75, height - 190), 'Glukose 999 mg/dl ist Schulungstext und kein Messwert.',
                  fill=(70, 70, 70), font=_font(20))
        draw.text((width - 230, height - 80), f"Seite {seite} / {gold['seiten']}", fill=(50, 50, 50), font=_font(18))

        pixels = img.load()
        for _ in range(2800):
            x, y = rng.randrange(width), rng.randrange(height)
            shade = rng.randrange(185, 256)
            pixels[x, y] = (shade, shade, shade)
        img = img.rotate(SCAN_IDS[gold['id']], resample=Image.Resampling.BICUBIC, fillcolor='white')
        pages.append(img)
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4, invariant=1, pageCompression=1)
    canvas.setTitle(f"Scan-Simulation {gold['id']}")
    for page in pages:
        png = BytesIO()
        page.save(png, format='PNG')
        png.seek(0)
        canvas.drawImage(ImageReader(png), 0, 0, width=A4[0], height=A4[1])
        canvas.showPage()
    canvas.save()
    return stream.getvalue()


def objekt(attr, label, oid, inhalt):
    return [(attr, label), ('8002', oid), *inhalt, ('8003', oid)]


def timestamp(attr, label):
    return objekt(attr, label, 'Obj_0054', [('7278', '20260928'), ('7279', '100000'), ('7273', 'UTC+2')])


def person(name, status='07'):
    return objekt('8147', 'Person', 'Obj_0047', [('7420', status), ('3101', name), ('3102', 'Synthetisch')])


def organisation(attr, label, name, arzt=False):
    return objekt(attr, label, 'Obj_0043', [('1250', name)] +
                  ([('1252', 'Laborarzt')] + person('Musterarzt') if arzt else []))


def ldt_rendern(gold, pdf):
    ident = gold['id']
    kopf = objekt('8132', 'Kopfdaten', 'Obj_0032', [('0001', 'LDT3.2.15')] +
                  objekt('8151', 'Sendendes_System', 'Obj_0051', [('0103', 'Hospitation-Testgenerator'), ('0132', '0.1.0')]) +
                  timestamp('8218', 'Timestamp_Erstellung_Datensatz'))
    labor = objekt('8136', 'Laborkennung', 'Obj_0036',
                   organisation('8239', 'Laborbezeichnung', 'Synthetisches Labor', True) + [('7266', '1')])
    betrieb = objekt('8119', 'Betriebsstaette', 'Obj_0019',
                     [('0204', '2'), ('0203', 'Synthetisches Labor'), ('0200', 'SYN-LAB')] +
                     organisation('8143', 'Organisation', 'Synthetisches Labor'))
    einsender = objekt('8122', 'Einsenderidentifikation', 'Obj_0022',
                       [('7321', '03')] + person('Musterarzt') + organisation('8143', 'Organisation', 'Synthetische Klinik'))
    patient = objekt('8145', 'Patient', 'Obj_0045',
                     objekt('8147', 'Person', 'Obj_0047', [('7420', '12'), ('3101', gold['patient']['nachname']),
                            ('3102', gold['patient']['vorname']), ('3103', gold['patient']['geburt']), ('3110', '1')]) + [('3000', ident)])
    befund = objekt('8117', 'Befundinformationen', 'Obj_0017',
                    [('8311', ident), ('7305', ident + '-B'), ('8401', '2')] + timestamp('8216', 'Timestamp_Befunderstellung'))
    material = objekt('8137', 'Material', 'Obj_0037',
                      [('7364', ident + '-P'), ('8428', 'SE'), ('8430', 'Serum')] + timestamp('8219', 'Timestamp_Materialabnahme_entnahme'))
    material += objekt('8137', 'Material', 'Obj_0037',
                       [('7364', ident + '-EDTA'), ('8428', 'EB'), ('8430', 'EDTA-Blut')] + timestamp('8219', 'Timestamp_Materialabnahme_entnahme'))
    ergebnisse = []
    for index, row in enumerate(gold['laborwerte']):
        fehler = gold['absichtliche_fehler'][0]['typ'] if index == 0 and gold['absichtliche_fehler'] else None
        eintrag = [('7304', row['ergebnis_id'])]
        if fehler == 'doppelte_ergebnis_id':
            eintrag.append(('7304', row['ergebnis_id']))
        eintrag += [('7364', ident + ('-EDTA' if row['material'] == 'EDTA-Blut' else '-P')), ('8410', row['test_ident']), ('8411', row['analyt']), ('8418', '06'),
                    ('7306', '02' if row['wert'].startswith('<') else '03' if row['wert'].startswith('>') else '01'), ('8420', row['wert']), ('8419', '2')]
        if fehler != 'fehlende_einheit':
            eintrag.append(('8421', row['einheit']))
        if fehler == 'flag_an_falscher_stelle':
            eintrag.append(('8422', row['flag']))
        ref = row['referenz']
        normal = [('8424', '20')]
        if ref:
            normal += [('8461', ref['untergrenze']), ('8419', '2'), ('8421', row['einheit']),
                       ('8462', ref['obergrenze']), ('8419', '2'), ('8421', row['einheit'])]
        else:
            normal.append(('8460', 'k.A.'))
        normal.append(('8422', row['flag']))
        eintrag += objekt('8142', 'Normalwert', 'Obj_0042', normal)
        eintrag += timestamp('8225', 'Timestamp_Messung')
        eintrag += objekt('8141', 'Namenskennung', 'Obj_0041', [('7420', '07'), ('7358', 'Synthetischer Musterarzt')])
        ergebnisse += objekt('8160', 'UE_Klinische_Chemie', 'Obj_0060', eintrag)
    bericht = objekt('8135', 'Laborergebnisbericht', 'Obj_0035', ergebnisse + timestamp('8221', 'Timestamp_Erstellung_Laborergebnisbericht'))
    kommentar = objekt('8167', 'Zusaetzliche_Informationen', 'Obj_0068', [('3564', gold['kommentar'])])
    b64 = base64.b64encode(pdf).decode('ascii')
    anhang = objekt('8110', 'Anhang', 'Obj_0010', [('9970', '100')] +
                    objekt('8242', 'base64-kodierte_Anlage', 'Obj_0068', [('6329', b64[i:i+60]) for i in range(0, len(b64), 60)]) + [('6303', 'PDF')])
    paare = [('8000', '8220'), *kopf, *labor, *betrieb, ('8001', '8220'),
             ('8000', '8205'), *einsender, *patient, *befund, *material, *bericht, *kommentar, *anhang,
             ('8001', '8205'), ('8000', '8221')]
    daten = b''
    for fk, wert in paare:
        raw = wert.encode('iso8859-15')
        if not raw or len(raw) > 990 or b'\r' in raw or b'\n' in raw:
            raise ValueError(f'Ungültiger Feldinhalt {fk}')
        daten += f'{len(raw)+9:03}{fk}'.encode('ascii') + raw + b'\r\n'
    return daten + b'0499300' + hashlib.sha1(daten).hexdigest().encode() + b'\r\n01380018221\r\n'


def generieren(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'seed': SEED, 'anzahl': 18, 'scan_simulationen': len(SCAN_IDS), 'befunde': []}
    for gold in gold_befunde():
        ordner = output / gold['id']
        ordner.mkdir(exist_ok=True)
        pdf = pdf_rendern(gold)
        ldt = ldt_rendern(gold, pdf)
        (ordner / 'gold.json').write_text(json.dumps(gold, ensure_ascii=False, indent=2) + '\n')
        (ordner / 'befund.pdf').write_bytes(pdf)
        (ordner / 'befund.ldt').write_bytes(ldt)
        entry = {'id': gold['id'], 'layout': gold['layout'], 'seiten': gold['seiten'],
                 'fehler': gold['absichtliche_fehler'],
                 'sha256_pdf': hashlib.sha256(pdf).hexdigest(),
                 'sha256_ldt': hashlib.sha256(ldt).hexdigest()}
        if gold['id'] in SCAN_IDS:
            scan = scan_pdf_rendern(gold)
            (ordner / 'befund_scan.pdf').write_bytes(scan)
            entry['scan_pdf'] = {'datei': 'befund_scan.pdf',
                                 'rotation_grad': SCAN_IDS[gold['id']],
                                 'rauschen_pixel': 2800,
                                 'sha256': hashlib.sha256(scan).hexdigest()}
        manifest['befunde'].append(entry)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/synthetisch'))
    args = parser.parse_args()
    manifest = generieren(args.output)
    print(f"{manifest['anzahl']} Gold/LDT/PDF-Paare in {args.output}")
