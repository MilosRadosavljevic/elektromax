"""HTML dokumenti: isečak 80 mm, A4 račun/predračun, dnevni presek.

Ne zavisi od Qt-a: koristi ga i desktop kasa (štampa preko QTextDocument) i admin panel (štampa iz pregledača).
HTML je namerno jednostavan (tabele, osnovni stilovi) da bi ga QTextDocument ispravno prikazao.
"""
from html import escape as e

from fiskal import PORESKE_OZNAKE
from obracun import format_din

NASLOV = {
    "racun": "PROMET PRODAJA",
    "storno": "PROMET REFUNDACIJA",
    "predracun": "PREDRAČUN PRODAJA",
}
NACIN = {"gotovina": "Gotovina", "kartica": "Platna kartica", "prenos": "Prenos na račun"}


def din(x, valuta=False):
    return format_din(x or 0, valuta)


def _kol(x):
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:g}".replace(".", ",")


def proc(x):
    """6.82 -> '6,82%'"""
    return f"{float(x):g}".replace(".", ",") + "%"


def _vreme(v):
    # '2026-10-11 13:05:22' -> '11.10.2026. 13:05:22'
    return f"{v[8:10]}.{v[5:7]}.{v[0:4]}. {v[11:19]}" if v and len(v) >= 19 else (v or "")


def _datum(v):
    return f"{v[8:10]}.{v[5:7]}.{v[0:4]}." if v and len(v) >= 10 else ""


# ------------------------------------------------------------------ 80 mm
def html_racun_80(r: dict, firma: dict, kopija: bool = False) -> str:
    tip = r["tip"]
    naslov = ("KOPIJA " if kopija else "") + NASLOV[tip]
    nije_fiskalni = kopija or tip == "predracun" or r.get("fiskal_rezim") == "DEMO"
    red = []
    red.append(f"""<p align="center"><b>{e(firma['naziv'])}</b><br>{e(firma['adresa'])}, {e(firma['mesto'])}<br>
        PIB: {e(firma['pib'])} &nbsp; MB: {e(firma['mb'])}<br>Tel: {e(firma['telefon'])}</p>""")
    if r.get("fiskal_rezim") == "DEMO":
        red.append('<p align="center"><b>*** DEMO – NIJE FISKALNI RAČUN ***</b></p>')
    red.append(f'<p align="center"><b>{"=" * 6} {e(naslov)} {"=" * 6}</b></p>')
    red.append(f"""<table width="100%" cellspacing="0" cellpadding="0">
        <tr><td>Kasir:</td><td align="right">{e(r['kasir'])}</td></tr>
        <tr><td>Broj:</td><td align="right">{e(r['broj'])}</td></tr>
        <tr><td>Vreme:</td><td align="right">{_vreme(r['vreme'])}</td></tr>""")
    if r.get("referentni_broj"):
        red.append(f"<tr><td>Ref. dokument:</td><td align='right'>{e(r['referentni_broj'])}</td></tr>")
    if r.get("kupac"):
        red.append(f"<tr><td>Kupac:</td><td align='right'>{e(r['kupac']['naziv'])}</td></tr>")
        if r["kupac"].get("pib"):
            red.append(f"<tr><td>PIB kupca:</td><td align='right'>{e(r['kupac']['pib'])}</td></tr>")
    red.append("</table><hr>")
    red.append('<table width="100%" cellspacing="0" cellpadding="0">'
               '<tr><td><b>Naziv</b></td><td align="right"><b>Cena</b></td><td align="right"><b>Kol.</b></td>'
               '<td align="right"><b>Ukupno</b></td></tr>')
    for s in r["stavke"]:
        oznaka = PORESKE_OZNAKE.get(int(s["pdv_stopa"]), "")
        red.append(f'<tr><td colspan="4">{e(s["naziv"])} ({oznaka})</td></tr>'
                   f'<tr><td>{e(s["jedinica_mere"])}</td><td align="right">{din(s["cena"])}</td>'
                   f'<td align="right">{_kol(s["kolicina"])}</td><td align="right">{din(s["cena"] * s["kolicina"])}</td></tr>')
        if s["popust"]:
            red.append(f'<tr><td colspan="3">&nbsp; popust {proc(s["popust_proc"])}</td>'
                       f'<td align="right">-{din(s["popust"])}</td></tr>')
    red.append("</table><hr>")
    znak = "-" if tip == "storno" else ""
    red.append('<table width="100%" cellspacing="0" cellpadding="0">')
    if r["popust"]:
        red.append(f"<tr><td>Iznos bez popusta:</td><td align='right'>{din(r['bruto'])}</td></tr>"
                   f"<tr><td>Ukupan popust:</td><td align='right'>-{din(r['popust'])}</td></tr>")
    red.append(f"<tr><td><b><big>{'Ukupan iznos refundacije' if tip == 'storno' else 'Ukupan iznos'}:</big></b></td>"
               f"<td align='right'><b><big>{znak}{din(r['ukupno'])}</big></b></td></tr>")
    for p in r["placanja"]:
        red.append(f"<tr><td>{NACIN[p['nacin']]}:</td><td align='right'>{din(p['primljeno'] or p['iznos'])}</td></tr>")
        if p.get("kusur"):
            red.append(f"<tr><td>Povraćaj (kusur):</td><td align='right'>{din(p['kusur'])}</td></tr>")
    red.append("</table><hr>")
    red.append('<table width="100%" cellspacing="0" cellpadding="0"><tr><td><b>Oznaka</b></td><td><b>Ime</b></td>'
               '<td align="right"><b>Stopa</b></td><td align="right"><b>Porez</b></td></tr>')
    for stopa, v in sorted(r["pdv_po_stopama"].items(), reverse=True):
        red.append(f"<tr><td>{PORESKE_OZNAKE.get(int(stopa), '')}</td><td>PDV</td><td align='right'>{stopa}%</td>"
                   f"<td align='right'>{din(v['pdv'])}</td></tr>")
    red.append(f"<tr><td colspan='3'>Ukupan iznos poreza:</td><td align='right'>{din(r['pdv'])}</td></tr></table><hr>")
    if r.get("vazi_do"):
        red.append(f"<p>Predračun važi do: {_datum(r['vazi_do'])}</p>")
    if r.get("napomena"):
        red.append(f"<p>{e(r['napomena'])}</p>")
    if r.get("popust_razlog"):
        red.append(f"<p>Razlog popusta/storna: {e(r['popust_razlog'])}</p>")
    if nije_fiskalni:
        red.append('<p align="center"><b>OVO NIJE FISKALNI RAČUN</b></p>')
    if r.get("fiskal_broj"):
        red.append(f'<p align="center">PFR broj: {e(r["fiskal_broj"])}<br>PFR vreme: {_vreme((r.get("fiskal_vreme") or "").replace("T", " "))}</p>')
    red.append(f'<p align="center">{"=" * 8} KRAJ {e(NASLOV[tip].split()[0])}A {"=" * 8}<br>Hvala na poseti!</p>')
    return f'<html><body style="font-family:Consolas,\'Courier New\',monospace; font-size:8pt;">{"".join(red)}</body></html>'


