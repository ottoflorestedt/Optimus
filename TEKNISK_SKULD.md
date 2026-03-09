# Teknisk skuld – Föräldrakalkylator

> Analyserad: `kalkyl.py` och `app.py`
> Syfte: Lista konkreta städpunkter inför produktionssättning.
> Inga kodändringar har gjorts – detta är enbart en inventering.

---

## 1. Temporära debugfiler (ta bort)

| Fil | Problem |
|-----|---------|
| `debug_chart.py` | Fristående debugskript med hårdkodade testparametrar (Otto/Angelica, specifika datum). Ska inte följa med till produktion. |
| `debug_plan.csv` | CSV-fil genererad av en temporär `df.to_csv()`-rad i `app.py`. Filen finns kvar på disk trots att kodraden togs bort. |

---

## 2. Hårdkodade namn – "Otto" och "Angelica"

Namnen förekommer på **14+ ställen** i `kalkyl.py` och i `app.py`:

**`kalkyl.py`**
- Rad 95–96: `otto = berakna_skatt(115000)` / `angelica = berakna_skatt(40000)` – körs vid importtid.
- Rad 152–153, 291–301, 339–340, 386–408, 518–539: Ytterligare demoscenarier med Otto/Angelica.
- Rad 729–768: `Familjeplan`-testscenarier med `namn_a="Otto", namn_b="Angelica"`.

**`app.py`**
- Rad 222–254: "Ladda testdata"-knappen sätter `namn_a="Otto"`, `namn_b="Angelica"` med specifika löner, datum och lånebelopp kopplade till verkliga förhållanden.

**Åtgärd:** Generalisera till neutrala exempelnamn ("Förälder A", "Förälder B") eller flytta testdata till en separat konfigurationsfil utanför produktionskoden.

---

## 3. `kalkyl.py` – Sidoeffekter vid importtid

Hela demokörningen av `kalkyl.py` exekveras när modulen importeras. Det är därför `app.py` rad 2 innehåller:

```python
sys.argv = ["kalkyl", "demo"]  # Hack för att undertrycka interaktivt läge
```

Konkreta sidoeffekter som körs vid varje `import kalkyl`:
- **Steg 1–3** (rad 95–309): `berakna_skatt`, `berakna_fk_ersattning`, `berakna_foraldralon` anropas för Otto och Angelica + utskrift (undertryckt via `io.StringIO()`).
- **Steg 4** (rad 339–351): `berakna_ranteavdrag` med hårdkodade 90 000 kr.
- **Steg 5** (rad 385–429): `berakna_manadsekonomi`-scenarier.
- **Steg 6** (rad 518–539): `berakna_vecka`-testscenario.
- **Steg 7** (rad 728–769): `Familjeplan`-testscenarier med 20 veckors körning.

**Åtgärd:** Flytta all demokod bakom `if __name__ == "__main__":` så att `import kalkyl` är bieffektsfritt.

---

## 4. Obsoleta funktioner som inte används av `app.py`

### 4a. `berakna_manadsekonomi` (Steg 5, rad 362–382)
Beräknar månadsekonomi med `andel_ledig = fk_dagar / arbetsdagar`, en enklare modell än vad `app.py` använder. Funktionen anropas aldrig från `app.py`. Demovariablerna `ARBETSDAGAR_MÅN = 22`, `OTTO_FK_DAGAR = 10`, `ANGELICA_FK_DAGAR = 22` (rad 357–359) är hårdkodade och oanvända utanför demokörningen.

### 4b. `Familjeplan`-klassen (Steg 7, rad 546–721)
Komplett planeringsmotor med `lagg_till_vecka`, `dagar_kvar`, `sammanfatta`, `sammanfatta_per_ar`. Används inte av `app.py` (appen hanterar dagssaldon direkt via `plan_df`). Innehåller egna utskriftsmetoder (`sammanfatta_per_ar`) inklusive ränteavdrag, ROT/RUT och barnbidrag – funktionalitet som delvis dupliceras i Resultat-sidan.

Obs: `Familjeplan.__init__` defaultar till `sp_dagar_a=240` medan `app.py` använder `SP_TOTAL = 390`. Inkonsekvent.

### 4c. `interaktivt_lage()` (Steg 8, rad 776–870)
Terminal-CLI med `input()`-anrop och filexport. Exponeras aldrig från Streamlit-appen. Den globala `_INTERAKTIVT`-flaggan (rad 86–89) + `_sys_stdout_backup` gör modulen svår att importera rent.

### 4d. `berakna_grundavdrag` (rad 8–20)
Funktionen finns men anropas aldrig – varken av `berakna_skatt` eller någon annanstans. Skattefunktionen använder enbart tabell 31-uppslaget. Returnyckeln `"grundavdrag"` i `berakna_skatt` är alltid `0` (rad 68), vilket är vilseledande.

---

## 5. Beräkningsinkonsistenser

### 5a. `semestertillägg` saknas i `_netto_manad`
`berakna_vecka` (via `_berakna_foraldra_vecka`, rad 463–464) lägger till semestertillägg:
```python
semestertillagg = round(manadslon * 0.0043 * semester_dagar)
lon_inkomst    += semestertillagg
```
Månadsberäkningen `_netto_manad` i `app.py` (rad 650–686) saknar denna post. Veckovyn och månadsvyn ger därmed olika totaler för veckor med semesterdagar.

