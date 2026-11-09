"""Postavljanje lozinke (ili pravljenje naloga) iz komandne linije na serveru.

    elektromax-lozinka admin          -> nova lozinka za postojeći nalog
    elektromax-lozinka marko          -> ako nalog ne postoji, pita da li da ga napravi (ime, uloga)

Lozinka se kuca dva puta i ne prikazuje se na ekranu. Baza: promenljiva ELEKTROMAX_DB.
"""
import getpass
import os
import sqlite3
import sys

from werkzeug.security import generate_password_hash


def pitaj(tekst, podrazumevano=""):
    v = input(f"{tekst}{f' [{podrazumevano}]' if podrazumevano else ''}: ").strip()
    return v or podrazumevano


def main():
    if len(sys.argv) != 2:
        print("Upotreba: elektromax-lozinka <korisnicko_ime>")
        return 2
    ime = sys.argv[1].strip().lower()
    con = sqlite3.connect(os.environ["ELEKTROMAX_DB"])
    k = con.execute("SELECT id, ime, uloga, aktivan FROM korisnici WHERE korisnicko_ime = ?", (ime,)).fetchone()
    if k:
        print(f"Nalog: {ime} – {k[1]} ({k[2]}){'' if k[3] else ', BLOKIRAN'}")
    else:
        if pitaj(f"Nalog „{ime}“ ne postoji. Napraviti ga? (da/ne)", "ne").lower() != "da":
            return 1
        puno = pitaj("Ime i prezime")
        uloga = pitaj("Uloga (admin/radnik)", "radnik").lower()
        if not puno or uloga not in ("admin", "radnik"):
            print("Ime je obavezno, a uloga je admin ili radnik.")
            return 1
    while True:
        l1 = getpass.getpass("Nova lozinka (najmanje 8 znakova): ")
        if len(l1) < 8:
            print("Prekratka.")
            continue
        if l1 != getpass.getpass("Ponovi lozinku: "):
            print("Lozinke se ne poklapaju.")
            continue
        break
    h = generate_password_hash(l1)
    if k:
        con.execute("UPDATE korisnici SET lozinka_hash = ?, aktivan = 1 WHERE id = ?", (h, k[0]))
        con.execute("DELETE FROM api_tokeni WHERE korisnik_id = ?", (k[0],))  # odjava sa kase
    else:
        con.execute("INSERT INTO korisnici (korisnicko_ime, ime, lozinka_hash, uloga) VALUES (?,?,?,?)",
                    (ime, puno, h, uloga))
    con.commit()
    print(f"Gotovo – lozinka za „{ime}“ je postavljena.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
