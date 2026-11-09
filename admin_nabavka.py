"""Admin – nabavka: za naručiti, dobavljači, narudžbenice, prijem robe, kartica artikla, korekcija stanja."""
import math
from collections import OrderedDict

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

import poslovanje as P
from jezgro import broj, get_db, login_required

bp = Blueprint("nabavka", __name__)

DANA_ANALIZE = 30       # period za prosečnu prodaju
DANA_POKRIVENOSTI = 30  # na koliko dana unapred se naručuje


# ---------------------------------------------------------------------------- za naručiti
def predlog_nabavke(db, svi=False):
    """Za svaki artikal: prodaja u poslednjih 30 dana, dana do nestanka, roba na putu, predlog količine.

    Predlog = zaliha za DANA_POKRIVENOSTI + rok isporuke (po prosečnoj prodaji), a najmanje 2 x minimalna
    količina, umanjeno za stanje i robu koja je već naručena (narudžbenice u nacrtu ili poslate).
    """
    redovi = db.execute(f"""
        WITH prodaja AS (
            SELECT s.artikal_id,
                   SUM(CASE WHEN r.tip = 'racun' THEN s.kolicina ELSE -s.kolicina END) AS kol
            FROM racun_stavke s JOIN racuni r ON r.id = s.racun_id
            WHERE r.tip IN ('racun', 'storno') AND r.vreme >= datetime('now', 'localtime', '-{DANA_ANALIZE} days')
            GROUP BY s.artikal_id),
        na_putu AS (
            SELECT ns.artikal_id, SUM(ns.kolicina) AS kol
            FROM narudzbenica_stavke ns JOIN narudzbenice n ON n.id = ns.narudzbenica_id
            WHERE n.status IN ('nacrt', 'poslata') GROUP BY ns.artikal_id)
        SELECT a.id, a.sifra, a.naziv, a.jedinica_mere, a.stanje, a.min_kolicina, a.nabavna_cena, a.aktivan,
               a.dobavljac_id, d.naziv AS dobavljac, COALESCE(d.rok_isporuke, 3) AS rok,
               COALESCE(p.kol, 0) AS prodato, COALESCE(np.kol, 0) AS na_putu
        FROM artikli a LEFT JOIN dobavljaci d ON d.id = a.dobavljac_id
        LEFT JOIN prodaja p ON p.artikal_id = a.id LEFT JOIN na_putu np ON np.artikal_id = a.id
        ORDER BY d.naziv IS NULL, d.naziv, a.naziv""").fetchall()
    out = []
    for r in redovi:
        x = dict(r)
        dnevno = max(0.0, x["prodato"]) / DANA_ANALIZE
        x["dnevno"] = dnevno
        x["dana_do_nestanka"] = (x["stanje"] / dnevno) if dnevno else None
        cilj = max(2 * x["min_kolicina"], math.ceil(dnevno * (DANA_POKRIVENOSTI + x["rok"])))
        x["predlog"] = max(0, cilj - x["stanje"] - x["na_putu"])
        if x["stanje"] <= 0:
            x["hitnost"] = "nema"
        elif x["stanje"] <= x["min_kolicina"] or (dnevno and x["dana_do_nestanka"] <= x["rok"]):
            x["hitnost"] = "kriticno"
        elif dnevno and x["dana_do_nestanka"] <= 14:
            x["hitnost"] = "uskoro"
        else:
            x["hitnost"] = "ok"
        if svi or (x["hitnost"] != "ok" and x["predlog"] > 0):
            out.append(x)
    return out


@bp.route("/admin/nabavka")
@login_required()
def za_naruciti():
    svi = request.args.get("svi") == "1"
    lista = predlog_nabavke(get_db(), svi)
    grupe = OrderedDict()
    for x in lista:
        grupe.setdefault(x["dobavljac"] or "Bez dobavljača", []).append(x)
    return render_template("admin/nabavka.html", grupe=grupe, svi=svi, ukupno=len(lista),
                           dana=DANA_ANALIZE, pokrivenost=DANA_POKRIVENOSTI)


