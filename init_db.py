"""Pravi bazu elektromax.db od nule i puni je demo podacima.

Pokretanje:  .venv\\Scripts\\python init_db.py
PAŽNJA: briše postojeću bazu (svi uneti artikli se gube).
"""
import json
import os
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE = Path(__file__).parent
DB_PATH = Path(os.environ.get("ELEKTROMAX_DB") or BASE / "elektromax.db")  # ELEKTROMAX_DB = druga baza (testovi)

# Demo nalozi za admin panel (samo za lokalno testiranje – promeniti pre produkcije!)
DEMO_KORISNICI = [
    ("admin", "Administrator", "admin123", "admin"),
    ("radnik", "Petar Radnik", "radnik123", "radnik"),
]

KATEGORIJE = [
    # naziv, slug, opis, ikonica
    ("Kablovi i provodnici", "kablovi", "Instalacioni i energetski kablovi, provodnici, produžni kablovi i pribor.", "cable"),
    ("Prekidači i utičnice", "prekidaci-uticnice", "Modularni i klasični program, OG i PG varijante, dozne, okviri i maske.", "socket"),
    ("Razvodne table", "razvodne-table", "Automatski osigurači, FID sklopke, ormarići, šine i kleme.", "fuse"),
    ("Rasveta", "rasveta", "LED sijalice, paneli, reflektori, lampe i trake.", "bulb"),
    ("Instalacioni pribor", "instalacioni-pribor", "Cevi, kanalice, razvodne kutije, tiple, vezice i izolir trake.", "box"),
    ("Alat", "alat", "Izolovan alat, kombinirke, odvijači, skidači izolacije.", "tool"),
    ("Merni instrumenti", "merni-instrumenti", "Multimetri, ispitivači napona, indikatori faze.", "meter"),
    ("Ostala oprema", "ostala-oprema", "Grejači, ventilatori, zvonca, senzori pokreta, tajmeri.", "sun"),
]

# slug kategorije, šifra, naziv, proizvođač, jm, cena, akcijska, stanje, istaknut, opis
ARTIKLI = [
    ("kablovi", "KAB-001", "Kabl PP-Y 3x1,5 mm²", "", "m", 95, None, 800, 1, "Instalacioni kabl za rasvetu i opšte instalacije."),
    ("kablovi", "KAB-002", "Kabl PP-Y 3x2,5 mm²", "", "m", 145, None, 650, 1, "Instalacioni kabl za utičnička kola."),
    ("kablovi", "KAB-003", "Kabl PP-Y 5x2,5 mm²", "", "m", 235, None, 300, 0, "Petožilni kabl za trofazne potrošače."),
    ("kablovi", "KAB-004", "Kabl PP/L 2x1,5 mm²", "", "m", 62, None, 500, 0, "Pljosnati kabl za polaganje u malter."),
    ("kablovi", "KAB-005", "Provodnik P/F 1x6 mm² žuto-zeleni", "", "m", 110, None, 200, 0, "Provodnik za izjednačavanje potencijala."),
    ("kablovi", "KAB-006", "Produžni kabl 3 utičnice, 3 m", "", "kom", 890, 790, 25, 1, "Produžni kabl sa prekidačem, 3x šuko."),
    ("prekidaci-uticnice", "PRU-001", "Utičnica šuko OG, bela", "", "kom", 320, None, 60, 0, "Nadgradna šuko utičnica, 16 A."),
    ("prekidaci-uticnice", "PRU-002", "Utičnica šuko PG modularna", "", "kom", 280, None, 90, 0, "Modularna ugradna utičnica, 2 modula."),
    ("prekidaci-uticnice", "PRU-003", "Prekidač obični PG modularni", "", "kom", 240, None, 75, 0, "Modularni prekidač, 1 modul."),
    ("prekidaci-uticnice", "PRU-004", "Naizmenični prekidač PG", "", "kom", 290, None, 40, 0, "Za paljenje svetla sa dva mesta."),
    ("prekidaci-uticnice", "PRU-005", "Dozna za ugradnju Ø60", "", "kom", 25, None, 400, 0, "Ugradna dozna za zid od opeke."),
    ("razvodne-table", "RTB-001", "Automatski osigurač B16 1P", "", "kom", 390, None, 120, 1, "Minijaturni prekidač, kriva B, 16 A."),
    ("razvodne-table", "RTB-002", "Automatski osigurač B10 1P", "", "kom", 390, None, 80, 0, "Minijaturni prekidač, kriva B, 10 A."),
    ("razvodne-table", "RTB-003", "FID sklopka 40A/30mA 4P", "", "kom", 3900, 3490, 12, 1, "Zaštitna strujna sklopka za trofaznu instalaciju."),
    ("razvodne-table", "RTB-004", "Razvodni ormarić PG 24 modula", "", "kom", 2750, None, 8, 0, "Ugradni ormarić sa vratima i šinom."),
    ("razvodne-table", "RTB-005", "Redna stezaljka 4 mm²", "", "kom", 45, None, 300, 0, "Klema za DIN šinu."),
    ("rasveta", "RAS-001", "LED sijalica E27 10W topla", "", "kom", 190, 149, 150, 1, "Zamena za klasičnu sijalicu od 75 W."),
    ("rasveta", "RAS-002", "LED sijalica E14 6W neutralna", "", "kom", 170, None, 110, 0, "Mala sijalica za lustere i lampe."),
    ("rasveta", "RAS-003", "LED panel 60x60 40W", "", "kom", 2490, None, 20, 1, "Panel za spušteni plafon, 4000K."),
    ("rasveta", "RAS-004", "LED reflektor 50W IP65", "", "kom", 1850, None, 15, 0, "Spoljni reflektor za dvorište i objekte."),
    ("rasveta", "RAS-005", "LED traka 5 m, 12V topla", "", "set", 1290, None, 18, 0, "Traka sa adapterom za dekorativno osvetljenje."),
    ("instalacioni-pribor", "PRB-001", "Rebrasto crevo Ø16", "", "m", 28, None, 1000, 0, "Savitljiva instalaciona cev."),
    ("instalacioni-pribor", "PRB-002", "Kanalica 25x16 bela, 2 m", "", "kom", 210, None, 60, 0, "PVC kanalica za nadgradnu instalaciju."),
    ("instalacioni-pribor", "PRB-003", "Razvodna kutija OG IP54", "", "kom", 160, None, 70, 0, "Nadgradna razvodna kutija sa uvodnicama."),
    ("instalacioni-pribor", "PRB-004", "Izolir traka crna", "", "kom", 90, None, 200, 0, "PVC izolaciona traka, 19 mm x 20 m."),
    ("instalacioni-pribor", "PRB-005", "Vezice kablovske 200 mm", "", "pak", 240, None, 45, 0, "Pakovanje 100 kom."),
    ("alat", "ALT-001", "Kombinirka izolovana 1000V", "", "kom", 1590, None, 10, 1, "VDE izolovana kombinirka, 180 mm."),
    ("alat", "ALT-002", "Set odvijača izolovanih, 6 kom", "", "set", 2290, None, 7, 0, "Ravni i krstasti odvijači, 1000 V."),
    ("alat", "ALT-003", "Skidač izolacije automatski", "", "kom", 1990, None, 6, 0, "Za provodnike 0,2–6 mm²."),
    ("merni-instrumenti", "MER-001", "Digitalni multimetar", "", "kom", 2490, 2190, 9, 1, "Merenje napona, struje i otpora, test kontinuiteta."),
    ("merni-instrumenti", "MER-002", "Ispitivač napona – odvijač", "", "kom", 690, None, 30, 0, "Fazni ispitivač za brzu proveru prisustva napona."),
    ("ostala-oprema", "OST-001", "Senzor pokreta 180° IP44", "", "kom", 1150, None, 14, 0, "Za automatsko paljenje spoljnog svetla."),
    ("ostala-oprema", "OST-002", "Digitalni tajmer za utičnicu", "", "kom", 890, None, 0, 0, "Nedeljni programator, šuko."),
    ("ostala-oprema", "OST-003", "Bežično zvono", "", "kom", 1290, None, 11, 0, "Domet do 100 m, 36 melodija."),
]

