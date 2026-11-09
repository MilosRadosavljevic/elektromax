"""Admin – analitika prodaje (samo admin)."""
from datetime import date, timedelta

from flask import Blueprint, render_template, request

from jezgro import get_db, login_required

bp = Blueprint("analitika", __name__)

DANI = ["Ned", "Pon", "Uto", "Sre", "Čet", "Pet", "Sub"]
ZNAK = "CASE WHEN r.tip = 'racun' THEN 1 ELSE -1 END"   # storno se oduzima
PRODAJA = "r.tip IN ('racun', 'storno') AND date(r.vreme) BETWEEN :od AND :do"


def _period():
    danas = date.today()
    p = request.args.get("period", "30")
    if p == "mesec":
        od, do = danas.replace(day=1), danas
    elif p == "prosli":
        kraj = danas.replace(day=1) - timedelta(days=1)
        od, do = kraj.replace(day=1), kraj
    elif p == "custom":
        try:
            od = date.fromisoformat(request.args.get("od", ""))
            do = date.fromisoformat(request.args.get("do", ""))
        except ValueError:
            od, do, p = danas - timedelta(days=29), danas, "30"
        if od > do:
            od, do = do, od
    else:
        n = int(p) if p in ("7", "30", "90", "365") else 30
        p = str(n)
        od, do = danas - timedelta(days=n - 1), danas
    return p, od, do


def pokazatelji(db, od: date, do: date) -> dict:
    par = {"od": od.isoformat(), "do": do.isoformat()}
    r = db.execute(f"""
        SELECT COALESCE(SUM({ZNAK} * r.ukupno), 0)                         AS promet,
               COALESCE(SUM({ZNAK} * r.osnovica), 0)                       AS osnovica,
               COALESCE(SUM(CASE WHEN r.tip='racun' THEN 1 END), 0)        AS racuna,
               COALESCE(SUM(CASE WHEN r.tip='racun' THEN r.ukupno END), 0) AS promet_racuna,
               COALESCE(SUM({ZNAK} * r.popust), 0)                         AS popusti,
               COALESCE(SUM(CASE WHEN r.tip='storno' THEN 1 END), 0)       AS storna,
               COALESCE(SUM(CASE WHEN r.tip='storno' THEN r.ukupno END), 0) AS storna_iznos
        FROM racuni r WHERE {PRODAJA}""", par).fetchone()
    nab = db.execute(f"""
        SELECT COALESCE(SUM({ZNAK} * s.kolicina * s.nabavna_cena), 0),
               COALESCE(SUM(CASE WHEN s.nabavna_cena IS NULL THEN 1 END), 0)
        FROM racun_stavke s JOIN racuni r ON r.id = s.racun_id WHERE {PRODAJA}""", par).fetchone()
    k = dict(r)
    k["nabavna"] = nab[0]
    k["bez_nabavne"] = nab[1]
    k["zarada"] = k["osnovica"] - k["nabavna"]
    k["marza"] = (k["zarada"] / k["osnovica"] * 100) if k["osnovica"] else 0
    k["prosek"] = (k["promet_racuna"] / k["racuna"]) if k["racuna"] else 0
    return k


