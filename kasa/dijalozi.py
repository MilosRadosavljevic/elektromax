"""Dijalozi kase: prijava, popust, kupac, naplata, odobrenje, izdati računi, storno, presek."""
from datetime import date

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDateEdit, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout)

import stampa
from klijent import Klijent, KlijentGreska, sacuvaj_podesavanja, ucitaj_podesavanja
from obracun import d, format_din, zaokruzi

TIP = {"racun": "Račun", "predracun": "Predračun", "storno": "Storno"}
STATUS = {"izdat": "Izdat", "storniran": "Storniran", "delimicno_storniran": "Delimično storniran",
          "realizovan": "Realizovan", "ponisten": "Poništen"}


def stavka(tekst, desno=False, podaci=None):
    it = QTableWidgetItem(str(tekst))
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if desno:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if podaci is not None:
        it.setData(Qt.ItemDataRole.UserRole, podaci)
    return it


def tabela(kolone, rastegni=1):
    t = QTableWidget(0, len(kolone))
    t.setHorizontalHeaderLabels(kolone)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(rastegni, QHeaderView.ResizeMode.Stretch)
    t.verticalHeader().setDefaultSectionSize(34)
    return t


def greska(roditelj, poruka, naslov="Greška"):
    QMessageBox.warning(roditelj, naslov, poruka)


def sa_odobrenjem(roditelj, poziv):
    """Pozove poziv(odobrenje=None); ako server traži odobrenje admina, pita i ponovi."""
    odobrenje = None
    while True:
        try:
            return poziv(odobrenje)
        except KlijentGreska as e:
            if e.kod != "potrebno_odobrenje":
                raise
            dlg = OdobrenjeDialog(roditelj, e.poruka)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            odobrenje = dlg.podaci()


# ============================================================ prijava
class PrijavaDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Elektromax kasa – prijava")
        self.setMinimumWidth(420)
        self.klijent = None
        p = ucitaj_podesavanja()
        lay = QVBoxLayout(self)
        n = QLabel("ELEKTROMAX KASA")
        n.setObjectName("naslov")
        lay.addWidget(n)
        lay.addWidget(QLabel("Prijavite se svojim nalogom iz admin panela."))
        f = QFormLayout()
        self.server = QLineEdit(p.get("server", ""))
        self.ime = QLineEdit(p.get("korisnicko_ime", ""))
        self.lozinka = QLineEdit()
        self.lozinka.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow("Server:", self.server)
        f.addRow("Korisničko ime:", self.ime)
        f.addRow("Lozinka:", self.lozinka)
        lay.addLayout(f)
        self.poruka = QLabel()
        self.poruka.setObjectName("greska")
        self.poruka.setWordWrap(True)
        lay.addWidget(self.poruka)
        b = QPushButton("Prijavi se")
        b.setObjectName("tamno")
        b.setDefault(True)
        b.clicked.connect(self.prijava)
        lay.addWidget(b)
        (self.lozinka if self.ime.text() else self.ime).setFocus()

    def prijava(self):
        k = Klijent(self.server.text().strip() or "http://127.0.0.1:5000")
        try:
            k.prijava(self.ime.text().strip(), self.lozinka.text())
        except KlijentGreska as e:
            self.poruka.setText(e.poruka)
            return
        sacuvaj_podesavanja({"server": k.server, "korisnicko_ime": self.ime.text().strip()})
        self.klijent = k
        self.accept()


# ============================================================ odobrenje admina
class OdobrenjeDialog(QDialog):
    def __init__(self, roditelj, poruka):
        super().__init__(roditelj)
        self.setWindowTitle("Potrebno odobrenje administratora")
        lay = QVBoxLayout(self)
        l = QLabel(poruka + "\n\nAdministrator unosi svoje podatke:")
        l.setWordWrap(True)
        lay.addWidget(l)
        f = QFormLayout()
        self.ime = QLineEdit()
        self.lozinka = QLineEdit()
        self.lozinka.setEchoMode(QLineEdit.EchoMode.Password)
        f.addRow("Admin:", self.ime)
        f.addRow("Lozinka:", self.lozinka)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Odobri")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Odustani")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def podaci(self):
        return {"korisnicko_ime": self.ime.text().strip(), "lozinka": self.lozinka.text()}


