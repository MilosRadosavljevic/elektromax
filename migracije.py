"""Dopunjava postojeću bazu na poslednju šemu, bez gubitka podataka.

Poziva se pri svakom pokretanju servera (app.py). Bezbedno je pokrenuti više puta.
"""
import re
import sqlite3
from pathlib import Path

import init_db

BASE = Path(__file__).parent

PODESAVANJA = {
    "max_popust_radnik": "10",   # % popusta koji radnik daje bez odobrenja admina
    "predracun_dana": "7",       # rok važenja predračuna
}


def _naredbe_seme():
    """CREATE naredbe iz schema.sql, prepravljene u 'IF NOT EXISTS' oblik."""
    tekst = "\n".join(l for l in (BASE / "schema.sql").read_text(encoding="utf-8").splitlines()
                      if not l.strip().startswith("--"))
    tekst = re.sub(r"\s--[^\n]*", "", tekst)  # komentari na kraju reda
    naredbe = {}
    for n in (x.strip() for x in tekst.split(";")):
        m = re.match(r"CREATE (TABLE|INDEX) (\w+)", n)
        if m:
            naredbe[m.group(2)] = (m.group(1), n)
    return naredbe


def _kolone(con, tabela):
    return [r[1] for r in con.execute(f"PRAGMA table_info({tabela})")]


def _prepravi_artikle(con, naredbe):
    """Stara tabela artikli (CHECK stanje >= 0, bez nabavnih podataka) -> nova definicija."""
    stari_sql = con.execute("SELECT sql FROM sqlite_master WHERE name = 'artikli'").fetchone()[0]
    nove = set(_kolone_iz_sql(naredbe["artikli"][1]))
    if "CHECK (stanje >= 0)" not in stari_sql and nove <= set(_kolone(con, "artikli")):
        return False
    zajednicke = [k for k in _kolone(con, "artikli") if k in nove]
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("BEGIN")
    con.execute(naredbe["artikli"][1].replace("CREATE TABLE artikli", "CREATE TABLE artikli_novo", 1))
    lista = ", ".join(zajednicke)
    con.execute(f"INSERT INTO artikli_novo ({lista}) SELECT {lista} FROM artikli")
    con.execute("DROP TABLE artikli")
    con.execute("ALTER TABLE artikli_novo RENAME TO artikli")
    con.execute("COMMIT")
    con.execute("PRAGMA foreign_keys = ON")
    return True


def _kolone_iz_sql(sql):
    telo = sql[sql.index("(") + 1:]
    return [m.group(1) for m in re.finditer(r"^\s{4}(\w+)\s+(?:INTEGER|TEXT|REAL)", telo, re.M)]


def migriraj(db_path=None) -> list[str]:
    con = sqlite3.connect(db_path or init_db.DB_PATH, isolation_level=None)
    uradjeno = []
    naredbe = _naredbe_seme()
    postoji = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}

    if "artikli" in postoji and _prepravi_artikle(con, naredbe):
        uradjeno.append("artikli: nova struktura")
        postoji.discard("ix_artikli_kategorija")
        postoji.discard("ix_artikli_naziv")

    for ime, (vrsta, sql) in naredbe.items():
        if ime not in postoji:
            con.execute(sql)
            uradjeno.append(f"{vrsta.lower()} {ime}")

    for k, v in PODESAVANJA.items():
        con.execute("INSERT OR IGNORE INTO podesavanja (kljuc, vrednost) VALUES (?, ?)", (k, v))

    # Artikli bez ijednog kretanja dobijaju početno stanje, da kartica artikla bude potpuna
    n = con.execute("""INSERT INTO kretanja (artikal_id, tip, kolicina, stanje_posle, dokument, korisnik)
                       SELECT id, 'pocetno', stanje, stanje, 'Početno stanje', 'migracija' FROM artikli a
                       WHERE NOT EXISTS (SELECT 1 FROM kretanja k WHERE k.artikal_id = a.id)""").rowcount
    if n:
        uradjeno.append(f"početno stanje za {n} artikala")
    con.close()
    return uradjeno


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(migriraj()) or "Baza je već ažurna.")
