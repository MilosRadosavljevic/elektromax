"""Poslovna pravila: računi, predračuni, storno, zalihe, prijem robe, presek.

Funkcije primaju otvorenu konekciju (sqlite3.Row) i NE rade commit – to radi pozivalac,
tako da je svaka operacija jedna transakcija (sve ili ništa).
"""
from datetime import date, datetime, timedelta

from werkzeug.security import check_password_hash

import fiskal
from obracun import D0, d, izracunaj, zaokruzi


class PoslovnaGreska(Exception):
    kod = "greska"

    def __init__(self, poruka, **detalji):
        super().__init__(poruka)
        self.poruka = poruka
        self.detalji = detalji


class PotrebnoOdobrenje(PoslovnaGreska):
    kod = "potrebno_odobrenje"


def sada() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def podesavanje(db, kljuc, podrazumevano=None):
    r = db.execute("SELECT vrednost FROM podesavanja WHERE kljuc = ?", (kljuc,)).fetchone()
    return r[0] if r else podrazumevano


def sledeci_broj(db, tabela: str, prefiks: str, cifara: int = 6, vreme: str | None = None) -> str:
    godina = (vreme or sada())[:4]
    osnova = f"{prefiks}-{godina}-"
    r = db.execute(f"SELECT MAX(broj) FROM {tabela} WHERE broj LIKE ?", (osnova + "%",)).fetchone()[0]
    n = int(r[len(osnova):]) + 1 if r else 1
    return f"{osnova}{n:0{cifara}d}"


