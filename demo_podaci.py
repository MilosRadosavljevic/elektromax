"""Demo podaci za kasu, nabavku i analitiku: 90 dana izmišljene prodaje.

Pokretanje (dopunjuje postojeću bazu, NE briše artikle):
    .venv\\Scripts\\python demo_podaci.py            -> 90 dana
    .venv\\Scripts\\python demo_podaci.py 30         -> 30 dana
Ako u bazi već postoje računi, generator odbija da radi (da se istorija ne duplira).

Sve firme, dobavljači i iznosi su IZMIŠLJENI.
"""
import math
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

import init_db
import migracije
import poslovanje as P
from obracun import izracunaj

DOBAVLJACI = [
    # naziv, pib, adresa, kontakt, telefon, email, rok isporuke (dana), kategorije
    ("Demo Kablovi d.o.o.", "999000011", "Industrijska 12, Jagodina", "Nenad P.", "035 000 111",
     "prodaja@demo-kablovi.example", 2, ["kablovi", "instalacioni-pribor"]),
    ("Demo Elektro Veleprodaja d.o.o.", "999000028", "Bulevar 45, Beograd", "Ivana S.", "011 000 222",
     "narudzbe@demo-veleprodaja.example", 3, ["prekidaci-uticnice", "razvodne-table", "ostala-oprema"]),
    ("Demo Svetlo i Alat d.o.o.", "999000035", "Kragujevačka 7, Kragujevac", "Marko J.", "034 000 333",
     "office@demo-svetlo.example", 5, ["rasveta", "alat", "merni-instrumenti"]),
]

KUPCI = [
    ("Demo Instal d.o.o.", "999100014", "20111111", "Karađorđeva 10", "11420 Smederevska Palanka"),
    ("Demo Gradnja d.o.o.", "999100021", "20222222", "Vuka Karadžića 3", "11420 Smederevska Palanka"),
    ("Demo Elektro Servis PR", "999100038", "60333333", "Kralja Petra I 21", "11320 Velika Plana"),
    ("Demo Stan Komerc d.o.o.", "999100045", "20444444", "Glavna 88", "11400 Mladenovac"),
    ("Demo Škola – održavanje", "999100052", "07555555", "Školska 1", "11420 Smederevska Palanka"),
]

# popularnost (težina) i tipična količina po šifri artikla
PROFIL = {
    "KAB-001": (14, (5, 60)), "KAB-002": (16, (5, 60)), "KAB-003": (5, (5, 40)), "KAB-004": (6, (5, 30)),
    "KAB-005": (4, (5, 20)), "KAB-006": (6, (1, 2)), "PRU-001": (7, (1, 4)), "PRU-002": (9, (1, 8)),
    "PRU-003": (9, (1, 8)), "PRU-004": (4, (1, 3)), "PRU-005": (8, (2, 20)), "RTB-001": (10, (1, 6)),
    "RTB-002": (7, (1, 6)), "RTB-003": (3, (1, 1)), "RTB-004": (2, (1, 1)), "RTB-005": (5, (5, 30)),
    "RAS-001": (15, (1, 6)), "RAS-002": (10, (1, 6)), "RAS-003": (3, (1, 4)), "RAS-004": (4, (1, 2)),
    "RAS-005": (3, (1, 2)), "PRB-001": (8, (5, 50)), "PRB-002": (5, (1, 10)), "PRB-003": (6, (1, 6)),
    "PRB-004": (10, (1, 3)), "PRB-005": (7, (1, 2)), "ALT-001": (2, (1, 1)), "ALT-002": (1, (1, 1)),
    "ALT-003": (1, (1, 1)), "MER-001": (2, (1, 1)), "MER-002": (4, (1, 2)), "OST-001": (3, (1, 2)),
    "OST-002": (3, (1, 2)), "OST-003": (2, (1, 1)),
}
# promet po danu u nedelji (0 = nedelja) i po satu
DAN_FAKTOR = {1: 1.25, 2: 1.0, 3: 1.0, 4: 1.05, 5: 1.2, 6: 0.85, 0: 0}
SATI = [(7, 9), (8, 12), (9, 11), (10, 9), (11, 7), (12, 6), (13, 7), (14, 9), (15, 10), (16, 8)]


