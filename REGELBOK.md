# Regelbok – Föräldrakalkylator

## Syfte
Denna fil dokumenterar alla regler, parametrar och källor
som kalkylatorn förhåller sig till. Uppdatera filen när
regler ändras och notera datum och källa.

## Del 1 – Parametrar (ändras vanligtvis årligen)

### Prisbasbelopp (PBB)
- 2026: 59 200 kr
- Källa: SCB (publiceras oktober, gäller från januari)
- Påverkar: FK-lönetak, lägstanivå

### Föräldrapenning
- FK-procent: 77.6% av SGI
- Lönetak FK: 10 × PBB / 12 = 49 333 kr/mån (2026)
- Lägstanivå: 180 kr/dag
- Källa: SFB kap 12, Försäkringskassan

### Skatt
- Skattetabell: SKVFS 2024:19 (tabell 31, kolumn 1)
- Kommunalskatter: SKV 2026 (290 kommuner)
- Kyrkoavgifter: SKV 2026 (1267 församlingar)
- Källa: Skatteverket (publiceras november, gäller januari)

### ROT och RUT
- ROT-tak: 50 000 kr/person/år (30% av arbetskostnad)
- RUT-tak: 75 000 kr/person/år (50% av arbetskostnad)
- Kombinerat tak ROT+RUT: 75 000 kr/person/år
- Källa: Skatteverket

### Barnbidrag
- 1 250 kr/barn/månad
- Källa: Försäkringskassan

### Semestertillägg
- 0.43% per sparad semesterdag
- Källa: Semesterlagen + praxis

## Del 2 – Regler (ändras via lagstiftning eller praxis)

### SGI-skydd
- SGI skyddas automatiskt under föräldraledighet (barn 0-1 år)
- Efter barnets 1-årsdag: kräver minst 5 FK-dagar/vecka
- Gravid och går ner i arbetstid: skyddas de sista 6 månaderna
  om man jobbat stadigvarande 240 dagar innan förlossning
- Gå ner i arbetstid efter ledighet sänker SGI inför nästa barn
- Källa: SFB kap 25-26, Försäkringskassan

### Helgregler (ny regel 1 april 2025)
- FK på helg/röd dag kräver FK-dag i minst samma omfattning
  direkt före eller efter
- Gäller alla nivåer (sjukpenning, grundnivå, lägstanivå)
- Undantag: arbetssökande och heltidsstuderande
- Källa: Försäkringskassan, SFB 12 kap

### Löneavdrag vid föräldraledighet
- 1-5 arbetsdagar: avdrag per arbetsdag (månadslön / 21)
- Mer än 5 arbetsdagar: kalenderavdrag (månadslön × 12 / 365)
  inkl röda dagar och helger
- Gäller vid ledighet som sträcker sig över storhelger
- Källa: Praxis, kollektivavtal (varierar per bransch)

### Dubbeldagar
- Max 30 dagar per förälder (60 totalt)
- Måste tas ut under barnets första 15 månader
- Räknas från vardera förälders dagar
- Källa: SFB 12 kap, Försäkringskassan

### Dagars giltighet
- Dagar gäller till barnet fyller 12 år (eller slutar år 5)
- Max 96 sparade dagar efter barnets 4-årsdag (132 tvillingar)
- Källa: SFB 12 kap

### Föräldraledighetsperioder
- Max 3 perioder per förälder per kalenderår
- Källa: Föräldraledighetslagen 12§

### Reserverade dagar
- 90 dagar per förälder är reserverade och kan ej överlåtas
- Källa: SFB 12 kap

### Överlåtelse av dagar
- Max 45 dagar kan överlåtas till närstående (ej vårdnadshavare)
  t.ex. mor/farförälder – gäller från 1 juli 2024
- Källa: SFB 12 kap, lagändring 2024

### Semestergrundande föräldraledighet
- De första 120 dagarna av föräldraledighet är
  semesterlönegrundande (180 för ensamstående)
- Källa: Semesterlagen 17§

### FK-dagar innan förlossning
- Kan tas ut från 60 dagar innan beräknad förlossning
- 10-pappadagar vid barnets födelse – förfaller inom 60 dagar
- Källa: SFB 12 kap, Försäkringskassan

## Del 3 – Kollektivavtal

| Avtal | Bevakas hos | Förhandlas | Senast kontrollerad |
|-------|-------------|------------|---------------------|
| Finansförbundet | finansforbundet.se | ~vartannat år | 2026-03 |
| Teknikavtalet IF Metall | ifmetall.se | ~vartannat år | 2026-03 |
| AB-avtalet (SKR) | skr.se | ~vartannat år | 2026-03 |
| Läkarförbundet | slf.se | ~vartannat år | 2026-03 |

## Del 4 – Bevakningslista

| Källa | Vad bevakas | När ändras | Senast kollad |
|-------|-------------|------------|---------------|
| SCB | Prisbasbelopp (PBB) | Oktober | 2026-03 |
| Skatteverket | Skattetabell 31 | November | 2026-03 |
| Skatteverket | Kommunalskatter | November | 2026-03 |
| Skatteverket | Kyrkoavgifter | November | 2026-03 |
| Skatteverket | ROT/RUT-regler | Vid lagändring | 2026-03 |
| Försäkringskassan | Lägstanivå FK | Vid lagändring | 2026-03 |
| Försäkringskassan | SGI-regler | Vid lagändring | 2026-03 |
| Försäkringskassan | Helgregler | Vid lagändring | 2026-03 |
| Försäkringskassan | Barnbidrag | Vid lagändring | 2026-03 |
| Riksdagen | SFB (föräldrabalken) | Vid lagstiftning | 2026-03 |

## Del 5 – Ändringslogg

| Datum | Ändring | Källa | Påverkar |
|-------|---------|-------|----------|
| 2025-04-01 | Ny helgregel FK för dagar man ej jobbar | FK | Planering |
| 2024-07-01 | Överlåtelse till närstående (45 dagar) | SFB | Info |
| 2026-01-01 | PBB höjt till 59 200 kr | SCB | FK-beräkning |
| 2025-05-12 | ROT höjt till 50% (tillfälligt t.o.m. 31 dec 2025) | SKV | ROT-avdrag |
| 2026-01-01 | ROT återgår till 30%, tak 50 000 kr | SKV | ROT-avdrag |
