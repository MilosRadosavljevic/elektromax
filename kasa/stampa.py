"""Štampa: isečak 80 mm (termalni štampač), A4 račun/predračun, dnevni presek.

Dokumenti se prave kao jednostavan HTML koji Qt (QTextDocument) ume da prikaže i odštampa.
"""
from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

from dokumenti import html_a4, html_presek_80, html_racun_80, proc  # noqa: F401  (koriste ih ekrani kase)


# ------------------------------------------------------------------ štampa
def _printer(format_: str) -> QPrinter:
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    if format_ == "80mm":
        pr.setPageLayout(QPageLayout(QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter, "Traka 80mm"),
                                     QPageLayout.Orientation.Portrait, QMarginsF(3, 3, 3, 3),
                                     QPageLayout.Unit.Millimeter))
    else:
        pr.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                     QMarginsF(14, 12, 14, 12), QPageLayout.Unit.Millimeter))
    return pr


def dokument(html: str, format_: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Consolas" if format_ == "80mm" else "Segoe UI", 8 if format_ == "80mm" else 9))
    doc.setHtml(html)
    return doc


def stampaj(roditelj, html: str, format_: str = "80mm"):
    """Otvara pregled pre štampe; korisnik bira štampač (ili 'Microsoft Print to PDF')."""
    pr = _printer(format_)
    doc = dokument(html, format_)
    dlg = QPrintPreviewDialog(pr, roditelj)
    dlg.setWindowTitle("Pregled pre štampe – " + ("traka 80 mm" if format_ == "80mm" else "A4"))
    dlg.paintRequested.connect(lambda p: doc.print_(p))
    dlg.resize(900 if format_ == "a4" else 520, 900)
    dlg.exec()