def html_presek_80(p: dict, firma: dict) -> str:
    redovi = "".join(f"<tr><td>{NACIN.get(k, k)}</td><td align='right'>{din(v)}</td></tr>"
                     for k, v in p["po_nacinu"].items())
    kasiri = "".join(f"<tr><td>{e(k['ime'])} ({k['broj']})</td><td align='right'>{din(k['promet'])}</td></tr>"
                     for k in p["po_kasiru"])
    return f"""<html><body style="font-family:Consolas,'Courier New',monospace; font-size:8pt;">
    <p align="center"><b>{e(firma['naziv'])}</b><br>PIB: {e(firma['pib'])}</p>
    <p align="center"><b>DNEVNI PRESEK – {_datum(p['dan'])}</b><br>(interni izveštaj, nije fiskalni)</p><hr>
    <table width="100%" cellspacing="0" cellpadding="0">
      <tr><td>Broj računa:</td><td align="right">{p['broj_racuna']}</td></tr>
      <tr><td>Promet (bruto):</td><td align="right">{din(p['promet_bruto'])}</td></tr>
      <tr><td>Storna ({p['broj_storna']}):</td><td align="right">-{din(p['storna'])}</td></tr>
      <tr><td><b>Promet neto:</b></td><td align="right"><b>{din(p['promet_neto'])}</b></td></tr>
      <tr><td>Od toga PDV:</td><td align="right">{din(p['pdv'])}</td></tr>
      <tr><td>Dati popusti:</td><td align="right">{din(p['popusti'])}</td></tr>
    </table><hr><b>Po načinu plaćanja</b>
    <table width="100%" cellspacing="0" cellpadding="0">{redovi}</table><hr><b>Po kasiru</b>
    <table width="100%" cellspacing="0" cellpadding="0">{kasiri}</table><hr>
    <p>Predračuna: {p['broj_predracuna']} ({din(p['iznos_predracuna'])})</p></body></html>"""


