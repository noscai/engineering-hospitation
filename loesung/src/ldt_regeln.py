"""Vorkommenshierarchien aus LDT 3.2.15, S. 127, 138, 152, 168–169.

Eintrag: Feldkennung, darf auf derselben Ebene wiederholt werden, Kinder.
Bedingte Pflichtfelder werden im Validator separat ausgewertet.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Feldregel:
    fk: str
    mehrfach: bool = False
    kinder: tuple = ()


def f(fk, mehrfach=False, *kinder):
    return Feldregel(fk, mehrfach, kinder)


def einheit():
    return f('8419', False, f('8421'))


SCHEMATA = {
    'Obj_0010': tuple(f(k, k == '9980') for k in
        '9970 6221 6305 8242 6303 6328 6327 9908 9909 9980 9981'.split()),
    'Obj_0068': (f('3564', True), f('6329', True)),
    'Obj_0042': (
        f('8424', False, f('8167')), f('8460', True),
        f('8461', False, einheit()), f('8462', False, einheit()),
        f('7316', False, f('7317', True)),
        f('7363', False, einheit()), f('7371', False, einheit()),
        f('8422', False, f('8126')),
    ),
    'Obj_0060': (
        f('7304'), f('7364', True),
        f('7260', False, f('7352'), f('7251'), f('7365', False, f('7366'))),
        f('8410', False, f('8411'), f('7263'), f('7264')),
        f('8418', False, f('7302', True),
          f('7306', True, f('8420', True, einheit(), f('8142', True),
                           f('8225'), f('8237')), f('8236'))),
        f('8167', True), f('8220'), f('8222'), f('8223'), f('8224'),
        f('8126'), f('8141'), f('8158'), f('7429'), f('3473'), f('8110', True),
    ),
}


def pruefe_reihenfolge(felder, schema):
    """Liest rekursiv geordnete Gruppen; Kindfelder brauchen ihren Elternwert.

    Fehler werden zurückgegeben, nicht durch Verschieben von Feldern repariert.
    Der verbleibende Rest wird ab dem ersten Zuordnungsfehler zurückgegeben.
    """
    position = 0

    def gruppe(regeln):
        nonlocal position
        for regel in regeln:
            while position < len(felder) and felder[position].feldkennung == regel.fk:
                position += 1
                gruppe(regel.kinder)
                if not regel.mehrfach:
                    break

    gruppe(schema)
    return felder[position:]

# Weitere für die synthetischen Befunde verwendete Tabellen.
# Quellen: S. 32, 34, 132–136, 141, 144–148, 151, 153–155, 158, 160.
METADATEN = {
    '8220': ('8132 8136 8119', '8132 8136 8119', ''),
    '8205': ('8136 8122 8145 8169 8150 8140 8153 8117 8127 8137 8135 8167 8110', '8122 8117 8137 8135', '8136 8127 8137 8167 8110'),
    '8221': ('9300', '9300', ''),
    'Obj_0032': ('0001 8151 8218 8212', '0001 8151', ''),
    'Obj_0051': ('8315 8316 0105 8212 0103 0132', '0103 0132', ''),
    'Obj_0036': ('8239 7352 8324 7266', '8239 7266', '7352'),
    'Obj_0019': ('0204 0203 0200 0201 0213 8143', '0204 0203 8143', '0204'),
    'Obj_0043': ('1250 1251 1252 8147 8229 8230 8131', '1250', '1252 8147 8229'),
    'Obj_0047': ('7420 3100 3120 3101 3102 3103 3104 3110 3628 8990 8228 8229 8230 8232 8233', '3101 3102', '3102'),
    'Obj_0045': ('8147 3119 3105 7329 7922 3000', '8147', ''),
    'Obj_0022': ('7321 8312 7267 8114 8240 8241 8147 7268 8119 8143', '7321', '7321'),
    'Obj_0017': ('8310 8313 8214 8215 8616 8626 8627 8617 4111 8631 8632 8618 8619 8620 8622 8625 8623 8311 7305 8401 0080 0081 7258 7251 4229 8118 8611 8147 7320 8154 8247 8216 8167 8110 8126 8141', '8311 7305 8401 8216', '8313 0081 4229 8611 8247 8167 8110 8126'),
    'Obj_0037': ('7364 8429 8428 8430 8431 7292 7310 7311 7312 8167 8504 8170 7318 8520 8421 8522 8219 8220 8126 8167 8110', '7364', '8504 7318 8167 8110'),
    'Obj_0035': ('8160 8161 8162 8163 8155 8248 8156 8221 8167 8110 8141', '8221', '8160 8161 8162 8163 8155 8248 8156 8167 8110'),
    'Obj_0041': ('7420 7358 8990 8110', '7420 7358', ''),
    'Obj_0054': ('7278 7279 7273 7272 8235', '7278', ''),
}

SCHEMATA.update({
    '8220': (f('8132'), f('8136'), f('8119')),
    '8205': tuple(f(k, k in {'8136', '8127', '8137', '8167', '8110'}) for k in METADATEN['8205'][0].split()),
    '8221': (f('9300'),),
    'Obj_0032': (f('0001'), f('8151'), f('8218'), f('8212')),
    'Obj_0051': (f('8315'), f('8316'), f('0105'), f('8212'), f('0103', False, f('0132'))),
    'Obj_0036': (f('8239'), f('7352', True), f('8324'), f('7266')),
    'Obj_0019': (f('0204', True), f('0203', False, f('0200'), f('0201'), f('0213'), f('8143'))),
    'Obj_0043': (f('1250', False, f('1251'), f('1252', True, f('8147', True)),
                    f('8229', True), f('8230'), f('8131')),),
    'Obj_0047': tuple(f(k, k == '3102') for k in METADATEN['Obj_0047'][0].split()),
    'Obj_0045': tuple(f(k) for k in METADATEN['Obj_0045'][0].split()),
    'Obj_0022': (f('7321', True), f('8312', False, f('7267')), f('8114'), f('8240'),
                 f('8241'), f('8147'), f('7268'), f('8119'), f('8143')),
    'Obj_0017': (f('8310', False, f('8313', True)), f('8214'), f('8215'), f('8616'),
                 f('8626', False, f('8627'), f('8617'), f('4111'), f('8631'), f('8632')),
                 f('8618'), f('8619'), f('8620'), f('8622'), f('8625'), f('8623'),
                 f('8311', False, f('7305'), f('8401')), f('0080', False, f('0081', True)),
                 f('7258', False, f('7251')), f('4229', True), f('8118'),
                 f('8611', True, f('8147')), f('7320', False, f('8154')),
                 f('8247', True), f('8216'), f('8167', True), f('8110', True), f('8126', True), f('8141')),
    'Obj_0037': (f('7364'), f('8429'), f('8428'), f('8430'), f('8431'), f('7292'),
                 f('7310', False, f('7311'), f('7312', False, f('8167'))),
                 f('8504', True, f('8170')), f('7318', True), f('8520', False, f('8421'), f('8522')),
                 f('8219'), f('8220'), f('8126'), f('8167', True), f('8110', True)),
    'Obj_0041': (f('7420', False, f('7358', False, f('8990'), f('8110'))),),
    'Obj_0054': (f('7278'), f('7279', False, f('7273')), f('7272'), f('8235')),
})
# Obj_0035 erlaubt ausdrücklich gemischte Ergebnisarten in beliebiger Reihenfolge
# (S. 144). Dieser Sonderfall wird im Validator vor der geordneten Restgruppe geprüft.
BERICHT_ERGEBNISSE = {'8160', '8161', '8162', '8163', '8155', '8248', '8156'}
BERICHT_REST = (f('8221'), f('8167', True), f('8110', True), f('8141'))