def _sat(rnd, do_sata):
    moguci = [(h, w) for h, w in SATI if h < do_sata]
    h = rnd.choices([h for h, _ in moguci], [w for _, w in moguci])[0]
    return h, rnd.randint(0, 59), rnd.randint(0, 59)


def pripremi_sifarnike(db, rnd):
    """Dobavljači, kupci, nabavne cene, minimalne količine, drugi kasir."""
    kat = {r["slug"]: r["id"] for r in db.execute("SELECT id, slug FROM kategorije")}
    for naziv, pib, adresa, kontakt, tel, email, rok, kategorije in DOBAVLJACI:
        did = db.execute("""INSERT INTO dobavljaci (naziv, pib, adresa, kontakt, telefon, email, rok_isporuke, napomena)
                            VALUES (?,?,?,?,?,?,?,'Izmišljen dobavljač (demo)')""",
                         (naziv, pib, adresa, kontakt, tel, email, rok)).lastrowid
        for slug in kategorije:
            db.execute("UPDATE artikli SET dobavljac_id = ? WHERE kategorija_id = ? AND dobavljac_id IS NULL",
                       (did, kat.get(slug)))
    for naziv, pib, mb, adresa, mesto in KUPCI:
        db.execute("INSERT INTO kupci (naziv, pib, mb, adresa, mesto, napomena) VALUES (?,?,?,?,?,'Izmišljen kupac (demo)')",
                   (naziv, pib, mb, adresa, mesto))
    for a in db.execute("SELECT id, sifra, cena, jedinica_mere FROM artikli").fetchall():
        marza = rnd.uniform(0.28, 0.42)
        nab = round(a["cena"] / 1.2 * (1 - marza), 2)
        tez, (lo, hi) = PROFIL.get(a["sifra"], (2, (1, 2)))
        dnevno = tez * 0.9 * (lo + hi) / 2 / 14   # gruba procena dnevne prodaje
        min_kol = max(2, math.ceil(dnevno * 5))
        db.execute("UPDATE artikli SET nabavna_cena = COALESCE(nabavna_cena, ?), min_kolicina = ? WHERE id = ?",
                   (nab, min_kol, a["id"]))
    if not db.execute("SELECT 1 FROM korisnici WHERE korisnicko_ime = 'jovana'").fetchone():
        db.execute("INSERT INTO korisnici (korisnicko_ime, ime, lozinka_hash, uloga) VALUES ('jovana','Jovana Kasirka',?,'radnik')",
                   (generate_password_hash("jovana123"),))


