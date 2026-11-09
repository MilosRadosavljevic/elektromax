-- Elektromax demo – šema baze (SQLite)
-- init_db.py: briše sve i pravi ponovo.  migracije.py: dopunjuje postojeću bazu (CREATE ... IF NOT EXISTS).

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS kretanja;
DROP TABLE IF EXISTS placanja;
DROP TABLE IF EXISTS racun_stavke;
DROP TABLE IF EXISTS racuni;
DROP TABLE IF EXISTS prijem_stavke;
DROP TABLE IF EXISTS prijemi;
DROP TABLE IF EXISTS narudzbenica_stavke;
DROP TABLE IF EXISTS narudzbenice;
DROP TABLE IF EXISTS api_tokeni;
DROP TABLE IF EXISTS kupci;
DROP TABLE IF EXISTS artikli;
DROP TABLE IF EXISTS dobavljaci;
DROP TABLE IF EXISTS kategorije;
DROP TABLE IF EXISTS radno_vreme;
DROP TABLE IF EXISTS podesavanja;
DROP TABLE IF EXISTS korisnici;

-- ===================================================================== katalog
CREATE TABLE kategorije (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    naziv       TEXT    NOT NULL,
    slug        TEXT    NOT NULL UNIQUE,          -- deo URL-a: /katalog?kategorija=kablovi
    opis        TEXT    NOT NULL DEFAULT '',
    ikonica     TEXT    NOT NULL DEFAULT 'box',   -- ključ ikonice iz templates/_ikonice.html
    redosled    INTEGER NOT NULL DEFAULT 0,
    aktivna     INTEGER NOT NULL DEFAULT 1 CHECK (aktivna IN (0, 1)),
    kreirano    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE dobavljaci (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    naziv       TEXT    NOT NULL,
    pib         TEXT    NOT NULL DEFAULT '',
    adresa      TEXT    NOT NULL DEFAULT '',
    kontakt     TEXT    NOT NULL DEFAULT '',     -- ime kontakt osobe
    telefon     TEXT    NOT NULL DEFAULT '',
    email       TEXT    NOT NULL DEFAULT '',
    rok_isporuke INTEGER NOT NULL DEFAULT 3,      -- dana, za predlog narudžbine
    napomena    TEXT    NOT NULL DEFAULT '',
    aktivan     INTEGER NOT NULL DEFAULT 1 CHECK (aktivan IN (0, 1)),
    kreirano    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Artikli – svaki pripada tačno jednoj kategoriji.
-- stanje se menja ISKLJUČIVO kroz poslovanje.promeni_stanje() (upisuje i red u tabelu kretanja).
-- stanje može biti negativno (prodaja preko stanja uz upozorenje).
CREATE TABLE artikli (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kategorija_id   INTEGER NOT NULL REFERENCES kategorije(id) ON DELETE RESTRICT,
    dobavljac_id    INTEGER          REFERENCES dobavljaci(id) ON DELETE SET NULL,
    sifra           TEXT    NOT NULL UNIQUE,
    naziv           TEXT    NOT NULL,
    opis            TEXT    NOT NULL DEFAULT '',
    proizvodjac     TEXT    NOT NULL DEFAULT '',
    jedinica_mere   TEXT    NOT NULL DEFAULT 'kom' CHECK (jedinica_mere IN ('kom', 'm', 'pak', 'kg', 'set')),
    cena            REAL    NOT NULL CHECK (cena >= 0),          -- prodajna, RSD sa PDV-om
    akcijska_cena   REAL             CHECK (akcijska_cena IS NULL OR akcijska_cena >= 0),
    nabavna_cena    REAL             CHECK (nabavna_cena IS NULL OR nabavna_cena >= 0), -- bez PDV-a, poslednja
    pdv_stopa       REAL    NOT NULL DEFAULT 20 CHECK (pdv_stopa IN (0, 10, 20)),
    stanje          INTEGER NOT NULL DEFAULT 0,
    min_kolicina    INTEGER NOT NULL DEFAULT 0 CHECK (min_kolicina >= 0), -- ispod ovoga -> „za naručiti“
    slika           TEXT,
    slika_kredit    TEXT,
    slika_izvor     TEXT,
    istaknut        INTEGER NOT NULL DEFAULT 0 CHECK (istaknut IN (0, 1)),
    aktivan         INTEGER NOT NULL DEFAULT 1 CHECK (aktivan IN (0, 1)),
    kreirano        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    izmenjeno       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    izmenio         TEXT
);
CREATE INDEX ix_artikli_kategorija ON artikli(kategorija_id);
CREATE INDEX ix_artikli_naziv      ON artikli(naziv);

CREATE TABLE radno_vreme (
    dan         INTEGER PRIMARY KEY CHECK (dan BETWEEN 0 AND 6),   -- 0 = nedelja
    radi        INTEGER NOT NULL DEFAULT 1 CHECK (radi IN (0, 1)),
    od          TEXT,
    do          TEXT,
    napomena    TEXT    NOT NULL DEFAULT '',
    CHECK (radi = 0 OR (od IS NOT NULL AND do IS NOT NULL AND od < do))
);

-- ===================================================================== korisnici
CREATE TABLE korisnici (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    korisnicko_ime  TEXT    NOT NULL UNIQUE,
    ime             TEXT    NOT NULL,
    lozinka_hash    TEXT    NOT NULL,
    uloga           TEXT    NOT NULL DEFAULT 'radnik' CHECK (uloga IN ('admin', 'radnik')),
    aktivan         INTEGER NOT NULL DEFAULT 1 CHECK (aktivan IN (0, 1)),
    kreirano        TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Prijave desktop kase (čuva se samo heš tokena)
CREATE TABLE api_tokeni (
    token_hash  TEXT    PRIMARY KEY,
    korisnik_id INTEGER NOT NULL REFERENCES korisnici(id) ON DELETE CASCADE,
    kreirano    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    koriscen    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE podesavanja (
    kljuc       TEXT PRIMARY KEY,
    vrednost    TEXT NOT NULL
);

-- ===================================================================== prodaja
CREATE TABLE kupci (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    naziv       TEXT    NOT NULL,
    pib         TEXT    NOT NULL DEFAULT '',
    mb          TEXT    NOT NULL DEFAULT '',
    adresa      TEXT    NOT NULL DEFAULT '',
    mesto       TEXT    NOT NULL DEFAULT '',
    telefon     TEXT    NOT NULL DEFAULT '',
    email       TEXT    NOT NULL DEFAULT '',
    napomena    TEXT    NOT NULL DEFAULT '',
    kreirano    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Računi, predračuni i storno računi (refundacije).
-- Iznosi su uvek POZITIVNI; storno se u analitici oduzima po tipu.
CREATE TABLE racuni (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broj            TEXT    NOT NULL UNIQUE,              -- R-2026-000001 / P-2026-000001 / S-2026-000001
    tip             TEXT    NOT NULL CHECK (tip IN ('racun', 'predracun', 'storno')),
    status          TEXT    NOT NULL DEFAULT 'izdat'
                    CHECK (status IN ('izdat', 'storniran', 'delimicno_storniran', 'realizovan', 'ponisten')),
    vreme           TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    kasir_id        INTEGER NOT NULL REFERENCES korisnici(id),
    kupac_id        INTEGER          REFERENCES kupci(id),
    referentni_id   INTEGER          REFERENCES racuni(id), -- storno -> original; račun -> predračun
    bruto           REAL    NOT NULL,     -- zbir cena x količina pre popusta (sa PDV-om)
    popust          REAL    NOT NULL DEFAULT 0,  -- ukupan popust (stavke + račun)
    ukupno          REAL    NOT NULL,     -- za naplatu (sa PDV-om)
    osnovica        REAL    NOT NULL,
    pdv             REAL    NOT NULL,
    popust_racun_proc REAL,               -- popust na ceo račun (ako je zadat u %)
    popust_odobrio_id INTEGER REFERENCES korisnici(id),
    popust_razlog   TEXT    NOT NULL DEFAULT '',
    napomena        TEXT    NOT NULL DEFAULT '',
    vazi_do         TEXT,                 -- predračun
    -- fiskalizacija (DEMO dok se ne poveže odobreni ESIR / L-PFR)
    fiskal_rezim    TEXT    NOT NULL DEFAULT 'DEMO',
    fiskal_broj     TEXT,
    fiskal_vreme    TEXT,
    fiskal_url      TEXT,
    fiskal_odgovor  TEXT
);
CREATE INDEX ix_racuni_vreme ON racuni(vreme);
CREATE INDEX ix_racuni_tip   ON racuni(tip, status);

CREATE TABLE racun_stavke (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    racun_id        INTEGER NOT NULL REFERENCES racuni(id) ON DELETE CASCADE,
    artikal_id      INTEGER          REFERENCES artikli(id) ON DELETE SET NULL,
    sifra           TEXT    NOT NULL,     -- snimak u trenutku prodaje
    naziv           TEXT    NOT NULL,
    jedinica_mere   TEXT    NOT NULL,
    kolicina        REAL    NOT NULL CHECK (kolicina > 0),
    cena            REAL    NOT NULL,     -- jedinična, sa PDV-om, pre popusta
    popust_proc     REAL    NOT NULL DEFAULT 0, -- efektivni % popusta na stavci (stavka + račun)
    popust          REAL    NOT NULL DEFAULT 0, -- iznos popusta na stavci
    ukupno          REAL    NOT NULL,     -- posle popusta, sa PDV-om
    pdv_stopa       REAL    NOT NULL,
    nabavna_cena    REAL,                 -- snimak, za obračun zarade
    storno_kolicina REAL    NOT NULL DEFAULT 0, -- koliko je već stornirano
    referentna_stavka_id INTEGER REFERENCES racun_stavke(id) -- storno stavka -> originalna
);
CREATE INDEX ix_stavke_racun   ON racun_stavke(racun_id);
CREATE INDEX ix_stavke_artikal ON racun_stavke(artikal_id);

CREATE TABLE placanja (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    racun_id    INTEGER NOT NULL REFERENCES racuni(id) ON DELETE CASCADE,
    nacin       TEXT    NOT NULL CHECK (nacin IN ('gotovina', 'kartica', 'prenos')),
    iznos       REAL    NOT NULL CHECK (iznos >= 0),
    primljeno   REAL,                     -- gotovina: koliko je kupac dao
    kusur       REAL
);

-- ===================================================================== nabavka
CREATE TABLE narudzbenice (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broj            TEXT    NOT NULL UNIQUE,              -- N-2026-0001
    dobavljac_id    INTEGER NOT NULL REFERENCES dobavljaci(id),
    status          TEXT    NOT NULL DEFAULT 'nacrt' CHECK (status IN ('nacrt', 'poslata', 'primljena', 'otkazana')),
    vreme           TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    napomena        TEXT    NOT NULL DEFAULT '',
    korisnik        TEXT
);
CREATE TABLE narudzbenica_stavke (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    narudzbenica_id INTEGER NOT NULL REFERENCES narudzbenice(id) ON DELETE CASCADE,
    artikal_id      INTEGER NOT NULL REFERENCES artikli(id),
    kolicina        INTEGER NOT NULL CHECK (kolicina > 0),
    nabavna_cena    REAL
);

CREATE TABLE prijemi (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broj            TEXT    NOT NULL UNIQUE,              -- K-2026-0001 (kalkulacija/prijemnica)
    dobavljac_id    INTEGER          REFERENCES dobavljaci(id),
    narudzbenica_id INTEGER          REFERENCES narudzbenice(id),
    vreme           TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    dokument        TEXT    NOT NULL DEFAULT '',          -- broj fakture/otpremnice dobavljača
    napomena        TEXT    NOT NULL DEFAULT '',
    korisnik        TEXT
);
CREATE TABLE prijem_stavke (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prijem_id       INTEGER NOT NULL REFERENCES prijemi(id) ON DELETE CASCADE,
    artikal_id      INTEGER NOT NULL REFERENCES artikli(id),
    kolicina        INTEGER NOT NULL CHECK (kolicina > 0),
    nabavna_cena    REAL
);

-- Svako kretanje zaliha (kartica artikla)
CREATE TABLE kretanja (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    artikal_id  INTEGER NOT NULL REFERENCES artikli(id) ON DELETE CASCADE,
    vreme       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    tip         TEXT    NOT NULL CHECK (tip IN ('pocetno', 'prodaja', 'storno', 'prijem', 'korekcija')),
    kolicina    INTEGER NOT NULL,         -- + ulaz, - izlaz
    stanje_posle INTEGER NOT NULL,
    dokument    TEXT    NOT NULL DEFAULT '',
    racun_id    INTEGER REFERENCES racuni(id) ON DELETE SET NULL,
    prijem_id   INTEGER REFERENCES prijemi(id) ON DELETE SET NULL,
    korisnik    TEXT,
    napomena    TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX ix_kretanja_artikal ON kretanja(artikal_id, vreme);