@bp.post("/admin/nabavka/naruci")
@login_required()
def naruci():
    """Iz označenih stavki pravi po jednu narudžbenicu za svakog dobavljača."""
    db = get_db()
    izabrani = request.form.getlist("artikal")
    po_dobavljacu = OrderedDict()
    for aid in izabrani:
        kol = broj(request.form.get(f"kol_{aid}"), ceo=True) or 0
        if kol <= 0:
            continue
        a = db.execute("SELECT id, dobavljac_id, nabavna_cena FROM artikli WHERE id = ?", (aid,)).fetchone()
        if a is None:
            continue
        if not a["dobavljac_id"]:
            flash("Artikli bez dobavljača su preskočeni – dodelite im dobavljača u kartici artikla.", "greska")
            continue
        po_dobavljacu.setdefault(a["dobavljac_id"], []).append((a, kol))
    if not po_dobavljacu:
        flash("Nije izabran nijedan artikal sa količinom.", "greska")
        return redirect(url_for(".za_naruciti"))
    brojevi = []
    for dob_id, stavke in po_dobavljacu.items():
        brn = P.sledeci_broj(db, "narudzbenice", "N", 4)
        nid = db.execute("INSERT INTO narudzbenice (broj, dobavljac_id, korisnik) VALUES (?,?,?)",
                         (brn, dob_id, g.korisnik["korisnicko_ime"])).lastrowid
        for a, kol in stavke:
            db.execute("INSERT INTO narudzbenica_stavke (narudzbenica_id, artikal_id, kolicina, nabavna_cena) "
                       "VALUES (?,?,?,?)", (nid, a["id"], kol, a["nabavna_cena"]))
        brojevi.append(brn)
    db.commit()
    flash(f"Napravljene narudžbenice: {', '.join(brojevi)}. Pregledajte ih, odštampajte i označite kao poslate.",
          "uspeh")
    return redirect(url_for(".narudzbenice"))


# ---------------------------------------------------------------------------- narudžbenice
@bp.route("/admin/narudzbenice")
@login_required()
def narudzbenice():
    status = request.args.get("status", "")
    sql = """SELECT n.*, d.naziv AS dobavljac, COUNT(s.id) AS stavki,
                    SUM(s.kolicina * COALESCE(s.nabavna_cena, 0)) AS vrednost
             FROM narudzbenice n JOIN dobavljaci d ON d.id = n.dobavljac_id
             LEFT JOIN narudzbenica_stavke s ON s.narudzbenica_id = n.id"""
    par = []
    if status:
        sql += " WHERE n.status = ?"
        par.append(status)
    sql += " GROUP BY n.id ORDER BY n.vreme DESC, n.id DESC LIMIT 300"
    return render_template("admin/narudzbenice.html", lista=get_db().execute(sql, par).fetchall(), status=status)


def _narudzbenica(db, nid):
    n = db.execute("""SELECT n.*, d.naziv AS dobavljac, d.adresa, d.pib, d.email, d.telefon, d.kontakt
                      FROM narudzbenice n JOIN dobavljaci d ON d.id = n.dobavljac_id WHERE n.id = ?""",
                   (nid,)).fetchone()
    if n is None:
        abort(404)
    stavke = db.execute("""SELECT s.*, a.sifra, a.naziv, a.jedinica_mere, a.stanje FROM narudzbenica_stavke s
                           JOIN artikli a ON a.id = s.artikal_id WHERE s.narudzbenica_id = ? ORDER BY a.naziv""",
                        (nid,)).fetchall()
    return n, stavke


@bp.route("/admin/narudzbenice/<int:nid>", methods=["GET", "POST"])
@login_required()
def narudzbenica(nid):
    db = get_db()
    n, stavke = _narudzbenica(db, nid)
    if request.method == "POST":
        akcija = request.form.get("akcija")
        if akcija == "sacuvaj" and n["status"] == "nacrt":
            for s in stavke:
                kol = broj(request.form.get(f"kol_{s['id']}"), ceo=True) or 0
                if kol <= 0:
                    db.execute("DELETE FROM narudzbenica_stavke WHERE id = ?", (s["id"],))
                else:
                    db.execute("UPDATE narudzbenica_stavke SET kolicina = ? WHERE id = ?", (kol, s["id"]))
            db.execute("UPDATE narudzbenice SET napomena = ? WHERE id = ?",
                       (request.form.get("napomena", "").strip(), nid))
            flash("Narudžbenica je sačuvana.", "uspeh")
        elif akcija == "poslata" and n["status"] == "nacrt":
            db.execute("UPDATE narudzbenice SET status = 'poslata' WHERE id = ?", (nid,))
            flash("Narudžbenica je označena kao poslata. Kada roba stigne, kliknite „Primi robu“.", "uspeh")
        elif akcija == "otkazi" and n["status"] in ("nacrt", "poslata"):
            db.execute("UPDATE narudzbenice SET status = 'otkazana' WHERE id = ?", (nid,))
            flash("Narudžbenica je otkazana.", "uspeh")
        db.commit()
        return redirect(url_for(".narudzbenica", nid=nid))
    return render_template("admin/narudzbenica.html", n=n, stavke=stavke)


