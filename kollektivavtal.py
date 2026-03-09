"""
Kollektivavtalsdata för föräldralön.
PBB_2025 används för att beräkna lönegränsen (lönetaket) enligt formeln 10 × PBB / 12.
"""

PBB_2025 = 59200  # Prisbasbelopp 2025/2026

KOLLEKTIVAVTAL = {
    "Unionen": {
        "procent_under_tak": 0.10,
        "procent_over_tak":  0.90,
        "loenetak":          round(10 * PBB_2025 / 12),
        "max_manader_kort":  3,
        "max_manader_lang":  6,
        "krav_kort_manader": 9,
        "krav_lang_manader": 12,
    },
    "Teknikavtalet": {
        "procent_under_tak": 0.10,
        "procent_over_tak":  0.90,
        "loenetak":          round(10 * PBB_2025 / 12),
        "max_manader_kort":  2,
        "max_manader_lang":  6,
        "krav_kort_manader": 12,
        "krav_lang_manader": 24,
    },
    "AB-avtalet": {
        "procent_under_tak": 0.10,
        "procent_over_tak":  0.90,
        "loenetak":          round(10 * PBB_2025 / 12),
        "steg": [
            {"krav_manader": 12, "max_manader": 2},
            {"krav_manader": 24, "max_manader": 3},
            {"krav_manader": 36, "max_manader": 4},
            {"krav_manader": 48, "max_manader": 5},
            {"krav_manader": 60, "max_manader": 6},
        ],
    },
    "Statliga sektorn": {
        "procent_under_tak": 0.10,
        "procent_over_tak":  0.90,
        "loenetak":          round(10 * PBB_2025 / 12),
        "max_manader_kort":  6,
        "max_manader_lang":  12,
        "krav_kort_manader": 12,
        "krav_lang_manader": 12,
    },
    "Finansförbundet": {
        "procent_under_tak": 0.10,
        "procent_over_tak":  0.80,
        "loenetak":          round(10 * PBB_2025 / 12),
        "max_manader_kort":  0,    # Ingen kortperiod – gäller från dag 1
        "max_manader_lang":  12,   # 360 dagar per Finansförbundets avtal
        "krav_kort_manader": 9999, # Deaktiverad
        "krav_lang_manader": 1,    # Gäller från dag 1 som tillsvidareanställd
    },
    "Läkarförbundet": {
        "procent_under_tak": 0.10,
        "procent_over_tak":  0.90,
        "loenetak":          round(10 * PBB_2025 / 12),
        "max_manader_kort":  3,
        "max_manader_lang":  9,
        "krav_kort_manader": 6,
        "krav_lang_manader": 6,
    },
}
