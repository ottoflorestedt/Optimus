from skattesatser import KOMMUNALSKATT_2026, KYRKOAVGIFT_2026
from kollektivavtal import KOLLEKTIVAVTAL, PBB_2025

# ============================================================
#  Föräldrakalkylator — Steg 1: Skatteberäkning
# ============================================================

# Skattetabell 31, kolumn 1 – 2025 (SKVFS 2024:19)
# Skatteavdrag (total_skatt/mån) i kr per månadslön
# OBS: Täcker 38 000–120 000 kr. Utanför intervallet används linjär extrapolation – uppdatera tabellen vid nytt år.
SKATTETABELL_31 = {
     38000:  6914,  39000:  7107,  40000:  7620,
     45000:  8957,  50000: 10294,  55000: 11631,
     60000: 12968,  65000: 14305,  70000: 16270,
     75000: 18397,  80000: 20524,  85000: 22651,
     90000: 24778,  95000: 26905, 100000: 29032,
    105000: 33411, 110000: 37790, 115000: 42578,
    120000: 47367,
}
_T31_KEYS = sorted(SKATTETABELL_31)


def _slå_upp_skatt(manadslon):
    """Slår upp total månadsskatt ur tabell 31 med linjär interpolation."""
    keys = _T31_KEYS
    if manadslon <= keys[0]:
        lo, hi = keys[0], keys[1]
        slope = (SKATTETABELL_31[hi] - SKATTETABELL_31[lo]) / (hi - lo)
        return SKATTETABELL_31[lo] + slope * (manadslon - lo)
    if manadslon >= keys[-1]:
        lo, hi = keys[-2], keys[-1]
        slope = (SKATTETABELL_31[hi] - SKATTETABELL_31[lo]) / (hi - lo)
        return SKATTETABELL_31[hi] + slope * (manadslon - hi)
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= manadslon <= hi:
            t = (manadslon - lo) / (hi - lo)
            return SKATTETABELL_31[lo] + t * (SKATTETABELL_31[hi] - SKATTETABELL_31[lo])


def berakna_skatt(manadslon, kommunalskatt=KOMMUNALSKATT_2026["Stockholm"] / 100, kyrkoavgift=0.0):
    """
    Beräknar nettolön per månad efter skatt (2025).
    Använder skattetabell 31, kolumn 1 (SKVFS 2024:19) med linjär interpolation.
    Kyrkoavgift läggs till utöver tabellvärdet om angiven.
    """
    if manadslon <= 0:
        return {"bruttolön": 0, "total_skatt/mån": 0, "nettolön/mån": 0, "effektiv_skattesats": 0.0}
    total_skatt_manad = _slå_upp_skatt(manadslon)
    total_skatt_manad = max(0, total_skatt_manad)
    if kyrkoavgift > 0:
        total_skatt_manad += manadslon * kyrkoavgift
    nettolön = manadslon - total_skatt_manad

    return {
        "bruttolön":           manadslon,
        "total_skatt/mån":     round(total_skatt_manad),
        "nettolön/mån":        round(nettolön),
        "effektiv_skattesats": round(total_skatt_manad / manadslon * 100, 2),
    }


# ============================================================
#  Steg 2: FK-ersättning (föräldrapenning)
# ============================================================

def berakna_fk_ersattning(manadslon, kommunalskatt=KOMMUNALSKATT_2026["Stockholm"] / 100, kyrkoavgift=0.0):
    """
    Beräknar FK-ersättning per dag på sjukpenningnivå.
    SGI = årslön (lön × 12), max 10 prisbasbelopp (592 000 kr/år).
    FK-ersättning = 77,6% av SGI per dag (matchar FK:s beräkningsmetod).
    """
    sgi_tak = 592000     # SGI-tak (10 × PBB 2025 = 10 × 59 200 kr), Försäkringskassan 2025
    fk_procent = 0.776   # FK-procentsats på sjukpenningnivå (77,6 %), Försäkringskassan 2025

    # SGI (sjukpenninggrundande inkomst) – utan 97 %-faktor per FK:s metod
    sgi = min(manadslon * 12, sgi_tak)

    # FK-ersättning brutto per dag
    fk_brutto_per_dag = sgi * fk_procent / 365

    # Skatt på FK (kommunalskatt + kyrka, ingen JSA på FK)
    skattesats_fk = kommunalskatt + kyrkoavgift

    # FK-ersättning netto per dag
    fk_netto_per_dag = fk_brutto_per_dag * (1 - skattesats_fk)

    # FK-ersättning netto per vecka (5 dagar)
    fk_netto_per_vecka = fk_netto_per_dag * 5

    # FK-ersättning netto per månad (approximation)
    fk_netto_per_manad = fk_netto_per_dag * 365 / 12

    return {
        "sgi/år":               round(sgi),
        "fk_brutto/dag":        round(fk_brutto_per_dag),
        "fk_netto/dag":         round(fk_netto_per_dag),
        "fk_netto/vecka":       round(fk_netto_per_vecka),
        "fk_netto/månad":       round(fk_netto_per_manad),
    }