# ============================================================ popust
class PopustDialog(QDialog):
    def __init__(self, roditelj, naslov, osnov, trenutni=None, max_radnik=None):
        super().__init__(roditelj)
        self.setWindowTitle(naslov)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Osnovica za popust: <b>{format_din(osnov)}</b>"))
        red = QHBoxLayout()
        self.proc = QRadioButton("U procentima (%)")
        self.iznos = QRadioButton("U dinarima")
        red.addWidget(self.proc)
        red.addWidget(self.iznos)
        lay.addLayout(red)
        self.vrednost = QDoubleSpinBox()
        self.vrednost.setDecimals(2)
        self.vrednost.setMaximum(10_000_000)
        lay.addWidget(self.vrednost)
        self.razlog = QLineEdit()
        self.razlog.setPlaceholderText("Razlog popusta (opciono) – npr. stalni kupac, oštećeno pakovanje")
        lay.addWidget(self.razlog)
        if max_radnik is not None:
            p = QLabel(f"Popust veći od {max_radnik:g}% traži odobrenje administratora.")
            p.setObjectName("pomoc")
            lay.addWidget(p)
        trenutni = trenutni or {}
        if trenutni.get("iznos") not in (None, ""):
            self.iznos.setChecked(True)
            self.vrednost.setValue(float(trenutni["iznos"]))
        else:
            self.proc.setChecked(True)
            self.vrednost.setValue(float(trenutni.get("proc") or 0))
        self.proc.toggled.connect(lambda: self.vrednost.setMaximum(100 if self.proc.isChecked() else 10_000_000))
        self.vrednost.setMaximum(100 if self.proc.isChecked() else 10_000_000)
        bb = QDialogButtonBox()
        bb.addButton("Primeni", QDialogButtonBox.ButtonRole.AcceptRole)
        ukloni = bb.addButton("Ukloni popust", QDialogButtonBox.ButtonRole.ResetRole)
        bb.addButton("Odustani", QDialogButtonBox.ButtonRole.RejectRole)
        ukloni.clicked.connect(lambda: (self.vrednost.setValue(0), self.accept()))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.vrednost.selectAll()
        self.vrednost.setFocus()

    def popust(self):
        v = self.vrednost.value()
        if not v:
            return None
        return {"proc": v} if self.proc.isChecked() else {"iznos": v}


