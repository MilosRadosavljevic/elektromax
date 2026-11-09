"""Izgled kase (Qt stylesheet) – iste boje kao sajt i admin panel."""

INK = "#14171c"
INK2 = "#1d2229"
VOLT = "#ffc21a"
PAPIR = "#f6f4ef"
LINIJA = "#e3dfd6"
TEKST = "#1b1f25"
SIVO = "#5d6672"
CRVENO = "#d64533"
ZELENO = "#1f9d55"

QSS = f"""
* {{ font-family: 'Segoe UI'; font-size: 11pt; color: {TEKST}; }}
QMainWindow, QDialog {{ background: {PAPIR}; }}
QWidget#zaglavlje {{ background: {INK}; }}
QWidget#zaglavlje QLabel {{ color: #eef1f5; }}
QLabel#logo {{ font-size: 18pt; font-weight: 800; color: white; letter-spacing: 1px; }}
QLabel#logo2 {{ font-size: 18pt; font-weight: 800; color: {VOLT}; }}
QLabel#sat {{ font-size: 13pt; font-weight: 600; color: {VOLT}; }}
QLabel#naslov {{ font-size: 15pt; font-weight: 700; }}
QLabel#pomoc {{ color: {SIVO}; font-size: 9.5pt; }}
QLabel#ukupno {{ font-size: 30pt; font-weight: 800; color: {INK}; }}
QLabel#ukupnoNaziv {{ font-size: 12pt; font-weight: 700; color: {SIVO}; }}
QLabel#kusur {{ font-size: 22pt; font-weight: 800; color: {ZELENO}; }}
QLabel#greska {{ color: {CRVENO}; font-weight: 600; }}
QLabel#bedz {{ background: {VOLT}; color: {INK}; border-radius: 5px; padding: 2px 8px; font-weight: 700; font-size: 9.5pt; }}
QFrame#panel {{ background: white; border: 1px solid {LINIJA}; border-radius: 10px; }}
QFrame#ukupnoPanel {{ background: white; border: 2px solid {INK}; border-radius: 10px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit {{
    background: white; border: 1.5px solid {LINIJA}; border-radius: 7px; padding: 6px 8px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{ border-color: #e8a800; }}
QLineEdit#pretraga {{ font-size: 14pt; padding: 9px 12px; }}
QTableWidget {{ background: white; border: 1px solid {LINIJA}; border-radius: 8px; gridline-color: #f0eee9;
    selection-background-color: #fff3c8; selection-color: {TEKST}; alternate-background-color: #faf9f6; }}
QHeaderView::section {{ background: #efede7; border: none; border-bottom: 1px solid {LINIJA}; padding: 6px;
    font-weight: 700; font-size: 9.5pt; color: {SIVO}; }}
QPushButton {{ background: white; border: 1.5px solid {LINIJA}; border-radius: 8px; padding: 8px 14px; font-weight: 600; }}
QPushButton:hover {{ border-color: {INK}; }}
QPushButton:disabled {{ color: #aaa; }}
QPushButton#glavno {{ background: {VOLT}; border: none; color: {INK}; font-weight: 800; font-size: 15pt; padding: 14px; }}
QPushButton#glavno:hover {{ background: #ffcf45; }}
QPushButton#tamno {{ background: {INK}; border: none; color: white; font-weight: 700; }}
QPushButton#tamno:hover {{ background: #2a313b; }}
QPushButton#opasno {{ color: {CRVENO}; border-color: #f1c4bf; }}
QPushButton#opasno:hover {{ background: #fdecea; }}
QPushButton#zaglavljeDugme {{ background: transparent; color: #eef1f5; border: 1px solid #3a424d; }}
QTextBrowser {{ background: white; border: 1px solid {LINIJA}; border-radius: 8px; }}
QRadioButton, QCheckBox {{ spacing: 8px; }}
"""
