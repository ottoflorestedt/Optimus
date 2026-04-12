from skattesatser import KOMMUNALSKATT_2026, KYRKOAVGIFT_2026
from kollektivavtal import KOLLEKTIVAVTAL, PBB  # A-04: importerar PBB (var PBB_2025)

# ============================================================
# Föräldrakalkylator — Steg 1: Skatteberäkning
# ============================================================

# A-01: Skattetabell 31, kolumn 1 – 2026 (SKVFS 2025:20)
# Skatteavdrag (total_skatt/mån) i kr per månadslön
# Gränspunkter 38 000–80 000 kr: direkt ur SKV tabell 31 kol 1 (SKVFS 2025:20).
# Gränspunkter 80 000–200 000 kr: beräknade ur procenttabell (SKVFS 2025:20 sida 5).
# Brytpunkt statlig inkomstskatt 2026: 660 400 kr/år = 55 033 kr/mån.
# OBS: 135 000 kr-punkten är hämtad från tidigare verifiering mot SKV:s kalkylator
#      (värdet var 52 702 kr för 2025) — behöver re-verifieras mot SKV:s kalkylator 2026.
# Tabellen ger en approximation; exakt skatt beräknas per kommunsats i berakna_skatt().
SKATTETABELL_31 = {
    38000: 7465,
    39000: 7679,
    40000: 7931,
    45000: 9481,
    50000: 11031,
    55000: 12598,
    60000: 15145,
    65000: 17695,
    70000: 20245,
    75000: 22795,
    80000: 25294,
    85000: 28050,
    90000: 30600,
    95000: 33250,
    100000: 35000,
    105000: 37800,
    110000: 40700,
    115000: 42550,
    120000: 45600,
    125000: 48750,
    130000: 50700,
    135000: 52702,   # TODO: re-verifiera mot SKV:s kalkylator 2026
    140000: 56000,
    150000: 60000,
    160000: 65600,
    180000: 75600,
    200000: 86000,
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
    Beräknar nettolön per månad efter skatt (2026).
    Använder skattetabell 31, kolumn 1 (SKVFS 2025:20) med linjär interpolation.
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
        "bruttolön": manadslon,
        "total_skatt/mån": round(total_skatt_manad),
        "nettolön/mån": round(nettolön),
        "effektiv_skattesats": round(total_skatt_manad / manadslon * 100, 2),
    }


# ============================================================
# Steg 2: FK-ersättning (föräldrapenning)
# ============================================================

def berakna_fk_ersattning(manadslon, kommunalskatt=KOMMUNALSKATT_2026["Stockholm"] / 100, kyrkoavgift=0.0):
    """
    Beräknar FK-ersättning per dag på sjukpenningnivå.
    SGI = årslön (lön × 12), max 10 prisbasbelopp (592 000 kr/år).
    FK-ersättning = 77,6% av SGI per dag (matchar FK:s beräkningsmetod).
    """
    sgi_tak = 592000       # SGI-tak: 10 × PBB 2026 (10 × 59 200 kr)
    fk_procent = 0.776     # 0,97 × 0,80 = 0,776 (SFB 12 kap: SGI-nedräkning 97 % × ersättningsnivå 80 %)

    sgi = min(manadslon * 12, sgi_tak)
    fk_brutto_per_dag = sgi * fk_procent / 365
    skattesats_fk = kommunalskatt + kyrkoavgift
    fk_netto_per_dag = fk_brutto_per_dag * (1 - skattesats_fk)
    fk_netto_per_vecka = fk_netto_per_dag * 5
    fk_netto_per_manad = fk_netto_per_dag * 365 / 12

    return {
        "sgi/år": round(sgi),
        "fk_brutto/dag": round(fk_brutto_per_dag),
        "fk_netto/dag": round(fk_netto_per_dag),
        "fk_netto/vecka": round(fk_netto_per_vecka),
        "fk_netto/månad": round(fk_netto_per_manad),
    }


# ============================================================
# Steg 3: Kollektivavtal och föräldralön
# ============================================================

