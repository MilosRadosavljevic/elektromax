"""Glavni ekran kase: pretraga artikala, stavke računa, ukupno, naplata."""
from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget)

import stampa
from dijalozi import (KupacDialog, NaplataDialog, PopustDialog, PresekDialog, RacuniDialog, greska,
                      sa_odobrenjem, stavka, tabela)
from klijent import Klijent, KlijentGreska
from obracun import format_din, izracunaj


class GlavniProzor(QMainWindow):
    def __init__(self, klijent: Klijent):
        super().__init__()
        self.k = klijent
        self.stavke = []          # [{"artikal": {...}, "kolicina": int, "popust": {...}|None}]
        self.popust_racun = None
        self.popust_razlog = ""
        self.kupac = None
        self.napomena = ""
        self.rezultati = []
        self.setWindowTitle("Elektromax kasa")
        self.resize(1400, 860)
        self.napravi()
        self.precice()
        self.trazi()
        self.osvezi()

    # ------------------------------------------------------------ izgled
    def napravi(self):
        koren = QWidget()
        self.setCentralWidget(koren)
        glavni = QVBoxLayout(koren)
        glavni.setContentsMargins(0, 0, 0, 0)
        glavni.setSpacing(0)

        zag = QWidget(objectName="zaglavlje")
        z = QHBoxLayout(zag)
        z.setContentsMargins(18, 10, 18, 10)
        z.addWidget(QLabel('ELEKTRO<span style="color:#ffc21a">MAX</span>', objectName="logo"))
        z.addSpacing(16)
        z.addWidget(QLabel("KASA"))
        if self.k.info.get("fiskal_rezim") == "DEMO":
            z.addSpacing(10)
            z.addWidget(QLabel("DEMO – nije fiskalna", objectName="bedz"))
        z.addStretch()
        u = self.k.korisnik
        z.addWidget(QLabel(f"Kasir: <b>{u['ime']}</b> ({u['uloga']})"))
        z.addSpacing(20)
        self.sat = QLabel(objectName="sat")
        z.addWidget(self.sat)
        z.addSpacing(16)
        odj = QPushButton("Odjava", objectName="zaglavljeDugme")
        odj.clicked.connect(self.odjava)
        z.addWidget(odj)
        glavni.addWidget(zag)
        QTimer(self, interval=1000, timeout=self.tik).start()
        self.tik()

        telo = QHBoxLayout()
        telo.setContentsMargins(14, 14, 14, 14)
        telo.setSpacing(14)
        glavni.addLayout(telo, 1)

        # levo: račun
        levo = QVBoxLayout()
        naslov = QHBoxLayout()
        naslov.addWidget(QLabel("Račun", objectName="naslov"))
        self.kupac_lbl = QLabel(objectName="pomoc")
        naslov.addWidget(self.kupac_lbl)
        naslov.addStretch()
        levo.addLayout(naslov)
        self.tab = tabela(["#", "Šifra", "Naziv", "Kol.", "JM", "Cena", "Popust", "Ukupno"], 2)
        self.tab.doubleClicked.connect(self.promeni_kolicinu)
        levo.addWidget(self.tab, 1)
        dug = QGridLayout()
        self.dug_grid, self.dug_lista = dug, []
        for i, (tekst, fn, kl) in enumerate([
                ("Količina (F4)", self.promeni_kolicinu, None), ("+1", lambda: self.korak(1), None),
                ("−1", lambda: self.korak(-1), None), ("Popust na stavku (F5)", self.popust_stavka, None),
                ("Ukloni stavku (Del)", self.ukloni, "opasno"), ("Popust na račun (F6)", self.popust_ceo, None),
                ("Kupac – firma (F7)", self.izaberi_kupca, None), ("Napomena (F8)", self.unesi_napomenu, None)]):
            b = QPushButton(tekst)
            if kl:
                b.setObjectName(kl)
            b.clicked.connect(fn)
            b.setMinimumWidth(0)
            self.dug_lista.append(b)
            dug.addWidget(b, i // 4, i % 4)
        levo.addLayout(dug)
        telo.addLayout(levo, 3)

        # desno: pretraga + ukupno + akcije
        desno = QVBoxLayout()
        self.q = QLineEdit(objectName="pretraga")
        self.q.setPlaceholderText("F1 – pretraga artikla (naziv ili šifra), npr. „5*kabl 3x2,5“")
        self.q.returnPressed.connect(self.dodaj_izabrani)
        self.q.installEventFilter(self)
        desno.addWidget(self.q)
        p = QLabel("Enter dodaje označeni artikal · ↑↓ biranje · „3*“ ispred teksta = količina 3", objectName="pomoc")
        p.setWordWrap(True)
        self.pomoc = p
        desno.addWidget(p)
        self.rez = tabela(["Šifra", "Naziv", "Cena", "Stanje"], 1)
        self.rez.doubleClicked.connect(self.dodaj_izabrani)
        desno.addWidget(self.rez, 1)
        self.tajmer = QTimer(self, singleShot=True, interval=220, timeout=self.trazi)
        self.q.textChanged.connect(self.tajmer.start)

        tot = QFrame(objectName="ukupnoPanel")
        tl = QGridLayout(tot)
        self.lbl = {}
        for i, (k, t) in enumerate([("bruto", "Bez popusta"), ("popust", "Popust"), ("osnovica", "Osnovica"),
                                    ("pdv", "PDV")]):
            tl.addWidget(QLabel(t), i, 0)
            self.lbl[k] = QLabel()
            self.lbl[k].setAlignment(Qt.AlignmentFlag.AlignRight)
            tl.addWidget(self.lbl[k], i, 1)
        tl.addWidget(QLabel("UKUPNO", objectName="ukupnoNaziv"), 4, 0)
        self.lbl["ukupno"] = QLabel(objectName="ukupno")
        self.lbl["ukupno"].setAlignment(Qt.AlignmentFlag.AlignRight)
        tl.addWidget(self.lbl["ukupno"], 4, 1)
        desno.addWidget(tot)

        self.b_naplata = QPushButton("NAPLATA  (F12)", objectName="glavno")
        self.b_naplata.clicked.connect(self.naplata)
        desno.addWidget(self.b_naplata)
        akc = QGridLayout()
        for i, (tekst, fn, kl) in enumerate([("Predračun (F9)", self.predracun, "tamno"),
                                             ("Izdati računi (F10)", self.racuni, None),
                                             ("Dnevni presek (F11)", self.presek, None),
                                             ("Novi račun (Esc)", self.novi_racun, "opasno")]):
            b = QPushButton(tekst)
            if kl:
                b.setObjectName(kl)
            b.clicked.connect(fn)
            akc.addWidget(b, i // 2, i % 2)
        desno.addLayout(akc)
        telo.addLayout(desno, 2)

    def resizeEvent(self, ev):
        """Na užem prozoru (manji laptop, tablet) dugmad ispod računa idu u dve kolone umesto u četiri."""
        super().resizeEvent(ev)
        kompakt = self.height() < 700          # nizak ekran: sakrij pomoć, smanji „UKUPNO“ i dugme za naplatu
        if getattr(self, "_kompakt", None) != kompakt:
            self._kompakt = kompakt
            self.pomoc.setVisible(not kompakt)
            self.lbl["ukupno"].setStyleSheet("font-size:22pt;" if kompakt else "")
            self.b_naplata.setStyleSheet("padding:8px;font-size:13pt;" if kompakt else "")
            self.tab.setMinimumHeight(60)
            self.rez.setMinimumHeight(60)
        kolone = 4 if self.width() >= 1250 else 2
        if getattr(self, "_kolone", None) != kolone:
            self._kolone = kolone
            for b in self.dug_lista:
                self.dug_grid.removeWidget(b)
            for i, b in enumerate(self.dug_lista):
                self.dug_grid.addWidget(b, i // kolone, i % kolone)

    def precice(self):
        for k, fn in {"F1": lambda: (self.q.setFocus(), self.q.selectAll()), "F4": self.promeni_kolicinu,
                      "F5": self.popust_stavka, "F6": self.popust_ceo, "F7": self.izaberi_kupca,
                      "F8": self.unesi_napomenu, "F9": self.predracun, "F10": self.racuni, "F11": self.presek,
                      "F12": self.naplata, "Esc": self.novi_racun}.items():
            QShortcut(QKeySequence(k), self, activated=fn)
        # ove prečice važe samo dok je fokus na tabeli računa (da ne smetaju kucanju u pretrazi)
        for k, fn in {"Del": self.ukloni, "+": lambda: self.korak(1), "-": lambda: self.korak(-1)}.items():
            QShortcut(QKeySequence(k), self.tab, activated=fn, context=Qt.ShortcutContext.WidgetShortcut)

    def eventFilter(self, obj, ev):
        # strelice u polju za pretragu pomeraju izbor u rezultatima
        if obj is self.q and ev.type() == ev.Type.KeyPress and ev.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            r = max(0, min(self.rez.rowCount() - 1, self.rez.currentRow() + (1 if ev.key() == Qt.Key.Key_Down else -1)))
            self.rez.selectRow(r)
            return True
        return super().eventFilter(obj, ev)

    def tik(self):
        self.sat.setText(QDateTime.currentDateTime().toString("dd.MM.yyyy  HH:mm:ss"))

    # ------------------------------------------------------------ pretraga
    def _upit(self):
        t = self.q.text().strip()
        if "*" in t:
            kol, _, ostalo = t.partition("*")
            if kol.strip().isdigit():
                return int(kol.strip()), ostalo.strip()
        return 1, t

    def trazi(self):
        _, tekst = self._upit()
        try:
            self.rezultati = [a for a in self.k.artikli(tekst) if a["aktivan"]]
        except KlijentGreska as e:
            return greska(self, e.poruka)
        self.rez.setRowCount(0)
        for a in self.rezultati:
            r = self.rez.rowCount()
            self.rez.insertRow(r)
            cena = a["akcijska_cena"] if a["akcijska_cena"] is not None else a["cena"]
            self.rez.setItem(r, 0, stavka(a["sifra"], podaci=a))
            self.rez.setItem(r, 1, stavka(a["naziv"] + ("  [AKCIJA]" if a["akcijska_cena"] is not None else "")))
            self.rez.setItem(r, 2, stavka(format_din(cena, False), True))
            st = stavka(f"{a['stanje']} {a['jedinica_mere']}", True)
            if a["stanje"] <= 0:
                st.setForeground(Qt.GlobalColor.red)
            self.rez.setItem(r, 3, st)
        if self.rezultati:
            self.rez.selectRow(0)

    def dodaj_izabrani(self):
        r = self.rez.currentRow()
        if r < 0:
            return
        a = self.rez.item(r, 0).data(Qt.ItemDataRole.UserRole)
        kol, _ = self._upit()
        for s in self.stavke:
            if s["artikal"]["id"] == a["id"] and not s["popust"]:
                s["kolicina"] += kol
                break
        else:
            self.stavke.append({"artikal": a, "kolicina": kol, "popust": None})
        self.q.clear()
        self.osvezi(izaberi=next(i for i, s in enumerate(self.stavke) if s["artikal"]["id"] == a["id"]))
        self.q.setFocus()

    # ------------------------------------------------------------ stavke
    def _izabrana(self):
        r = self.tab.currentRow()
        return r if 0 <= r < len(self.stavke) else None

    def promeni_kolicinu(self):
        i = self._izabrana()
        if i is None:
            return
        s = self.stavke[i]
        kol, ok = QInputDialog.getInt(self, "Količina", f"{s['artikal']['naziv']} ({s['artikal']['jedinica_mere']}):",
                                      s["kolicina"], 1, 1_000_000)
        if ok:
            s["kolicina"] = kol
            self.osvezi(i)

    def korak(self, n):
        i = self._izabrana()
        if i is None:
            return
        self.stavke[i]["kolicina"] = max(1, self.stavke[i]["kolicina"] + n)
        self.osvezi(i)

    def ukloni(self):
        i = self._izabrana()
        if i is not None:
            del self.stavke[i]
            self.osvezi(min(i, len(self.stavke) - 1))

    def popust_stavka(self):
        i = self._izabrana()
        if i is None:
            return
        s = self.stavke[i]
        a = s["artikal"]
        cena = a["akcijska_cena"] if a["akcijska_cena"] is not None else a["cena"]
        dlg = PopustDialog(self, f"Popust – {a['naziv']}", cena * s["kolicina"], s["popust"],
                           None if self.k.korisnik["uloga"] == "admin" else self.k.info.get("max_popust_radnik"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s["popust"] = dlg.popust()
            if dlg.razlog.text().strip():
                self.popust_razlog = dlg.razlog.text().strip()
            self.osvezi(i)

    def popust_ceo(self):
        if not self.stavke:
            return
        o = self._obracun(bez_racuna=True)
        dlg = PopustDialog(self, "Popust na ceo račun", o["ukupno"], self.popust_racun,
                           None if self.k.korisnik["uloga"] == "admin" else self.k.info.get("max_popust_radnik"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.popust_racun = dlg.popust()
            if dlg.razlog.text().strip():
                self.popust_razlog = dlg.razlog.text().strip()
            self.osvezi(self._izabrana())

    def izaberi_kupca(self):
        dlg = KupacDialog(self, self.k)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.izabran is not None:
            self.kupac = dlg.izabran or None
            self.osvezi(self._izabrana())

    def unesi_napomenu(self):
        t, ok = QInputDialog.getText(self, "Napomena", "Napomena na računu:", text=self.napomena)
        if ok:
            self.napomena = t.strip()
            self.osvezi(self._izabrana())

    # ------------------------------------------------------------ obračun i prikaz
    def _obracun(self, bez_racuna=False):
        ul = []
        for s in self.stavke:
            a = s["artikal"]
            ul.append({"cena": a["akcijska_cena"] if a["akcijska_cena"] is not None else a["cena"],
                       "kolicina": s["kolicina"], "pdv_stopa": a["pdv_stopa"], "popust": s["popust"]})
        return izracunaj(ul, None if bez_racuna else self.popust_racun)

    def osvezi(self, izaberi=None):
        o = self._obracun()
        self.tab.setRowCount(0)
        for i, (s, r) in enumerate(zip(self.stavke, o["stavke"])):
            self.tab.insertRow(i)
            a = s["artikal"]
            vrednosti = [i + 1, a["sifra"], a["naziv"], s["kolicina"], a["jedinica_mere"], format_din(r["cena"], False),
                         stampa.proc(r["popust_proc"]) if r["popust"] else "", format_din(r["ukupno"], False)]
            for c, v in enumerate(vrednosti):
                it = stavka(v, desno=c in (3, 5, 6, 7))
                if c == 3 and s["kolicina"] > a["stanje"]:
                    it.setForeground(Qt.GlobalColor.red)
                    it.setToolTip(f"Na stanju: {a['stanje']}")
                self.tab.setItem(i, c, it)
        if izaberi is not None and 0 <= izaberi < len(self.stavke):
            self.tab.selectRow(izaberi)
        for k in ("bruto", "popust", "osnovica", "pdv", "ukupno"):
            self.lbl[k].setText(("−" if k == "popust" and o[k] else "") + format_din(o[k]))
        delovi = []
        if self.kupac:
            delovi.append(f"Kupac: <b>{self.kupac['naziv']}</b> (PIB {self.kupac['pib'] or '—'})")
        if self.popust_racun:
            v = self.popust_racun
            delovi.append(f"Popust na račun: <b>{v['proc']:g}%</b>" if "proc" in v else
                          f"Popust na račun: <b>{format_din(v['iznos'])}</b>")
        if self.napomena:
            delovi.append(f"Napomena: {self.napomena}")
        self.kupac_lbl.setText("  ·  ".join(delovi))
        self.b_naplata.setEnabled(bool(self.stavke))

    # ------------------------------------------------------------ dokumenti
    def _telo(self, tip):
        return {"tip": tip, "kupac_id": self.kupac["id"] if self.kupac else None,
                "stavke": [{"artikal_id": s["artikal"]["id"], "kolicina": s["kolicina"], "popust": s["popust"]}
                           for s in self.stavke],
                "popust_racun": self.popust_racun, "popust_razlog": self.popust_razlog, "napomena": self.napomena}

    def _proveri_stanje(self):
        manjak = [f"• {s['artikal']['naziv']}: na stanju {s['artikal']['stanje']}, na računu {s['kolicina']}"
                  for s in self.stavke if s["kolicina"] > s["artikal"]["stanje"]]
        if not manjak:
            return True
        return QMessageBox.question(self, "Nema dovoljno na stanju",
                                    "Sledeći artikli nemaju dovoljno na stanju:\n\n" + "\n".join(manjak) +
                                    "\n\nNastaviti ipak? (stanje će otići u minus)") == QMessageBox.StandardButton.Yes

    def naplata(self):
        if not self.stavke or not self._proveri_stanje():
            return
        o = self._obracun()
        dlg = NaplataDialog(self, o["ukupno"], kupac=self.kupac)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        telo = {**self._telo("racun"), "placanja": dlg.placanja()}
        try:
            r = sa_odobrenjem(self, lambda odo: self.k.izdaj({**telo, "odobrenje": odo}))
        except KlijentGreska as e:
            return greska(self, e.poruka)
        if not r:
            return
        fmt = dlg.format_stampe()
        if fmt != "ne":
            stampa.stampaj(self, (stampa.html_a4 if fmt == "a4" else stampa.html_racun_80)(r, self.k.info["firma"]), fmt)
        kusur = sum(p.get("kusur") or 0 for p in r["placanja"])
        self.statusBar().showMessage(f"Izdat račun {r['broj']} – {format_din(r['ukupno'])}"
                                     + (f" · kusur {format_din(kusur)}" if kusur else ""), 15000)
        self.isprazni()

    def predracun(self):
        if not self.stavke:
            return
        try:
            r = sa_odobrenjem(self, lambda odo: self.k.izdaj({**self._telo("predracun"), "odobrenje": odo}))
        except KlijentGreska as e:
            return greska(self, e.poruka)
        if not r:
            return
        stampa.stampaj(self, stampa.html_a4(r, self.k.info["firma"]), "a4")
        self.statusBar().showMessage(f"Izdat predračun {r['broj']} (važi do {r['vazi_do']})", 15000)
        self.isprazni()

    def novi_racun(self):
        if self.stavke and QMessageBox.question(self, "Novi račun", "Odbaciti trenutni račun?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.isprazni()

    def isprazni(self):
        self.stavke, self.popust_racun, self.popust_razlog, self.kupac, self.napomena = [], None, "", None, ""
        self.trazi()
        self.osvezi()
        self.q.setFocus()

    def racuni(self):
        RacuniDialog(self, self.k).exec()
        self.trazi()

    def presek(self):
        PresekDialog(self, self.k).exec()

    def odjava(self):
        if self.stavke and QMessageBox.question(self, "Odjava", "Račun nije završen. Odjaviti se ipak?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.k.odjava()
        self.odjavljen = True
        self.close()
