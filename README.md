# Elektromax – retail management demo

**Live demo:** https://elektromax88.duckdns.org

A demo system for an electrical supplies store: a product catalog website with an admin panel, a desktop
point-of-sale app, purchasing and sales analytics. There is no online shopping – the website is a catalog and
sales happen in the store.

- **Website & admin panel:** Python, Flask, SQLite, Jinja, plain CSS/JS (SVG charts without libraries)
- **Desktop POS:** PySide6 (Qt), REST API with token login, 80 mm and A4 receipt printing, packaged with PyInstaller
- **Business logic:** discounts and VAT, pro-forma invoices, cancellations, stock movements, purchase suggestions,
  daily reports
- **Deployment:** Ubuntu, gunicorn + nginx, HTTPS (Let's Encrypt), systemd service, nightly backups – see `deploy/`
- **Tests:** unittest (website, admin, POS API, calculations)

The rest of this README is in Serbian.

---

# Elektromax – demo: sajt, admin panel, desktop kasa, nabavka i analitika

Demo sistem za prodavnicu elektro opreme **Elektromax** iz Smederevske Palanke. **Nema online kupovine** –
sajt je katalog, prodaja je samo u radnji.

| Deo | Šta je | Kako se pokreće |
|---|---|---|
| **Sajt** | katalog, kategorije, radno vreme, kontakt | `pokreni.bat` → http://127.0.0.1:5000 |
| **Admin panel** | artikli, nabavka, računi, kupci, analitika, korisnici | http://127.0.0.1:5000/admin |
| **Desktop kasa** | prodaja, popusti, naplata, štampa, predračuni, storno, presek | `pokreni_kasu.bat` ili `dist\ElektromaxKasa\ElektromaxKasa.exe` |

**Tehnologija:** Python 3 · Flask · SQLite · Jinja · čist CSS/JS (sajt i admin) · PySide6/Qt (kasa) · PyInstaller (exe)

## Pokretanje

1. **Server** (sajt + admin + API za kasu): dvoklik na `pokreni.bat`.
   Za pristup sa telefona ili drugog računara u istoj Wi-Fi mreži pre pokretanja postaviti
   `set ELEKTROMAX_HOST=<IP adresa računara>`.
2. **Kasa**: `pokreni_kasu.bat` (iz koda) – na ekranu za prijavu upisati adresu servera i nalog iz admin panela.
3. **Exe kase**: `napravi_exe.bat` → `dist\ElektromaxKasa\` (ceo folder se kopira na računar za kasom,
   Python tamo nije potreban).

Demo nalozi (`admin`, `radnik`) prave se u `init_db.py` i služe samo za lokalno testiranje. Na serveru
`deploy/postavi_server.sh` svim demo nalozima postavlja nove, nasumične lozinke koje vidi samo root.

## Desktop kasa – prečice

| Taster | Radnja | Taster | Radnja |
|---|---|---|---|
| F1 | pretraga artikla (`5*kabl` = količina 5) | F8 | napomena na računu |
| Enter | dodaj označeni artikal | F9 | predračun (A4) |
| F4 / +/− / Del | količina / korak / ukloni stavku | F10 | izdati računi (kopija, A4, storno, naplata predračuna) |
| F5 | popust na stavku (% ili RSD) | F11 | dnevni presek |
| F6 | popust na ceo račun | F12 | **naplata** (gotovina/kartica/prenos, kombinovano, kusur) |
| F7 | kupac – firma (PIB, za A4 račun) | Esc | novi račun |

Pravila: radnik daje popust do **10%** bez odobrenja (podešava se u adminu), veći popust i svaki **storno** traže
prijavu administratora; prodaja preko stanja je dozvoljena uz upozorenje; predračun važi **7 dana** i ne skida robu.
Štampa: isečak **80 mm** (termalni štampač) ili **A4**, uz pregled pre štampe (može i „Microsoft Print to PDF“).

## Admin panel – novo

- **Analitika** (admin): promet, broj računa, prosečan račun, bruto zarada i marža, popusti, storna, vrednost zaliha –
  sve sa poređenjem prema prethodnom periodu; promet po danu, „kada se najviše prodaje“ (dan × sat), po kategoriji,
  najprodavaniji artikli (promet/količina/zarada), načini plaćanja, učinak kasira, artikli koji se ne prodaju.
- **Za naručiti**: predlog količina iz prodaje u poslednjih 30 dana, roka isporuke dobavljača, minimalne količine i
  robe na putu → jednim klikom narudžbenice po dobavljaču.
- **Narudžbenice** (štampa/PDF), **Prijem robe** (uvećava stanje, ažurira nabavnu cenu), **Dobavljači**.
- **Kartica artikla**: svako kretanje zaliha (prodaja, storno, prijem, korekcija) + korekcija stanja (popis).
- **Računi** (pregled + A4/PDF), **Kupci** (firme sa prometom), **Podešavanja kase**.

## Fiskalizacija

Kasa radi u **DEMO režimu** – računi nisu fiskalni i ne smeju se koristiti za stvarnu prodaju.
Plan povezivanja sa odobrenim ESIR-om / L-PFR-om: **[FISKALIZACIJA.md](FISKALIZACIJA.md)**.

## Baza (`schema.sql`)

```
kategorije ─< artikli >─ dobavljaci          artikli: cena, akcijska, nabavna, PDV, stanje, min. količina
artikli ─< kretanja                          (kartica artikla – svaka promena stanja)
racuni ─< racun_stavke, placanja             tip: racun | predracun | storno; snimak cena i nabavne cene
racuni >─ kupci, korisnici (kasir, odobrio)  fiskal_* kolone za PFR odgovor
narudzbenice ─< narudzbenica_stavke          prijemi ─< prijem_stavke
korisnici, api_tokeni (prijava kase), podesavanja, radno_vreme
```

Stanje artikla menja **samo** `poslovanje.promeni_stanje()` – zato se stanje uvek slaže sa karticom artikla.

## Struktura

```
app.py              javni sajt + admin (artikli, kategorije, radno vreme, korisnici)
admin_nabavka.py    za naručiti, narudžbenice, prijem robe, dobavljači, kartica artikla
admin_prodaja.py    računi, kupci, podešavanja kase
admin_analitika.py  analitika prodaje
api.py              REST API za desktop kasu (/api, token prijava)
poslovanje.py       poslovna pravila: račun, predračun, storno, zalihe, prijem, presek
obracun.py          obračun popusta i PDV-a (isti kod koristi i kasa)
fiskal.py           fiskalni adapter (DEMO) + mapiranje na ESIR
dokumenti.py        HTML isečka 80 mm, A4 računa/predračuna, preseka
firma.py            podaci o firmi (PIB, MB, tekući račun…)
migracije.py        dopunjava postojeću bazu bez gubitka podataka
init_db.py          nova baza sa demo katalogom  ·  demo_podaci.py  90 dana izmišljene prodaje
kasa/               desktop kasa (PySide6): main.py, glavni_prozor.py, dijalozi.py, stampa.py, klijent.py
templates/, static/ šabloni, stilovi, skripte (grafikoni.js – SVG grafikoni bez biblioteka)
tests/              automatski testovi (sajt, admin, API kase, obračun)
```

Testovi: `.venv\Scripts\python -m unittest discover tests -v`

## Napomene za demo

- Artikli, cene, dobavljači, kupci i prodaja u bazi su **izmišljeni demo podaci**.
- Slike artikala su sa Wikimedia Commons (slobodne licence); autori na `/izvori-fotografija`.
- `init_db.py` briše sve i pravi bazu ispočetka; `demo_podaci.py` dodaje 90 dana prodaje (samo ako nema računa).
- Za produkciju: fiskalizacija (vidi gore), pravi server (waitress/gunicorn), HTTPS, rezervne kopije,
  `ELEKTROMAX_SECRET` u okruženju, ograničen broj pokušaja prijave, rad kase bez interneta.