# dan, radi, od, do  (DEMO vrednosti – prave unosi radnja kroz admin panel)
RADNO_VREME = [
    (0, 0, None, None),
    (1, 1, "07:00", "17:00"),
    (2, 1, "07:00", "17:00"),
    (3, 1, "07:00", "17:00"),
    (4, 1, "07:00", "17:00"),
    (5, 1, "07:00", "17:00"),
    (6, 1, "07:00", "14:00"),
]


def init_db(db_path: Path = DB_PATH) -> None:
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript((BASE / "schema.sql").read_text(encoding="utf-8"))

    for i, (naziv, slug, opis, ikonica) in enumerate(KATEGORIJE, start=1):
        con.execute(
            "INSERT INTO kategorije (naziv, slug, opis, ikonica, redosled) VALUES (?, ?, ?, ?, ?)",
            (naziv, slug, opis, ikonica, i * 10),
        )
    kat_id = {slug: id_ for id_, slug in con.execute("SELECT id, slug FROM kategorije")}

    for slug, sifra, naziv, proizv, jm, cena, akc, stanje, ist, opis in ARTIKLI:
        con.execute(
            """INSERT INTO artikli (kategorija_id, sifra, naziv, proizvodjac, jedinica_mere,
                                    cena, akcijska_cena, stanje, istaknut, opis, izmenio)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'init_db')""",
            (kat_id[slug], sifra, naziv, proizv, jm, cena, akc, stanje, ist, opis),
        )

    # Demo slike (Wikimedia Commons, slobodne licence) – fajlovi su u static/uploads
    slike = BASE / "demo_slike.json"
    if slike.exists():
        for sifra, v in json.loads(slike.read_text(encoding="utf-8")).items():
            con.execute("UPDATE artikli SET slika = ?, slika_kredit = ?, slika_izvor = ? WHERE sifra = ?",
                        (v["slika"], v["slika_kredit"], v["slika_izvor"], sifra))

    con.executemany("INSERT INTO radno_vreme (dan, radi, od, do) VALUES (?, ?, ?, ?)", RADNO_VREME)

    for kor, ime, loz, uloga in DEMO_KORISNICI:
        con.execute(
            "INSERT INTO korisnici (korisnicko_ime, ime, lozinka_hash, uloga) VALUES (?, ?, ?, ?)",
            (kor, ime, generate_password_hash(loz), uloga),
        )

    con.commit()
    con.close()

    import migracije  # podešavanja + početna stanja na kartici artikala
    migracije.migriraj(db_path)


if __name__ == "__main__":
    init_db()
    print(f"Baza napravljena: {DB_PATH}")
