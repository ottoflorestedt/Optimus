# Föräldrakalkylator – Backend

FastAPI-backend som exponerar kalkyllogiken från `kalkyl.py` som ett REST-API.

## Installation

```bash
pip install -r requirements.txt
```

## Starta servern

```bash
uvicorn main:app --reload
```

Servern startar på `http://localhost:8000`.

## Endpoints

| Metod | URL | Beskrivning |
|-------|-----|-------------|
| GET | `/health` | Hälsokontroll |
| POST | `/berakna` | Beräkna veckoplan + skatteavdragstabell |
| GET | `/docs` | Interaktiv API-dokumentation (Swagger UI) |

## Exempel – POST /berakna

```json
{
  "foraldrar_a": {
    "namn": "Otto",
    "manadslon": 135000,
    "avtal": "Finansförbundet",
    "anstallning": 36,
    "lan": [{"belopp": 1000000, "ranta": 2.5}],
    "rot": 50000,
    "rut": 0,
    "perioder": [
      {"start": "2026-04-01", "slut": "2027-08-31", "fk_v": 5}
    ]
  },
  "foraldrar_b": {
    "namn": "Angelica",
    "manadslon": 40000,
    "avtal": "Ingen föräldralön",
    "anstallning": 12,
    "lan": [],
    "perioder": []
  },
  "antal_barn": 1,
  "kommun": "Stockholm"
}
```

## Svarsstruktur

```json
{
  "plan_veckor": [...],
  "manadsinkomst_a": [...],
  "manadsinkomst_b": [...],
  "skatteavdrag": {
    "2026": {
      "a": {"betald_skatt": 234052, "ranteavdrag": 30000, ...},
      "b": {"betald_skatt": 91440, "ranteavdrag": 0, ...}
    }
  }
}
```
