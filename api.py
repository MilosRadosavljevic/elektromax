"""REST API za desktop kasu.  Sve rute su pod /api, prijava je token (Authorization: Bearer ...)."""
import hashlib
import secrets
from datetime import date
from decimal import Decimal
from functools import wraps

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash

import poslovanje as P
from firma import FIRMA
from jezgro import get_db

api = Blueprint("api", __name__, url_prefix="/api")
VERZIJA_API = 1


def _json(x):
    """Decimal -> float, rekurzivno."""
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, dict):
        return {k: _json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json(v) for v in x]
    return x


def ok(podaci=None, status=200):
    return jsonify(_json(podaci if podaci is not None else {"ok": True})), status


def greska(poruka, status=400, kod="greska", **detalji):
    return jsonify({"greska": poruka, "kod": kod, **detalji}), status


@api.errorhandler(P.PoslovnaGreska)
def _poslovna(e):
    return greska(e.poruka, 403 if e.kod == "potrebno_odobrenje" else 400, e.kod, **e.detalji)


def _hes(token):
    return hashlib.sha256(token.encode()).hexdigest()


def token_required(uloga=None):
    def dek(view):
        @wraps(view)
        def omotac(*a, **kw):
            zag = request.headers.get("Authorization", "")
            token = zag[7:] if zag.startswith("Bearer ") else ""
            db = get_db()
            k = db.execute("""SELECT k.* FROM api_tokeni t JOIN korisnici k ON k.id = t.korisnik_id
                              WHERE t.token_hash = ? AND k.aktivan = 1""", (_hes(token),)).fetchone() if token else None
            if k is None:
                return greska("Niste prijavljeni ili je sesija istekla.", 401, "neprijavljen")
            if uloga and k["uloga"] != uloga:
                return greska("Nemate ovlašćenje za ovu radnju.", 403, "zabranjeno")
            db.execute("UPDATE api_tokeni SET koriscen = datetime('now','localtime') WHERE token_hash = ?",
                       (_hes(token),))
            db.commit()
            g.api_korisnik = k
            return view(*a, **kw)
        return omotac
    return dek


def _telo():
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------------------- prijava
@api.post("/login")
def login():
    t = _telo()
    db = get_db()
    k = db.execute("SELECT * FROM korisnici WHERE korisnicko_ime = ? AND aktivan = 1",
                   ((t.get("korisnicko_ime") or "").strip().lower(),)).fetchone()
    if not k or not check_password_hash(k["lozinka_hash"], t.get("lozinka") or ""):
        return greska("Pogrešno korisničko ime ili lozinka.", 401, "neprijavljen")
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO api_tokeni (token_hash, korisnik_id) VALUES (?, ?)", (_hes(token), k["id"]))
    db.commit()
    return ok({"token": token, "korisnik": {"id": k["id"], "ime": k["ime"], "uloga": k["uloga"],
                                             "korisnicko_ime": k["korisnicko_ime"]}})


@api.post("/logout")
@token_required()
def logout():
    zag = request.headers.get("Authorization", "")
    get_db().execute("DELETE FROM api_tokeni WHERE token_hash = ?", (_hes(zag[7:]),))
    get_db().commit()
    return ok()


@api.get("/info")
@token_required()
def info():
    db = get_db()
    return ok({"api": VERZIJA_API, "firma": FIRMA,
               "max_popust_radnik": float(P.podesavanje(db, "max_popust_radnik", "10")),
               "predracun_dana": int(P.podesavanje(db, "predracun_dana", "7")),
               "fiskal_rezim": __import__("fiskal").adapter().rezim})


# ---------------------------------------------------------------------------- šifarnici
@api.get("/artikli")
@token_required()
def artikli():
    q = (request.args.get("q") or "").strip()
    sql = """SELECT a.id, a.sifra, a.naziv, a.jedinica_mere, a.cena, a.akcijska_cena, a.pdv_stopa, a.stanje,
                    a.min_kolicina, a.aktivan, k.naziv AS kategorija
             FROM artikli a JOIN kategorije k ON k.id = a.kategorija_id"""
    par = []
    if q:
        sql += " WHERE a.naziv LIKE ? OR a.sifra LIKE ? OR a.proizvodjac LIKE ?"
        par = [f"%{q}%"] * 3
    sql += " ORDER BY a.naziv LIMIT 300"
    return ok([dict(r) for r in get_db().execute(sql, par)])