@bp.route("/admin/analitika")
@login_required("admin")
def pregled():
    db = get_db()
    period, od, do = _period()
    par = {"od": od.isoformat(), "do": do.isoformat()}
    trajanje = (do - od).days + 1
    pre_od, pre_do = od - timedelta(days=trajanje), od - timedelta(days=1)
    k = pokazatelji(db, od, do)
    kp = pokazatelji(db, pre_od, pre_do)

    po_danu = {x[0]: (x[1], x[2]) for x in db.execute(f"""
        SELECT date(r.vreme), SUM({ZNAK} * r.ukupno), SUM(CASE WHEN r.tip='racun' THEN 1 ELSE 0 END)
        FROM racuni r WHERE {PRODAJA} GROUP BY 1""", par)}
    dani = []
    for i in range(trajanje):
        dd = od + timedelta(days=i)
        v = po_danu.get(dd.isoformat(), (0, 0))
        dani.append({"d": dd.isoformat(), "dan": DANI[(dd.weekday() + 1) % 7], "v": round(v[0], 2), "n": v[1]})

    toplota = [{"dan": int(x[0]), "sat": int(x[1]), "v": round(x[2], 2), "n": x[3]} for x in db.execute(f"""
        SELECT strftime('%w', r.vreme), CAST(strftime('%H', r.vreme) AS INTEGER),
               SUM({ZNAK} * r.ukupno), SUM(CASE WHEN r.tip='racun' THEN 1 ELSE 0 END)
        FROM racuni r WHERE {PRODAJA} GROUP BY 1, 2""", par)]

    kategorije = [dict(x) for x in db.execute(f"""
        SELECT COALESCE(k.naziv, 'Obrisani artikli') AS naziv, SUM({ZNAK} * s.ukupno) AS promet,
               SUM({ZNAK} * (s.ukupno - s.ukupno * s.pdv_stopa / (100 + s.pdv_stopa) - s.kolicina * COALESCE(s.nabavna_cena, 0))) AS zarada
        FROM racun_stavke s JOIN racuni r ON r.id = s.racun_id
        LEFT JOIN artikli a ON a.id = s.artikal_id LEFT JOIN kategorije k ON k.id = a.kategorija_id
        WHERE {PRODAJA} GROUP BY 1 ORDER BY promet DESC""", par)]

    artikli = [dict(x) for x in db.execute(f"""
        SELECT s.artikal_id AS id, s.sifra, s.naziv, s.jedinica_mere AS jm,
               SUM({ZNAK} * s.kolicina) AS kolicina, SUM({ZNAK} * s.ukupno) AS promet,
               SUM({ZNAK} * (s.ukupno - s.ukupno * s.pdv_stopa / (100 + s.pdv_stopa) - s.kolicina * COALESCE(s.nabavna_cena, 0))) AS zarada,
               COUNT(DISTINCT CASE WHEN r.tip='racun' THEN r.id END) AS racuna
        FROM racun_stavke s JOIN racuni r ON r.id = s.racun_id
        WHERE {PRODAJA} GROUP BY s.sifra ORDER BY promet DESC""", par)]

    placanja = [dict(x) for x in db.execute(f"""
        SELECT p.nacin, SUM({ZNAK} * p.iznos) AS iznos, COUNT(DISTINCT CASE WHEN r.tip='racun' THEN r.id END) AS racuna
        FROM placanja p JOIN racuni r ON r.id = p.racun_id WHERE {PRODAJA} GROUP BY 1 ORDER BY iznos DESC""", par)]

    kasiri = [dict(x) for x in db.execute(f"""
        SELECT ko.ime, SUM(CASE WHEN r.tip='racun' THEN 1 ELSE 0 END) AS racuna, SUM({ZNAK} * r.ukupno) AS promet,
               SUM(CASE WHEN r.tip='racun' THEN r.popust ELSE 0 END) AS popusti,
               SUM(CASE WHEN r.tip='storno' THEN 1 ELSE 0 END) AS storna
        FROM racuni r JOIN korisnici ko ON ko.id = r.kasir_id WHERE {PRODAJA} GROUP BY ko.id ORDER BY promet DESC""", par)]

    prodati = {a["id"] for a in artikli if a["kolicina"] > 0}
    zalihe = db.execute("SELECT COALESCE(SUM(stanje * nabavna_cena), 0) FROM artikli WHERE stanje > 0").fetchone()[0]
    mrtvi = [dict(x) for x in db.execute("""
        SELECT id, sifra, naziv, stanje, jedinica_mere AS jm, nabavna_cena, stanje * COALESCE(nabavna_cena, 0) AS vrednost
        FROM artikli WHERE stanje > 0 AND aktivan = 1 ORDER BY vrednost DESC""") if x["id"] not in prodati]

    return render_template(
        "admin/analitika.html", period=period, od=od, do=do, pre_od=pre_od, pre_do=pre_do, k=k, kp=kp,
        dani=dani, toplota=toplota, kategorije=kategorije, artikli=artikli, placanja=placanja, kasiri=kasiri,
        zalihe=zalihe, mrtvi=mrtvi, trajanje=trajanje)
