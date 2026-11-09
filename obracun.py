"""Obračun računa: popusti, PDV, ukupni iznosi.

Isti kod koriste server (konačan obračun koji se upisuje u bazu) i desktop kasa (prikaz na ekranu),
pa je sve što kupac vidi na kasi tačno ono što se upisuje.

Sve cene su SA PDV-om (maloprodaja). Iznosi se zaokružuju na 2 decimale (para).
"""
from decimal import ROUND_HALF_UP, Decimal

D0 = Decimal("0")
D100 = Decimal("100")
PARA = Decimal("0.01")


def d(x) -> Decimal:
    return Decimal(str(x if x is not None else 0))


def zaokruzi(x: Decimal) -> Decimal:
    return x.quantize(PARA, rounding=ROUND_HALF_UP)


def _popust(osnov: Decimal, popust: dict | None) -> Decimal:
    """popust = {"proc": 10} ili {"iznos": 150}; nikad veći od osnova."""
    if not popust:
        return D0
    if popust.get("proc") not in (None, ""):
        p = zaokruzi(osnov * d(popust["proc"]) / D100)
    elif popust.get("iznos") not in (None, ""):
        p = zaokruzi(d(popust["iznos"]))
    else:
        return D0
    return max(D0, min(p, osnov))


def izracunaj(stavke: list[dict], popust_racun: dict | None = None) -> dict:
    """stavke: [{cena, kolicina, pdv_stopa, popust: {"proc"|"iznos"}?, ...ostala polja se prenose}]

    Vraća {"stavke": [... + bruto, popust, popust_proc, ukupno, osnovica, pdv],
           "bruto", "popust", "popust_racun", "ukupno", "osnovica", "pdv", "pdv_po_stopama", "max_popust_proc"}
    Popust na ceo račun se raspoređuje na stavke srazmerno iznosu (zbog tačnog PDV-a po stopama).
    """
    rez = []
    for s in stavke:
        bruto = zaokruzi(d(s["cena"]) * d(s["kolicina"]))
        p1 = _popust(bruto, s.get("popust"))
        rez.append({**s, "bruto": bruto, "_neto": bruto - p1})

    zbir_neto = sum((r["_neto"] for r in rez), D0)
    p_racun = _popust(zbir_neto, popust_racun)

    # raspodela popusta na račun (poslednja stavka sa iznosom uzima ostatak zbog zaokruživanja)
    ostatak = p_racun
    indeksi = [i for i, r in enumerate(rez) if r["_neto"] > 0]
    for i, r in enumerate(rez):
        if p_racun and zbir_neto and r["_neto"] > 0:
            deo = ostatak if i == indeksi[-1] else zaokruzi(p_racun * r["_neto"] / zbir_neto)
            ostatak -= deo
        else:
            deo = D0
        ukupno = r.pop("_neto") - deo
        stopa = d(r.get("pdv_stopa", 20))
        pdv = zaokruzi(ukupno * stopa / (D100 + stopa))
        r.update(ukupno=ukupno, popust=r["bruto"] - ukupno, pdv=pdv, osnovica=ukupno - pdv,
                 popust_proc=(zaokruzi((r["bruto"] - ukupno) * D100 / r["bruto"]) if r["bruto"] else D0))

    po_stopama = {}
    for r in rez:
        k = str(d(r.get("pdv_stopa", 20)).normalize())
        x = po_stopama.setdefault(k, {"osnovica": D0, "pdv": D0, "ukupno": D0})
        x["osnovica"] += r["osnovica"]
        x["pdv"] += r["pdv"]
        x["ukupno"] += r["ukupno"]

    return {
        "stavke": rez,
        "bruto": sum((r["bruto"] for r in rez), D0),
        "popust": sum((r["popust"] for r in rez), D0),
        "popust_racun": p_racun,
        "ukupno": sum((r["ukupno"] for r in rez), D0),
        "osnovica": sum((r["osnovica"] for r in rez), D0),
        "pdv": sum((r["pdv"] for r in rez), D0),
        "pdv_po_stopama": po_stopama,
        "max_popust_proc": max((r["popust_proc"] for r in rez), default=D0),
    }


def format_din(x, valuta=True) -> str:
    """1290.5 -> '1.290,50 RSD'"""
    s = f"{zaokruzi(d(x)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + (" RSD" if valuta else "")
