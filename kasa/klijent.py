"""Komunikacija kase sa serverom (REST API, /api)."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KONFIG = Path(os.environ.get("APPDATA", Path.home())) / "ElektromaxKasa" / "podesavanja.json"


def ucitaj_podesavanja() -> dict:
    try:
        return json.loads(KONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"server": "http://127.0.0.1:5000", "korisnicko_ime": ""}


def sacuvaj_podesavanja(p: dict):
    KONFIG.parent.mkdir(parents=True, exist_ok=True)
    KONFIG.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")


class KlijentGreska(Exception):
    def __init__(self, poruka, kod="greska", status=0):
        super().__init__(poruka)
        self.poruka, self.kod, self.status = poruka, kod, status


class Klijent:
    def __init__(self, server: str):
        self.server = server.rstrip("/")
        self.token = None
        self.korisnik = None
        self.info = {}

    def _zahtev(self, metod, putanja, telo=None, parametri=None):
        url = f"{self.server}/api{putanja}"
        if parametri:
            url += "?" + urllib.parse.urlencode({k: v for k, v in parametri.items() if v not in (None, "")})
        podaci = json.dumps(telo).encode() if telo is not None else None
        zahtev = urllib.request.Request(url, data=podaci, method=metod)
        zahtev.add_header("Content-Type", "application/json")
        if self.token:
            zahtev.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(zahtev, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read().decode("utf-8"))
                raise KlijentGreska(j.get("greska", str(e)), j.get("kod", "greska"), e.code) from None
            except ValueError:
                raise KlijentGreska(f"Greška servera ({e.code}).", "server", e.code) from None
        except urllib.error.URLError as e:
            raise KlijentGreska(f"Server nije dostupan ({self.server}).\n{e.reason}", "veza") from None

    # prijava
    def prijava(self, korisnicko_ime, lozinka):
        r = self._zahtev("POST", "/login", {"korisnicko_ime": korisnicko_ime, "lozinka": lozinka})
        self.token, self.korisnik = r["token"], r["korisnik"]
        self.info = self._zahtev("GET", "/info")
        return self.korisnik

    def odjava(self):
        try:
            self._zahtev("POST", "/logout", {})
        except KlijentGreska:
            pass
        self.token = self.korisnik = None

    # šifarnici
    def artikli(self, q=""):
        return self._zahtev("GET", "/artikli", parametri={"q": q})

    def kupci(self, q=""):
        return self._zahtev("GET", "/kupci", parametri={"q": q})

    def novi_kupac(self, podaci):
        return self._zahtev("POST", "/kupci", podaci)

    # računi
    def izdaj(self, podaci):
        return self._zahtev("POST", "/racuni", podaci)

    def racuni(self, od=None, do=None, tip=None, q=None):
        return self._zahtev("GET", "/racuni", parametri={"od": od, "do": do, "tip": tip, "q": q})

    def racun(self, rid):
        return self._zahtev("GET", f"/racuni/{rid}")

    def storno(self, rid, podaci):
        return self._zahtev("POST", f"/racuni/{rid}/storno", podaci)

    def realizuj(self, rid, placanja):
        return self._zahtev("POST", f"/racuni/{rid}/realizuj", {"placanja": placanja})

    def ponisti(self, rid):
        return self._zahtev("POST", f"/racuni/{rid}/ponisti", {})

    def presek(self, dan=None):
        return self._zahtev("GET", "/presek", parametri={"dan": dan})