# ============================================================
#  Steg 3: Kollektivavtal och föräldralön
# ============================================================


def berakna_foraldralon(manadslon, kollektivavtal, anstallningstid_manader):
    """
    Beräknar föräldralön per månad och hur många månader den gäller.
    kollektivavtal kan vara ett avtalsnamn (str) eller ett eget avtal (dict) med nycklarna:
        procent_under_tak (float)  – andel av lön under lönetak (t.ex. 0.10)
        procent_over_tak  (float)  – andel av lön över lönetak  (t.ex. 0.90)
        loenetak          (int)    – lönegräns i kr/mån          (t.ex. 49 333)
        max_manader       (int)    – max antal månader med föräldralön
        krav_manader      (int)    – minsta anställningstid i månader
        fast_belopp       (float)  – valfri fast ersättning kr/mån (åsidosätter procentberäkning)
    Returnerar {"foraldralon/mån": int, "max_månader": int}.
    Returnerar 0 kr om personen inte kvalificerar eller saknar kollektivavtal.
    """
    if kollektivavtal == "Ingen föräldralön":
        return {"foraldralon/mån": 0, "max_månader": 0}
    if isinstance(kollektivavtal, dict):
        fast_belopp = kollektivavtal.get("fast_belopp", 0)
        avtal = {
            "procent_under_tak": kollektivavtal["procent_under_tak"],
            "procent_over_tak":  kollektivavtal["procent_over_tak"],
            "loenetak":          kollektivavtal["loenetak"],
            "max_manader_lang":  kollektivavtal["max_manader"],
            "krav_lang_manader": kollektivavtal["krav_manader"],
            "max_manader_kort":  0,
            "krav_kort_manader": 9999,
        }
    elif kollektivavtal not in KOLLEKTIVAVTAL:
        print(f"Okänt kollektivavtal: {kollektivavtal}")
        return {"foraldralon/mån": 0, "max_månader": 0}
    else:
        fast_belopp = 0
        avtal = KOLLEKTIVAVTAL[kollektivavtal]

    # Hur många månader kvalificerar personen för?
    if "steg" in avtal:
        max_manader = 0
        for steg in reversed(avtal["steg"]):
            if anstallningstid_manader >= steg["krav_manader"]:
                max_manader = steg["max_manader"]
                break
    elif anstallningstid_manader >= avtal["krav_lang_manader"]:
        max_manader = avtal["max_manader_lang"]
    elif anstallningstid_manader >= avtal["krav_kort_manader"]:
        max_manader = avtal["max_manader_kort"]
    else:
        max_manader = 0

    if max_manader == 0:
        return {"foraldralon/mån": 0, "max_månader": 0}

    if fast_belopp > 0:
        return {"foraldralon/mån": round(fast_belopp), "max_månader": max_manader}

    # Beräkna föräldralön
    # Del under lönetak: procent_under_tak * min(lön, lönetak)
    # Del över lönetak:  procent_over_tak  * max(lön - lönetak, 0)
    lon_under_tak = min(manadslon, avtal["loenetak"])
    lon_over_tak  = max(manadslon - avtal["loenetak"], 0)

    foraldralon = (
        lon_under_tak * avtal["procent_under_tak"] +
        lon_over_tak  * avtal["procent_over_tak"]
    )

    return {
        "foraldralon/mån": round(foraldralon),
        "max_månader":     max_manader,
    }


# ============================================================
#  Steg 4: Ränteavdrag
# ============================================================

def berakna_ranteavdrag(rantor_ar):
    """
    Beräknar skatteminskning via ränteavdrag.
    30% avdrag på räntor upp till 100 000 kr/år,
    21% på räntor däröver.
    """
    tak = 100000
    if rantor_ar <= tak:
        avdrag_ar = rantor_ar * 0.30
    else:
        avdrag_ar = tak * 0.30 + (rantor_ar - tak) * 0.21

    return {
        "räntor/år":            round(rantor_ar),
        "skatteminskning/år":   round(avdrag_ar),
        "skatteminskning/mån":  round(avdrag_ar / 12),
    }


# ============================================================
#  Steg 5: Veckoberäkning med valfria dagtyper
# ============================================================

