"""Brzi test celog toka na privremenoj bazi.
Pokretanje:  .venv\\Scripts\\python -m unittest discover tests -v
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import init_db  # noqa: E402
from app import app  # noqa: E402


class Smoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stari_db = init_db.DB_PATH
        init_db.DB_PATH = Path(self.tmp.name) / "test.db"
        init_db.init_db(init_db.DB_PATH)
        app.config["TESTING"] = True
        self.c = app.test_client()

    def tearDown(self):
        init_db.DB_PATH = self.stari_db
        self.tmp.cleanup()

    def csrf(self, url):
        html = self.c.get(url).get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def login(self, ime="admin", loz="admin123"):
        t = self.csrf("/admin/login")
        return self.c.post("/admin/login", data={"csrf": t, "korisnicko_ime": ime, "lozinka": loz})

    def test_javne_strane(self):
        for url in ["/", "/katalog", "/katalog?kategorija=kablovi", "/katalog?q=kabl", "/artikal/1"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertEqual(self.c.get("/artikal/9999").status_code, 404)
        self.assertIn("PP-Y 3x2,5", self.c.get("/katalog?q=3x2,5").get_data(as_text=True))

    def test_admin_trazi_prijavu(self):
        self.assertEqual(self.c.get("/admin/artikli").status_code, 302)

    def test_pogresna_lozinka(self):
        r = self.login(loz="pogresno")
        self.assertIn("Pogrešno", r.get_data(as_text=True))

    def test_dodaj_izmeni_obrisi_artikal(self):
        self.login()
        t = self.csrf("/admin/artikli/novi")
        r = self.c.post("/admin/artikli/novi", data={
            "csrf": t, "naziv": "Test sijalica", "sifra": "TST-1", "kategorija_id": "4",
            "cena": "199,90", "stanje": "5", "jedinica_mere": "kom", "aktivan": "1"})
        self.assertEqual(r.status_code, 302)
        html = self.c.get("/katalog?q=Test sijalica").get_data(as_text=True)
        self.assertIn("199,90 RSD", html)
        # duplikat šifre mora da padne
        r = self.c.post("/admin/artikli/novi", data={
            "csrf": t, "naziv": "X", "sifra": "TST-1", "kategorija_id": "4", "cena": "1",
            "jedinica_mere": "kom"})
        self.assertIn("već postoji", r.get_data(as_text=True))
        # sakrij pa obriši
        aid = re.search(r"/artikal/(\d+)", html).group(1)
        self.c.post(f"/admin/artikli/{aid}/vidljivost", data={"csrf": t})
        self.assertNotIn("Test sijalica", self.c.get("/katalog").get_data(as_text=True))
        self.c.post(f"/admin/artikli/{aid}/obrisi", data={"csrf": t})
        self.assertEqual(self.c.get(f"/admin/artikli/{aid}").status_code, 404)

    def test_radno_vreme(self):
        self.login("radnik", "radnik123")
        t = self.csrf("/admin/radno-vreme")
        data = {"csrf": t}
        for d in range(1, 7):
            data |= {f"radi_{d}": "1", f"od_{d}": "08:00", f"do_{d}": "16:00"}
        data["do_6"] = "07:00"  # zatvaranje pre otvaranja -> greška
        self.assertIn("posle otvaranja", self.c.post("/admin/radno-vreme", data=data).get_data(as_text=True))
        data["do_6"] = "13:00"
        self.c.post("/admin/radno-vreme", data=data)
        self.assertIn("08:00 – 16:00", self.c.get("/").get_data(as_text=True))

    def test_radnik_ne_vidi_kategorije(self):
        self.login("radnik", "radnik123")
        self.assertEqual(self.c.get("/admin/kategorije").status_code, 302)

    def test_csrf(self):
        self.login()
        self.assertEqual(self.c.post("/admin/artikli/1/obrisi", data={"csrf": "lose"}).status_code, 400)

    def test_kategorija_sa_artiklima_se_ne_brise(self):
        self.login()
        t = self.csrf("/admin/kategorije")
        r = self.c.post("/admin/kategorije/1/obrisi", data={"csrf": t}, follow_redirects=True)
        self.assertIn("ima 6 artikala", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
