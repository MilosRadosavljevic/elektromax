"""Testovi API-ja kase i poslovnih pravila (privremena baza).
Pokretanje:  .venv\\Scripts\\python -m unittest discover tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import init_db  # noqa: E402
import migracije  # noqa: E402
from app import app  # noqa: E402
from obracun import izracunaj  # noqa: E402


class Obracun(unittest.TestCase):
    def test_popust_raspodela_i_pdv(self):
        o = izracunaj([{"cena": 1000, "kolicina": 1, "pdv_stopa": 20},
                       {"cena": 333.33, "kolicina": 3, "pdv_stopa": 20, "popust": {"proc": 10}}],
                      {"iznos": 100})
        self.assertEqual(str(o["bruto"]), "1999.99")
        self.assertEqual(o["ukupno"], sum(s["ukupno"] for s in o["stavke"]))
        self.assertEqual(o["ukupno"] + o["popust"], o["bruto"])
        self.assertEqual(o["osnovica"] + o["pdv"], o["ukupno"])
        self.assertEqual(str(o["popust_racun"]), "100.00")

    def test_popust_ne_prelazi_iznos(self):
        o = izracunaj([{"cena": 50, "kolicina": 2, "pdv_stopa": 20, "popust": {"iznos": 500}}])
        self.assertEqual(str(o["ukupno"]), "0.00")


class KasaAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stari = init_db.DB_PATH
        init_db.DB_PATH = Path(self.tmp.name) / "t.db"
        init_db.init_db(init_db.DB_PATH)
        migracije.migriraj(init_db.DB_PATH)
        app.config["TESTING"] = True
        self.c = app.test_client()
        self.token = self.prijava("radnik", "radnik123")

    def tearDown(self):
        init_db.DB_PATH = self.stari
        self.tmp.cleanup()

    def prijava(self, k, l):
        r = self.c.post("/api/login", json={"korisnicko_ime": k, "lozinka": l})
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["token"]

    def api(self, metod, url, token=None, **kw):
        h = {"Authorization": f"Bearer {token or self.token}"}
        return getattr(self.c, metod)(url, headers=h, **kw)

    def stanje(self, aid):
        return next(a for a in self.api("get", "/api/artikli").get_json() if a["id"] == aid)["stanje"]

    def test_bez_tokena(self):
        self.assertEqual(self.c.get("/api/artikli").status_code, 401)

    def test_racun_kusur_i_stanje(self):
        pre = self.stanje(1)  # Kabl PP-Y 3x1,5 – 95 RSD/m
        r = self.api("post", "/api/racuni", json={
            "stavke": [{"artikal_id": 1, "kolicina": 10}],
            "placanja": [{"nacin": "gotovina", "iznos": 950, "primljeno": 1000}]})
        self.assertEqual(r.status_code, 201, r.get_json())
        j = r.get_json()
        self.assertEqual(j["ukupno"], 950)
        self.assertEqual(j["placanja"][0]["kusur"], 50)
        self.assertEqual(round(j["pdv"], 2), 158.33)
        self.assertTrue(j["broj"].startswith("R-"))
        self.assertTrue(j["fiskal_broj"].startswith("DEMO-"))
        self.assertEqual(self.stanje(1), pre - 10)

    def test_pogresan_zbir_placanja(self):
        r = self.api("post", "/api/racuni", json={
            "stavke": [{"artikal_id": 1, "kolicina": 1}], "placanja": [{"nacin": "kartica", "iznos": 10}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("ne odgovara", r.get_json()["greska"])

    def test_veliki_popust_trazi_odobrenje(self):
        telo = {"stavke": [{"artikal_id": 1, "kolicina": 10}], "popust_racun": {"proc": 15},
                "placanja": [{"nacin": "kartica", "iznos": 807.5}]}
        r = self.api("post", "/api/racuni", json=telo)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["kod"], "potrebno_odobrenje")
        telo["odobrenje"] = {"korisnicko_ime": "admin", "lozinka": "admin123"}
        r = self.api("post", "/api/racuni", json=telo)
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(r.get_json()["odobrio"], "Administrator")

    def test_predracun_pa_racun(self):
        pre = self.stanje(2)
        p = self.api("post", "/api/racuni", json={"tip": "predracun", "stavke": [{"artikal_id": 2, "kolicina": 5}]})
        self.assertEqual(p.status_code, 201)
        p = p.get_json()
        self.assertEqual(self.stanje(2), pre)  # predračun ne skida stanje
        r = self.api("post", f"/api/racuni/{p['id']}/realizuj",
                     json={"placanja": [{"nacin": "prenos", "iznos": p["ukupno"]}]})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(self.stanje(2), pre - 5)
        self.assertEqual(self.api("get", f"/api/racuni/{p['id']}").get_json()["status"], "realizovan")

    def test_delimican_storno(self):
        r = self.api("post", "/api/racuni", json={
            "stavke": [{"artikal_id": 1, "kolicina": 4}, {"artikal_id": 17, "kolicina": 2}],
            "placanja": [{"nacin": "gotovina", "iznos": 678}]}).get_json()
        pre = self.stanje(1)
        sid = r["stavke"][0]["id"]
        # radnik bez odobrenja ne može
        self.assertEqual(self.api("post", f"/api/racuni/{r['id']}/storno",
                                  json={"stavke": [{"stavka_id": sid, "kolicina": 1}], "razlog": "x"}).status_code, 403)
        s = self.api("post", f"/api/racuni/{r['id']}/storno", json={
            "stavke": [{"stavka_id": sid, "kolicina": 1}], "razlog": "Vraćeno",
            "odobrenje": {"korisnicko_ime": "admin", "lozinka": "admin123"}})
        self.assertEqual(s.status_code, 201, s.get_json())
        self.assertEqual(s.get_json()["ukupno"], 95)
        self.assertEqual(self.stanje(1), pre + 1)
        self.assertEqual(self.api("get", f"/api/racuni/{r['id']}").get_json()["status"], "delimicno_storniran")
        # ne može više nego što je ostalo
        admin = self.prijava("admin", "admin123")
        x = self.api("post", f"/api/racuni/{r['id']}/storno", token=admin,
                     json={"stavke": [{"stavka_id": sid, "kolicina": 4}], "razlog": "x"})
        self.assertEqual(x.status_code, 400)
        # ostatak celog računa
        y = self.api("post", f"/api/racuni/{r['id']}/storno", token=admin, json={"razlog": "Ceo ostatak"})
        self.assertEqual(y.status_code, 201)
        self.assertEqual(self.api("get", f"/api/racuni/{r['id']}").get_json()["status"], "storniran")
        p = self.api("get", "/api/presek").get_json()
        self.assertEqual(p["promet_neto"], 0)
        self.assertEqual(p["broj_storna"], 2)

    def test_kartica_artikla_slaze_se_sa_stanjem(self):
        self.api("post", "/api/racuni", json={"stavke": [{"artikal_id": 3, "kolicina": 7}],
                                              "placanja": [{"nacin": "kartica", "iznos": 1645}]})
        import sqlite3
        con = sqlite3.connect(init_db.DB_PATH)
        for aid, stanje, zbir in con.execute(
                "SELECT a.id, a.stanje, (SELECT SUM(kolicina) FROM kretanja k WHERE k.artikal_id = a.id) FROM artikli a"):
            self.assertEqual(stanje, zbir, f"artikal {aid}")
        con.close()


if __name__ == "__main__":
    unittest.main()