@bp.route("/admin/narudzbenice/<int:nid>/stampa")
@login_required()
def narudzbenica_stampa(nid):
    n, stavke = _narudzbenica(get_db(), nid)
    return render_template("admin/narudzbenica_stampa.html", n=n, stavke=stavke)


# ---------------------------------------------------------------------------- prijem robe
@bp.route("/admin/prijemi")
@login_required()
def prijemi():
    lista = get_db().execute("""
        SELECT p.*, d.naziv AS dobavljac, n.broj AS narudzbenica, COUNT(s.id) AS stavki,
               SUM(s.kolicina * COALESCE(s.nabavna_cena, 0)) AS vrednost
        FROM prijemi p LEFT JOIN dobavljaci d ON d.id = p.dobavljac_id
        LEFT JOIN narudzbenice n ON n.id = p.narudzbenica_id
        LEFT JOIN prijem_stavke s ON s.prijem_id = p.id
        GROUP BY p.id ORDER BY p.vreme DESC, p.id DESC LIMIT 300""").fetchall()
    return render_template("admin/prijemi.html", lista=lista)


@bp.route("/admin/prijemi/novi", methods=["GET", "POST"])
@login_required()
def prijem_novi():
    db = get_db()
    nid = request.values.get("narudzbenica", type=int)
    nar = stavke_nar = None
    if nid:
        nar, stavke_nar = _narudzbenica(db, nid)
        if nar["status"] not in ("nacrt", "poslata"):
            flash(f"Narudžbenica {nar['broj']} je {nar['status']}.", "greska")
            return redirect(url_for(".narudzbenica", nid=nid))
    if request.method == "POST":
        stavke = []
        for aid, kol, cena in zip(request.form.getlist("artikal_id"), request.form.getlist("kolicina"),
                                  request.form.getlist("nabavna_cena")):
            try:
                k = broj(kol, ceo=True) or 0
                c = broj(cena)
            except ValueError:
                flash("Količine moraju biti celi brojevi, a cene brojevi.", "greska")
                return redirect(request.url)
            if aid and k > 0:
                stavke.append({"artikal_id": int(aid), "kolicina": k, "nabavna_cena": c})
        dob = request.form.get("dobavljac_id", type=int) or (nar["dobavljac_id"] if nar else None)
        try:
            pid = P.primi_robu(db, g.korisnik["korisnicko_ime"], stavke, dob,
                               request.form.get("dokument", "").strip(), request.form.get("napomena", "").strip(),
                               nid)
        except P.PoslovnaGreska as e:
            db.rollback()
            flash(e.poruka, "greska")
            return redirect(request.url)
        db.commit()
        flash("Roba je primljena i stanje je uvećano.", "uspeh")
        return redirect(url_for(".prijem", pid=pid))
    artikli = db.execute("SELECT id, sifra, naziv, jedinica_mere, nabavna_cena, stanje, dobavljac_id FROM artikli "
                         "ORDER BY naziv").fetchall()
    dobavljaci = db.execute("SELECT id, naziv FROM dobavljaci WHERE aktivan = 1 ORDER BY naziv").fetchall()
    return render_template("admin/prijem_form.html", nar=nar, stavke_nar=stavke_nar, artikli=artikli,
                           dobavljaci=dobavljaci)


@bp.route("/admin/prijemi/<int:pid>")
@login_required()
def prijem(pid):
    db = get_db()
    p = db.execute("""SELECT p.*, d.naziv AS dobavljac, n.broj AS narudzbenica FROM prijemi p
                      LEFT JOIN dobavljaci d ON d.id = p.dobavljac_id LEFT JOIN narudzbenice n ON n.id = p.narudzbenica_id
                      WHERE p.id = ?""", (pid,)).fetchone()
    if p is None:
        abort(404)
    stavke = db.execute("""SELECT s.*, a.sifra, a.naziv, a.jedinica_mere FROM prijem_stavke s
                           JOIN artikli a ON a.id = s.artikal_id WHERE s.prijem_id = ?""", (pid,)).fetchall()
    return render_template("admin/prijem.html", p=p, stavke=stavke)


