"""Fiskalizacija računa – zamenljivi adapter.

Kasa u Srbiji mora svaki račun da prijavi preko odobrenog ESIR-a i procesora fiskalnih računa (L-PFR / V-PFR).
Dok se ne izabere rešenje, radi DemoFiskal: račun dobija oznaku „NIJE FISKALNI RAČUN“.
Detalji i plan povezivanja: FISKALIZACIJA.md

Za povezivanje se pravi nova klasa sa istom metodom fiskalizuj() i bira se promenljivom okruženja
ELEKTROMAX_FISKAL (npr. „esir_api“). Ostatak sistema se ne menja.
"""
import json
import os
import secrets
from datetime import datetime

# Vrste računa i transakcija iz fiskalnog sistema (eFiskalizacija):
#   InvoiceType: Normal (promet), ProForma (predračun), Copy (kopija), Training (obuka), Advance (avans)
#   TransactionType: Sale (prodaja), Refund (refundacija = storno)
VRSTA = {
    "racun": ("Normal", "Sale"),
    "storno": ("Normal", "Refund"),
    "predracun": ("ProForma", "Sale"),
    "kopija": ("Copy", "Sale"),
}

# Poreske oznake po stopi PDV-a – PROVERITI u važećem tehničkom vodiču pre povezivanja.
PORESKE_OZNAKE = {20: "Ђ", 10: "Е", 0: "Г"}

NACIN_PLACANJA = {"gotovina": "Cash", "kartica": "Card", "prenos": "WireTransfer"}


class DemoFiskal:
    rezim = "DEMO"

    def fiskalizuj(self, racun: dict, stavke: list[dict], placanja: list[dict],
                   referentni: dict | None = None) -> dict:
        """Vraća podatke koje vraća pravi PFR: broj, vreme, verifikacioni URL, sirov odgovor."""
        zahtev = pripremi_zahtev(racun, stavke, placanja, referentni)
        return {
            "fiskal_rezim": self.rezim,
            "fiskal_broj": f"DEMO-{secrets.token_hex(4).upper()}-{racun['broj']}",
            "fiskal_vreme": datetime.now().isoformat(timespec="seconds"),
            "fiskal_url": None,
            "fiskal_odgovor": json.dumps({"zahtev": zahtev, "napomena": "DEMO – nije poslato PFR-u"},
                                         ensure_ascii=False),
        }


def pripremi_zahtev(racun, stavke, placanja, referentni=None) -> dict:
    """Zahtev u obliku koji ESIR šalje PFR-u (pojednostavljeno; tačna polja po tehničkom vodiču)."""
    vrsta, transakcija = VRSTA[racun["tip"]]
    z = {
        "invoiceType": vrsta,
        "transactionType": transakcija,
        "cashier": racun.get("kasir", ""),
        "buyerId": f"10:{racun['kupac_pib']}" if racun.get("kupac_pib") else None,
        "payment": [{"paymentType": NACIN_PLACANJA[p["nacin"]], "amount": float(p["iznos"])}
                    for p in placanja],
        "items": [{
            "name": s["naziv"],
            "quantity": float(s["kolicina"]),
            "unitPrice": float(s["ukupno"]) / float(s["kolicina"]),
            "labels": [PORESKE_OZNAKE.get(int(s["pdv_stopa"]), "?")],
            "totalAmount": float(s["ukupno"]),
        } for s in stavke],
    }
    if referentni:
        z["referentDocumentNumber"] = referentni.get("fiskal_broj")
        z["referentDocumentDT"] = referentni.get("fiskal_vreme")
    return z


def adapter():
    izbor = os.environ.get("ELEKTROMAX_FISKAL", "demo")
    if izbor == "demo":
        return DemoFiskal()
    raise RuntimeError(f"Fiskalni adapter „{izbor}“ nije implementiran – vidi FISKALIZACIJA.md")
