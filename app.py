"""Elektromax – demo sajt sa admin panelom (Flask + SQLite).

Pokretanje:  .venv\\Scripts\\python app.py   ->  http://127.0.0.1:5000
Admin panel: http://127.0.0.1:5000/admin
"""
import os
import secrets
import sqlite3
import uuid
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import init_db
import migracije
import poslovanje
from firma import FIRMA
from jezgro import broj, close_db, get_db, login_required

BASE = Path(__file__).parent
# Na serveru slike koje se otpremaju kroz admin idu van koda (ELEKTROMAX_UPLOAD_DIR); nginx ih služi na /static/uploads/
UPLOAD_DIR = Path(os.environ.get("ELEKTROMAX_UPLOAD_DIR") or BASE / "static" / "uploads")
DOZVOLJENE_SLIKE = {"jpg", "jpeg", "png", "webp"}

DANI = ["Nedelja", "Ponedeljak", "Utorak", "Sreda", "Četvrtak", "Petak", "Subota"]
REDOSLED_DANA = [1, 2, 3, 4, 5, 6, 0]  # prikaz od ponedeljka
JEDINICE_MERE = {"kom": "kom", "m": "m", "pak": "pak", "kg": "kg", "set": "set"}
IKONICE = {
    "cable": "Kabl", "socket": "Utičnica", "fuse": "Osigurač", "bulb": "Sijalica",
    "box": "Kutija", "tool": "Alat", "meter": "Instrument", "sun": "Ostalo",
}