# ---------------------------------------------------------------------------- kartica artikla
@bp.route("/admin/artikli/<int:aid>/kartica", methods=["GET", "POST"])
@login_required()
def kartica(aid):
    db = get_db()
    a = db.execute("""SELECT a.*, d.naziv AS dobavljac FROM artikli a LEFT JOIN dobavljaci d ON d.id = a.dobavljac_id
                      WHERE a.id = ?""", (aid,)).fetchone()
    if a is None:
        abort(404)
    if request.method == "POST":
        try:
            novo = broj(request.form.get("novo_stanje"), ceo=True)
        except ValueError:
            novo = None
        napomena = request.form.get("napomena", "").strip()
        if novo is None or novo < 0:
            flash("Unesite novo stanje (ceo broj, 0 ili više).", "greska")
        elif not napomena:
            flash("Unesite razlog korekcije (npr. popis, oštećenje).", "greska")
        else:
            P.korekcija_stanja(db, g.korisnik["korisnicko_ime"], aid, novo, napomena)
            db.commit()
            flash("Stanje je korigovano.", "uspeh")
        return redirect(url_for(".kartica", aid=aid))
    kretanja = db.execute("SELECT * FROM kretanja WHERE artikal_id = ? ORDER BY vreme DESC, id DESC LIMIT 500",
                          (aid,)).fetchall()
    return render_template("admin/kartica.html", a=a, kretanja=kretanja)


# ---------------------------------------------------------------------------- dobavljači
@bp.route("/admin/dobavljaci")
@login_required()
def dobavljaci():
    lista = get_db().execute("""SELECT d.*, COUNT(a.id) AS artikala FROM dobavljaci d
                                LEFT JOIN artikli a ON a.dobavljac_id = d.id GROUP BY d.id ORDER BY d.naziv""").fetchall()
    return render_template("admin/dobavljaci.html", lista=lista)


@bp.route("/admin/dobavljaci/novi", methods=["GET", "POST"])
@bp.route("/admin/dobavljaci/<int:did>", methods=["GET", "POST"])
@login_required()
def dobavljac(did=None):
    db = get_db()
    post = db.execute("SELECT * FROM dobavljaci WHERE id = ?", (did,)).fetchone() if did else None
    if did and post is None:
        abort(404)
    polja = ("naziv", "pib", "adresa", "kontakt", "telefon", "email", "napomena")
    if request.method == "POST":
        d = {p: request.form.get(p, "").strip() for p in polja}
        d["aktivan"] = 1 if request.form.get("aktivan") else 0
        greske = {}
        if not d["naziv"]:
            greske["naziv"] = "Naziv je obavezan."
        if d["pib"] and (not d["pib"].isdigit() or len(d["pib"]) != 9):
            greske["pib"] = "PIB ima tačno 9 cifara."
        try:
            d["rok_isporuke"] = broj(request.form.get("rok_isporuke"), ceo=True) or 0
        except ValueError:
            greske["rok_isporuke"] = "Rok isporuke je ceo broj dana."
        if greske:
            flash("Proverite označena polja.", "greska")
            return render_template("admin/dobavljac_form.html", d=d, post=post, greske=greske)
        kolone = list(polja) + ["aktivan", "rok_isporuke"]
        vr = [d[k] for k in kolone]
        if post:
            db.execute(f"UPDATE dobavljaci SET {', '.join(k + '=?' for k in kolone)} WHERE id = ?", vr + [did])
        else:
            db.execute(f"INSERT INTO dobavljaci ({', '.join(kolone)}) VALUES ({', '.join('?' * len(kolone))})", vr)
        db.commit()
        flash(f"Dobavljač „{d['naziv']}“ je sačuvan.", "uspeh")
        return redirect(url_for(".dobavljaci"))
    return render_template("admin/dobavljac_form.html", d=dict(post) if post else {"aktivan": 1, "rok_isporuke": 3},
                           post=post, greske={})
