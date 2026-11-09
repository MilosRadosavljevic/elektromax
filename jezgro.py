"""Zajedničke funkcije za sve delove aplikacije (javni sajt, admin, API kase)."""
import sqlite3
from functools import wraps

from flask import flash, g, redirect, request, url_for

import init_db


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(init_db.DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def login_required(uloga: str | None = None):
    """Admin panel: traži prijavu (i po potrebi ulogu)."""
    def dekorator(view):
        @wraps(view)
        def omotac(*args, **kwargs):
            if g.korisnik is None:
                return redirect(url_for("admin_login", next=request.path))
            if uloga and g.korisnik["uloga"] != uloga:
                flash("Za ovu stranicu nemate ovlašćenje.", "greska")
                return redirect(url_for("admin_pocetna"))
            return view(*args, **kwargs)
        return omotac
    return dekorator


def broj(s, ceo=False):
    """Broj iz forme: prihvata '1.290,50', '1290.5', '12'. Prazno -> None."""
    s = (str(s) if s is not None else "").strip().replace(" ", "")
    if not s:
        return None
    if not ceo:
        s = s.replace(".", "").replace(",", ".") if "," in s else s
    return int(s) if ceo else float(s)
