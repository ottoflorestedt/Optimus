"""
Kollektivavtalsdata för föräldralön.

Ändringslogg:
  A-02: Unionen krav_kort_manader 9 → 12 (avtalet kräver 12 mån sammanhängande)
  A-03: Finansförbundet max_fl_man() – ta bort 12-mån-krav (gäller från dag 1)
  A-04: PBB_2025 → PBB (värdet var korrekt 59 200 kr men namnet vilseledande)
  D-01: max_fl_man() för Finansförbundet matchar nu KOLLEKTIVAVTAL-dicten (krav_lang_manader=1)
"""

from typing import Optional

# A-04: Prisbasbelopp 2026 (SCB/Regeringen) — var felaktigt namngivet PBB_2025
PBB = 59200  # Prisbasbelopp 2026

# Bakåtkompatibelt alias så att kalkyl.py-importet (from kollektivavtal import PBB_2025) inte kraschar
# innan kalkyl.py uppdateras — ta bort när alla imports är uppdaterade
PBB_2025 = PBB

FL_FINANSFORBUNDET_MAX_DAGAR = 360  # Finansförbundets FL-tak i FK-dagar


def max_fl_man(avtal_namn: str, anstallningstid: Optional[int]) -> int:
    """
    Returnerar max antal FL-månader givet avtal och anställningstid.

    Returvärden:
      0   = ingen FL (ej kvalificerad eller "Ingen föräldralön")
      999 = obegränsat ("Ange föräldralön själv" eller AnpassatAvtal)
      2/3/6/12 = avtalsspecifikt tak

    None-anställningstid behandlas som >= 24 mån (generöst default).

    Finansförbundet: gäller från dag 1 som tillsvidareanställd (A-03).
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

    if avtal_namn in ("Teknikavtalet", "Innovationsföretagen"):
        # Båda avtalen: 0 mån vid <12 mån anst, 2 mån vid 12-23 mån, 6 mån vid 24+ mån
        return 0 if mån < 12 else (2 if mån < 24 else 6)

    if avtal_namn == "Finansförbundet":
        # A-03 + D-01: Gäller från dag 1 som tillsvidareanställd – ingen kvalificeringstid.
        # Matchar KOLLEKTIVAVTAL["Finansförbundet"]["krav_lang_manader"] = 1.
        # (Tidigare felaktigt: return 0 if mån < 12 else 12)
        return 0 if mån < 1 else 12

    if avtal_namn in ("Byggföretagen (tjänstemän)",):
        return 0 if mån < 12 else 6

    if avtal_namn in ("Svensk Handel (tjänstemän)", "Almega IT/konsult", "Stål och metall (tjänstemän)"):
        return 0 if mån < 12 else (2 if mån < 24 else 6)

    if avtal_namn in ("Vårdförbundet (region)",):
        # Steg-modell identisk med AB-avtalet
        if mån < 12: return 0
        if mån < 24: return 2
        if mån < 36: return 3
        if mån < 48: return 4
        if mån < 60: return 5
        return 6

    # Unionen, AB-avtalet, Statliga sektorn, Läkarförbundet, övriga
    # A-02: Unionen kräver 12 mån sammanhängande (KOLLEKTIVAVTAL["Unionen"]["krav_kort_manader"] = 12)
    return 0 if mån < 12 else (3 if mån < 24 else 6)


KOLLEKTIVAVTAL = {
    "Unionen": {
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),  # A-04
        "max_manader_kort": 3,
        "max_manader_lang": 6,
        "krav_kort_manader": 12,  # A-02: var felaktigt 9 — Unionen kräver 12 mån sammanhängande
        "krav_lang_manader": 24,  # fix: 12–23 mån → 3 FL-mån (kort), 24+ mån → 6 FL-mån (lång)
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Teknikavtalet": {
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),  # A-04
        "max_manader_kort": 2,
        "max_manader_lang": 6,
        "krav_kort_manader": 12,
        "krav_lang_manader": 24,
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "AB-avtalet": {
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),  # A-04
        "steg": [
            {"krav_manader": 12, "max_manader": 2},
            {"krav_manader": 24, "max_manader": 3},
            {"krav_manader": 36, "max_manader": 4},
            {"krav_manader": 48, "max_manader": 5},
            {"krav_manader": 60, "max_manader": 6},
        ],
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Statliga sektorn": {
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),
        "steg": [
            {"krav_manader": 12, "max_manader": 2},
            {"krav_manader": 24, "max_manader": 3},
            {"krav_manader": 36, "max_manader": 4},
            {"krav_manader": 48, "max_manader": 5},
            {"krav_manader": 60, "max_manader": 6},
        ],
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Finansförbundet": {
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.80,
        "loenetak": round(10 * PBB / 12),  # A-04
        "max_manader_kort": 0,       # Ingen kortperiod – gäller från dag 1
        "max_manader_lang": 12,      # 360 dagar per Finansförbundets avtal
        "krav_kort_manader": 9999,   # Deaktiverad
        "krav_lang_manader": 1,      # Gäller från dag 1 som tillsvidareanställd
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Läkarförbundet": {
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),  # A-04
        "max_manader_kort": 3,
        "max_manader_lang": 9,
        "krav_kort_manader": 6,
        "krav_lang_manader": 6,
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Innovationsföretagen": {
        # Innovationsföretagen (fd. IT&Telekomföretagen) – kollektivavtal med Unionen/Sveriges Ingenjörer
        # Samma villkor som Teknikavtalet: sammanhängande anställningstid avgör.
        # Källor: Innovationsavtalet 2024 § 12 Föräldralön
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),
        "max_manader_kort": 2,   # 12–23 mån anst. → 2 mån FL
        "max_manader_lang": 6,   # 24+ mån anst.   → 6 mån FL
        "krav_kort_manader": 12,
        "krav_lang_manader": 24,
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Byggföretagen (tjänstemän)": {
        # Källa: Sveriges Ingenjörer Byggföretagen — 6 mån vid 12+ mån anst.
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),
        "max_manader_kort": 6,
        "max_manader_lang": 6,
        "krav_kort_manader": 12,
        "krav_lang_manader": 12,
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Svensk Handel (tjänstemän)": {
        # Källa: Opus-analys MEDEL konfidens — samma modell som Unionen
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),
        "max_manader_kort": 2,
        "max_manader_lang": 6,
        "krav_kort_manader": 12,
        "krav_lang_manader": 24,
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Almega IT/konsult": {
        # Källa: Almega/Innovationsföretagen-modellen — bekräftad HÖG
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),
        "max_manader_kort": 2,
        "max_manader_lang": 6,
        "krav_kort_manader": 12,
        "krav_lang_manader": 24,
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Stål och metall (tjänstemän)": {
        # Källa: Opus-analys MEDEL — Teknikavtalsstandard
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),
        "max_manader_kort": 2,
        "max_manader_lang": 6,
        "krav_kort_manader": 12,
        "krav_lang_manader": 24,
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
    "Vårdförbundet (region)": {
        # Sjuksköterskor, barnmorskor, biomedicinska analytiker i region
        # Täcks av AB-avtalet — alias för tydlighetens skull
        "procent_under_tak": 0.10,
        "procent_over_tak": 0.90,
        "loenetak": round(10 * PBB / 12),
        "steg": [
            {"krav_manader": 12, "max_manader": 2},
            {"krav_manader": 24, "max_manader": 3},
            {"krav_manader": 36, "max_manader": 4},
            {"krav_manader": 48, "max_manader": 5},
            {"krav_manader": 60, "max_manader": 6},
        ],
        "fl_10_dagar": False,
        "tio_dagar_avdrag": "timme",
    },
}

_AVTAL_ALIAS: dict[str, str] = {
    "Byggforetagen (tjansteman)": "Byggföretagen (tjänstemän)",
    "Svensk Handel (tjansteman)": "Svensk Handel (tjänstemän)",
    "Almega IT/konsult": "Almega IT/konsult",
    "Vardförbundet (region)": "Vårdförbundet (region)",
}