# ---------------------------------------------------------------------------- zalihe
def promeni_stanje(db, artikal_id, kolicina, tip, dokument="", korisnik=None,
                   racun_id=None, prijem_id=None, napomena="", vreme=None) -> int:
    """Jedino mesto gde se menja artikli.stanje; svaka promena ide i u karticu artikla."""
    kolicina = int(kolicina)
    db.execute("UPDATE artikli SET stanje = stanje + ? WHERE id = ?", (kolicina, artikal_id))
    novo = db.execute("SELECT stanje FROM artikli WHERE id = ?", (artikal_id,)).fetchone()[0]
    db.execute("""INSERT INTO kretanja (artikal_id, vreme, tip, kolicina, stanje_posle, dokument,
                                        racun_id, prijem_id, korisnik, napomena)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
               (artikal_id, vreme or sada(), tip, kolicina, novo, dokument, racun_id, prijem_id,
                korisnik, napomena))
    return novo


def korekcija_stanja(db, korisnik: str, artikal_id: int, novo_stanje: int, napomena: str = ""):
    staro = db.execute("SELECT stanje FROM artikli WHERE id = ?", (artikal_id,)).fetchone()[0]
    if int(novo_stanje) != staro:
        promeni_stanje(db, artikal_id, int(novo_stanje) - staro, "korekcija", "Korekcija stanja",
                       korisnik, napomena=napomena)


# ---------------------------------------------------------------------------- odobrenja
def proveri_odobrenje(db, odobrenje: dict | None, poruka: str):
    """Vraća admina koji je odobrio, ili diže PotrebnoOdobrenje."""
    if not odobrenje:
        raise PotrebnoOdobrenje(poruka)
    a = db.execute("SELECT * FROM korisnici WHERE korisnicko_ime = ? AND aktivan = 1 AND uloga = 'admin'",
                   ((odobrenje.get("korisnicko_ime") or "").strip().lower(),)).fetchone()
    if not a or not check_password_hash(a["lozinka_hash"], odobrenje.get("lozinka") or ""):
        raise PotrebnoOdobrenje("Pogrešni podaci administratora za odobrenje.")
    return a


# ---------------------------------------------------------------------------- računi
def _ucitaj_stavke(db, ulaz: list[dict]) -> list[dict]:
    if not ulaz:
        raise PoslovnaGreska("Račun nema nijednu stavku.")
    stavke = []
    for s in ulaz:
        a = db.execute("SELECT * FROM artikli WHERE id = ?", (s.get("artikal_id"),)).fetchone()
        if a is None:
            raise PoslovnaGreska(f"Artikal {s.get('artikal_id')} ne postoji.")
        try:
            kol = int(s.get("kolicina"))
        except (TypeError, ValueError):
            raise PoslovnaGreska(f"Neispravna količina za „{a['naziv']}“.")
        if kol <= 0:
            raise PoslovnaGreska(f"Količina za „{a['naziv']}“ mora biti veća od nule.")
        stavke.append({
            "artikal_id": a["id"], "sifra": a["sifra"], "naziv": a["naziv"],
            "jedinica_mere": a["jedinica_mere"], "kolicina": kol,
            "cena": a["akcijska_cena"] if a["akcijska_cena"] is not None else a["cena"],
            "pdv_stopa": a["pdv_stopa"], "nabavna_cena": a["nabavna_cena"],
            "popust": s.get("popust"), "_stanje": a["stanje"],
        })
    return stavke


def _proveri_placanja(placanja: list[dict], ukupno) -> list[dict]:
    if not placanja:
        raise PoslovnaGreska("Nije unet način plaćanja.")
    out, zbir = [], D0
    for p in placanja:
        if p.get("nacin") not in ("gotovina", "kartica", "prenos"):
            raise PoslovnaGreska("Nepoznat način plaćanja.")
        iznos = zaokruzi(d(p.get("iznos")))
        if iznos <= 0:
            continue
        primljeno = kusur = None
        if p["nacin"] == "gotovina" and p.get("primljeno") not in (None, ""):
            primljeno = zaokruzi(d(p["primljeno"]))
            if primljeno < iznos:
                raise PoslovnaGreska("Primljeni iznos je manji od iznosa za gotovinu.")
            kusur = primljeno - iznos
        out.append({"nacin": p["nacin"], "iznos": iznos, "primljeno": primljeno, "kusur": kusur})
        zbir += iznos
    if zbir != zaokruzi(d(ukupno)):
        raise PoslovnaGreska(f"Zbir plaćanja ({zbir}) ne odgovara iznosu računa ({zaokruzi(d(ukupno))}).")
    return out


def _upisi_racun(db, *, tip, broj, kasir, obr, stavke, placanja, kupac_id=None, referentni_id=None,
                 popust_racun_proc=None, odobrio_id=None, razlog="", napomena="", vazi_do=None,
                 vreme=None):
    vreme = vreme or sada()
    cur = db.execute(
        """INSERT INTO racuni (broj, tip, vreme, kasir_id, kupac_id, referentni_id, bruto, popust, ukupno,
                               osnovica, pdv, popust_racun_proc, popust_odobrio_id, popust_razlog,
                               napomena, vazi_do)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (broj, tip, vreme, kasir["id"], kupac_id, referentni_id, float(obr["bruto"]), float(obr["popust"]),
         float(obr["ukupno"]), float(obr["osnovica"]), float(obr["pdv"]), popust_racun_proc, odobrio_id,
         razlog, napomena, vazi_do))
    rid = cur.lastrowid
    for s in stavke:
        db.execute(
            """INSERT INTO racun_stavke (racun_id, artikal_id, sifra, naziv, jedinica_mere, kolicina, cena,
                                         popust_proc, popust, ukupno, pdv_stopa, nabavna_cena,
                                         referentna_stavka_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, s["artikal_id"], s["sifra"], s["naziv"], s["jedinica_mere"], float(s["kolicina"]),
             float(s["cena"]), float(s["popust_proc"]), float(s["popust"]), float(s["ukupno"]),
             float(s["pdv_stopa"]), s.get("nabavna_cena"), s.get("referentna_stavka_id")))
    for p in placanja:
        db.execute("INSERT INTO placanja (racun_id, nacin, iznos, primljeno, kusur) VALUES (?,?,?,?,?)",
                   (rid, p["nacin"], float(p["iznos"]),
                    float(p["primljeno"]) if p.get("primljeno") is not None else None,
                    float(p["kusur"]) if p.get("kusur") is not None else None))
    return rid


def _fiskalizuj(db, rid, referentni=None):
    r = dict(db.execute("""SELECT r.*, k.ime AS kasir, ku.pib AS kupac_pib FROM racuni r
                           JOIN korisnici k ON k.id = r.kasir_id LEFT JOIN kupci ku ON ku.id = r.kupac_id
                           WHERE r.id = ?""", (rid,)).fetchone())
    st = [dict(x) for x in db.execute("SELECT * FROM racun_stavke WHERE racun_id = ?", (rid,))]
    pl = [dict(x) for x in db.execute("SELECT * FROM placanja WHERE racun_id = ?", (rid,))]
    f = fiskal.adapter().fiskalizuj(r, st, pl, referentni)
    db.execute("""UPDATE racuni SET fiskal_rezim=?, fiskal_broj=?, fiskal_vreme=?, fiskal_url=?, fiskal_odgovor=?
                  WHERE id=?""", (f["fiskal_rezim"], f["fiskal_broj"], f["fiskal_vreme"], f["fiskal_url"],
                                  f["fiskal_odgovor"], rid))


def izdaj(db, kasir, podaci: dict, vreme: str | None = None) -> dict:
    """Izdaje račun (tip 'racun') ili predračun (tip 'predracun').

    podaci: {tip, stavke:[{artikal_id, kolicina, popust?}], popust_racun?, placanja?, kupac_id?,
             napomena?, popust_razlog?, odobrenje?:{korisnicko_ime, lozinka}}
    """
    tip = podaci.get("tip", "racun")
    if tip not in ("racun", "predracun"):
        raise PoslovnaGreska("Nepoznat tip dokumenta.")
    stavke = _ucitaj_stavke(db, podaci.get("stavke"))
    obr = izracunaj(stavke, podaci.get("popust_racun"))

    odobrio_id = None
    limit = d(podesavanje(db, "max_popust_radnik", "10"))
    if obr["max_popust_proc"] > limit and kasir["uloga"] != "admin":
        odobrio_id = proveri_odobrenje(db, podaci.get("odobrenje"),
                                       f"Popust veći od {limit}% mora da odobri administrator.")["id"]
    elif obr["popust"] > 0:
        odobrio_id = kasir["id"]

    kupac_id = podaci.get("kupac_id") or None
    if kupac_id and not db.execute("SELECT 1 FROM kupci WHERE id = ?", (kupac_id,)).fetchone():
        raise PoslovnaGreska("Kupac ne postoji.")

    pr = podaci.get("popust_racun") or {}
    zajednicko = dict(kasir=kasir, obr=obr, stavke=obr["stavke"], kupac_id=kupac_id,
                      popust_racun_proc=pr.get("proc") or None, odobrio_id=odobrio_id,
                      razlog=(podaci.get("popust_razlog") or "").strip(),
                      napomena=(podaci.get("napomena") or "").strip(), vreme=vreme)

    if tip == "predracun":
        dana = int(podesavanje(db, "predracun_dana", "7"))
        osnova = datetime.strptime(vreme, "%Y-%m-%d %H:%M:%S").date() if vreme else date.today()
        rid = _upisi_racun(db, tip="predracun", broj=sledeci_broj(db, "racuni", "P", vreme=vreme),
                           placanja=[], vazi_do=(osnova + timedelta(days=dana)).isoformat(), **zajednicko)
    else:
        placanja = _proveri_placanja(podaci.get("placanja"), obr["ukupno"])
        broj = sledeci_broj(db, "racuni", "R", vreme=vreme)
        rid = _upisi_racun(db, tip="racun", broj=broj, placanja=placanja, **zajednicko)
        for s in obr["stavke"]:
            promeni_stanje(db, s["artikal_id"], -s["kolicina"], "prodaja", f"Račun {broj}",
                           kasir["korisnicko_ime"], racun_id=rid, vreme=vreme)
    _fiskalizuj(db, rid)
    rez = racun(db, rid)
    rez["upozorenja"] = [f"„{s['naziv']}“: na stanju {s['_stanje']}, prodato {s['kolicina']}"
                         for s in obr["stavke"] if tip == "racun" and s["_stanje"] < s["kolicina"]]
    return rez


def realizuj_predracun(db, kasir, predracun_id: int, placanja: list[dict], vreme: str | None = None) -> dict:
    """Predračun -> račun po cenama i popustima iz predračuna."""
    p = db.execute("SELECT * FROM racuni WHERE id = ? AND tip = 'predracun'", (predracun_id,)).fetchone()
    if p is None:
        raise PoslovnaGreska("Predračun ne postoji.")
    if p["status"] != "izdat":
        raise PoslovnaGreska(f"Predračun je već {p['status']}.")
    st = [dict(s) for s in db.execute("SELECT * FROM racun_stavke WHERE racun_id = ?", (predracun_id,))]
    pl = _proveri_placanja(placanja, p["ukupno"])
    broj = sledeci_broj(db, "racuni", "R", vreme=vreme)
    obr = {k: d(p[k]) for k in ("bruto", "popust", "ukupno", "osnovica", "pdv")}
    for s in st:
        nab = db.execute("SELECT nabavna_cena FROM artikli WHERE id = ?", (s["artikal_id"],)).fetchone()
        s["nabavna_cena"] = nab[0] if nab else s["nabavna_cena"]
        s["referentna_stavka_id"] = None
    rid = _upisi_racun(db, tip="racun", broj=broj, kasir=kasir, obr=obr, stavke=st, placanja=pl,
                       kupac_id=p["kupac_id"], referentni_id=p["id"], popust_racun_proc=p["popust_racun_proc"],
                       odobrio_id=p["popust_odobrio_id"], razlog=p["popust_razlog"],
                       napomena=f"Po predračunu {p['broj']}" + (f". {p['napomena']}" if p["napomena"] else ""),
                       vreme=vreme)
    for s in st:
        if s["artikal_id"]:
            promeni_stanje(db, s["artikal_id"], -int(s["kolicina"]), "prodaja", f"Račun {broj}",
                           kasir["korisnicko_ime"], racun_id=rid, vreme=vreme)
    db.execute("UPDATE racuni SET status = 'realizovan' WHERE id = ?", (predracun_id,))
    _fiskalizuj(db, rid)
    return racun(db, rid)


def ponisti_predracun(db, predracun_id: int):
    n = db.execute("UPDATE racuni SET status = 'ponisten' WHERE id = ? AND tip = 'predracun' AND status = 'izdat'",
                   (predracun_id,)).rowcount
    if not n:
        raise PoslovnaGreska("Predračun ne postoji ili nije aktivan.")


def storniraj(db, korisnik, racun_id: int, stavke: list[dict] | None = None, razlog: str = "",
              odobrenje: dict | None = None, nacin_povrata: str | None = None, vreme: str | None = None) -> dict:
    """Storno celog računa (stavke=None) ili dela: stavke=[{stavka_id, kolicina}]."""
    o = db.execute("SELECT * FROM racuni WHERE id = ?", (racun_id,)).fetchone()
    if o is None or o["tip"] != "racun":
        raise PoslovnaGreska("Može se stornirati samo izdat račun.")
    if o["status"] not in ("izdat", "delimicno_storniran"):
        raise PoslovnaGreska("Račun je već u potpunosti storniran.")
    odobrio = korisnik if korisnik["uloga"] == "admin" else \
        proveri_odobrenje(db, odobrenje, "Storno mora da odobri administrator.")
    if not (razlog or "").strip():
        raise PoslovnaGreska("Unesite razlog storniranja.")

    orig = {s["id"]: dict(s) for s in db.execute("SELECT * FROM racun_stavke WHERE racun_id = ?", (racun_id,))}
    trazeno = ({sid: s["kolicina"] - s["storno_kolicina"] for sid, s in orig.items()} if stavke is None
               else {int(x["stavka_id"]): d(x["kolicina"]) for x in stavke if d(x.get("kolicina")) > 0})
    if not any(v > 0 for v in trazeno.values()):
        raise PoslovnaGreska("Nije izabrana nijedna stavka za storno.")

    nove = []
    for sid, kol in trazeno.items():
        s = orig.get(sid)
        if s is None:
            raise PoslovnaGreska("Stavka ne pripada ovom računu.")
        preostalo = d(s["kolicina"]) - d(s["storno_kolicina"])
        kol = d(kol)
        if kol <= 0:
            continue
        if kol > preostalo:
            raise PoslovnaGreska(f"Za „{s['naziv']}“ može se stornirati najviše {preostalo}.")
        udeo = kol / d(s["kolicina"])
        ukupno = zaokruzi(d(s["ukupno"]) * udeo)
        bruto = zaokruzi(d(s["cena"]) * kol)
        stopa = d(s["pdv_stopa"])
        pdv = zaokruzi(ukupno * stopa / (d(100) + stopa))
        nove.append({**s, "kolicina": kol, "ukupno": ukupno, "popust": bruto - ukupno, "bruto": bruto,
                     "pdv": pdv, "osnovica": ukupno - pdv, "referentna_stavka_id": sid})

    obr = {"bruto": sum((s["bruto"] for s in nove), D0), "popust": sum((s["popust"] for s in nove), D0),
           "ukupno": sum((s["ukupno"] for s in nove), D0), "osnovica": sum((s["osnovica"] for s in nove), D0),
           "pdv": sum((s["pdv"] for s in nove), D0)}
    if not nacin_povrata:
        prvi = db.execute("SELECT nacin FROM placanja WHERE racun_id = ? ORDER BY iznos DESC", (racun_id,)).fetchone()
        nacin_povrata = prvi[0] if prvi else "gotovina"
    broj = sledeci_broj(db, "racuni", "S", vreme=vreme)
    rid = _upisi_racun(db, tip="storno", broj=broj, kasir=korisnik, obr=obr, stavke=nove,
                       placanja=[{"nacin": nacin_povrata, "iznos": obr["ukupno"]}], kupac_id=o["kupac_id"],
                       referentni_id=o["id"], odobrio_id=odobrio["id"], razlog=razlog.strip(),
                       napomena=f"Storno računa {o['broj']}", vreme=vreme)
    for s in nove:
        db.execute("UPDATE racun_stavke SET storno_kolicina = storno_kolicina + ? WHERE id = ?",
                   (float(s["kolicina"]), s["referentna_stavka_id"]))
        if s["artikal_id"]:
            promeni_stanje(db, s["artikal_id"], int(s["kolicina"]), "storno", f"Storno {broj}",
                           korisnik["korisnicko_ime"], racun_id=rid, napomena=razlog.strip(), vreme=vreme)
    ostalo = db.execute("SELECT SUM(kolicina - storno_kolicina) FROM racun_stavke WHERE racun_id = ?",
                        (racun_id,)).fetchone()[0]
    db.execute("UPDATE racuni SET status = ? WHERE id = ?",
               ("storniran" if ostalo <= 0 else "delimicno_storniran", racun_id))
    _fiskalizuj(db, rid, referentni=dict(o))
    return racun(db, rid)


def racun(db, rid: int) -> dict:
    r = db.execute("""SELECT r.*, k.ime AS kasir, o.ime AS odobrio, ref.broj AS referentni_broj
                      FROM racuni r JOIN korisnici k ON k.id = r.kasir_id
                      LEFT JOIN korisnici o ON o.id = r.popust_odobrio_id
                      LEFT JOIN racuni ref ON ref.id = r.referentni_id
                      WHERE r.id = ?""", (rid,)).fetchone()
    if r is None:
        raise PoslovnaGreska("Račun ne postoji.")
    rez = dict(r)
    rez.pop("fiskal_odgovor", None)
    rez["stavke"] = [dict(s) for s in db.execute("SELECT * FROM racun_stavke WHERE racun_id = ? ORDER BY id", (rid,))]
    rez["placanja"] = [dict(p) for p in db.execute("SELECT * FROM placanja WHERE racun_id = ? ORDER BY id", (rid,))]
    rez["kupac"] = dict(k) if r["kupac_id"] and (k := db.execute(
        "SELECT * FROM kupci WHERE id = ?", (r["kupac_id"],)).fetchone()) else None
    po_stopama = {}
    for s in rez["stavke"]:
        x = po_stopama.setdefault(str(int(s["pdv_stopa"])), {"osnovica": D0, "pdv": D0, "ukupno": D0})
        u = d(s["ukupno"])
        p = zaokruzi(u * d(s["pdv_stopa"]) / (d(100) + d(s["pdv_stopa"])))
        x["ukupno"] += u
        x["pdv"] += p
        x["osnovica"] += u - p
    rez["pdv_po_stopama"] = {k: {kk: float(vv) for kk, vv in v.items()} for k, v in po_stopama.items()}
    if rez["tip"] == "racun":
        rez["storna"] = [dict(x) for x in db.execute(
            "SELECT id, broj, vreme, ukupno FROM racuni WHERE referentni_id = ? AND tip = 'storno'", (rid,))]
    return rez


# ---------------------------------------------------------------------------- presek
def presek(db, dan: str) -> dict:
    """Dnevni presek: promet po načinu plaćanja i kasiru, storna, popusti (dan = 'YYYY-MM-DD')."""
    def zbir(sql, *par):
        return db.execute(sql, (dan, *par)).fetchone()

    racuni = zbir("SELECT COUNT(*), COALESCE(SUM(ukupno),0), COALESCE(SUM(popust),0), COALESCE(SUM(pdv),0) "
                  "FROM racuni WHERE tip='racun' AND date(vreme)=?")
    storna = zbir("SELECT COUNT(*), COALESCE(SUM(ukupno),0), COALESCE(SUM(pdv),0) "
                  "FROM racuni WHERE tip='storno' AND date(vreme)=?")
    nacini = {}
    for r in db.execute("""SELECT p.nacin, r.tip, SUM(p.iznos) FROM placanja p JOIN racuni r ON r.id = p.racun_id
                           WHERE date(r.vreme)=? AND r.tip IN ('racun','storno') GROUP BY p.nacin, r.tip""", (dan,)):
        nacini[r[0]] = nacini.get(r[0], 0) + (r[2] if r[1] == "racun" else -r[2])
    kasiri = [dict(r) for r in db.execute(
        """SELECT k.ime, COUNT(*) AS broj,
                  SUM(CASE WHEN r.tip='racun' THEN r.ukupno ELSE -r.ukupno END) AS promet
           FROM racuni r JOIN korisnici k ON k.id = r.kasir_id
           WHERE date(r.vreme)=? AND r.tip IN ('racun','storno') GROUP BY k.id ORDER BY promet DESC""", (dan,))]
    predracuni = zbir("SELECT COUNT(*), COALESCE(SUM(ukupno),0) FROM racuni WHERE tip='predracun' AND date(vreme)=?")
    return {
        "dan": dan,
        "broj_racuna": racuni[0], "promet_bruto": racuni[1], "popusti": racuni[2],
        "broj_storna": storna[0], "storna": storna[1],
        "promet_neto": round(racuni[1] - storna[1], 2), "pdv": round(racuni[3] - storna[2], 2),
        "po_nacinu": {k: round(v, 2) for k, v in nacini.items()},
        "po_kasiru": kasiri,
        "broj_predracuna": predracuni[0], "iznos_predracuna": predracuni[1],
    }


# ---------------------------------------------------------------------------- nabavka
def primi_robu(db, korisnik: str, stavke: list[dict], dobavljac_id=None, dokument="", napomena="",
               narudzbenica_id=None, vreme=None) -> int:
    stavke = [s for s in stavke if int(s.get("kolicina") or 0) > 0]
    if not stavke:
        raise PoslovnaGreska("Prijem nema nijednu stavku.")
    broj = sledeci_broj(db, "prijemi", "K", 4, vreme=vreme)
    pid = db.execute("""INSERT INTO prijemi (broj, dobavljac_id, narudzbenica_id, vreme, dokument, napomena, korisnik)
                        VALUES (?,?,?,?,?,?,?)""",
                     (broj, dobavljac_id, narudzbenica_id, vreme or sada(), dokument, napomena, korisnik)).lastrowid
    for s in stavke:
        nab = s.get("nabavna_cena")
        nab = float(nab) if nab not in (None, "") else None
        db.execute("INSERT INTO prijem_stavke (prijem_id, artikal_id, kolicina, nabavna_cena) VALUES (?,?,?,?)",
                   (pid, s["artikal_id"], int(s["kolicina"]), nab))
        promeni_stanje(db, s["artikal_id"], int(s["kolicina"]), "prijem", f"Prijem {broj}", korisnik,
                       prijem_id=pid, vreme=vreme)
        if nab is not None:
            db.execute("UPDATE artikli SET nabavna_cena = ? WHERE id = ?", (nab, s["artikal_id"]))
    if narudzbenica_id:
        db.execute("UPDATE narudzbenice SET status = 'primljena' WHERE id = ?", (narudzbenica_id,))
    return pid