def _berakna_foraldra_vecka(manadslon, kommunalskatt, kollektivavtal, anstallningstid,
                             sp_dagar, lg_dagar, semester_dagar, arbets_dagar,
                             far_foraldralon, kyrkoavgift=0.0):
    """Beräknar en veckas ekonomiskt utfall för en förälder.
    sp_dagar kan vara 0-7; dag 6-7 är lördag/söndag med FK-ersättning men inga lönedagar.
    """
    if sp_dagar > 7:
        raise ValueError(f"SP-dagar ({sp_dagar}) kan inte överstiga 7 per vecka.")
    if lg_dagar > 7:
        raise ValueError(f"LG-dagar ({lg_dagar}) kan inte överstiga 7 per vecka.")
    sp_vardagar = min(sp_dagar, 5)
    lg_vardagar = min(lg_dagar, 5)
    # Begränsa så att totalt inte överstiger 5 vardagar
    overskott = max(0, sp_vardagar + lg_vardagar + semester_dagar + arbets_dagar - 5)
    arbets_dagar = max(0, arbets_dagar - overskott)

    skatt = berakna_skatt(manadslon, kommunalskatt, kyrkoavgift)
    fk    = berakna_fk_ersattning(manadslon, kommunalskatt, kyrkoavgift)
    fl    = berakna_foraldralon(manadslon, kollektivavtal, anstallningstid)

    nettodagslon    = skatt["nettolön/mån"] * 12 / 260
    fk_dag          = fk["fk_netto/dag"]
    lg_netto_dag    = 180 * (1 - kommunalskatt - kyrkoavgift)  # Lägstanivå FK = 180 kr/dag, Försäkringskassan 2025
    foraldralon_dag = (fl["foraldralon/mån"] * 12 / 260) if (far_foraldralon and fl["max_månader"] > 0) else 0

    lon_inkomst     = round(nettodagslon * (arbets_dagar + semester_dagar))
    semestertillagg = round(manadslon * 0.0043 * semester_dagar)  # Sammalöneregeln: 0,43 % av månadslon per semesterdag (Semesterlagen 7 §)
    lon_inkomst    += semestertillagg
    fk_inkomst      = round(fk_dag * sp_dagar + lg_netto_dag * lg_dagar)
    fl_inkomst      = round(foraldralon_dag * min(sp_dagar, 5))

    # Skatt: brutto minus netto per komponent (föräldralön behandlas som netto i nuläget)
    bruttodag_lon = manadslon * 12 / 260
    skatt_lon = (bruttodag_lon - nettodagslon) * (arbets_dagar + semester_dagar)
    skatt_fk  = (fk["fk_brutto/dag"] - fk_dag) * sp_dagar + 180 * (kommunalskatt + kyrkoavgift) * lg_dagar

    return {
        "nettoinkomst":      lon_inkomst + fk_inkomst + fl_inkomst,
        "varav_fk":          fk_inkomst,
        "varav_lon":         lon_inkomst,
        "varav_foraldralon": fl_inkomst,
        "skatt":             round(skatt_lon + skatt_fk),
    }


def berakna_vecka(
    manadslon_a, kommunalskatt_a, kollektivavtal_a, anstallningstid_a,
    sp_dagar_a, lg_dagar_a, semester_dagar_a, arbets_dagar_a, foraldralon_a,
    manadslon_b, kommunalskatt_b, kollektivavtal_b, anstallningstid_b,
    sp_dagar_b, lg_dagar_b, semester_dagar_b, arbets_dagar_b, foraldralon_b,
    kyrkoavgift_a=0.0, kyrkoavgift_b=0.0,
):
    """
    Beräknar en veckas ekonomiska utfall för två föräldrar.
    SP-dagar per förälder kan vara 0-7; dag 6-7 är lördag/söndag med FK-ersättning.
    LG, semester och arbete begränsas till max 5 vardagar totalt per förälder.
    """
    a = _berakna_foraldra_vecka(
        manadslon_a, kommunalskatt_a, kollektivavtal_a, anstallningstid_a,
        sp_dagar_a, lg_dagar_a, semester_dagar_a, arbets_dagar_a, foraldralon_a, kyrkoavgift_a)
    b = _berakna_foraldra_vecka(
        manadslon_b, kommunalskatt_b, kollektivavtal_b, anstallningstid_b,
        sp_dagar_b, lg_dagar_b, semester_dagar_b, arbets_dagar_b, foraldralon_b, kyrkoavgift_b)
    return {
        "nettoinkomst_a":      a["nettoinkomst"],
        "nettoinkomst_b":      b["nettoinkomst"],
        "varav_fk_a":          a["varav_fk"],
        "varav_fk_b":          b["varav_fk"],
        "varav_lon_a":         a["varav_lon"],
        "varav_lon_b":         b["varav_lon"],
        "varav_foraldralon_a": a["varav_foraldralon"],
        "varav_foraldralon_b": b["varav_foraldralon"],
        "skatt_a":             a["skatt"],
        "skatt_b":             b["skatt"],
    }


