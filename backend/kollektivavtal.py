"""
Kollektivavtalsdata för föräldralön.
PBB_2025 används för att beräkna lönegränsen (lönetaket) enligt formeln 10 × PBB / 12.
"""
from typing import Optional

PBB_2025 = 59200  # Prisbasbelopp 2025/2026

FL_FINANSFORBUNDET_MAX_DAGAR = 360  # Finansförbundets FL-tak i FK-dagar


def max_fl_man(avtal_namn: str, anstallningstid: Optional[int]) -> int:
    """
    Returnerar max antal FL-månader givet avtal och anställningstid.

    Returvärden:
      0   = ingen FL (ej kvalificerad eller "Ingen föräldralön")
      999 = obegränsat ("Ange föräldralön själv" eller AnpassatAvtal)
      2/3/6/12 = avtalsspecifikt tak

    None-anställningstid behandlas som >= 24 mån (generöst default).
    Finansförbundet: returnerar 0 (< 12 mån) eller 12 (>= 12 mån).
      Begränsningen räknas i dagar (FL_FINANSFORBUNDET_MAX_DAGAR = 360)
      i beräkningsmotorn, men rapporteras i månader i API-svaret.
    """
    mån = 9999 if anstallningstid is None else anstallningstid

    if avtal_namn in ("Ingen föräldralön", "Ingen foraldralon"):
        return 0
    if avtal_namn in (
        "Ange föräldralön själv",
        "Ange foraldralon sjalv",
        "Ange foraldraelon sjaelv",
        "AnpassatAvtal",
    ):
        return 999
    if avtal_namn == "Teknikavtalet":
        return 0 if mån < 12 else (2 if mån < 24 else 6)
    if avtal_namn == "Finansförbundet":
        # Flat 360 dagar (≈ 12 mån) – ingen tier; kräver >= 12 mån anstallning
        return 0 if mån < 12 else 12
    # Unionen, AB-avtalet, Statliga sektorn, Läkarförbundet, övriga
    return 0 if mån < 12 else (3 if mån < 24 else 6)

KOLLEKTIVAVTAL = {
    "Unionen": {
        "procent_under_tak":  0.10,
        "procent_over_tak":   0.90,
        "loenetak":           round(10 * PBB_2025 / 12),
        "max_manader_kort":   3,
        "max_manader_lang":   6,
        "krav_kort_manader":  9,
        "krav_lang_manader":  12,
        "fl_10_dagar":        False,  # Tillfällig FP ger timlöneavdrag, inte FL (Teknikavtalet mom 8)
        "tio_dagar_avdrag":   "timme",
    },
    "Teknikavtalet": {
        "procent_under_tak":  0.10,
        "procent_over_tak":   0.90,
        "loenetak":           round(10 * PBB_2025 / 12),
        "max_manader_kort":   2,
        "max_manader_lang":   6,
        "krav_kort_manader":  12,
        "krav_lang_manader":  24,
        "fl_10_dagar":        False,  # Tillfällig FP ger timlöneavdrag, inte FL (Teknikavtalet mom 8)
        "tio_dagar_avdrag":   "timme",
    },
    "AB-avtalet": {
        "procent_under_tak":  0.10,
        "procent_over_tak":   0.90,
        "loenetak":           round(10 * PBB_2025 / 12),
        "steg": [
            {"krav_manader": 12, "max_manader": 2},
            {"krav_manader": 24, "max_manader": 3},
            {"krav_manader": 36, "max_manader": 4},
            {"krav_manader": 48, "max_manader": 5},
            {"krav_manader": 60, "max_manader": 6},
        ],
        "fl_10_dagar":        False,  # Tillfällig FP hanteras separat från föräldralön
        "tio_dagar_avdrag":   "timme",
    },
    "Statliga sektorn": {
        "procent_under_tak":  0.10,
        "procent_over_tak":   0.90,
        "loenetak":           round(10 * PBB_2025 / 12),
        "max_manader_kort":   6,
        "max_manader_lang":   12,
        "krav_kort_manader":  12,
        "krav_lang_manader":  12,
        "fl_10_dagar":        False,  # Tillfällig FP hanteras separat från föräldralön
        "tio_dagar_avdrag":   "timme",
    },
    "Finansförbundet": {
        "procent_under_tak":  0.10,
        "procent_over_tak":   0.80,
        "loenetak":           round(10 * PBB_2025 / 12),
        "max_manader_kort":   0,    # Ingen kortperiod – gäller från dag 1
        "max_manader_lang":   12,   # 360 dagar per Finansförbundets avtal
        "krav_kort_manader":  9999, # Deaktiverad
        "krav_lang_manader":  1,    # Gäller från dag 1 som tillsvidareanställd
        "fl_10_dagar":        False,  # FL kräver hel kalenderdag FK på sjukpenningnivå
        "tio_dagar_avdrag":   "timme",
    },
    "Läkarförbundet": {
        "procent_under_tak":  0.10,
        "procent_over_tak":   0.90,
        "loenetak":           round(10 * PBB_2025 / 12),
        "max_manader_kort":   3,
        "max_manader_lang":   9,
        "krav_kort_manader":  6,
        "krav_lang_manader":  6,
        "fl_10_dagar":        False,  # Tillfällig FP ger inte föräldralön
        "tio_dagar_avdrag":   "timme",
    },
}
