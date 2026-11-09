"""Admin – prodaja: pregled računa (sa štampom A4), kupci, podešavanja kase."""
import re
from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import dokumenti
import poslovanje as P
from firma import FIRMA
from jezgro import broj, get_db, login_required

bp = Blueprint("prodaja", __name__)


@bp.route("/admin/racuni")
@login_required()
def racuni():
    a = request.args
    od = a.get("od") or (date.today() - timedelta(days=6)).isoformat()
    do = a.get("do") or date.today().isoformat()
    sql = """SELECT r.*, k.ime AS kasir, ku.naziv AS kupac FROM racuni r JOIN korisnici k ON k.id = r.kasir_id
             LEFT JOIN kupci ku ON ku.id = r.kupac_id WHERE date(r.vreme) BETWEEN ? AND ?"""
    par = [od, do]
    if a.get("tip"):
        sql += " AND r.tip = ?"
        par.append(a["tip"])
    if a.get("q"):
        sql += " AND (r.broj LIKE ? OR ku.naziv LIKE ?)"
        par += [f"%{a['q']}%"] * 2
    sql += " ORDER BY r.vreme DESC, r.id DESC LIMIT 1000"
    lista = get_db().execute(sql, par).fetchall()
    zbir = sum(r["ukupno"] if r["tip"] == "racun" else -r["ukupno"] for r in lista if r["tip"] != "predracun")
    return render_template("admin/racuni.html", lista=lista, od=od, do=do, tip=a.get("tip", ""),
                           q=a.get("q", ""), zbir=zbir)


@bp.route("/admin/racuni/<int:rid>")
@login_required()
def racun(rid):
    try:
        r = P.racun(get_db(), rid)
    except P.PoslovnaGreska:
        abort(404)
    html = dokumenti.html_racun_80(r, FIRMA)
    telo = re.search(r"<body[^>]*>(.*)</body>", html, re.S)   # samo sadržaj, bez <html>/<body> stilova
    return render_template("admin/racun.html", r=r, isecak=telo.group(1) if telo else html)


@bp.route("/admin/racuni/<int:rid>/stampa")
@login_required()
def racun_stampa(rid):
    try:
        r = P.racun(get_db(), rid)
    except P.PoslovnaGreska:
        abort(404)
    kopija = r["tip"] != "predracun"
    return render_template("admin/stampa_a4.html", html=dokumenti.html_a4(r, FIRMA, kopija=kopija), naslov=r["broj"])


# ---------------------------------------------------------------------------- kupci
@bp.route("/admin/kupci")
@login_required()
def kupci():
    q = request.args.get("q", "").strip()
    lista = get_db().execute("""
        SELECT ku.*, COUNT(r.id) AS racuna,
               COALESCE(SUM(CASE WHEN r.tip='racun' THEN r.ukupno WHEN r.tip='storno' THEN -r.ukupno END), 0) AS promet,
               MAX(r.vreme) AS poslednji
        FROM kupci ku LEFT JOIN racuni r ON r.kupac_id = ku.id AND r.tip IN ('racun', 'storno')
        WHERE ku.naziv LIKE ? OR ku.pib LIKE ? GROUP BY ku.id ORDER BY promet DESC, ku.naziv""",
                             (f"%{q}%", f"%{q}%")).fetchall()
    return render_template("admin/kupci.html", lista=lista, q=q)


@bp.route("/admin/kupci/novi", methods=["GET", "POST"])
@bp.route("/admin/kupci/<int:kid>", methods=["GET", "POST"])
@login_required()
def kupac(kid=None):
    db = get_db()
    post = db.execute("SELECT * FROM kupci WHERE id = ?", (kid,)).fetchone() if kid else None
    if kid and post is None:
        abort(404)
    polja = ("naziv", "pib", "mb", "adresa", "mesto", "telefon", "email", "napomena")
    if request.method == "POST":
        k = {p: request.form.get(p, "").strip() for p in polja}
        greske = {}
        if not k["naziv"]:
            greske["naziv"] = "Naziv je obavezan."
        if k["pib"] and (not k["pib"].isdigit() or len(k["pib"]) != 9):
            greske["pib"] = "PIB ima tačno 9 cifara."
        if k["mb"] and not k["mb"].isdigit():
            greske["mb"] = "Matični broj sadrži samo cifre."
        if greske:
            flash("Proverite označena polja.", "greska")
            return render_template("admin/kupac_form.html", k=k, post=post, greske=greske, racuni=[])
        if post:
            db.execute(f"UPDATE kupci SET {', '.join(p + '=?' for p in polja)} WHERE id = ?",
                       [k[p] for p in polja] + [kid])
        else:
            db.execute(f"INSERT INTO kupci ({', '.join(polja)}) VALUES ({', '.join('?' * len(polja))})",
                       [k[p] for p in polja])
        db.commit()
        flash(f"Kupac „{k['naziv']}“ je sačuvan.", "uspeh")
        return redirect(url_for(".kupci"))
    racuni = db.execute("SELECT * FROM racuni WHERE kupac_id = ? ORDER BY vreme DESC LIMIT 50", (kid,)).fetchall() \
        if kid else []
    return render_template("admin/kupac_form.html", k=dict(post) if post else {}, post=post, greske={}, racuni=racuni)


# ---------------------------------------------------------------------------- podešavanja kase
@bp.route("/admin/podesavanja", methods=["GET", "POST"])
@login_required("admin")
def podesavanja():
    db = get_db()
    if request.method == "POST":
        try:
            mp = broj(request.form.get("max_popust_radnik"))
            pd = broj(request.form.get("predracun_dana"), ceo=True)
            if mp is None or not 0 <= mp <= 100 or pd is None or not 1 <= pd <= 90:
                raise ValueError
        except ValueError:
            flash("Popust je između 0 i 100%, a rok predračuna između 1 i 90 dana.", "greska")
            return redirect(url_for(".podesavanja"))
        for k, v in (("max_popust_radnik", f"{mp:g}"), ("predracun_dana", str(pd))):
            db.execute("INSERT INTO podesavanja (kljuc, vrednost) VALUES (?, ?) "
                       "ON CONFLICT(kljuc) DO UPDATE SET vrednost = excluded.vrednost", (k, v))
        db.commit()
        flash("Podešavanja su sačuvana. Kasa ih preuzima pri sledećoj prijavi.", "uspeh")
        return redirect(url_for(".podesavanja"))
    return render_template("admin/podesavanja.html",
                           max_popust=P.podesavanje(db, "max_popust_radnik", "10"),
                           predracun_dana=P.podesavanje(db, "predracun_dana", "7"), firma=FIRMA)