### 5b. `berakna_skatt` ignorerar `kyrkoavgift` i sitt returvärde
`kommunalskatt_mån`, `statlig_skatt_mån` m.fl. returneras alltid som `0` (rad 68–73). Enda användbara nycklar är `total_skatt/mån` och `nettolön/mån`. Resten är dekorativa nyckelnamn utan värde.

### 5c. Kyrkoavgift exponeras inte i UI
`kyrkoavgift`-parametern finns i alla kalkyl-funktioner men saknar widget i `app.py`. Alla beräkningar kör med `kyrkoavgift=0.0`. Antingen ska parametern exponeras eller tas bort konsekvent.

---

## 6. Arkitekturproblem

### 6a. Kolumnnamn i `plan_df` beror på föräldrarnas namn
```python
COL_FK_A = f"SGI-dagar {namn_a}"
```
Om användaren byter namn efter att ha genererat en plan bryts kolumnuppslagningen i `plan_df`. Kolumnnamnen borde vara konstanta (t.ex. `"fk_a"`, `"lg_a"`) och bara etiketteras med namn i visningsskedet.

### 6b. `_netto_manad` är en closure som fångar yttre scope
Funktionen (rad 650) fångar `veckor` och `edited_df` implicit från det omgivande `elif`-blocket. Det gör den omöjlig att testa isolerat och svår att följa. Bör refaktoreras till en ren funktion med explicita parametrar.

### 6c. O(n²) beräkningar för månadsdiagrammet
`_netto_manad` anropas för varje (år, månad)-kombination och itererar i sin tur över alla veckor. Inuti loopen anropas `berakna_skatt`, `berakna_fk_ersattning` och `berakna_foraldralon` med identiska parametrar för varje iteration. För en plan på 18 månader × 78 veckor = ~1 400 onödiga kalkylkörnin­gar. Dessa borde beräknas en gång utanför loopen.

### 6d. Dubbel beräkning av `fl_a`/`fl_b`
`berakna_foraldralon` anropas på rad 616–617 för att hämta `fl_a`/`fl_b`, och sedan igen inne i `_netto_manad` (rad 653) och i `chart_rows`-loopen via `berakna_vecka`. Samma resultat beräknas 3× per renderingscykel.

---

## 7. Hårdkodade gränsvärden

| Plats | Värde | Problem |
|-------|-------|---------|
| `kalkyl.py` rad 10 | `pbb = 58800` | Prisbasbelopp 2025 – behöver uppdateras varje år |
| `kalkyl.py` rad 25–33 | Skattetabell 31 | Täcker bara 38 000–120 000 kr, årsversion 2025. Extrapolation utanför intervallet är linjär och kan vara felaktig |
| `kalkyl.py` rad 118 | `sgi_tak = 592000` | SGI-taket 2025 (10 × PBB) – behöver uppdateras |
| `kalkyl.py` rad 119 | `fk_procent = 0.776` | FK-procentsatsen 2025 |
| `kalkyl.py` rad 463 | `0.0043` (semestertillägg) | Sammalöneregeln 0,43 % – hårdkodat utan kommentar om källa |
| `kalkyl.py` rad 459 | `180` (lägstanivå kr/dag) | Lägstanivån 2025 – behöver uppdateras |
| `app.py` rad 489 | `SP_TOTAL = 390` | Totalt antal SGI-dagar per förälder |
| `app.py` rad 490 | `LG_TOTAL = 90` | Totalt antal lägstanivådagar per förälder |
| `app.py` rad 28–29 | `[0, 0, 0, 0]` (4 lån) | Max 4 lån hårdkodat på tre ställen |
| `app.py` rad 692 | `barnbidrag 1250 kr/barn` i `Familjeplan` | Barnbidraget 2025 |

---

## 8. Saknad testning

- **Inga tester för `app.py`** – all Streamlit-logik är otesterad. `_netto_manad`, `generera_plan_veckor`, `berakna_rot_rut_avdrag` saknar enhetstester.
- **`Familjeplan`-klassen** har inga tester trots relativt komplex logik (`lagg_till_vecka`, `sammanfatta_per_ar`).
- **`test_kalkyl.py`** testar inte gränsfall för `berakna_skatt` vid löner utanför tabellintervallet (< 38 000 kr och > 120 000 kr).

---

## 9. Övriga städpunkter

- **`berakna_skatt` defaultparameter `kommunalskatt=0.2999`** – Stockholms kommunalskatt hårdkodad som default. Kan vilseleda om modulen används i annan kontext.
- **`KOLLEKTIVAVTAL["Ingen föräldralön"]`** – Tekniskt en sentinel-post i en dict avsedd för avtal. Bör hanteras som ett specialfall i koden snarare än som ett "avtal".
- **`berakna_foraldralon` med `dict`-ingång** – Stödjer ett odokumenterat "anpassat avtal"-format (`max_manader`/`krav_manader` utan `_kort`/`_lang`-suffix). Avviker från strukturen i `KOLLEKTIVAVTAL` och kan ge missvisande felmeddelanden.
- **`Familjeplan.sammanfatta_per_ar` beräknar `berakna_ranteavdrag` inuti loop** (rad 684) – Kallas med konstanta `rantor_ar`-värden; bör lyftas ut.