# ------------------------------------------------------------------ A4
def html_a4(r: dict, firma: dict, kopija: bool = False) -> str:
    tip = r["tip"]
    naslov = {"racun": "RAČUN", "storno": "STORNO RAČUN", "predracun": "PREDRAČUN"}[tip]
    if kopija:
        naslov += " – KOPIJA"
    k = r.get("kupac") or {}
    kupac = (f"<b>{e(k.get('naziv', ''))}</b><br>{e(k.get('adresa', ''))}<br>{e(k.get('mesto', ''))}<br>"
             f"PIB: {e(k.get('pib', ''))} &nbsp; MB: {e(k.get('mb', ''))}") if k else "<i>Fizičko lice</i>"
    stavke = "".join(
        f"<tr><td>{i}</td><td>{e(s['sifra'])}</td><td>{e(s['naziv'])}</td><td align='center'>{e(s['jedinica_mere'])}</td>"
        f"<td align='right'>{_kol(s['kolicina'])}</td><td align='right'>{din(s['cena'])}</td>"
        f"<td align='right'>{proc(s['popust_proc'])}</td><td align='right'>{proc(s['pdv_stopa'])}</td>"
        f"<td align='right'>{din(s['ukupno'])}</td></tr>" for i, s in enumerate(r["stavke"], 1))
    pdv = "".join(f"<tr><td>PDV {st}%</td><td align='right'>{din(v['osnovica'])}</td><td align='right'>{din(v['pdv'])}</td>"
                  f"<td align='right'>{din(v['ukupno'])}</td></tr>" for st, v in sorted(r["pdv_po_stopama"].items(), reverse=True))
    rok = (f"<p><b>Predračun važi do: {_datum(r['vazi_do'])}</b> Uplatu izvršiti na tekući račun "
           f"<b>{e(firma['tekuci_racun'])}</b> ({e(firma['banka'])}), poziv na broj: <b>{e(r['broj'])}</b>.</p>"
           if tip == "predracun" else "")
    placanja = ", ".join(f"{NACIN[p['nacin']]} {din(p['iznos'], True)}" for p in r["placanja"])
    napomena_fiskal = ("<p><b>Ovo nije fiskalni račun.</b></p>" if tip == "predracun" or kopija
                       or r.get("fiskal_rezim") == "DEMO" else "")
    return f"""<html><body style="font-family:'Segoe UI',Arial; font-size:9.5pt;">
    <table width="100%" cellspacing="0" cellpadding="0"><tr>
      <td width="55%"><span style="font-size:18pt;"><b>ELEKTRO</b><b style="color:#c98f00;">MAX</b></span><br>
        <b>{e(firma['naziv'])}</b><br>{e(firma['adresa'])}, {e(firma['mesto'])}<br>
        PIB: {e(firma['pib'])} &nbsp; MB: {e(firma['mb'])}<br>Tekući račun: {e(firma['tekuci_racun'])}<br>
        Tel: {e(firma['telefon'])} &nbsp; {e(firma['email'])}</td>
      <td width="45%" align="right"><span style="font-size:20pt;"><b>{naslov}</b></span><br>
        Broj: <b>{e(r['broj'])}</b><br>Datum i vreme: {_vreme(r['vreme'])}<br>
        Mesto izdavanja: Smederevska Palanka<br>
        {('Referentni dokument: ' + e(r['referentni_broj']) + '<br>') if r.get('referentni_broj') else ''}
        {('Fiskalni broj: ' + e(r['fiskal_broj'])) if r.get('fiskal_broj') and tip != 'predracun' else ''}</td>
    </tr></table>
    <p></p>
    <table width="100%" cellspacing="0" cellpadding="6" style="background-color:#f3f1ec;">
      <tr><td><span style="color:#666;">KUPAC</span><br>{kupac}</td></tr></table>
    <p></p>
    <table width="100%" cellspacing="0" cellpadding="4" border="1" style="border-color:#bbb; border-style:solid;">
      <tr style="background-color:#14171c; color:white;"><th>R.br.</th><th>Šifra</th><th align="left">Naziv</th><th>JM</th>
        <th align="right">Kol.</th><th align="right">Cena sa PDV</th><th align="right">Rabat</th><th align="right">PDV</th>
        <th align="right">Iznos</th></tr>
      {stavke}
    </table>
    <p></p>
    <table width="100%" cellspacing="0" cellpadding="0"><tr>
      <td width="50%" valign="top">
        <table cellspacing="0" cellpadding="3" border="1" style="border-color:#bbb; border-style:solid;">
          <tr><th align="left">Rekapitulacija</th><th>Osnovica</th><th>PDV</th><th>Ukupno</th></tr>{pdv}</table>
      </td>
      <td width="50%" align="right" valign="top">
        <table cellspacing="0" cellpadding="3">
          <tr><td>Iznos bez popusta:</td><td align="right">{din(r['bruto'], True)}</td></tr>
          <tr><td>Popust:</td><td align="right">-{din(r['popust'], True)}</td></tr>
          <tr><td>Osnovica:</td><td align="right">{din(r['osnovica'], True)}</td></tr>
          <tr><td>PDV:</td><td align="right">{din(r['pdv'], True)}</td></tr>
          <tr><td><span style="font-size:13pt;"><b>ZA UPLATU:</b></span></td>
              <td align="right"><span style="font-size:13pt;"><b>{din(r['ukupno'], True)}</b></span></td></tr>
        </table></td></tr></table>
    {rok}
    {('<p>Način plaćanja: ' + placanja + '</p>') if placanja else ''}
    {('<p>Napomena: ' + e(r['napomena']) + '</p>') if r.get('napomena') else ''}
    {napomena_fiskal}
    <p>Obveznik je u sistemu PDV-a. Dokument je izdat elektronski i punovažan je bez pečata i potpisa.</p>
    <p></p><p></p>
    <table width="100%"><tr><td width="50%" align="center">______________________<br>Izdao: {e(r['kasir'])}</td>
      <td width="50%" align="center">______________________<br>Primio</td></tr></table>
    </body></html>"""