def _secret_key() -> str:
    """Ključ za sesije: iz okruženja, ili generisan jednom i sačuvan u fajlu."""
    if os.environ.get("ELEKTROMAX_SECRET"):
        return os.environ["ELEKTROMAX_SECRET"]
    f = BASE / ".secret_key"
    if not f.exists():
        f.write_text(secrets.token_hex(32), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_secret_key(),
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,  # max 4 MB po slici
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# Produkcija (server iza nginx-a): ispravna adresa/protokol klijenta i kolačić samo preko HTTPS-a
if os.environ.get("ELEKTROMAX_PRODUKCIJA") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("ELEKTROMAX_HTTPS") == "1"


# --------------------------------------------------------------------------
# Baza
# --------------------------------------------------------------------------
app.teardown_appcontext(close_db)

from api import api  # noqa: E402  (REST API za desktop kasu)
app.register_blueprint(api)
from admin_nabavka import bp as bp_nabavka  # noqa: E402
from admin_prodaja import bp as bp_prodaja  # noqa: E402
app.register_blueprint(bp_nabavka)
app.register_blueprint(bp_prodaja)
from admin_analitika import bp as bp_analitika  # noqa: E402
app.register_blueprint(bp_analitika)


def radno_vreme():
    rows = {r["dan"]: dict(r) for r in get_db().execute("SELECT * FROM radno_vreme")}
    return [dict(rows.get(d, {"dan": d, "radi": 0, "od": None, "do": None, "napomena": ""}),
                 naziv=DANI[d]) for d in REDOSLED_DANA]


# --------------------------------------------------------------------------
# Šabloni – filteri i globalne vrednosti
# --------------------------------------------------------------------------
@app.template_filter("din")
def format_din(v):
    """1290 -> '1.290 RSD', 45.9 -> '45,90 RSD'."""
    if v is None:
        return ""
    v = float(v)
    s = f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " RSD"


@app.template_filter("broj")
def format_broj(v):
    """Za polja forme: 190.0 -> '190', 45.9 -> '45.9', None -> ''."""
    if not isinstance(v, (int, float)):  # None, prazno ili nepostojeće polje (novi artikal)
        return v if isinstance(v, str) else ""
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


@app.context_processor
def globalne():
    return {
        "IKONICE": IKONICE,
        "JEDINICE_MERE": JEDINICE_MERE,
        "korisnik": g.get("korisnik"),
        "csrf_token": _csrf_token,
        "FIRMA": FIRMA,
        "RV": radno_vreme,  # u šablonu: {% set rv = RV() %}
        "ZA_NARUCITI": _za_naruciti_broj,
        "URL_MAPA": {r.endpoint for r in app.url_map.iter_rules()},
    }


def _za_naruciti_broj():
    from admin_nabavka import predlog_nabavke
    return len(predlog_nabavke(get_db())) if g.get("korisnik") else 0


# --------------------------------------------------------------------------
# Prijava, uloge, CSRF
# --------------------------------------------------------------------------
def _csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def ucitaj_korisnika_i_proveri_csrf():
    g.korisnik = None
    if "korisnik_id" in session:
        g.korisnik = get_db().execute(
            "SELECT * FROM korisnici WHERE id = ? AND aktivan = 1", (session["korisnik_id"],)
        ).fetchone()
        if g.korisnik is None:
            session.clear()
    if request.method == "POST" and request.path.startswith("/admin"):
        if request.form.get("csrf") != session.get("csrf"):
            abort(400, "Neispravan sigurnosni token – osvežite stranicu i pokušajte ponovo.")


# --------------------------------------------------------------------------
# Javni deo sajta
# --------------------------------------------------------------------------
@app.route("/")
def pocetna():
    db = get_db()
    kategorije = db.execute("""
        SELECT k.*, COUNT(a.id) AS broj
        FROM kategorije k
        LEFT JOIN artikli a ON a.kategorija_id = k.id AND a.aktivan = 1
        WHERE k.aktivna = 1
        GROUP BY k.id ORDER BY k.redosled, k.naziv""").fetchall()
    istaknuti = db.execute("""
        SELECT a.*, k.naziv AS kategorija, k.ikonica FROM artikli a
        JOIN kategorije k ON k.id = a.kategorija_id
        WHERE a.aktivan = 1 AND a.istaknut = 1 AND k.aktivna = 1
        ORDER BY a.izmenjeno DESC LIMIT 8""").fetchall()
    return render_template("index.html", kategorije=kategorije, istaknuti=istaknuti)


@app.route("/katalog")
def katalog():
    db = get_db()
    q = request.args.get("q", "").strip()
    slug = request.args.get("kategorija", "")
    kategorije = db.execute(
        "SELECT * FROM kategorije WHERE aktivna = 1 ORDER BY redosled, naziv").fetchall()
    trenutna = next((k for k in kategorije if k["slug"] == slug), None)

    sql = """SELECT a.*, k.naziv AS kategorija, k.ikonica FROM artikli a
             JOIN kategorije k ON k.id = a.kategorija_id
             WHERE a.aktivan = 1 AND k.aktivna = 1"""
    par = []
    if trenutna:
        sql += " AND k.id = ?"
        par.append(trenutna["id"])
    if q:
        sql += " AND (a.naziv LIKE ? OR a.sifra LIKE ? OR a.opis LIKE ? OR a.proizvodjac LIKE ?)"
        par += [f"%{q}%"] * 4
    sql += " ORDER BY a.naziv"
    artikli = db.execute(sql, par).fetchall()
    return render_template("katalog.html", artikli=artikli, kategorije=kategorije,
                           trenutna=trenutna, q=q)


@app.route("/artikal/<int:id>")
def artikal(id):
    a = get_db().execute("""
        SELECT a.*, k.naziv AS kategorija, k.slug AS kategorija_slug, k.ikonica
        FROM artikli a JOIN kategorije k ON k.id = a.kategorija_id
        WHERE a.id = ? AND a.aktivan = 1 AND k.aktivna = 1""", (id,)).fetchone()
    if a is None:
        abort(404)
    return render_template("artikal.html", a=a)


@app.route("/izvori-fotografija")
def izvori_slika():
    artikli = get_db().execute("""
        SELECT a.id, a.naziv, a.slika, a.slika_kredit, a.slika_izvor FROM artikli a
        JOIN kategorije k ON k.id = a.kategorija_id
        WHERE a.aktivan = 1 AND k.aktivna = 1 AND a.slika_kredit IS NOT NULL
        ORDER BY a.naziv""").fetchall()
    return render_template("izvori.html", artikli=artikli)


# --------------------------------------------------------------------------
# Admin – prijava
# --------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("csrf") != session.get("csrf"):
            abort(400)
        k = get_db().execute(
            "SELECT * FROM korisnici WHERE korisnicko_ime = ? AND aktivan = 1",
            (request.form.get("korisnicko_ime", "").strip(),)).fetchone()
        if k and check_password_hash(k["lozinka_hash"], request.form.get("lozinka", "")):
            session.clear()
            session["korisnik_id"] = k["id"]
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin_pocetna"))
        flash("Pogrešno korisničko ime ili lozinka.", "greska")
    return render_template("admin/login.html")


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/")
@login_required()
def admin_pocetna():
    db = get_db()
    stat = db.execute("""
        SELECT
          (SELECT COUNT(*) FROM artikli)                         AS artikala,
          (SELECT COUNT(*) FROM artikli WHERE aktivan = 0)       AS sakrivenih,
          (SELECT COUNT(*) FROM artikli WHERE stanje = 0)        AS nema_na_stanju,
          (SELECT COUNT(*) FROM artikli WHERE akcijska_cena IS NOT NULL) AS na_akciji,
          (SELECT COUNT(*) FROM kategorije)                      AS kategorija""").fetchone()
    poslednji = db.execute("""
        SELECT a.id, a.naziv, a.sifra, a.izmenjeno, a.izmenio, k.naziv AS kategorija
        FROM artikli a JOIN kategorije k ON k.id = a.kategorija_id
        ORDER BY a.izmenjeno DESC LIMIT 6""").fetchall()
    from datetime import date
    danas = poslovanje.presek(db, date.today().isoformat())
    return render_template("admin/pocetna.html", stat=stat, poslednji=poslednji,
                           radno_vreme=radno_vreme(), danas=danas)


# --------------------------------------------------------------------------
# Admin – artikli
# --------------------------------------------------------------------------
def _sacuvaj_sliku(fajl) -> str | None:
    if not fajl or not fajl.filename:
        return None
    ext = fajl.filename.rsplit(".", 1)[-1].lower() if "." in fajl.filename else ""
    if ext not in DOZVOLJENE_SLIKE:
        raise ValueError("Slika mora biti JPG, PNG ili WEBP.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ime = f"{uuid.uuid4().hex}.{ext}"
    fajl.save(UPLOAD_DIR / ime)
    return ime


def _obrisi_sliku(ime: str | None):
    if ime:
        (UPLOAD_DIR / ime).unlink(missing_ok=True)


_broj = broj


def _procitaj_artikal(form, id_=None):
    """Validira formu artikla. Vraća (podaci, greške)."""
    p = {k: (form.get(k) or "").strip() for k in
         ("naziv", "sifra", "opis", "proizvodjac", "jedinica_mere", "kategorija_id",
          "slika_kredit", "slika_izvor")}
    p["istaknut"] = 1 if form.get("istaknut") else 0
    p["aktivan"] = 1 if form.get("aktivan") else 0
    greske = {}
    if not p["naziv"]:
        greske["naziv"] = "Naziv je obavezan."
    if p["slika_izvor"] and not p["slika_izvor"].startswith(("https://", "http://")):
        greske["slika_izvor"] = "Link mora počinjati sa https://"
    if not p["sifra"]:
        greske["sifra"] = "Šifra je obavezna."
    elif get_db().execute("SELECT 1 FROM artikli WHERE sifra = ? AND id IS NOT ?",
                          (p["sifra"], id_)).fetchone():
        greske["sifra"] = "Artikal sa ovom šifrom već postoji."
    if not get_db().execute("SELECT 1 FROM kategorije WHERE id = ?",
                            (p["kategorija_id"] or 0,)).fetchone():
        greske["kategorija_id"] = "Izaberite kategoriju."
    if p["jedinica_mere"] not in JEDINICE_MERE:
        greske["jedinica_mere"] = "Neispravna jedinica mere."
    try:
        p["cena"] = _broj(form.get("cena"))
        if p["cena"] is None or p["cena"] < 0:
            greske["cena"] = "Unesite cenu (0 ili više)."
    except ValueError:
        greske["cena"] = "Cena mora biti broj."
    try:
        p["akcijska_cena"] = _broj(form.get("akcijska_cena"))
        if p["akcijska_cena"] is not None and "cena" not in greske and \
                not 0 <= p["akcijska_cena"] < p["cena"]:
            greske["akcijska_cena"] = "Akcijska cena mora biti manja od redovne."
    except ValueError:
        greske["akcijska_cena"] = "Akcijska cena mora biti broj."
    try:
        p["stanje"] = _broj(form.get("stanje"), ceo=True) or 0
        if p["stanje"] < 0:
            greske["stanje"] = "Stanje ne može biti negativno."
    except ValueError:
        greske["stanje"] = "Stanje mora biti ceo broj."
    p["stanje_napomena"] = (form.get("stanje_napomena") or "").strip()
    try:
        p["nabavna_cena"] = _broj(form.get("nabavna_cena"))
        if p["nabavna_cena"] is not None and p["nabavna_cena"] < 0:
            greske["nabavna_cena"] = "Nabavna cena ne može biti negativna."
    except ValueError:
        greske["nabavna_cena"] = "Nabavna cena mora biti broj."
    try:
        p["min_kolicina"] = _broj(form.get("min_kolicina"), ceo=True) or 0
        if p["min_kolicina"] < 0:
            greske["min_kolicina"] = "Minimalna količina ne može biti negativna."
    except ValueError:
        greske["min_kolicina"] = "Minimalna količina mora biti ceo broj."
    try:
        p["pdv_stopa"] = float(form.get("pdv_stopa") or 20)
        if p["pdv_stopa"] not in (0, 10, 20):
            raise ValueError
    except ValueError:
        greske["pdv_stopa"] = "PDV stopa mora biti 20, 10 ili 0%."
    p["dobavljac_id"] = int(form.get("dobavljac_id")) if (form.get("dobavljac_id") or "").isdigit() else None
    return p, greske


@app.route("/admin/artikli")
@login_required()
def admin_artikli():
    db = get_db()
    q = request.args.get("q", "").strip()
    kat = request.args.get("kategorija", "")
    status = request.args.get("status", "")
    sql = """SELECT a.*, k.naziv AS kategorija FROM artikli a
             JOIN kategorije k ON k.id = a.kategorija_id WHERE 1 = 1"""
    par = []
    if q:
        sql += " AND (a.naziv LIKE ? OR a.sifra LIKE ? OR a.proizvodjac LIKE ?)"
        par += [f"%{q}%"] * 3
    if kat.isdigit():
        sql += " AND a.kategorija_id = ?"
        par.append(int(kat))
    if status == "aktivni":
        sql += " AND a.aktivan = 1"
    elif status == "sakriveni":
        sql += " AND a.aktivan = 0"
    elif status == "nema":
        sql += " AND a.stanje = 0"
    elif status == "akcija":
        sql += " AND a.akcijska_cena IS NOT NULL"
    sql += " ORDER BY k.redosled, a.naziv"
    return render_template(
        "admin/artikli.html", artikli=db.execute(sql, par).fetchall(),
        kategorije=db.execute("SELECT * FROM kategorije ORDER BY redosled, naziv").fetchall(),
        q=q, kat=kat, status=status)


@app.route("/admin/artikli/novi", methods=["GET", "POST"])
@app.route("/admin/artikli/<int:id>", methods=["GET", "POST"])
@login_required()
def admin_artikal(id=None):
    db = get_db()
    postojeci = None
    if id is not None:
        postojeci = db.execute("SELECT * FROM artikli WHERE id = ?", (id,)).fetchone()
        if postojeci is None:
            abort(404)
    kategorije = db.execute("SELECT * FROM kategorije ORDER BY redosled, naziv").fetchall()
    dobavljaci = db.execute("SELECT id, naziv FROM dobavljaci WHERE aktivan = 1 ORDER BY naziv").fetchall()

    if request.method == "POST":
        p, greske = _procitaj_artikal(request.form, id)
        nova_slika = None
        if not greske:
            try:
                nova_slika = _sacuvaj_sliku(request.files.get("slika"))
            except ValueError as e:
                greske["slika"] = str(e)
        if greske:
            flash("Proverite označena polja.", "greska")
            return render_template("admin/artikal_form.html", a=p, postojeci=postojeci,
                                   kategorije=kategorije, dobavljaci=dobavljaci, greske=greske)

        slika = postojeci["slika"] if postojeci else None
        if nova_slika or request.form.get("ukloni_sliku"):
            _obrisi_sliku(slika)
            slika = nova_slika
        kredit = (p["slika_kredit"] or None, p["slika_izvor"] or None) if slika else (None, None)
        vrednosti = (p["kategorija_id"], p["dobavljac_id"], p["sifra"], p["naziv"], p["opis"],
                     p["proizvodjac"], p["jedinica_mere"], p["cena"], p["akcijska_cena"],
                     p["nabavna_cena"], p["pdv_stopa"], p["min_kolicina"], slika, *kredit,
                     p["istaknut"], p["aktivan"], g.korisnik["korisnicko_ime"])
        ko = g.korisnik["korisnicko_ime"]
        if postojeci:
            db.execute("""UPDATE artikli SET kategorija_id=?, dobavljac_id=?, sifra=?, naziv=?, opis=?,
                          proizvodjac=?, jedinica_mere=?, cena=?, akcijska_cena=?, nabavna_cena=?,
                          pdv_stopa=?, min_kolicina=?, slika=?, slika_kredit=?, slika_izvor=?,
                          istaknut=?, aktivan=?, izmenio=?, izmenjeno=datetime('now','localtime')
                          WHERE id=?""", vrednosti + (id,))
            # stanje se ne upisuje direktno – razlika ide kao korekcija na karticu artikla
            poslovanje.korekcija_stanja(db, ko, id, p["stanje"], p["stanje_napomena"] or "Izmena u adminu")
            flash(f"Artikal „{p['naziv']}“ je sačuvan.", "uspeh")
        else:
            novi = db.execute("""INSERT INTO artikli (kategorija_id, dobavljac_id, sifra, naziv, opis,
                          proizvodjac, jedinica_mere, cena, akcijska_cena, nabavna_cena, pdv_stopa,
                          min_kolicina, slika, slika_kredit, slika_izvor, istaknut, aktivan, izmenio)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vrednosti).lastrowid
            poslovanje.promeni_stanje(db, novi, p["stanje"], "pocetno", "Početno stanje", ko)
            flash(f"Artikal „{p['naziv']}“ je dodat.", "uspeh")
        db.commit()
        if request.form.get("akcija") == "sacuvaj_i_novi":
            return redirect(url_for("admin_artikal"))
        return redirect(url_for("admin_artikli"))

    a = dict(postojeci) if postojeci else {
        "aktivan": 1, "istaknut": 0, "jedinica_mere": "kom", "stanje": 0, "pdv_stopa": 20,
        "min_kolicina": 0,
        "kategorija_id": request.args.get("kategorija", type=int)}
    return render_template("admin/artikal_form.html", a=a, postojeci=postojeci,
                           kategorije=kategorije, dobavljaci=dobavljaci, greske={})


@app.post("/admin/artikli/<int:id>/obrisi")
@login_required()
def admin_artikal_obrisi(id):
    db = get_db()
    a = db.execute("SELECT naziv, slika FROM artikli WHERE id = ?", (id,)).fetchone()
    istorija = db.execute("""SELECT (SELECT COUNT(*) FROM racun_stavke WHERE artikal_id = :id)
                                  + (SELECT COUNT(*) FROM prijem_stavke WHERE artikal_id = :id)
                                  + (SELECT COUNT(*) FROM narudzbenica_stavke WHERE artikal_id = :id)""",
                          {"id": id}).fetchone()[0]
    if a and istorija:
        flash(f"„{a['naziv']}“ se pojavljuje na računima ili u nabavci, pa ne može da se obriše "
              "(istorija mora da ostane). Sakrijte ga sa sajta umesto brisanja.", "greska")
    elif a:
        db.execute("DELETE FROM artikli WHERE id = ?", (id,))
        db.commit()
        _obrisi_sliku(a["slika"])
        flash(f"Artikal „{a['naziv']}“ je obrisan.", "uspeh")
    return redirect(url_for("admin_artikli"))


@app.post("/admin/artikli/<int:id>/vidljivost")
@login_required()
def admin_artikal_vidljivost(id):
    db = get_db()
    db.execute("""UPDATE artikli SET aktivan = 1 - aktivan, izmenio = ?,
                  izmenjeno = datetime('now','localtime') WHERE id = ?""",
               (g.korisnik["korisnicko_ime"], id))
    db.commit()
    return redirect(request.referrer or url_for("admin_artikli"))


# --------------------------------------------------------------------------
# Admin – kategorije (samo admin)
# --------------------------------------------------------------------------
@app.route("/admin/kategorije")
@login_required("admin")
def admin_kategorije():
    kategorije = get_db().execute("""
        SELECT k.*, COUNT(a.id) AS broj FROM kategorije k
        LEFT JOIN artikli a ON a.kategorija_id = k.id
        GROUP BY k.id ORDER BY k.redosled, k.naziv""").fetchall()
    return render_template("admin/kategorije.html", kategorije=kategorije)


def _slug(s: str) -> str:
    zamene = str.maketrans({"č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj",
                            "Č": "c", "Ć": "c", "Š": "s", "Ž": "z", "Đ": "dj"})
    s = s.translate(zamene).lower()
    out = "".join(c if c.isalnum() else "-" for c in s)
    return "-".join(filter(None, out.split("-")))


@app.route("/admin/kategorije/nova", methods=["GET", "POST"])
@app.route("/admin/kategorije/<int:id>", methods=["GET", "POST"])
@login_required("admin")
def admin_kategorija(id=None):
    db = get_db()
    postojeca = None
    if id is not None:
        postojeca = db.execute("SELECT * FROM kategorije WHERE id = ?", (id,)).fetchone()
        if postojeca is None:
            abort(404)
    if request.method == "POST":
        f = request.form
        k = {"naziv": f.get("naziv", "").strip(), "opis": f.get("opis", "").strip(),
             "ikonica": f.get("ikonica", "box"), "aktivna": 1 if f.get("aktivna") else 0,
             "slug": _slug(f.get("slug", "").strip() or f.get("naziv", ""))}
        greske = {}
        if not k["naziv"]:
            greske["naziv"] = "Naziv je obavezan."
        if not k["slug"]:
            greske["slug"] = "Unesite URL oznaku."
        elif db.execute("SELECT 1 FROM kategorije WHERE slug = ? AND id IS NOT ?",
                        (k["slug"], id)).fetchone():
            greske["slug"] = "Ova URL oznaka je već zauzeta."
        if k["ikonica"] not in IKONICE:
            k["ikonica"] = "box"
        try:
            k["redosled"] = int(f.get("redosled") or 0)
        except ValueError:
            greske["redosled"] = "Redosled mora biti ceo broj."
        if greske:
            flash("Proverite označena polja.", "greska")
            return render_template("admin/kategorija_form.html", k=k, postojeca=postojeca,
                                   greske=greske)
        if postojeca:
            db.execute("""UPDATE kategorije SET naziv=?, slug=?, opis=?, ikonica=?, redosled=?,
                          aktivna=? WHERE id=?""",
                       (k["naziv"], k["slug"], k["opis"], k["ikonica"], k["redosled"],
                        k["aktivna"], id))
        else:
            db.execute("""INSERT INTO kategorije (naziv, slug, opis, ikonica, redosled, aktivna)
                          VALUES (?,?,?,?,?,?)""",
                       (k["naziv"], k["slug"], k["opis"], k["ikonica"], k["redosled"],
                        k["aktivna"]))
        db.commit()
        flash(f"Kategorija „{k['naziv']}“ je sačuvana.", "uspeh")
        return redirect(url_for("admin_kategorije"))

    k = dict(postojeca) if postojeca else {
        "aktivna": 1, "ikonica": "box",
        "redosled": (db.execute("SELECT COALESCE(MAX(redosled),0)+10 FROM kategorije")
                     .fetchone()[0])}
    return render_template("admin/kategorija_form.html", k=k, postojeca=postojeca, greske={})


@app.post("/admin/kategorije/<int:id>/obrisi")
@login_required("admin")
def admin_kategorija_obrisi(id):
    db = get_db()
    k = db.execute("SELECT naziv FROM kategorije WHERE id = ?", (id,)).fetchone()
    broj = db.execute("SELECT COUNT(*) FROM artikli WHERE kategorija_id = ?", (id,)).fetchone()[0]
    if k and broj:
        flash(f"Kategorija „{k['naziv']}“ ima {broj} artikala – prvo ih premestite ili obrišite.",
              "greska")
    elif k:
        db.execute("DELETE FROM kategorije WHERE id = ?", (id,))
        db.commit()
        flash(f"Kategorija „{k['naziv']}“ je obrisana.", "uspeh")
    return redirect(url_for("admin_kategorije"))


# --------------------------------------------------------------------------
# Admin – radno vreme
# --------------------------------------------------------------------------
@app.route("/admin/radno-vreme", methods=["GET", "POST"])
@login_required()
def admin_radno_vreme():
    db = get_db()
    if request.method == "POST":
        greske, dani = {}, []
        for d in range(7):
            radi = 1 if request.form.get(f"radi_{d}") else 0
            od = request.form.get(f"od_{d}") or None
            do = request.form.get(f"do_{d}") or None
            nap = request.form.get(f"napomena_{d}", "").strip()
            if radi and (not od or not do):
                greske[d] = "Unesite vreme otvaranja i zatvaranja."
            elif radi and od >= do:
                greske[d] = "Zatvaranje mora biti posle otvaranja."
            dani.append((d, radi, od if radi else None, do if radi else None, nap))
        if greske:
            flash("Radno vreme nije sačuvano – proverite označene dane.", "greska")
            rv = [{"dan": d, "naziv": DANI[d], "radi": r, "od": o, "do": z, "napomena": n}
                  for d, r, o, z, n in dani]
            rv.sort(key=lambda x: REDOSLED_DANA.index(x["dan"]))
            return render_template("admin/radno_vreme.html", radno_vreme=rv, greske=greske)
        db.executemany("""INSERT INTO radno_vreme (dan, radi, od, do, napomena)
                          VALUES (?,?,?,?,?)
                          ON CONFLICT(dan) DO UPDATE SET radi=excluded.radi, od=excluded.od,
                          do=excluded.do, napomena=excluded.napomena""", dani)
        db.commit()
        flash("Radno vreme je sačuvano i odmah se vidi na sajtu.", "uspeh")
        return redirect(url_for("admin_radno_vreme"))
    return render_template("admin/radno_vreme.html", radno_vreme=radno_vreme(), greske={})


# --------------------------------------------------------------------------
# Admin – korisnici (samo admin)
# --------------------------------------------------------------------------
@app.route("/admin/korisnici")
@login_required("admin")
def admin_korisnici():
    korisnici = get_db().execute("SELECT * FROM korisnici ORDER BY uloga, ime").fetchall()
    return render_template("admin/korisnici.html", korisnici=korisnici)


@app.route("/admin/korisnici/novi", methods=["GET", "POST"])
@app.route("/admin/korisnici/<int:id>", methods=["GET", "POST"])
@login_required("admin")
def admin_korisnik(id=None):
    db = get_db()
    postojeci = None
    if id is not None:
        postojeci = db.execute("SELECT * FROM korisnici WHERE id = ?", (id,)).fetchone()
        if postojeci is None:
            abort(404)
    if request.method == "POST":
        f = request.form
        k = {"korisnicko_ime": f.get("korisnicko_ime", "").strip().lower(),
             "ime": f.get("ime", "").strip(),
             "uloga": f.get("uloga") if f.get("uloga") in ("admin", "radnik") else "radnik",
             "aktivan": 1 if f.get("aktivan") else 0}
        lozinka = f.get("lozinka", "")
        greske = {}
        if not k["korisnicko_ime"]:
            greske["korisnicko_ime"] = "Korisničko ime je obavezno."
        elif db.execute("SELECT 1 FROM korisnici WHERE korisnicko_ime = ? AND id IS NOT ?",
                        (k["korisnicko_ime"], id)).fetchone():
            greske["korisnicko_ime"] = "Korisničko ime je zauzeto."
        if not k["ime"]:
            greske["ime"] = "Ime je obavezno."
        if (not postojeci or lozinka) and len(lozinka) < 6:
            greske["lozinka"] = "Lozinka mora imati bar 6 znakova."
        if postojeci and postojeci["id"] == g.korisnik["id"] and \
                (k["uloga"] != "admin" or not k["aktivan"]):
            greske["uloga"] = "Ne možete sebi oduzeti admin prava ili se deaktivirati."
        if greske:
            flash("Proverite označena polja.", "greska")
            return render_template("admin/korisnik_form.html", k=k, postojeci=postojeci,
                                   greske=greske)
        if postojeci:
            db.execute("UPDATE korisnici SET korisnicko_ime=?, ime=?, uloga=?, aktivan=? WHERE id=?",
                       (k["korisnicko_ime"], k["ime"], k["uloga"], k["aktivan"], id))
            if lozinka:
                db.execute("UPDATE korisnici SET lozinka_hash=? WHERE id=?",
                           (generate_password_hash(lozinka), id))
        else:
            db.execute("""INSERT INTO korisnici (korisnicko_ime, ime, lozinka_hash, uloga, aktivan)
                          VALUES (?,?,?,?,?)""",
                       (k["korisnicko_ime"], k["ime"], generate_password_hash(lozinka),
                        k["uloga"], k["aktivan"]))
        db.commit()
        flash(f"Korisnik „{k['ime']}“ je sačuvan.", "uspeh")
        return redirect(url_for("admin_korisnici"))
    k = dict(postojeci) if postojeci else {"uloga": "radnik", "aktivan": 1}
    return render_template("admin/korisnik_form.html", k=k, postojeci=postojeci, greske={})


# --------------------------------------------------------------------------
@app.errorhandler(404)
def nije_nadjeno(_e):
    return render_template("404.html"), 404


@app.errorhandler(413)
def prevelik_fajl(_e):
    flash("Slika je prevelika (najviše 4 MB).", "greska")
    return redirect(request.referrer or url_for("admin_artikli"))


if __name__ == "__main__":
    if not init_db.DB_PATH.exists():
        init_db.init_db()
        print("Napravljena nova baza sa demo podacima.")
    migracije.migriraj()
    # Podrazumevano samo ovaj računar. Za pregled sa telefona u istoj Wi-Fi mreži:
    #   set ELEKTROMAX_HOST=<IP adresa računara>   (npr. 192.168.1.127)
    host = os.environ.get("ELEKTROMAX_HOST", "127.0.0.1")
    # Interaktivni debugger samo lokalno – u mreži bi omogućio izvršavanje koda na računaru.
    port = int(os.environ.get("ELEKTROMAX_PORT", "5000"))
    app.run(host=host, port=port, debug=True, use_debugger=host == "127.0.0.1")