if __name__ == "__main__":
    # ── Steg 1: Skatteberäkning ──────────────────────────────
    fa = berakna_skatt(manadslon=115000)
    fb = berakna_skatt(manadslon=40000)
    print("=" * 45)
    print(f"{'':25} {'FÖRÄLDER A':>10}  {'FÖRÄLDER B':>10}")
    print("=" * 45)
    for nyckel in fa:
        enhet = "%" if "sats" in nyckel else "kr"
        print(f"{nyckel:25} {fa[nyckel]:>7} {enhet}  {fb[nyckel]:>7} {enhet}")
    print("=" * 45)

    # ── Steg 2: FK-ersättning ────────────────────────────────
    fa_fk = berakna_fk_ersattning(manadslon=115000)
    fb_fk = berakna_fk_ersattning(manadslon=40000)
    print()
    print("=" * 45)
    print(f"{'FK-ERSÄTTNING':25} {'FÖRÄLDER A':>10}  {'FÖRÄLDER B':>10}")
    print("=" * 45)
    for nyckel in fa_fk:
        print(f"{nyckel:25} {fa_fk[nyckel]:>7} kr  {fb_fk[nyckel]:>7} kr")
    print("=" * 45)

    # ── Steg 3: Föräldralön ──────────────────────────────────
    fa_fl = berakna_foraldralon(manadslon=115000, kollektivavtal="Finansförbundet",
                                anstallningstid_manader=36)
    fb_fl = berakna_foraldralon(manadslon=40000, kollektivavtal="Ingen föräldralön",
                                anstallningstid_manader=24)
    print()
    print("=" * 45)
    print(f"{'FÖRÄLDRALÖN':25} {'FÖRÄLDER A':>10}  {'FÖRÄLDER B':>10}")
    print("=" * 45)
    print(f"{'foraldralon/mån':25} {fa_fl['foraldralon/mån']:>7} kr  {fb_fl['foraldralon/mån']:>7} kr")
    print(f"{'max_månader':25} {fa_fl['max_månader']:>7} mån {fb_fl['max_månader']:>7} mån")
    print("=" * 45)

    # ── Steg 4: Ränteavdrag ──────────────────────────────────
    fa_ra = berakna_ranteavdrag(rantor_ar=90000)
    fb_ra = berakna_ranteavdrag(rantor_ar=90000)
    print()
    print("=" * 45)
    print(f"{'RÄNTEAVDRAG':25} {'FÖRÄLDER A':>10}  {'FÖRÄLDER B':>10}")
    print("=" * 45)
    for nyckel in fa_ra:
        print(f"{nyckel:25} {fa_ra[nyckel]:>7} kr  {fb_ra[nyckel]:>7} kr")
    print("=" * 45)

    # ── Steg 5: Veckoberäkning ───────────────────────────────
    vecka = berakna_vecka(
        manadslon_a=115000, kommunalskatt_a=0.2999, kollektivavtal_a="Finansförbundet",
        anstallningstid_a=36, sp_dagar_a=5, lg_dagar_a=0, semester_dagar_a=0,
        arbets_dagar_a=0, foraldralon_a=True,
        manadslon_b=40000, kommunalskatt_b=0.2999, kollektivavtal_b="Ingen föräldralön",
        anstallningstid_b=24, sp_dagar_b=3, lg_dagar_b=0, semester_dagar_b=0,
        arbets_dagar_b=2, foraldralon_b=False,
    )
    print()
    print("=" * 55)
    print(f"{'VECKOBERÄKNING':25} {'FÖRÄLDER A':>10}  {'FÖRÄLDER B':>10}")
    print(f"{'':25} {'(5 SP)':>10}  {'(3 SP+2 arb)':>10}")
    print("=" * 55)
    print(f"{'nettoinkomst/vecka':25} {vecka['nettoinkomst_a']:>7} kr  {vecka['nettoinkomst_b']:>7} kr")
    print(f"{'  varav lön/semester':25} {vecka['varav_lon_a']:>7} kr  {vecka['varav_lon_b']:>7} kr")
    print(f"{'  varav FK':25} {vecka['varav_fk_a']:>7} kr  {vecka['varav_fk_b']:>7} kr")
    print(f"{'  varav föräldralön':25} {vecka['varav_foraldralon_a']:>7} kr  {vecka['varav_foraldralon_b']:>7} kr")
    print("-" * 55)
    print(f"{'hushåll totalt/vecka':25} {vecka['nettoinkomst_a'] + vecka['nettoinkomst_b']:>7} kr")
    print("=" * 55)