# ============================================================ kupac (firma)
class KupacDialog(QDialog):
    def __init__(self, roditelj, klijent: Klijent):
        super().__init__(roditelj)
        self.k = klijent
        self.izabran = None
        self.setWindowTitle("Kupac – pravno lice")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        self.q = QLineEdit()
        self.q.setPlaceholderText("Pretraga po nazivu ili PIB-u…")
        lay.addWidget(self.q)
        self.t = tabela(["Naziv", "PIB", "Mesto"], 0)
        lay.addWidget(self.t)
        self.t.doubleClicked.connect(self.izaberi)
        okvir = QFrame()
        okvir.setObjectName("panel")
        g = QGridLayout(okvir)
        g.addWidget(QLabel("<b>Novi kupac</b>"), 0, 0, 1, 4)
        self.polja = {}
        for i, (kljuc, naziv) in enumerate([("naziv", "Naziv*"), ("pib", "PIB"), ("mb", "MB"),
                                           ("adresa", "Adresa"), ("mesto", "Mesto"), ("email", "E-mail")]):
            self.polja[kljuc] = QLineEdit()
            g.addWidget(QLabel(naziv), 1 + i // 2, (i % 2) * 2)
            g.addWidget(self.polja[kljuc], 1 + i // 2, (i % 2) * 2 + 1)
        dodaj = QPushButton("Dodaj i izaberi")
        dodaj.clicked.connect(self.dodaj)
        g.addWidget(dodaj, 4, 3)
        lay.addWidget(okvir)
        red = QHBoxLayout()
        bez = QPushButton("Bez kupca (fizičko lice)")
        bez.clicked.connect(lambda: (setattr(self, "izabran", {}), self.accept()))
        izb = QPushButton("Izaberi označenog")
        izb.setObjectName("tamno")
        izb.clicked.connect(self.izaberi)
        red.addWidget(bez)
        red.addStretch()
        red.addWidget(izb)
        lay.addLayout(red)
        self.tajmer = QTimer(self, singleShot=True, interval=250, timeout=self.trazi)
        self.q.textChanged.connect(self.tajmer.start)
        self.trazi()

    def trazi(self):
        try:
            self.lista = self.k.kupci(self.q.text().strip())
        except KlijentGreska as e:
            return greska(self, e.poruka)
        self.t.setRowCount(0)
        for k in self.lista:
            r = self.t.rowCount()
            self.t.insertRow(r)
            self.t.setItem(r, 0, stavka(k["naziv"], podaci=k))
            self.t.setItem(r, 1, stavka(k["pib"]))
            self.t.setItem(r, 2, stavka(k["mesto"]))

    def izaberi(self):
        r = self.t.currentRow()
        if r >= 0:
            self.izabran = self.t.item(r, 0).data(Qt.ItemDataRole.UserRole)
            self.accept()

    def dodaj(self):
        try:
            self.izabran = self.k.novi_kupac({k: v.text().strip() for k, v in self.polja.items()})
        except KlijentGreska as e:
            return greska(self, e.poruka)
        self.accept()


# ============================================================ naplata
class NaplataDialog(QDialog):
    def __init__(self, roditelj, ukupno, naslov="Naplata", kupac=None):
        super().__init__(roditelj)
        self.ukupno = zaokruzi(d(ukupno))
        self.setWindowTitle(naslov)
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        n = QLabel("ZA NAPLATU")
        n.setObjectName("ukupnoNaziv")
        lay.addWidget(n)
        u = QLabel(format_din(self.ukupno))
        u.setObjectName("ukupno")
        lay.addWidget(u)
        brzo = QHBoxLayout()
        for nacin, tekst in (("gotovina", "Sve gotovinom (F1)"), ("kartica", "Sve karticom (F2)"),
                             ("prenos", "Sve prenosom (F3)")):
            b = QPushButton(tekst)
            b.clicked.connect(lambda _=False, n=nacin: self.sve(n))
            b.setShortcut(f"F{['gotovina', 'kartica', 'prenos'].index(nacin) + 1}")
            brzo.addWidget(b)
        lay.addLayout(brzo)
        f = QFormLayout()
        self.iznosi = {}
        for nacin, tekst in (("gotovina", "Gotovina"), ("kartica", "Platna kartica"), ("prenos", "Prenos na račun")):
            s = QDoubleSpinBox()
            s.setDecimals(2)
            s.setMaximum(100_000_000)
            s.setSuffix(" RSD")
            s.valueChanged.connect(self.osvezi)
            self.iznosi[nacin] = s
            f.addRow(tekst + ":", s)
        self.primljeno = QDoubleSpinBox()
        self.primljeno.setDecimals(2)
        self.primljeno.setMaximum(100_000_000)
        self.primljeno.setSuffix(" RSD")
        self.primljeno.valueChanged.connect(self.osvezi)
        f.addRow("Kupac dao (gotovina):", self.primljeno)
        lay.addLayout(f)
        self.kusur = QLabel()
        self.kusur.setObjectName("kusur")
        lay.addWidget(self.kusur)
        self.info = QLabel()
        self.info.setObjectName("greska")
        lay.addWidget(self.info)
        if kupac is None:
            p = QLabel("Prenos na račun se obično koristi za firme – izaberite kupca (F7) pre naplate.")
            p.setObjectName("pomoc")
            p.setWordWrap(True)
            lay.addWidget(p)
        st = QHBoxLayout()
        st.addWidget(QLabel("Štampa:"))
        self.format = QButtonGroup(self)
        for i, (k, t) in enumerate((("80mm", "Isečak 80 mm"), ("a4", "A4 račun"), ("ne", "Bez štampe"))):
            rb = QRadioButton(t)
            rb.setProperty("k", k)
            self.format.addButton(rb, i)
            st.addWidget(rb)
            if k == ("a4" if kupac else "80mm"):
                rb.setChecked(True)
        lay.addLayout(st)
        self.ok = QPushButton("NAPLATI  (Enter)")
        self.ok.setObjectName("glavno")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.potvrdi)
        lay.addWidget(self.ok)
        self.sve("gotovina")

    def sve(self, nacin):
        for k, s in self.iznosi.items():
            s.blockSignals(True)
            s.setValue(float(self.ukupno) if k == nacin else 0)
            s.blockSignals(False)
        self.primljeno.setValue(float(self.ukupno) if nacin == "gotovina" else 0)
        self.osvezi()
        (self.primljeno if nacin == "gotovina" else self.ok).setFocus()
        self.primljeno.selectAll()

    def osvezi(self):
        zbir = sum((zaokruzi(d(s.value())) for s in self.iznosi.values()), d(0))
        got = zaokruzi(d(self.iznosi["gotovina"].value()))
        prim = zaokruzi(d(self.primljeno.value()))
        problem = ""
        if zbir != self.ukupno:
            problem = f"Zbir plaćanja je {format_din(zbir)} – razlika {format_din(self.ukupno - zbir)}."
        elif got and prim < got:
            problem = "Kupac je dao manje od iznosa za gotovinu."
        self.info.setText(problem)
        self.kusur.setText(f"Kusur: {format_din(prim - got)}" if got and prim >= got else "")
        self.ok.setEnabled(not problem)

    def potvrdi(self):
        if self.ok.isEnabled():
            self.accept()

    def placanja(self):
        out = []
        for k, s in self.iznosi.items():
            if s.value():
                p = {"nacin": k, "iznos": round(s.value(), 2)}
                if k == "gotovina":
                    p["primljeno"] = round(self.primljeno.value(), 2) or p["iznos"]
                out.append(p)
        return out

    def format_stampe(self):
        return self.format.checkedButton().property("k")


# ============================================================ izdati računi
class RacuniDialog(QDialog):
    def __init__(self, roditelj, klijent: Klijent):
        super().__init__(roditelj)
        self.k = klijent
        self.r = None
        self.setWindowTitle("Izdati računi i predračuni")
        self.resize(1250, 760)
        lay = QHBoxLayout(self)
        levo = QVBoxLayout()
        f = QHBoxLayout()
        self.od = QDateEdit(QDate.currentDate())
        self.do = QDateEdit(QDate.currentDate())
        for x in (self.od, self.do):
            x.setCalendarPopup(True)
            x.setDisplayFormat("dd.MM.yyyy")
        self.tip = QComboBox()
        for k, t in (("", "Svi dokumenti"), ("racun", "Računi"), ("predracun", "Predračuni"), ("storno", "Storno")):
            self.tip.addItem(t, k)
        self.q = QLineEdit()
        self.q.setPlaceholderText("Broj ili kupac…")
        osvezi = QPushButton("Prikaži")
        osvezi.clicked.connect(self.ucitaj)
        for w in (QLabel("Od"), self.od, QLabel("do"), self.do, self.tip, self.q, osvezi):
            f.addWidget(w)
        levo.addLayout(f)
        self.t = tabela(["Broj", "Tip", "Vreme", "Kupac", "Iznos", "Status", "Kasir"], 3)
        self.t.itemSelectionChanged.connect(self.prikazi)
        levo.addWidget(self.t)
        lay.addLayout(levo, 3)
        desno = QVBoxLayout()
        self.pregled = QTextBrowser()
        self.pregled.setMinimumWidth(380)
        desno.addWidget(self.pregled, 1)
        g = QGridLayout()
        self.b_kopija = QPushButton("Kopija 80 mm")
        self.b_a4 = QPushButton("Štampa A4")
        self.b_storno = QPushButton("Storno…")
        self.b_storno.setObjectName("opasno")
        self.b_realizuj = QPushButton("Naplati predračun")
        self.b_realizuj.setObjectName("tamno")
        self.b_ponisti = QPushButton("Poništi predračun")
        self.b_ponisti.setObjectName("opasno")
        self.b_kopija.clicked.connect(lambda: self.r and stampa.stampaj(self, stampa.html_racun_80(self.r, self.k.info["firma"], kopija=True), "80mm"))
        self.b_a4.clicked.connect(lambda: self.r and stampa.stampaj(self, stampa.html_a4(self.r, self.k.info["firma"], kopija=self.r["tip"] != "predracun"), "a4"))
        self.b_storno.clicked.connect(self.storno)
        self.b_realizuj.clicked.connect(self.realizuj)
        self.b_ponisti.clicked.connect(self.ponisti)
        for i, b in enumerate((self.b_kopija, self.b_a4, self.b_storno, self.b_realizuj, self.b_ponisti)):
            g.addWidget(b, i // 2, i % 2)
        desno.addLayout(g)
        lay.addLayout(desno, 2)
        self.ucitaj()

    def ucitaj(self):
        try:
            lista = self.k.racuni(self.od.date().toString("yyyy-MM-dd"), self.do.date().toString("yyyy-MM-dd"),
                                  self.tip.currentData(), self.q.text().strip())
        except KlijentGreska as e:
            return greska(self, e.poruka)
        self.t.setRowCount(0)
        for x in lista:
            r = self.t.rowCount()
            self.t.insertRow(r)
            znak = "-" if x["tip"] == "storno" else ""
            for c, v in enumerate([x["broj"], TIP[x["tip"]], x["vreme"][8:10] + "." + x["vreme"][5:7] + ". " + x["vreme"][11:16],
                                   x["kupac"] or "", znak + format_din(x["ukupno"], False),
                                   STATUS[x["status"]], x["kasir"]]):
                self.t.setItem(r, c, stavka(v, desno=c == 4, podaci=x["id"] if c == 0 else None))
        self.r = None
        self.pregled.clear()
        self.dugmad()

    def prikazi(self):
        red = self.t.currentRow()
        if red < 0:
            return
        try:
            self.r = self.k.racun(self.t.item(red, 0).data(Qt.ItemDataRole.UserRole))
        except KlijentGreska as e:
            return greska(self, e.poruka)
        self.pregled.setHtml(stampa.html_racun_80(self.r, self.k.info["firma"]))
        self.dugmad()

    def dugmad(self):
        r = self.r or {}
        self.b_kopija.setEnabled(bool(r))
        self.b_a4.setEnabled(bool(r))
        self.b_storno.setEnabled(r.get("tip") == "racun" and r.get("status") in ("izdat", "delimicno_storniran"))
        aktivan_pr = r.get("tip") == "predracun" and r.get("status") == "izdat"
        self.b_realizuj.setEnabled(aktivan_pr)
        self.b_ponisti.setEnabled(aktivan_pr)

    def storno(self):
        dlg = StornoDialog(self, self.k, self.r)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.rezultat:
            if QMessageBox.question(self, "Storno", f"Storno račun {dlg.rezultat['broj']} je izdat. Štampati ga?") \
                    == QMessageBox.StandardButton.Yes:
                stampa.stampaj(self, stampa.html_racun_80(dlg.rezultat, self.k.info["firma"]), "80mm")
            self.ucitaj()

    def realizuj(self):
        dlg = NaplataDialog(self, self.r["ukupno"], f"Naplata predračuna {self.r['broj']}", self.r.get("kupac"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            r = self.k.realizuj(self.r["id"], dlg.placanja())
        except KlijentGreska as e:
            return greska(self, e.poruka)
        if dlg.format_stampe() != "ne":
            fmt = dlg.format_stampe()
            stampa.stampaj(self, (stampa.html_a4 if fmt == "a4" else stampa.html_racun_80)(r, self.k.info["firma"]), fmt)
        self.ucitaj()

    def ponisti(self):
        if QMessageBox.question(self, "Poništi predračun", f"Poništiti predračun {self.r['broj']}?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            self.k.ponisti(self.r["id"])
        except KlijentGreska as e:
            return greska(self, e.poruka)
        self.ucitaj()


class StornoDialog(QDialog):
    def __init__(self, roditelj, klijent: Klijent, r: dict):
        super().__init__(roditelj)
        self.k, self.r, self.rezultat = klijent, r, None
        self.setWindowTitle(f"Storno računa {r['broj']}")
        self.resize(820, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Unesite količine koje se vraćaju (0 = ne vraća se). Roba se vraća na stanje."))
        self.t = tabela(["Artikal", "Prodato", "Već vraćeno", "Vraća se", "Iznos stavke"], 0)
        self.spinovi = []
        for s in r["stavke"]:
            red = self.t.rowCount()
            self.t.insertRow(red)
            ostalo = int(s["kolicina"] - s["storno_kolicina"])
            self.t.setItem(red, 0, stavka(s["naziv"]))
            self.t.setItem(red, 1, stavka(f"{s['kolicina']:g}", True))
            self.t.setItem(red, 2, stavka(f"{s['storno_kolicina']:g}", True))
            sp = QSpinBox()
            sp.setRange(0, ostalo)
            sp.setValue(ostalo)
            self.t.setCellWidget(red, 3, sp)
            self.spinovi.append((s, sp))
            self.t.setItem(red, 4, stavka(format_din(s["ukupno"]), True))
        lay.addWidget(self.t)
        f = QFormLayout()
        self.razlog = QLineEdit()
        self.razlog.setPlaceholderText("npr. kupac vratio robu, greška pri kucanju")
        self.nacin = QComboBox()
        for k, t in (("", "Kao na računu"), ("gotovina", "Gotovina"), ("kartica", "Kartica"), ("prenos", "Prenos")):
            self.nacin.addItem(t, k)
        f.addRow("Razlog*:", self.razlog)
        f.addRow("Povraćaj novca:", self.nacin)
        lay.addLayout(f)
        b = QPushButton("Storniraj izabrano")
        b.setObjectName("tamno")
        b.clicked.connect(self.potvrdi)
        lay.addWidget(b)

    def potvrdi(self):
        stavke = [{"stavka_id": s["id"], "kolicina": sp.value()} for s, sp in self.spinovi if sp.value()]
        if not stavke:
            return greska(self, "Nije izabrana nijedna količina.")
        if not self.razlog.text().strip():
            return greska(self, "Unesite razlog storniranja.")
        telo = {"stavke": stavke, "razlog": self.razlog.text().strip(), "nacin_povrata": self.nacin.currentData() or None}
        try:
            self.rezultat = sa_odobrenjem(self, lambda odo: self.k.storno(self.r["id"], {**telo, "odobrenje": odo}))
        except KlijentGreska as e:
            return greska(self, e.poruka)
        if self.rezultat:
            self.accept()


# ============================================================ presek
class PresekDialog(QDialog):
    def __init__(self, roditelj, klijent: Klijent):
        super().__init__(roditelj)
        self.k = klijent
        self.setWindowTitle("Dnevni presek")
        self.resize(480, 720)
        lay = QVBoxLayout(self)
        red = QHBoxLayout()
        self.dan = QDateEdit(QDate.currentDate())
        self.dan.setCalendarPopup(True)
        self.dan.setDisplayFormat("dd.MM.yyyy")
        self.dan.dateChanged.connect(self.ucitaj)
        red.addWidget(QLabel("Dan:"))
        red.addWidget(self.dan)
        red.addStretch()
        st = QPushButton("Štampaj")
        st.setObjectName("tamno")
        st.clicked.connect(lambda: stampa.stampaj(self, self.html, "80mm"))
        red.addWidget(st)
        lay.addLayout(red)
        self.pregled = QTextBrowser()
        lay.addWidget(self.pregled)
        self.ucitaj()

    def ucitaj(self):
        try:
            p = self.k.presek(self.dan.date().toString("yyyy-MM-dd"))
        except KlijentGreska as e:
            return greska(self, e.poruka)
        self.html = stampa.html_presek_80(p, self.k.info["firma"])
        self.pregled.setHtml(self.html)