def generisi(db, dana=90, seme=88):
    rnd = random.Random(seme)
    if db.execute("SELECT COUNT(*) FROM racuni").fetchone()[0]:
        raise SystemExit("U bazi već postoje računi – generator se ne pokreće (istorija bi se duplirala).")
    pripremi_sifarnike(db, rnd)

    pocetak = date.today() - timedelta(days=dana)
    # početna stanja „pomeri“ na početak perioda, da kartica artikla ima smislen redosled
    db.execute("UPDATE kretanja SET vreme = ? WHERE tip = 'pocetno'", (f"{pocetak} 06:30:00",))

    artikli = {a["id"]: dict(a) for a in db.execute("SELECT * FROM artikli WHERE aktivan = 1")}
    ids = list(artikli)
    tezine = [PROFIL.get(artikli[i]["sifra"], (2, 0))[0] for i in ids]
    kasiri = [dict(k) for k in db.execute("SELECT * FROM korisnici WHERE aktivan = 1 AND uloga = 'radnik'")]
    admin = dict(db.execute("SELECT * FROM korisnici WHERE uloga = 'admin' AND aktivan = 1 ORDER BY id").fetchone())
    kupci = [k["id"] for k in db.execute("SELECT id FROM kupci")]
    rv = {r["dan"]: r for r in db.execute("SELECT * FROM radno_vreme")}
    odobrenje = None  # admin izdaje sam kada daje veliki popust
    na_putu = {}      # artikal_id -> (datum prijema, narudzbenica_id)
    otvoreni_predracuni = []
    prodaja = {i: {} for i in artikli}   # artikal -> {redni dan: prodato}
    rokovi = {r[0]: r[1] for r in db.execute("SELECT id, rok_isporuke FROM dobavljaci")}
    brojac = {"racuni": 0, "storna": 0, "predracuni": 0, "prijemi": 0}

    for d in range(dana + 1):
        dan = pocetak + timedelta(days=d)
        r = rv.get((dan.weekday() + 1) % 7)
        if not r or not r["radi"]:
            continue
        do_sata = int(r["do"][:2]) if r["do"] else 17
        if dan == date.today():
            do_sata = min(do_sata, datetime.now().hour)
            if do_sata <= 7:
                break

        # 1) roba koja stiže danas (ujutru, pre otvaranja)
        for nid in sorted({nid for (dp, nid) in na_putu.values() if dp <= dan}):
            stavke = [dict(s) for s in db.execute(
                "SELECT artikal_id, kolicina, nabavna_cena FROM narudzbenica_stavke WHERE narudzbenica_id = ?", (nid,))]
            n = db.execute("SELECT dobavljac_id, broj FROM narudzbenice WHERE id = ?", (nid,)).fetchone()
            P.primi_robu(db, "admin", stavke, n["dobavljac_id"], f"OTP-{n['broj'][-4:]}", "", nid,
                         vreme=f"{dan} 06:45:00")
            brojac["prijemi"] += 1
            for s in stavke:
                na_putu.pop(s["artikal_id"], None)
                artikli[s["artikal_id"]]["stanje"] += s["kolicina"]

        # 2) prodaja tokom dana
        n_racuna = max(4, int(rnd.gauss(26, 6) * DAN_FAKTOR[(dan.weekday() + 1) % 7]))
        vremena = sorted(_sat(rnd, do_sata) for _ in range(n_racuna))
        for (h, m, s) in vremena:
            vreme = f"{dan} {h:02d}:{m:02d}:{s:02d}"
            kasir = rnd.choice(kasiri) if rnd.random() < 0.85 else admin
            izabrani = set(rnd.choices(ids, tezine, k=rnd.choices([1, 2, 3, 4, 6], [40, 28, 17, 10, 5])[0]))
            stavke = []
            for aid in izabrani:
                lo, hi = PROFIL.get(artikli[aid]["sifra"], (1, (1, 2)))[1]
                kol = rnd.randint(lo, hi)
                if artikli[aid]["jedinica_mere"] == "m":
                    kol = max(lo, round(kol / 5) * 5)
                kol = min(kol, artikli[aid]["stanje"])   # kupac uzme koliko ima
                if kol > 0:
                    stavke.append({"artikal_id": aid, "kolicina": kol})
            if not stavke:
                continue
            firma = rnd.random() < 0.09
            podaci = {"tip": "racun", "stavke": stavke, "kupac_id": rnd.choice(kupci) if firma else None}
            x = rnd.random()
            if firma or x < 0.06:
                podaci["popust_racun"] = {"proc": rnd.choice([5, 10] if firma else [3, 5, 10])}
                podaci["popust_razlog"] = "Stalni kupac" if firma else "Popust za majstore"
            elif x < 0.075:
                podaci["popust_racun"] = {"proc": 15}
                podaci["popust_razlog"] = "Veća količina"
                kasir = admin
            # predračun za firme ponekad umesto računa
            if firma and rnd.random() < 0.45:
                p = P.izdaj(db, kasir, {**podaci, "tip": "predracun"}, vreme=vreme)
                brojac["predracuni"] += 1
                if rnd.random() < 0.7:
                    otvoreni_predracuni.append((dan + timedelta(days=rnd.randint(1, 5)), p["id"]))
                continue
            obr = izracunaj([{"cena": (artikli[s["artikal_id"]]["akcijska_cena"] or artikli[s["artikal_id"]]["cena"]),
                              "kolicina": s["kolicina"], "pdv_stopa": artikli[s["artikal_id"]]["pdv_stopa"]}
                             for s in stavke], podaci.get("popust_racun"))
            ukupno = float(obr["ukupno"])
            nacin = "prenos" if firma else rnd.choices(["gotovina", "kartica"], [58, 42])[0]
            pl = {"nacin": nacin, "iznos": ukupno}
            if nacin == "gotovina":
                pl["primljeno"] = math.ceil(ukupno / 100) * 100 if rnd.random() < 0.7 else ukupno
            podaci["placanja"] = [pl]
            rac = P.izdaj(db, kasir, podaci, vreme=vreme)
            brojac["racuni"] += 1
            for st in stavke:
                artikli[st["artikal_id"]]["stanje"] -= st["kolicina"]
                prodaja[st["artikal_id"]][d] = prodaja[st["artikal_id"]].get(d, 0) + st["kolicina"]
            # povremeni storno (kupac vratio robu / greška)
            if rnd.random() < 0.018:
                sv = f"{dan} {min(h + 1, do_sata - 1):02d}:{rnd.randint(0, 59):02d}:00"
                if sv > vreme:
                    st = rac["stavke"][0]
                    kol = 1 if rnd.random() < 0.6 else st["kolicina"]
                    P.storniraj(db, admin, rac["id"], [{"stavka_id": st["id"], "kolicina": kol}],
                                rnd.choice(["Kupac vratio robu", "Greška pri kucanju", "Pogrešan artikal"]), vreme=sv)
                    artikli[st["artikal_id"]]["stanje"] += int(kol)
                    brojac["storna"] += 1

        # 3) naplata predračuna koji su na redu
        for (dn, pid) in [x for x in otvoreni_predracuni if x[0] <= dan]:
            otvoreni_predracuni.remove((dn, pid))
            pr = db.execute("SELECT ukupno FROM racuni WHERE id = ?", (pid,)).fetchone()
            rac = P.realizuj_predracun(db, admin, pid, [{"nacin": "prenos", "iznos": pr["ukupno"]}],
                                       vreme=f"{dan} 08:{rnd.randint(10, 50)}:00")
            for st in rac["stavke"]:
                artikli[st["artikal_id"]]["stanje"] -= int(st["kolicina"])
                prodaja[st["artikal_id"]][d] = prodaja[st["artikal_id"]].get(d, 0) + int(st["kolicina"])

        # 4) na kraju dana: naruči ono što pada ispod minimuma (kao lista „Za naručiti“)
        if dan < date.today() - timedelta(days=4):
            po_dob = {}
            for aid, a in artikli.items():
                if aid in na_putu or not a["dobavljac_id"]:
                    continue
                rok = rokovi[a["dobavljac_id"]]
                dnevno = sum(v for dd, v in prodaja[aid].items() if dd > d - 21) / 21
                if a["stanje"] <= max(a["min_kolicina"], dnevno * (rok + 2)):
                    kol = math.ceil(dnevno * (rok + 21)) + a["min_kolicina"] - a["stanje"]
                    kol = max(kol, a["min_kolicina"] * 2)
                    po_dob.setdefault(a["dobavljac_id"], []).append((aid, int(kol)))
            for did, stavke in po_dob.items():
                rok = rokovi[did]
                brn = P.sledeci_broj(db, "narudzbenice", "N", 4, vreme=f"{dan} 17:00:00")
                nid = db.execute("""INSERT INTO narudzbenice (broj, dobavljac_id, status, vreme, korisnik)
                                    VALUES (?,?,'poslata',?,'admin')""", (brn, did, f"{dan} 17:05:00")).lastrowid
                for aid, kol in stavke:
                    db.execute("INSERT INTO narudzbenica_stavke (narudzbenica_id, artikal_id, kolicina, nabavna_cena) "
                               "VALUES (?,?,?,?)", (nid, aid, kol, artikli[aid]["nabavna_cena"]))
                    na_putu[aid] = (dan + timedelta(days=rok), nid)

    # podesi min. količine i nabavne cene iz baze u keš nije potrebno – sve je upisano kroz poslovanje.*
    return brojac


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    migracije.migriraj()
    con = sqlite3.connect(init_db.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        b = generisi(con, int(sys.argv[1]) if len(sys.argv) > 1 else 90)
        con.commit()
    except BaseException:
        con.rollback()
        raise
    print(f"Gotovo: {b['racuni']} računa, {b['predracuni']} predračuna, {b['storna']} storna, {b['prijemi']} prijema robe.")
