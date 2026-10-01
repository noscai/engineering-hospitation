"""Gemeinsames Schema fuer LDT- und PDF-Laborwerte."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Referenzbereich(BaseModel):
    spezifikation: str | None = Field(description="Referenztyp oder Codespezifikation, falls vorhanden.")
    untergrenze: str | None = Field(description="Gedruckte oder uebertragene Untergrenze ohne Normalisierung.")
    obergrenze: str | None = Field(description="Gedruckte oder uebertragene Obergrenze ohne Normalisierung.")
    untergrenze_einheit: str | None = Field(description="Einheit der Untergrenze, falls separat erkennbar.")
    obergrenze_einheit: str | None = Field(description="Einheit der Obergrenze, falls separat erkennbar.")
    text: list[str] = Field(description="Freitext-Referenzen, wenn keine numerische Grenze erkennbar ist.")
    flag: str | None = Field(description="Gedruckter oder uebertragener Grenzwertindikator, z. B. H, L oder +.")


class Laborwert(BaseModel):
    befund_index: int | None = Field(description="LDT-Befundnummer oder null fuer einzelne PDF-Extraktionen.")
    ergebnis_id: str | None = Field(description="Technische Ergebnis-ID aus LDT, falls vorhanden.")
    test_ident: str | None = Field(description="Testkennung oder laborinternes Kuerzel, falls vorhanden.")
    analyt: str | None = Field(description="Analyt exakt wie im Ausgangsdokument gedruckt oder uebertragen.")
    wert: str | None = Field(description="Messwert exakt wie gedruckt, inklusive Komma, < oder >.")
    einheit: str | None = Field(description="Einheit exakt wie gedruckt; null, wenn nicht angegeben.")
    einheitensystem: str | None = Field(description="LDT-Einheitensystem oder null fuer PDF.")
    referenzen: list[Referenzbereich] = Field(description="Referenzbereiche oder Referenztexte aus dem Dokument.")
    ergebnisstatus: str | None = Field(description="LDT-Ergebnisstatus oder null fuer PDF.")
    quelle: Literal["LDT", "PDF"] = Field(description="Ursprung der Extraktion.")
    seite: int | None = Field(description="PDF-Seite ab 1; null fuer reine LDT-Werte.")
    confidence: float | None = Field(description="0 bis 1 fuer LLM/PDF-Sicherheit; null fuer deterministische LDT-Werte.")
    begruendung: str | None = Field(description="Kurze Begruendung oder Fundstelle; bei Unsicherheit erklaeren.")
    zeile: int | None = Field(description="LDT-Zeile oder null fuer PDF.")
    objektpfad: str | None = Field(description="LDT-Objektpfad oder null fuer PDF.")


class LaborbefundExtraktion(BaseModel):
    laborwerte: list[Laborwert] = Field(description="Alle im PDF erkennbaren Laborwerte; keine erfundenen Werte.")
    hinweise: list[str] = Field(description="Kurze Hinweise zu fehlenden, unklaren oder nicht lesbaren Angaben.")