@api.get("/kupci")
@token_required()
def kupci():
    q = (request.args.get("q") or "").strip()
    r = get_db().execute("SELECT * FROM kupci WHERE naziv LIKE ? OR pib LIKE ? ORDER BY naziv LIMIT 100",
                         (f"%{q}%", f"%{q}%"))
    return ok([dict(x) for x in r])


@api.post("/kupci")
@token_required()
def kupac_novi():
    t = _telo()
    if not (t.get("naziv") or "").strip():
        return greska("Naziv kupca je obavezan.")
    pib = (t.get("pib") or "").strip()
    if pib and (not pib.isdigit() or len(pib) != 9):
        return greska("PIB mora imati tačno 9 cifara.")
    db = get_db()
    polja = ("naziv", "pib", "mb", "adresa", "mesto", "telefon", "email")
    kid = db.execute(f"INSERT INTO kupci ({', '.join(polja)}) VALUES ({', '.join('?' * len(polja))})",
                     [(t.get(p) or "").strip() for p in polja]).lastrowid
    db.commit()
    return ok(dict(db.execute("SELECT * FROM kupci WHERE id = ?", (kid,)).fetchone()), 201)


# ---------------------------------------------------------------------------- računi
@api.post("/racuni")
@token_required()
def racun_novi():
    db = get_db()
    try:
        r = P.izdaj(db, g.api_korisnik, _telo())
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ok(r, 201)


@api.get("/racuni")
@token_required()
def racuni_lista():
    a = request.args
    sql = """SELECT r.id, r.broj, r.tip, r.status, r.vreme, r.ukupno, r.popust, r.vazi_do, k.ime AS kasir,
                    ku.naziv AS kupac
             FROM racuni r JOIN korisnici k ON k.id = r.kasir_id LEFT JOIN kupci ku ON ku.id = r.kupac_id
             WHERE date(r.vreme) BETWEEN ? AND ?"""
    par = [a.get("od") or date.today().isoformat(), a.get("do") or date.today().isoformat()]
    if a.get("tip"):
        sql += " AND r.tip = ?"
        par.append(a["tip"])
    if a.get("q"):
        sql += " AND (r.broj LIKE ? OR ku.naziv LIKE ?)"
        par += [f"%{a['q']}%"] * 2
    sql += " ORDER BY r.vreme DESC, r.id DESC LIMIT 500"
    return ok([dict(r) for r in get_db().execute(sql, par)])


@api.get("/racuni/<int:rid>")
@token_required()
def racun_detalj(rid):
    return ok(P.racun(get_db(), rid))


def _transakcija(fn):
    db = get_db()
    try:
        r = fn(db)
        db.commit()
        return r
    except Exception:
        db.rollback()
        raise


@api.post("/racuni/<int:rid>/storno")
@token_required()
def racun_storno(rid):
    t = _telo()
    r = _transakcija(lambda db: P.storniraj(db, g.api_korisnik, rid, t.get("stavke"), t.get("razlog", ""),
                                            t.get("odobrenje"), t.get("nacin_povrata")))
    return ok(r, 201)


@api.post("/racuni/<int:rid>/realizuj")
@token_required()
def predracun_realizuj(rid):
    t = _telo()
    return ok(_transakcija(lambda db: P.realizuj_predracun(db, g.api_korisnik, rid, t.get("placanja"))), 201)


@api.post("/racuni/<int:rid>/ponisti")
@token_required()
def predracun_ponisti(rid):
    _transakcija(lambda db: P.ponisti_predracun(db, rid))
    return ok()


@api.get("/presek")
@token_required()
def presek():
    return ok(P.presek(get_db(), request.args.get("dan") or date.today().isoformat()))