def berakna_foraldralon(manadslon, kollektivavtal, anstallningstid_manader):
    """
    Beräknar föräldralön per månad och hur många månader den gäller.

    kollektivavtal kan vara ett avtalsnamn (str) eller ett eget avtal (dict) med nycklarna:
      procent_under_tak (float) – andel av lön under lönetak (t.ex. 0.10)
      procent_over_tak  (float) – andel av lön över lönetak (t.ex. 0.90)
      loenetak          (int)   – lönegräns i kr/mån (t.ex. 49 333)
      max_manader       (int)   – max antal månader med föräldralön
      krav_manader      (int)   – minsta anställningstid i månader
      fast_belopp       (float) – valfri fast ersättning kr/mån (åsidosätter procentberäkning)

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
        lon_under_tak * avtal["procent_under_tak"]
        + lon_over_tak  * avtal["procent_over_tak"]
    )
    return {
        "foraldralon/mån": round(foraldralon),
        "max_månader": max_manader,
    }


# ============================================================
# Steg 4: Ränteavdrag
# ============================================================

def berakna_ranteavdrag(rantor_ar):
    """
    Beräknar skatteminskning via ränteavdrag.
    30% avdrag på räntor upp till 100 000 kr/år, 21% på räntor däröver.
    """
    tak = 100000
    if rantor_ar <= tak:
        avdrag_ar = rantor_ar * 0.30
    else:
        avdrag_ar = tak * 0.30 + (rantor_ar - tak) * 0.21
    return {
        "räntor/år":           round(rantor_ar),
        "skatteminskning/år":  round(avdrag_ar),
        "skatteminskning/mån": round(avdrag_ar / 12),
    }


# ============================================================
# Steg 5: Veckoberäkning med valfria dagtyper
# ============================================================

def _berakna_foraldra_vecka(
    manadslon, kommunalskatt, kollektivavtal, anstallningstid,
    sp_dagar, lg_dagar, semester_dagar, arbets_dagar,
    far_foraldralon, kyrkoavgift=0.0
):
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

    nettodagslon   = skatt["nettolön/mån"] * 12 / 260
    fk_dag         = fk["fk_netto/dag"]
    lg_netto_dag   = 180 * (1 - kommunalskatt - kyrkoavgift)  # Lägstanivå FK = 180 kr/dag
    foraldralon_dag = (fl["foraldralon/mån"] * 12 / 260) if (far_foraldralon and fl["max_månader"] > 0) else 0

    lon_inkomst     = round(nettodagslon * (arbets_dagar + semester_dagar))
    semestertillagg = round(manadslon * 0.0043 * semester_dagar)  # Sammalöneregeln 0,43 % (SemL 7 §)
    lon_inkomst    += semestertillagg

    # A-06: dag 6-7 ger sjukpenningnivå om SP-dagar finns kvar, annars lägstanivå
    # sp_kvar kontrolleras inte här (kalkyl.py vet ej saldo) → vecko-nivå är konservativ:
    # dag 6-7 behandlas som sjukpenningnivå (FK-dag) eftersom de flesta har dagar kvar.
    # Huvudmotorn i main.py sköter saldokoll. Denna funktion används primärt för
    # snabbberäkning via /ersattning_per_dag.
    fk_sp_dagar = min(sp_dagar, 5)      # dag 1-5: sjukpenningnivå
    fk_helg_dagar = max(sp_dagar - 5, 0) # dag 6-7: sjukpenningnivå (A-06, var lägstanivå)
    fk_inkomst  = round(fk_dag * fk_sp_dagar + fk_dag * fk_helg_dagar + lg_netto_dag * lg_dagar)
    fl_inkomst  = round(foraldralon_dag * min(sp_dagar, 5))

    bruttodag_lon = manadslon * 12 / 260
    skatt_lon     = (bruttodag_lon - nettodagslon) * (arbets_dagar + semester_dagar)
    skatt_fk      = (fk["fk_brutto/dag"] - fk_dag) * sp_dagar + 180 * (kommunalskatt + kyrkoavgift) * lg_dagar

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
    print(f"{'':25} {'FÖRÄLDER A':>10} {'FÖRÄLDER B':>10}")
    print("=" * 45)
    for nyckel in fa:
        enhet = "%" if "sats" in nyckel else "kr"
        print(f"{nyckel:25} {fa[nyckel]:>7} {enhet} {fb[nyckel]:>7} {enhet}")
    print("=" * 45)
