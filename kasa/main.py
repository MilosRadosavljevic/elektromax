"""Elektromax kasa – desktop program (Windows).

Pokretanje iz projekta:  .venv\\Scripts\\python kasa\\main.py   (ili pokreni_kasu.bat)
Exe:                     napravi_exe.bat  ->  dist\\ElektromaxKasa\\ElektromaxKasa.exe
"""
import sys
from pathlib import Path

# zajednički moduli (obracun.py, fiskal.py) su u korenu projekta
KOREN = Path(__file__).resolve().parent.parent
if str(KOREN) not in sys.path:
    sys.path.insert(0, str(KOREN))

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from dijalozi import PrijavaDialog  # noqa: E402
from glavni_prozor import GlavniProzor  # noqa: E402
from tema import QSS  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Elektromax kasa")
    app.setStyleSheet(QSS)
    while True:
        prijava = PrijavaDialog()
        if prijava.exec() != QDialog.DialogCode.Accepted:
            return 0
        prozor = GlavniProzor(prijava.klijent)
        prozor.odjavljen = False
        prozor.showMaximized()
        app.exec()
        if not prozor.odjavljen:      # zatvoren prozor = kraj rada; odjava = nova prijava
            prijava.klijent.odjava()
            return 0


if __name__ == "__main__":
    sys.exit(main())
