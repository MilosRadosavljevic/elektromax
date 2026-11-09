# Fiskalizacija – plan povezivanja kase

> Stanje: kasa radi u **DEMO režimu**. Svaki račun nosi oznaku „NIJE FISKALNI RAČUN“ i **ne sme se koristiti
> za stvarnu prodaju**, dok se ne poveže sa odobrenim fiskalnim rešenjem.
> Podaci u ovom dokumentu su prikupljeni 11.10.2026. Pre implementacije obavezno proveriti važeći
> tehnički vodič Poreske uprave i uslove izabranog dobavljača.

## 1. Kako fiskalizacija radi u Srbiji (eFiskalizacija)

| Pojam | Značenje |
|---|---|
| **ESIR** | Elektronski sistem za izdavanje računa – program kase. Mora biti **odobren** od Poreske uprave (PU). |
| **L-PFR / V-PFR** | Procesor fiskalnih računa – lokalni (uređaj/softver u radnji) ili virtuelni (u oblaku PU). Potpisuje račun. |
| **BE** | Bezbednosni element (kartica/sertifikat) koji PU izdaje obvezniku; otključava se PIN-om (PAK). |
| **Fiskalni račun** | Dobija broj od PFR-a, vreme PFR-a i **QR kod** za proveru na portalu PU – QR mora biti odštampan. |

Vrste računa (InvoiceType): **Normal** (promet), **ProForma** (predračun), **Copy** (kopija), **Training** (obuka),
**Advance** (avans). Vrste transakcije: **Sale** (prodaja) i **Refund** (refundacija).
Na isečku se to vidi kao „PROMET PRODAJA“, „PROMET REFUNDACIJA“, „PREDRAČUN PRODAJA“, „KOPIJA …“.
Naš demo isečak već prati ovaj raspored.

## 2. Dve opcije

### A) Povezivanje preko već odobrenog ESIR servisa – **preporuka**
Naša kasa ostaje kakva jeste (artikli, stanje, popusti, nabavka, analitika), a za svaki račun pozove REST API
odobrenog ESIR-a. Taj servis komunicira sa PFR-om i vraća fiskalni broj, QR kod i tekst žurnala.

- Bez sopstvene sertifikacije, brzo puštanje u rad.
- Primeri servisa sa javnim API-jem: **Otkucaj** (`https://otkucaj.com/en/api-docs`), **FiskalAPI**
  (`https://fiskalapi.rs/en/`). Cene i ugovorne uslove treba proveriti direktno kod njih.
- Primer (Otkucaj, javna dokumentacija): `POST /api/v1/invoices` sa `invoiceType`, `transactionType`,
  `items[]` (`name`, `quantity`, `unitPrice`, `label`), `payments[]` (`Cash`, `Card`, `WireTransfer`…), `buyerId`
  (`10:PIB` za firme); odgovor sadrži `pfr.invoiceNumber`, `sdcDateTime`, `verificationUrl`, `verificationQRCode`
  i `journal`. Postoji **sandbox** (nefiskalni računi) za testiranje i `Idempotency-Key` protiv duplih računa.

### B) Sopstveni sertifikovani ESIR
Naša kasa direktno priča sa L-PFR/V-PFR-om. Traži usklađivanje sa tehničkim vodičem PU (verzije se menjaju,
poslednja koju smo našli je 1.17), testiranje u sandbox-u PU i postupak odobravanja. Ima smisla samo ako se
softver prodaje većem broju radnji.

## 3. Šta je u kodu već pripremljeno

| Gde | Šta |
|---|---|
| `fiskal.py` | Adapter: `DemoFiskal.fiskalizuj(racun, stavke, placanja, referentni)` → vraća `fiskal_broj`, `fiskal_vreme`, `fiskal_url`, sirov odgovor. Izbor adaptera: promenljiva `ELEKTROMAX_FISKAL`. |
| `fiskal.pripremi_zahtev()` | Već pravi zahtev u obliku ESIR API-ja (invoiceType, transactionType, items, payments, buyerId, referentni dokument za refundaciju). |
| `racuni` tabela | Kolone `fiskal_rezim`, `fiskal_broj`, `fiskal_vreme`, `fiskal_url`, `fiskal_odgovor`. |
| Mapiranje | račun → Normal/Sale · storno → Normal/Refund (+ referentni dokument) · predračun → ProForma/Sale · kopija → Copy |
| Plaćanja | gotovina → Cash · kartica → Card · prenos → WireTransfer |
| Poreske oznake | `PORESKE_OZNAKE = {20: "Ђ", 10: "Е", 0: "Г"}` – **proveriti** u vodiču / `GET /tax-labels` servisa. |

## 4. Šta treba uraditi pri povezivanju (opcija A)

1. **Nova klasa** `EsirApiFiskal` u `fiskal.py` (HTTP poziv, API ključ iz okruženja – nikad u kodu kase).
2. **Redosled**: fiskalizacija mora uspeti **pre** nego što se račun smatra izdatim. Ako PFR odbije ili nije dostupan,
   transakcija se poništava i kasir dobija jasnu poruku (sada se upis i fiskalizacija rade u istoj transakciji – zadržati).
3. **Idempotentnost**: kao `Idempotency-Key` slati broj našeg računa (R-…), da ponovljen zahtev ne napravi dva računa.
4. **QR kod i žurnal na isečku**: štampati tekst žurnala koji vrati PFR i QR (`verificationQRCode`) – zameniti
   DEMO zaglavlje u `dokumenti.html_racun_80`.
5. **Refundacija (storno)**: servis traži **identifikaciju kupca** (`buyerId`) za svaku refundaciju i
   referentni fiskalni broj originala. → Dodati polje „Identifikacija kupca“ u dijalog storna na kasi
   (za fizička lica npr. broj lične karte, za firme PIB) i kolonu u tabeli `racuni`.
6. **Kopija**: „Kopija 80 mm“ na kasi treba da ide kroz PFR kao `Copy` (sada se štampa lokalno sa oznakom
   „OVO NIJE FISKALNI RAČUN“).
7. **Predračun**: štampati kao ProForma kroz PFR ako ga kupac traži sa fiskalnim brojem; A4 predračun za uplatu
   može ostati naš dokument.
8. **Avans** (ako radnja uzima avanse od firmi): nova vrsta dokumenta – trenutno ne postoji u kasi.
9. **Testiranje** u sandbox okruženju servisa: prodaja, popust, kombinovano plaćanje, delimičan i ceo storno,
   kopija, predračun → račun, pad mreže usred naplate.
10. **Dnevni presek** uporediti sa izveštajem servisa (`/reports/daily`) – moraju se slagati.

## 5. Pitanja za vlasnika i knjigovođu

- Koju fiskalnu kasu / ESIR radnja **trenutno** koristi i do kada važi ugovor? (Naša kasa bi je zamenila.)
- Da li firma već ima **bezbednosni element (BE)** i koji PFR koristi (L-PFR ili V-PFR)?
- Da li se izdaju **avansni računi**?
- Koliko kasa (računara) radi istovremeno u radnji?
- Ko je kontakt kod knjigovođe za usaglašavanje dnevnih preseka i PDV evidencije?

## 6. Bez fiskalizacije se ne prodaje

Dok se ne završe koraci iz tačke 4, kasa sme da služi samo za **demo, obuku i interne evidencije**
(stanje, nabavka, analitika). Svaki stvarni promet mora da prođe kroz postojeću fiskalnu kasu radnje.
