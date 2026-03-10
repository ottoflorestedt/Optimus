from datetime import date, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from kalkyl import (
    berakna_skatt, berakna_fk_ersattning,
    berakna_foraldralon, berakna_ranteavdrag, berakna_vecka, KOLLEKTIVAVTAL,
)
from skattesatser import KOMMUNALSKATT_2026, KYRKOAVGIFT_2026

st.set_page_config(page_title="Föräldrakalkylator", page_icon="👶", layout="wide")

PBB_2025        = 59200
LONETAK_DEFAULT = round(10 * PBB_2025 / 12)   # 49 333 kr

AVTAL_LISTA = list(KOLLEKTIVAVTAL.keys()) + ["Ingen föräldralön", "Ange föräldralön själv"]
_IDAG = date.today()

_KOMMUN_OPTIONS = [f"{k} ({v:.2f}%)" for k, v in sorted(KOMMUNALSKATT_2026.items())]
_STOCKHOLM_OPT  = next(o for o in _KOMMUN_OPTIONS if o.startswith("Stockholm ("))

# ── SESSION STATE ─────────────────────────────────────────────
def default(key, val):
    if key not in st.session_state:
        st.session_state[key] = val

for _kod in ("a", "b"):
    default(f"namn_{_kod}",               "Förälder A" if _kod == "a" else "Förälder B")
    default(f"manadslon_{_kod}",          40000)
    default(f"avtal_{_kod}",              "Ingen föräldralön")
    default(f"anstallning_{_kod}",        12)
    default(f"antal_lan_{_kod}",           1)
    default(f"lan_belopp_{_kod}",         [0] * 10)  # Max 10 låneslots per förälder
    default(f"lan_ranta_{_kod}",          [0.0] * 10)
    default(f"rot_{_kod}",                0)
    default(f"rut_{_kod}",                0)
    default(f"anpassat_pct_under_{_kod}", 10.0)
    default(f"anpassat_pct_over_{_kod}",  90.0)
    default(f"anpassat_loenetak_{_kod}",  LONETAK_DEFAULT)
    default(f"fast_foraldralon_{_kod}",   0)
    default(f"anpassat_max_man_{_kod}",   6)
    default(f"anpassat_krav_man_{_kod}",  12)
    # Kyrka
    default(f"kyrka_{_kod}",      False)
    default(f"forsamling_{_kod}", "")
    # Planering
    default(f"perioder_{_kod}", [{
        "start":     _IDAG,
        "slut":      _IDAG + timedelta(weeks=20),
        "fk_v":      5,
        "sem_dagar": 0,
        "sem_start": _IDAG + timedelta(weeks=8),
        "sem_slut":  _IDAG + timedelta(weeks=10),
    }])

default("antal_barn",       0)
default("sparade_sgi_a",    0)
default("sparade_sgi_b",    0)
default("sparade_lagsta_a", 0)
default("sparade_lagsta_b", 0)
default("kommun",        "Stockholm")
default("kommunalskatt", KOMMUNALSKATT_2026["Stockholm"])
default("wi_kommun",     _STOCKHOLM_OPT)
default("plan_veckor",   None)
default("nav_sida",      "Indata")
default("visa_resultat", False)

SIDOR = ["Indata", "Planering", "Resultat"]


# ── BERÄKNINGS-HELPERS ────────────────────────────────────────
def berakna_rantor(belopp_lista, ranta_lista):
    return round(sum(b * r / 100 for b, r in zip(belopp_lista, ranta_lista) if b > 0 and r > 0))


def berakna_rot_rut_avdrag(rot, rut):
    """30 % på ROT (max 50 000 kr), 50 % på RUT (max 75 000 kr), kombinerat max 75 000 kr."""
    rot_avd = min(round(rot * 0.30), 50_000)
    rut_avd = min(round(rut * 0.50), 75_000)
    return min(rot_avd + rut_avd, 75_000)


def _komponenter_manad(ar, man, veckor, edited_df, lon, nettolön_mån, ki,
                       fl_r, fl_bool, col_fk, col_lg, col_sem, col_ledig, barnbidrag):
    """Beräknar en månads inkomstkomponenter för en förälder givet veckoplan och planredigerare."""
    fk_r = berakna_fk_ersattning(lon, ki)
    _d = date(ar, man, 1)
    wd_i_man = 0
    while _d.month == man:
        if _d.weekday() < 5:
            wd_i_man += 1
        _d += timedelta(days=1)
    netto_dag  = nettolön_mån / wd_i_man if wd_i_man else 0
    brutto_dag = lon / wd_i_man if wd_i_man else 0
    fk_ndag = fk_r["fk_netto/dag"]
    fk_bdag = fk_r["fk_brutto/dag"]
    lg_ndag = 180 * (1 - ki)
    lg_bdag = 180
    fl_ndag = (fl_r["foraldralon/mån"] * (1 - ki) / wd_i_man) if (fl_bool and fl_r["max_månader"] > 0 and wd_i_man) else 0
    fl_bdag = (fl_r["foraldralon/mån"] / wd_i_man) if (fl_bool and fl_r["max_månader"] > 0 and wd_i_man) else 0
    lon_n = lon_b = sem_b = 0.0
    fk_n = fk_b = fl_n = fl_b = sem_n = 0.0
    for i in range(len(veckor)):
        fk  = int(edited_df.iloc[i][col_fk])
        lg  = int(edited_df.iloc[i][col_lg])
        sem = int(edited_df.iloc[i][col_sem])
        n = sum(1 for d in range(5)
                if (veckor[i]["datum_start"] + timedelta(days=d)).year == ar
                and (veckor[i]["datum_start"] + timedelta(days=d)).month == man)
        if n == 0:
            continue
        frac  = n / 5
        ledig = bool(veckor[i][col_ledig])
        fk_wd = min(fk, 5)
        arb   = 0 if ledig else max(0, 5 - fk_wd - lg - sem)
        tillagg = lon * 0.0043 * sem * frac   # semestertillägg (netto, ej extra skatt)
        lon_n += arb * netto_dag  * frac
        lon_b += arb * brutto_dag * frac
        # sem_n = full nettolön under semesterdagar + semestertillägg
        sem_n += sem * netto_dag  * frac + tillagg
        sem_b += sem * brutto_dag * frac + tillagg   # tillägg är skattefritt (netto=brutto)
        fk_n  += (fk_ndag * fk_wd + lg_ndag * max(fk - 5, 0) + lg_ndag * lg) * frac
        fk_b  += (fk_bdag * fk_wd + lg_bdag * max(fk - 5, 0) + lg_bdag * lg) * frac
        if fl_bool and fk > 0:
            fl_n += fl_ndag * fk_wd * frac
            fl_b += fl_bdag * fk_wd * frac
    total_n = lon_n + fk_n + fl_n + sem_n + barnbidrag
    total_b = lon_b + fk_b + fl_b + sem_b + barnbidrag
    return {
        "lon_netto":   round(lon_n),
        "sem_netto":   round(sem_n),
        "fk_netto":    round(fk_n),
        "fl_netto":    round(fl_n),
        "bb":          barnbidrag,
        "skatt":       round(total_b - total_n),
        "netto_total": round(total_n),
    }


def get_avtal_for_calc(kod):
    """Returnerar avtalsvärde (str eller dict) till berakna_foraldralon."""
    avtal = st.session_state[f"avtal_{kod}"]
    if avtal == "Ange föräldralön själv":
        result = {
            "procent_under_tak": st.session_state[f"anpassat_pct_under_{kod}"] / 100,
            "procent_over_tak":  st.session_state[f"anpassat_pct_over_{kod}"]  / 100,
            "loenetak":          st.session_state[f"anpassat_loenetak_{kod}"],
            "max_manader":       st.session_state[f"anpassat_max_man_{kod}"],
            "krav_manader":      st.session_state[f"anpassat_krav_man_{kod}"],
        }
        fast = st.session_state.get(f"fast_foraldralon_{kod}", 0)
        if fast > 0:
            result["fast_belopp"] = fast
        return result
    return avtal


def get_ki(kod):
    """Returnerar kommunalskatt+kyrkoavgift som koefficient för förälder."""
    base = st.session_state["kommunalskatt"]
    if st.session_state.get(f"kyrka_{kod}", False):
        fsm = st.session_state.get(f"forsamling_{kod}", "")
        if fsm and fsm in KYRKOAVGIFT_2026:
            return KYRKOAVGIFT_2026[fsm] / 100
    return base / 100


# ── PLANERINGS-HELPERS ────────────────────────────────────────
def _wd_i_vecka(monday: date, period_start, period_end) -> int:
    """Antal arbetsdagar (mån–fre) i skärningen mellan veckan och [period_start, period_end]."""
    if period_start is None or period_end is None:
        return 0
    friday = monday + timedelta(days=4)
    s = max(monday, period_start)
    e = min(friday, period_end)
    if s > e:
        return 0
    return sum(1 for i in range((e - s).days + 1) if (s + timedelta(days=i)).weekday() < 5)


def generera_plan_veckor(perioder_a: list[dict], perioder_b: list[dict]) -> list[dict]:
    """
    Skapar en lista av vecko-dicts från flera ledighetsperioder per förälder.
    Varje period-dict: start, slut, fk_v, sem_dagar, sem_start, sem_slut.
    """
    all_dates = [p[k] for p in perioder_a + perioder_b for k in ("start", "slut")]
    if not all_dates:
        return []

    global_start = min(all_dates)
    global_end   = max(all_dates)
    monday       = global_start - timedelta(days=global_start.weekday())
    sem_kvar_a   = [p["sem_dagar"] for p in perioder_a]
    sem_kvar_b   = [p["sem_dagar"] for p in perioder_b]
    veckor: list[dict] = []

    while monday <= global_end:
        friday = monday + timedelta(days=4)
        iso    = monday.isocalendar()

        fk_a, s_a, ledig_a = 0, 0, False
        for i, p in enumerate(perioder_a):
            leave = _wd_i_vecka(monday, p["start"], p["slut"])
            if leave > 0:
                ledig_a = True
                ss = p["sem_start"] if p["sem_dagar"] > 0 else None
                se = p["sem_slut"]  if p["sem_dagar"] > 0 else None
                s  = min(_wd_i_vecka(monday, ss, se), sem_kvar_a[i], leave)
                sem_kvar_a[i] -= s
                s_a  += s
                fk_a += min(min(p["fk_v"], 5), leave - s) + max(p["fk_v"] - 5, 0)

        fk_b, s_b, ledig_b = 0, 0, False
        for i, p in enumerate(perioder_b):
            leave = _wd_i_vecka(monday, p["start"], p["slut"])
            if leave > 0:
                ledig_b = True
                ss = p["sem_start"] if p["sem_dagar"] > 0 else None
                se = p["sem_slut"]  if p["sem_dagar"] > 0 else None
                s  = min(_wd_i_vecka(monday, ss, se), sem_kvar_b[i], leave)
                sem_kvar_b[i] -= s
                s_b  += s
                fk_b += min(min(p["fk_v"], 5), leave - s) + max(p["fk_v"] - 5, 0)

        veckor.append({
            "vecka":            int(iso[1]),
            "ar":               int(iso[0]),
            "datum_start":      monday,
            "datum_slut":       friday,
            "fk_dagar_a":       int(fk_a),
            "lg_dagar_a":       0,
            "semester_dagar_a": int(s_a),
            "ledig_a":          ledig_a,
            "fk_dagar_b":       int(fk_b),
            "lg_dagar_b":       0,
            "semester_dagar_b": int(s_b),
            "ledig_b":          ledig_b,
        })
        monday += timedelta(weeks=1)

    return veckor


# ── UI-HELPERS (Indata) ───────────────────────────────────────
def lan_inputs(kod, namn):
    st.markdown(f"**Lån – {namn}**")
    st.caption(
        "Lånens räntekostnader räknas av mot skatten (ränteavdrag). Ange belopp och "
        "årsränta för bolån och övriga lån."
    )
    antal  = st.session_state[f"antal_lan_{kod}"]
    belopp = list(st.session_state[f"lan_belopp_{kod}"])
    ranta  = list(st.session_state[f"lan_ranta_{kod}"])
    for i in range(antal):
        c1, c2, c3 = st.columns([5, 4, 1])
        with c1:
            belopp[i] = st.number_input(
                f"Lån {i + 1} – Belopp (kr)",
                min_value=0, max_value=50_000_000,
                value=belopp[i], step=10_000, key=f"wi_lan_belopp_{kod}_{i}")
        with c2:
            ranta[i] = st.number_input(
                f"Lån {i + 1} – Årsränta (%)",
                min_value=0.0, max_value=30.0,
                value=ranta[i], step=0.1, format="%.2f", key=f"wi_lan_ranta_{kod}_{i}")
        with c3:
            if i > 0:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                if st.button("Ta bort", key=f"wi_lan_tabort_{kod}_{i}"):
                    belopp.pop(i)
                    belopp.append(0)
                    ranta.pop(i)
                    ranta.append(0.0)
                    st.session_state[f"antal_lan_{kod}"] -= 1
                    st.session_state[f"lan_belopp_{kod}"] = belopp
                    st.session_state[f"lan_ranta_{kod}"]  = ranta
                    st.rerun()
    if antal < 10:
        if st.button("+ Lägg till lån", key=f"wi_lan_lagg_till_{kod}"):
            st.session_state[f"antal_lan_{kod}"] += 1
            st.rerun()
    st.session_state[f"lan_belopp_{kod}"] = belopp
    st.session_state[f"lan_ranta_{kod}"]  = ranta
    rantor = berakna_rantor(belopp, ranta)
    st.info(f"Total räntekostnad per år: **{rantor:,} kr**")
    return rantor


def rot_rut_inputs(kod, namn):
    st.markdown(f"**ROT/RUT-avdrag – {namn}**")
    c1, c2 = st.columns(2)
    with c1:
        rot = st.number_input(
            "Planerade ROT-utgifter per år (kr)",
            min_value=0, max_value=1_000_000,
            value=st.session_state[f"rot_{kod}"],
            step=1000, key=f"wi_rot_{kod}",
            help="Avdrag: 30 % av arbetskostnaden")
    with c2:
        rut = st.number_input(
            "Planerade RUT-utgifter per år (kr)",
            min_value=0, max_value=1_000_000,
            value=st.session_state[f"rut_{kod}"],
            step=1000, key=f"wi_rut_{kod}",
            help="Avdrag: 50 % av arbetskostnaden")
    st.session_state[f"rot_{kod}"] = rot
    st.session_state[f"rut_{kod}"] = rut
    avdrag = berakna_rot_rut_avdrag(rot, rut)
    st.success(f"Beräknat ROT/RUT-avdrag per år: **{avdrag:,} kr**")
    st.caption("ROT max 50 000 kr, RUT max 75 000 kr, kombinerat max 75 000 kr per person och år.")
    return avdrag


# ── SIDEBAR ───────────────────────────────────────────────────
st.sidebar.title("Föräldrakalkylator")
sida = st.sidebar.radio(
    "Välj sida",
    SIDOR,
    index=SIDOR.index(st.session_state["nav_sida"]),
)
st.session_state["nav_sida"] = sida


# ════════════════════════════════════════════════════════════
#  INDATA
# ════════════════════════════════════════════════════════════
if sida == "Indata":
    st.title("Indata")
    st.info(
        "Kalkylatorn visar hur hushållets månadsinkomst ser ut under föräldraledigheten "
        "– med hänsyn till föräldrapenning, föräldralön, skatt, lån och barnbidrag.\n\n"
        "**Ha följande redo:** månadslön (brutto) för varje förälder, kollektivavtal och "
        "ungefärlig anställningstid, lånbelopp och räntor, samt en grov bild av när ni "
        "tänker vara lediga."
    )

    with st.expander("🧪 Testdata"):
        def _ladda_gemensamt():
            """Sätter alla gemensamma fält för båda testdata-scenarierna."""
            st.session_state["namn_a"]              = "Förälder A"
            st.session_state["wi_namn_a"]           = "Förälder A"
            st.session_state["manadslon_a"]         = 135000
            st.session_state["wi_manadslon_a"]      = 135000
            st.session_state["avtal_a"]             = "Finansförbundet"
            st.session_state["wi_avtal_a"]          = "Finansförbundet"
            st.session_state["anstallning_a"]       = 12
            st.session_state["wi_anstallning_a"]    = 12
            st.session_state["antal_lan_a"]         = 4
            st.session_state["lan_belopp_a"]        = [1000000, 1000000, 1000000, 1000000] + [0] * 6
            st.session_state["lan_ranta_a"]         = [2.5, 2.5, 2.5, 2.5] + [0.0] * 6
            for _i in range(4):
                st.session_state[f"wi_lan_belopp_a_{_i}"] = 1000000
                st.session_state[f"wi_lan_ranta_a_{_i}"]  = 2.5
            st.session_state["rot_a"]               = 50000
            st.session_state["wi_rot_a"]            = 50000
            st.session_state["rut_a"]               = 12000
            st.session_state["wi_rut_a"]            = 12000
            st.session_state["fast_foraldralon_a"]  = 0
            st.session_state["wi_fast_foraldralon_a"] = 0
            st.session_state["namn_b"]              = "Förälder B"
            st.session_state["wi_namn_b"]           = "Förälder B"
            st.session_state["manadslon_b"]         = 40000
            st.session_state["wi_manadslon_b"]      = 40000
            st.session_state["avtal_b"]             = "AB-avtalet"
            st.session_state["wi_avtal_b"]          = "AB-avtalet"
            st.session_state["anstallning_b"]       = 12
            st.session_state["wi_anstallning_b"]    = 12
            st.session_state["antal_lan_b"]         = 4
            st.session_state["lan_belopp_b"]        = [1000000, 1000000, 1000000, 1000000] + [0] * 6
            st.session_state["lan_ranta_b"]         = [2.5, 2.5, 2.5, 2.5] + [0.0] * 6
            for _i in range(4):
                st.session_state[f"wi_lan_belopp_b_{_i}"] = 1000000
                st.session_state[f"wi_lan_ranta_b_{_i}"]  = 2.5
            st.session_state["rot_b"]               = 50000
            st.session_state["wi_rot_b"]            = 50000
            st.session_state["rut_b"]               = 12000
            st.session_state["wi_rut_b"]            = 12000
            st.session_state["fast_foraldralon_b"]  = 0
            st.session_state["wi_fast_foraldralon_b"] = 0
            st.session_state["antal_barn"]          = 0
            st.session_state["wi_antal_barn"]       = 0
            st.session_state["sparade_sgi_a"]       = 0
            st.session_state["wi_sparade_sgi_a"]    = 0
            st.session_state["sparade_sgi_b"]       = 0
            st.session_state["wi_sparade_sgi_b"]    = 0
            st.session_state["sparade_lagsta_a"]    = 0
            st.session_state["wi_sparade_lagsta_a"] = 0
            st.session_state["sparade_lagsta_b"]    = 0
            st.session_state["wi_sparade_lagsta_b"] = 0
            st.session_state["kommun"]              = "Stockholm"
            st.session_state["wi_kommun"]           = _STOCKHOLM_OPT
            st.session_state["kommunalskatt"]       = KOMMUNALSKATT_2026["Stockholm"]
            st.session_state["kyrka_a"]             = False
            st.session_state["wi_kyrka_a"]          = False
            st.session_state["kyrka_b"]             = False
            st.session_state["wi_kyrka_b"]          = False
            for _kod in ("a", "b"):
                for _i in range(10):
                    for _fld in ("start", "slut", "fk_v", "sem_dagar", "sem_start", "sem_slut"):
                        st.session_state.pop(f"plan_{_fld}_{_kod}_{_i}", None)
            st.session_state.pop("plan_df", None)
            st.session_state.pop("plan_veckor", None)

        _td_col1, _td_col2 = st.columns(2)
        with _td_col1:
            if st.button("Ladda testdata", key="wi_ladda_testdata"):
                _ladda_gemensamt()
                st.session_state["perioder_a"] = [{
                    "start":     date(2026, 3, 6),
                    "slut":      date(2027, 8, 31),
                    "fk_v":      5,
                    "sem_dagar": 30,
                    "sem_start": date(2026, 4, 30),
                    "sem_slut":  date(2026, 6, 11),
                }]
                st.session_state["perioder_b"] = [{
                    "start":     date(2027, 6, 1),
                    "slut":      date(2027, 8, 31),
                    "fk_v":      5,
                    "sem_dagar": 0,
                    "sem_start": date(2027, 7, 1),
                    "sem_slut":  date(2027, 7, 14),
                }]
                st.rerun()
        with _td_col2:
            if st.button("Ladda testdata 2", key="wi_ladda_testdata_2"):
                _ladda_gemensamt()
                # Överskrivningar för testdata 2
                st.session_state["rut_a"]               = 0
                st.session_state["wi_rut_a"]            = 0
                st.session_state["rut_b"]               = 0
                st.session_state["wi_rut_b"]            = 0
                st.session_state["rot_a"]               = 170000
                st.session_state["wi_rot_a"]            = 170000
                st.session_state["rot_b"]               = 170000
                st.session_state["wi_rot_b"]            = 170000
                st.session_state["lan_belopp_a"]        = [1100000, 1000000, 1000000, 1000000] + [0] * 6
                st.session_state["wi_lan_belopp_a_0"]   = 1100000
                st.session_state["lan_belopp_b"]        = [1100000, 1000000, 1000000, 1000000] + [0] * 6
                st.session_state["wi_lan_belopp_b_0"]   = 1100000
                for _i in range(4):
                    st.session_state["lan_ranta_a"][_i]            = 2.6
                    st.session_state[f"wi_lan_ranta_a_{_i}"]       = 2.6
                    st.session_state["lan_ranta_b"][_i]            = 2.6
                    st.session_state[f"wi_lan_ranta_b_{_i}"]       = 2.6
                st.session_state["avtal_a"]             = "Ange föräldralön själv"
                st.session_state["wi_avtal_a"]          = "Ange föräldralön själv"
                st.session_state["fast_foraldralon_a"]  = 27000
                st.session_state["wi_fast_foraldralon_a"] = 27000
                st.session_state["avtal_b"]             = "Ingen föräldralön"
                st.session_state["wi_avtal_b"]          = "Ingen föräldralön"
                st.session_state["fast_foraldralon_b"]  = 0
                st.session_state["wi_fast_foraldralon_b"] = 0
                st.session_state["perioder_a"] = [{
                    "start":     date(2026, 3, 6),
                    "slut":      date(2027, 8, 31),
                    "fk_v":      5,
                    "sem_dagar": 30,
                    "sem_start": date(2026, 4, 30),
                    "sem_slut":  date(2026, 6, 11),
                }]
                st.session_state["perioder_b"] = [{
                    "start":     date(2027, 6, 1),
                    "slut":      date(2027, 8, 31),
                    "fk_v":      5,
                    "sem_dagar": 0,
                    "sem_start": date(2027, 7, 1),
                    "sem_slut":  date(2027, 7, 14),
                }]
                st.rerun()

    st.subheader("Gemensamma uppgifter")
    st.caption(
        "Det nya barnet räknas automatiskt in i dagkvoten. Ange eventuella syskon och "
        "välj den kommun ni bor i – kommunalskattesatsen påverkar beräknad nettolön."
    )
    col1, col2 = st.columns(2)
    with col1:
        st.session_state["antal_barn"] = st.number_input(
            "Antal barn utöver det ni tänker vara föräldralediga med",
            min_value=0, max_value=10,
            value=st.session_state["antal_barn"],
            key="wi_antal_barn",
            help="Det nya barnet räknas in automatiskt. Ange bara eventuella syskon.")
    with col2:
        st.selectbox("Kommun", _KOMMUN_OPTIONS, key="wi_kommun")
        _kommunnamn = st.session_state["wi_kommun"].split(" (")[0]
        st.session_state["kommun"]        = _kommunnamn
        st.session_state["kommunalskatt"] = KOMMUNALSKATT_2026[_kommunnamn]

    if st.session_state["antal_barn"] > 0:
        st.subheader("Sparade föräldradagar från tidigare barn")
        st.caption(
            "Om ni har sparade dagar från tidigare föräldraledigheter kan ni lägga in dem "
            "här. Sparade SGI-dagar adderas till kvoten om 390 dagar, sparade "
            "lägstanivådagar till kvoten om 90 dagar."
        )
        namn_a_sp = st.session_state["namn_a"]
        namn_b_sp = st.session_state["namn_b"]
        sp_col_a, sp_col_b = st.columns(2)
        with sp_col_a:
            st.session_state["sparade_sgi_a"] = st.number_input(
                f"Sparade SGI-dagar {namn_a_sp}",
                min_value=0, max_value=195,
                value=st.session_state["sparade_sgi_a"],
                key="wi_sparade_sgi_a")
            st.session_state["sparade_lagsta_a"] = st.number_input(
                f"Sparade lägstanivådagar {namn_a_sp}",
                min_value=0, max_value=45,
                value=st.session_state["sparade_lagsta_a"],
                key="wi_sparade_lagsta_a")
        with sp_col_b:
            st.session_state["sparade_sgi_b"] = st.number_input(
                f"Sparade SGI-dagar {namn_b_sp}",
                min_value=0, max_value=195,
                value=st.session_state["sparade_sgi_b"],
                key="wi_sparade_sgi_b")
            st.session_state["sparade_lagsta_b"] = st.number_input(
                f"Sparade lägstanivådagar {namn_b_sp}",
                min_value=0, max_value=45,
                value=st.session_state["sparade_lagsta_b"],
                key="wi_sparade_lagsta_b")

    st.divider()

    def foralder_inputs(kod):
        namn = st.session_state[f"namn_{kod}"]
        st.session_state[f"namn_{kod}"] = st.text_input(
            "Namn", value=namn, key=f"wi_namn_{kod}")

        st.session_state[f"manadslon_{kod}"] = st.number_input(
            "Månadslön (kr)", min_value=1, max_value=500_000,
            value=max(1, st.session_state[f"manadslon_{kod}"]),
            step=1000, key=f"wi_manadslon_{kod}")

        avtal = st.selectbox(
            "Kollektivavtal", AVTAL_LISTA,
            index=AVTAL_LISTA.index(st.session_state[f"avtal_{kod}"]),
            key=f"wi_avtal_{kod}")
        st.session_state[f"avtal_{kod}"] = avtal
        st.caption(
            "Kollektivavtalet avgör om arbetsgivaren betalar föräldralön utöver "
            "Försäkringskassans ersättning. Vet du inte vilket avtal som gäller, välj "
            "'Ingen föräldralön' eller ange föräldralön själv."
        )

        if avtal == "Ange föräldralön själv":
            c1, c2 = st.columns(2)
            with c1:
                st.session_state[f"anpassat_pct_under_{kod}"] = st.number_input(
                    "Föräldralön % av lön upp till lönegränsen", min_value=0.0, max_value=100.0,
                    value=st.session_state[f"anpassat_pct_under_{kod}"],
                    step=1.0, format="%.1f", key=f"pct_under_{kod}")
                st.session_state[f"anpassat_loenetak_{kod}"] = st.number_input(
                    "Lönegräns kr/mån", min_value=1, max_value=200_000,
                    value=st.session_state[f"anpassat_loenetak_{kod}"],
                    step=1000, key=f"loenetak_{kod}",
                    help=f"Lönegränsen är 10 × prisbasbeloppet / 12. För 2025 är prisbasbeloppet {PBB_2025:,} kr vilket ger {LONETAK_DEFAULT:,} kr/mån.")
                st.session_state[f"anpassat_krav_man_{kod}"] = st.number_input(
                    "Krav på anställningstid (månader)", min_value=0, max_value=120,
                    value=st.session_state[f"anpassat_krav_man_{kod}"],
                    key=f"krav_man_{kod}")
            with c2:
                st.session_state[f"anpassat_pct_over_{kod}"] = st.number_input(
                    "Föräldralön % av lön över lönegränsen", min_value=0.0, max_value=100.0,
                    value=st.session_state[f"anpassat_pct_over_{kod}"],
                    step=1.0, format="%.1f", key=f"pct_over_{kod}")
                st.session_state[f"anpassat_max_man_{kod}"] = st.number_input(
                    "Antal månader med föräldralön", min_value=0, max_value=24,
                    value=st.session_state[f"anpassat_max_man_{kod}"],
                    key=f"max_man_{kod}")
            st.session_state[f"fast_foraldralon_{kod}"] = st.number_input(
                "Fast föräldralön per månad (kr)",
                min_value=0, max_value=200_000,
                value=st.session_state[f"fast_foraldralon_{kod}"],
                step=100, key=f"wi_fast_foraldralon_{kod}",
                help="Använd detta om din arbetsgivare betalar ett fast månadsbelopp istället för procent av lönen. Fyller du i detta används beloppet direkt och procentfälten ignoreras.")

        if st.session_state[f"manadslon_{kod}"] < 38_000:
            st.warning(
                "OBS: Löner under 38 000 kr/mån ligger utanför skattetabellens intervall "
                "– beräkningen är en uppskattning."
            )

        st.session_state[f"anstallning_{kod}"] = st.number_input(
            "Anställningstid (månader)", min_value=0, max_value=600,
            value=st.session_state[f"anstallning_{kod}"],
            key=f"wi_anstallning_{kod}")
        st.caption(
            "Anställningstiden avgör om du uppfyller kvalifikationskravet för föräldralön "
            "enligt ditt kollektivavtal."
        )

        st.session_state[f"kyrka_{kod}"] = st.toggle(
            "Medlem i Svenska kyrkan",
            value=st.session_state[f"kyrka_{kod}"],
            key=f"wi_kyrka_{kod}")
        if st.session_state[f"kyrka_{kod}"]:
            _kom = st.session_state.get("kommun", "Stockholm")
            _fsm_lista = sorted(k for k in KYRKOAVGIFT_2026 if k.endswith(f"({_kom})"))
            if _fsm_lista:
                _cur_fsm = st.session_state.get(f"forsamling_{kod}", "")
                if _cur_fsm not in _fsm_lista:
                    st.session_state[f"forsamling_{kod}"] = _fsm_lista[0]
                    st.session_state.pop(f"wi_forsamling_{kod}", None)
                st.selectbox("Församling", _fsm_lista, key=f"wi_forsamling_{kod}")
                st.session_state[f"forsamling_{kod}"] = st.session_state[f"wi_forsamling_{kod}"]
            else:
                st.caption("Inga församlingar hittades för vald kommun.")

        lan_inputs(kod, st.session_state[f"namn_{kod}"])
        rot_rut_inputs(kod, st.session_state[f"namn_{kod}"])

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Förälder A")
        foralder_inputs("a")
    with col_b:
        st.subheader("Förälder B")
        foralder_inputs("b")

    st.divider()
    if st.button("Beräkna →", type="primary", use_container_width=True):
        st.session_state["nav_sida"] = "Planering"
        st.rerun()


# ════════════════════════════════════════════════════════════
#  PLANERING – Steg 1: Grovplanering
# ════════════════════════════════════════════════════════════
elif sida == "Planering":
    namn_a = st.session_state["namn_a"]
    namn_b = st.session_state["namn_b"]

    st.title("Planering – Steg 1: Grovplanering")
    st.caption(
        "Ange ledighetsperioder och uttakstakt per förälder. "
        "Klicka **Generera plan** för att skapa en vecka-för-vecka-plan."
    )

    def _perioder_overlappar(perioder):
        """Returnerar lista av (i+1, j+1)-par som överlappar (1-indexerat)."""
        fel = []
        for i in range(len(perioder)):
            for j in range(i + 1, len(perioder)):
                if perioder[i]["start"] <= perioder[j]["slut"] and perioder[j]["start"] <= perioder[i]["slut"]:
                    fel.append((i + 1, j + 1))
        return fel

    def _period_inputs(kod, namn):
        perioder = list(st.session_state[f"perioder_{kod}"])
        new_perioder = []

        for i, p in enumerate(perioder):
            with st.container(border=True):
                hdr_col, del_col = st.columns([5, 1])
                with hdr_col:
                    st.markdown(f"**Period {i + 1}**")
                with del_col:
                    if i > 0 and st.button("Ta bort", key=f"ta_bort_{kod}_{i}", use_container_width=True):
                        for j in range(i, len(perioder)):
                            for fld in ("start", "slut", "fk_v", "sem_dagar", "sem_start", "sem_slut"):
                                st.session_state.pop(f"plan_{fld}_{kod}_{j}", None)
                        st.session_state[f"perioder_{kod}"] = [pp for idx, pp in enumerate(perioder) if idx != i]
                        st.rerun()

                c1, c2 = st.columns(2)
                with c1:
                    ny_start = st.date_input(
                        "Start", value=p["start"], key=f"plan_start_{kod}_{i}")
                with c2:
                    ny_slut = st.date_input(
                        "Slut", value=p["slut"], key=f"plan_slut_{kod}_{i}")

                ny_fk_v = st.slider(
                    "FK-dagar per vecka", min_value=1, max_value=7,
                    value=p["fk_v"], key=f"plan_fk_v_{kod}_{i}",
                    help="Antal dagar per vecka föräldrapenning tas ut på sjukpenningnivå.")

                ny_sem = st.number_input(
                    "Semesterdagar under perioden", min_value=0, max_value=50,
                    value=p["sem_dagar"], key=f"plan_sem_dagar_{kod}_{i}",
                    help="Arbetsgivaren betalar lön – räknas inte som FK-dagar.")

                ny_sem_start = p["sem_start"]
                ny_sem_slut  = p["sem_slut"]
                if ny_sem > 0:
                    _s = ny_start if ny_start <= ny_slut else ny_slut
                    _e = ny_slut  if ny_start <= ny_slut else ny_start
                    _ss = max(_s, min(_e, p["sem_start"]))
                    _se = max(_s, min(_e, p["sem_slut"]))
                    if _ss > _se:
                        _se = _ss
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        ny_sem_start = st.date_input(
                            "Semester startar", value=_ss,
                            min_value=_s, max_value=_e,
                            key=f"plan_sem_start_{kod}_{i}")
                    with sc2:
                        ny_sem_slut = st.date_input(
                            "Semester slutar", value=_se,
                            min_value=_s, max_value=_e,
                            key=f"plan_sem_slut_{kod}_{i}")

                new_perioder.append({
                    "start":     ny_start,
                    "slut":      ny_slut,
                    "fk_v":      ny_fk_v,
                    "sem_dagar": ny_sem,
                    "sem_start": ny_sem_start,
                    "sem_slut":  ny_sem_slut,
                })

        st.session_state[f"perioder_{kod}"] = new_perioder

        overlap = _perioder_overlappar(new_perioder)
        for (pi, pj) in overlap:
            st.error(f"{namn}: period {pi} och period {pj} överlappar varandra.")

        if st.button(f"+ Lägg till period", key=f"lagg_till_{kod}"):
            last      = new_perioder[-1]
            ny_s      = last["slut"] + timedelta(days=1)
            ny_e      = ny_s + timedelta(weeks=20)
            new_perioder.append({
                "start":     ny_s,
                "slut":      ny_e,
                "fk_v":      5,
                "sem_dagar": 0,
                "sem_start": ny_s + timedelta(weeks=8),
                "sem_slut":  ny_s + timedelta(weeks=10),
            })
            st.session_state[f"perioder_{kod}"] = new_perioder
            st.rerun()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader(namn_a)
        _period_inputs("a", namn_a)
    with col_b:
        st.subheader(namn_b)
        _period_inputs("b", namn_b)

    st.divider()

    if st.button("Generera plan →", type="primary", use_container_width=True):
        perioder_a = st.session_state["perioder_a"]
        perioder_b = st.session_state["perioder_b"]
        fel = []

        for kod, perioder, namn in [("a", perioder_a, namn_a), ("b", perioder_b, namn_b)]:
            for i, p in enumerate(perioder):
                if p["start"] > p["slut"]:
                    fel.append(f"{namn} period {i + 1}: start är efter slut.")
                if p["sem_dagar"] > 0 and p["sem_start"] > p["sem_slut"]:
                    fel.append(f"{namn} period {i + 1}: semesterstart är efter semesterslut.")
            for (pi, pj) in _perioder_overlappar(perioder):
                fel.append(f"{namn}: period {pi} och period {pj} överlappar varandra.")

        if fel:
            for f in fel:
                st.error(f)
        else:
            veckor = generera_plan_veckor(perioder_a, perioder_b)
            st.session_state["plan_veckor"] = veckor
            st.session_state.pop("plan_df", None)
            st.session_state["visa_resultat"] = False
            st.session_state["nav_sida"] = "Resultat"
            st.rerun()


# ════════════════════════════════════════════════════════════
#  RESULTAT
# ════════════════════════════════════════════════════════════
elif sida == "Resultat":
    veckor = st.session_state.get("plan_veckor")
    st.title("Resultat")

    if not veckor:
        st.warning("Ingen plan genererad ännu. Gå till **Planering** och klicka *Generera plan*.")
        if st.button("← Gå till Planering"):
            st.session_state["nav_sida"] = "Planering"
            st.rerun()
    else:
        namn_a = st.session_state["namn_a"]
        namn_b = st.session_state["namn_b"]
        COL_FK_A  = "fk_a"
        COL_LG_A  = "lg_a"
        COL_SEM_A = "sem_a"
        COL_FK_B  = "fk_b"
        COL_LG_B  = "lg_b"
        COL_SEM_B = "sem_b"
        # SP-dagar (sjukpenningnivå) per förälder: 195 dagar, SFB 12 kap 12 §
        SP_TOTAL_A = 195 + st.session_state["sparade_sgi_a"]
        SP_TOTAL_B = 195 + st.session_state["sparade_sgi_b"]
        # LG-dagar (lägstanivå) per förälder: 45 dagar, SFB 12 kap 12 §
        LG_TOTAL_A = 45  + st.session_state["sparade_lagsta_a"]
        LG_TOTAL_B = 45  + st.session_state["sparade_lagsta_b"]

        # ── Initiering av plan_df (en gång per genererad plan) ──
        if "plan_df" not in st.session_state:
            _MÅNADER = ["jan","feb","mar","apr","maj","jun",
                        "jul","aug","sep","okt","nov","dec"]
            rows = []
            for v in veckor:
                ds, de = v["datum_start"], v["datum_slut"]
                period = f"{ds.day} {_MÅNADER[ds.month-1]} – {de.day} {_MÅNADER[de.month-1]}"
                rows.append({
                    "Vecka":   f"V{v['vecka']:02d} {v['ar']}",
                    "Period":  period,
                    COL_FK_A:  v["fk_dagar_a"],
                    COL_LG_A:  v["lg_dagar_a"],
                    COL_SEM_A: v["semester_dagar_a"],
                    COL_FK_B:  v["fk_dagar_b"],
                    COL_LG_B:  v["lg_dagar_b"],
                    COL_SEM_B: v["semester_dagar_b"],
                })
            df = pd.DataFrame(rows)
            for col in [COL_FK_A, COL_LG_A, COL_SEM_A, COL_FK_B, COL_LG_B, COL_SEM_B]:
                df[col] = df[col].astype(int)
            st.session_state["plan_df"] = df

        df = st.session_state["plan_df"]

        st.caption(
            "Justera SGI-dagar (0–7), lägstanivådagar (0–7) och semesterdagar (0–5) per vecka. "
            "Saldot uppdateras direkt."
        )

        # ── SP-dagssaldo (beräknat från föregående frame → live) ──
        fk_used_a = int(df[COL_FK_A].sum())
        fk_used_b = int(df[COL_FK_B].sum())
        fk_left_a = SP_TOTAL_A - fk_used_a
        fk_left_b = SP_TOTAL_B - fk_used_b

        st.subheader("Föräldrapenning på sjukpenningnivå (SGI-baserad)")
        st.caption("390 dagar per förälder – ersättning baserad på din inkomst (ca 77% av SGI)")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric(f"Totalt – {namn_a}",  SP_TOTAL_A)
        c2.metric(f"Använda – {namn_a}", fk_used_a)
        c3.metric(f"Kvar – {namn_a}",    fk_left_a)
        c4.metric(f"Totalt – {namn_b}",  SP_TOTAL_B)
        c5.metric(f"Använda – {namn_b}", fk_used_b)
        c6.metric(f"Kvar – {namn_b}",    fk_left_b)

        underskott_a = max(0, fk_used_a - SP_TOTAL_A)
        underskott_b = max(0, fk_used_b - SP_TOTAL_B)
        overskott_a  = max(0, SP_TOTAL_A - fk_used_a)
        overskott_b  = max(0, SP_TOTAL_B - fk_used_b)

        if underskott_a > 0 and underskott_b > 0:
            # Scenario 3 – båda har underskott
            st.error(
                f"🔴 Båda föräldrarna har för många dagar i planen\n\n"
                f"{namn_a}: {underskott_a} dagar för många. "
                f"{namn_b}: {underskott_b} dagar för många.\n\n"
                f"Dagar kan bara överlåtas från en förälder med överskott – "
                f"överlåtelse är inte möjlig här. Minska uttaget för båda eller förläng ledighetsperioderna."
            )
        elif underskott_a > 0 and overskott_b >= underskott_a:
            # Scenario 1 eller 2 – A har underskott, B har tillräckligt överskott
            if underskott_a <= 150:
                st.success(
                    f"✅ Planen är genomförbar – men kräver överlåtelse av dagar\n\n"
                    f"{namn_a} tar ut {underskott_a} fler SGI-dagar än sin egen kvot. "
                    f"För att planen ska fungera behöver {namn_b} överlåta {underskott_a} av sina dagar till {namn_a}.\n\n"
                    f"Överlåtelse är tillåten upp till 150 dagar och görs via ansökan hos Försäkringskassan "
                    f"– ansök i god tid innan ledigheten börjar."
                )
            else:
                st.error(
                    f"🔴 Planen är inte genomförbar\n\n"
                    f"{namn_a} tar ut {underskott_a} fler SGI-dagar än tillgängligt. "
                    f"Max 150 dagar kan överlåtas – planen kräver {underskott_a - 150} dagar för många.\n\n"
                    f"Minska {namn_a}s uttag eller förläng ledighetsperioden."
                )
        elif underskott_b > 0 and overskott_a >= underskott_b:
            # Scenario 1 eller 2 – B har underskott, A har tillräckligt överskott
            if underskott_b <= 150:
                st.success(
                    f"✅ Planen är genomförbar – men kräver överlåtelse av dagar\n\n"
                    f"{namn_b} tar ut {underskott_b} fler SGI-dagar än sin egen kvot. "
                    f"För att planen ska fungera behöver {namn_a} överlåta {underskott_b} av sina dagar till {namn_b}.\n\n"
                    f"Överlåtelse är tillåten upp till 150 dagar och görs via ansökan hos Försäkringskassan "
                    f"– ansök i god tid innan ledigheten börjar."
                )
            else:
                st.error(
                    f"🔴 Planen är inte genomförbar\n\n"
                    f"{namn_b} tar ut {underskott_b} fler SGI-dagar än tillgängligt. "
                    f"Max 150 dagar kan överlåtas – planen kräver {underskott_b - 150} dagar för många.\n\n"
                    f"Minska {namn_b}s uttag eller förläng ledighetsperioden."
                )

        # ── LG-dagssaldo ─────────────────────────────────────────
        lg_used_a = int(df[COL_LG_A].sum())
        lg_used_b = int(df[COL_LG_B].sum())
        lg_left_a = LG_TOTAL_A - lg_used_a
        lg_left_b = LG_TOTAL_B - lg_used_b

        st.subheader("Föräldrapenning på lägstanivå")
        st.caption("90 dagar per förälder – fast ersättning 180 kr/dag")
        d1, d2, d3, d4, d5, d6 = st.columns(6)
        d1.metric(f"Totalt – {namn_a}",  LG_TOTAL_A)
        d2.metric(f"Använda – {namn_a}", lg_used_a)
        d3.metric(f"Kvar – {namn_a}",    lg_left_a)
        d4.metric(f"Totalt – {namn_b}",  LG_TOTAL_B)
        d5.metric(f"Använda – {namn_b}", lg_used_b)
        d6.metric(f"Kvar – {namn_b}",    lg_left_b)

        if lg_left_a < 0:
            st.error(f"{namn_a} har planerat {lg_used_a} lägstanivådagar – {-lg_left_a} dagar fler än tillåtet ({LG_TOTAL_A}).")
        if lg_left_b < 0:
            st.error(f"{namn_b} har planerat {lg_used_b} lägstanivådagar – {-lg_left_b} dagar fler än tillåtet ({LG_TOTAL_B}).")

        # ── Redigerbar tabell ────────────────────────────────────
        col_config = {
            "Vecka":   st.column_config.TextColumn("Vecka",  disabled=True, width="small"),
            "Period":  st.column_config.TextColumn("Period", disabled=True, width="medium"),
            COL_FK_A:  st.column_config.NumberColumn(
                f"SGI-dagar {namn_a}", min_value=0, max_value=7, step=1, width="small"),
            COL_LG_A:  st.column_config.NumberColumn(
                f"Lägsta-dagar {namn_a}", min_value=0, max_value=7, step=1, width="small"),
            COL_SEM_A: st.column_config.NumberColumn(
                f"Semester {namn_a}", min_value=0, max_value=5, step=1, width="small"),
            COL_FK_B:  st.column_config.NumberColumn(
                f"SGI-dagar {namn_b}", min_value=0, max_value=7, step=1, width="small"),
            COL_LG_B:  st.column_config.NumberColumn(
                f"Lägsta-dagar {namn_b}", min_value=0, max_value=7, step=1, width="small"),
            COL_SEM_B: st.column_config.NumberColumn(
                f"Semester {namn_b}", min_value=0, max_value=5, step=1, width="small"),
        }

        edited_df = st.data_editor(
            df,
            column_config=col_config,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
        )
        st.session_state["plan_df"] = edited_df

        _overbokad = (
            edited_df[COL_FK_A].clip(upper=5) + edited_df[COL_LG_A] + edited_df[COL_SEM_A] > 5
        ).any() or (
            edited_df[COL_FK_B].clip(upper=5) + edited_df[COL_LG_B] + edited_df[COL_SEM_B] > 5
        ).any()
        if _overbokad:
            st.warning(
                "En eller flera veckor har fler dagar än en arbetsvecka "
                "– kontrollera planeringen."
            )

        st.divider()
        col_back, col_calc = st.columns([1, 2])
        with col_back:
            if st.button("← Tillbaka till Planering"):
                st.session_state["nav_sida"] = "Planering"
                st.rerun()
        with col_calc:
            if st.button("Beräkna resultat", type="primary", use_container_width=True):
                st.session_state["visa_resultat"] = True
                st.rerun()

        if st.session_state.get("visa_resultat", False):
            # ── Nettoinkomst per vecka/månad (linjediagram) ──────────
            ki_a   = get_ki("a")
            ki_b   = get_ki("b")
            _base_ki   = st.session_state["kommunalskatt"] / 100
            kyrkoavg_a = max(0.0, ki_a - _base_ki)
            kyrkoavg_b = max(0.0, ki_b - _base_ki)
            lon_a  = st.session_state["manadslon_a"]
            lon_b  = st.session_state["manadslon_b"]
            anst_a = st.session_state["anstallning_a"]
            anst_b = st.session_state["anstallning_b"]
            avtal_a = get_avtal_for_calc("a")
            avtal_b = get_avtal_for_calc("b")
            fl_r_a  = berakna_foraldralon(lon_a, avtal_a, anst_a)
            fl_r_b  = berakna_foraldralon(lon_b, avtal_b, anst_b)
            fl_a    = fl_r_a["max_månader"] > 0
            fl_b    = fl_r_b["max_månader"] > 0
            nettolön_mån_a = berakna_skatt(lon_a, ki_a, kyrkoavg_a)["nettolön/mån"]
            nettolön_mån_b = berakna_skatt(lon_b, ki_b, kyrkoavg_b)["nettolön/mån"]

            _MÅN = ["Jan","Feb","Mar","Apr","Maj","Jun","Jul","Aug","Sep","Okt","Nov","Dec"]

            # ── Månadsdata: inkomstkomponenter + skatt ────────────────
            bb_mån = round(1250 * st.session_state["antal_barn"] / 2)  # per förälder

            y0, m0 = veckor[0]["datum_start"].year, veckor[0]["datum_start"].month
            last   = veckor[-1]["datum_start"] + timedelta(days=4)
            y1, m1 = last.year, last.month
            months_list = []
            y, m = y0, m0
            while (y, m) <= (y1, m1):
                months_list.append((y, m))
                m += 1
                if m > 12:
                    m, y = 1, y + 1

            komp_a, komp_b = [], []
            for ar, man in months_list:
                mlab = f"{_MÅN[man-1]} {ar}"
                ka = _komponenter_manad(ar, man, veckor, edited_df, lon_a, nettolön_mån_a, ki_a,
                                        fl_r_a, fl_a, COL_FK_A, COL_LG_A, COL_SEM_A, "ledig_a", bb_mån)
                kb = _komponenter_manad(ar, man, veckor, edited_df, lon_b, nettolön_mån_b, ki_b,
                                        fl_r_b, fl_b, COL_FK_B, COL_LG_B, COL_SEM_B, "ledig_b", bb_mån)
                komp_a.append({"Månad": mlab, **ka})
                komp_b.append({"Månad": mlab, **kb})

            _mlab = [k["Månad"] for k in komp_a]

            # ── Nettoinkomst per månad (tre linjer) ───────────────────
            st.subheader("Nettoinkomst per månad")
            fig_netto = go.Figure()
            fig_netto.add_trace(go.Scatter(
                x=_mlab, y=[k["netto_total"] for k in komp_a],
                name=namn_a, mode="lines+markers",
                line=dict(color="rgba(59,130,246,1)", width=2),
            ))
            fig_netto.add_trace(go.Scatter(
                x=_mlab, y=[k["netto_total"] for k in komp_b],
                name=namn_b, mode="lines+markers",
                line=dict(color="rgba(219,39,119,1)", width=2),
            ))
            fig_netto.add_trace(go.Scatter(
                x=_mlab,
                y=[ka["netto_total"] + kb["netto_total"] for ka, kb in zip(komp_a, komp_b)],
                name="Hushåll totalt", mode="lines+markers",
                line=dict(color="rgba(156,163,175,1)", width=2),
            ))
            fig_netto.update_layout(
                yaxis_title="kr/månad (efter skatt)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
                height=350,
            )
            st.plotly_chart(fig_netto, use_container_width=True)

            # ── Graf 1: Inkomstkomponenter per förälder ───────────────
            st.subheader("Inkomstkomponenter per månad (efter skatt)")

            def _bar_chart(komp, titel):
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=_mlab, y=[k["lon_netto"] for k in komp],
                    name="Lön från arbete (efter skatt)", marker_color="#4A90D9",
                ))
                fig.add_trace(go.Bar(
                    x=_mlab, y=[k["sem_netto"] for k in komp],
                    name="Semester (efter skatt)", marker_color="#E74C3C",
                ))
                fig.add_trace(go.Bar(
                    x=_mlab, y=[k["fk_netto"] for k in komp],
                    name="FK-ersättning (efter skatt)", marker_color="#2ECC71",
                ))
                fig.add_trace(go.Bar(
                    x=_mlab, y=[k["fl_netto"] for k in komp],
                    name="Föräldralön (efter skatt)", marker_color="#9B59B6",
                ))
                fig.add_trace(go.Bar(
                    x=_mlab, y=[k["bb"] for k in komp],
                    name="Barnbidrag (skattefritt)", marker_color="#F1C40F",
                ))
                fig.update_layout(
                    barmode="stack",
                    title=titel,
                    yaxis_title="kr/månad (efter skatt)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                xanchor="right", x=1),
                    height=380,
                    margin=dict(t=60),
                )
                return fig

            gc1, gc2 = st.columns(2)
            with gc1:
                st.plotly_chart(_bar_chart(komp_a, namn_a), use_container_width=True)
            with gc2:
                st.plotly_chart(_bar_chart(komp_b, namn_b), use_container_width=True)

            # ── Graf 2: Skattebetalningar per månad ───────────────────
            st.subheader("Skattebetalningar per månad")
            skatt_a_list = [k["skatt"] for k in komp_a]
            skatt_b_list = [k["skatt"] for k in komp_b]
            skatt_hus    = [a + b for a, b in zip(skatt_a_list, skatt_b_list)]
            fig_skatt = go.Figure()
            fig_skatt.add_trace(go.Bar(
                x=_mlab, y=skatt_a_list,
                name=namn_a, marker_color="rgba(59,130,246,0.8)",
            ))
            fig_skatt.add_trace(go.Bar(
                x=_mlab, y=skatt_b_list,
                name=namn_b, marker_color="rgba(219,39,119,0.8)",
            ))
            fig_skatt.add_trace(go.Bar(
                x=_mlab, y=skatt_hus,
                name="Hushåll totalt", marker_color="rgba(156,163,175,0.8)",
            ))
            fig_skatt.update_layout(
                barmode="group",
                yaxis_title="kr/månad",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
                height=350,
            )
            st.plotly_chart(fig_skatt, use_container_width=True)

            st.divider()

            # ── Skatteavdrag och kvittning (per kalenderår) ──────────
            st.subheader("Skatteavdrag och kvittning")
            st.caption(
                "Skatteberäkningen inkluderar månader utanför den angivna planen, "
                "där full heltidslön antas för båda föräldrarna. Detta ger en korrekt "
                "helårsbild för kvittning av ROT-, RUT- och ränteavdrag. "
                "ROT max 50 000 kr, RUT max 75 000 kr, kombinerat max 75 000 kr per person och år."
            )

            rantor_a_år  = berakna_rantor(st.session_state["lan_belopp_a"], st.session_state["lan_ranta_a"])
            rantor_b_år  = berakna_rantor(st.session_state["lan_belopp_b"], st.session_state["lan_ranta_b"])
            ranteavd_a_år = berakna_ranteavdrag(rantor_a_år)["skatteminskning/år"]
            ranteavd_b_år = berakna_ranteavdrag(rantor_b_år)["skatteminskning/år"]

            rot_avd_a = min(round(st.session_state["rot_a"] * 0.30), 50_000)
            rut_avd_a = min(round(st.session_state["rut_a"] * 0.50), 75_000)
            rot_avd_b = min(round(st.session_state["rot_b"] * 0.30), 50_000)
            rut_avd_b = min(round(st.session_state["rut_b"] * 0.50), 75_000)
            rotrut_a  = min(rot_avd_a + rut_avd_a, 75_000)   # årstak 75 000 kr
            rotrut_b  = min(rot_avd_b + rut_avd_b, 75_000)

            # Plan-skatt-uppslagning: (år, mån) → skatt
            plan_skatt_a = dict(zip(months_list, skatt_a_list))
            plan_skatt_b = dict(zip(months_list, skatt_b_list))

            # Månader utanför planen → antag heltidslön
            heltid_skatt_a = berakna_skatt(lon_a, ki_a, kyrkoavg_a)["total_skatt/mån"]
            heltid_skatt_b = berakna_skatt(lon_b, ki_b, kyrkoavg_b)["total_skatt/mån"]

            years_in_plan = sorted(set(ar for ar, _ in months_list))

            for ar in years_in_plan:
                # Helårsskatt: planmånader från chart_rows, övriga = heltidslön
                årets_skatt_a = sum(
                    plan_skatt_a.get((ar, m), heltid_skatt_a) for m in range(1, 13)
                )
                årets_skatt_b = sum(
                    plan_skatt_b.get((ar, m), heltid_skatt_b) for m in range(1, 13)
                )

                totalt_avd_a  = ranteavd_a_år + rotrut_a
                totalt_avd_b  = ranteavd_b_år + rotrut_b
                skatt_efter_a = årets_skatt_a - totalt_avd_a
                skatt_efter_b = årets_skatt_b - totalt_avd_b

                st.markdown(f"**{ar}**")
                df_avd = pd.DataFrame({
                    "": [
                        "Betald skatt helår (plan + heltidslön övriga mån)",
                        "Ränteavdrag (30 % av räntekostnader)",
                        "ROT-avdrag",
                        "RUT-avdrag",
                        "Totala avdrag",
                        "Skatt efter avdrag",
                    ],
                    namn_a: [
                        f"{årets_skatt_a:,} kr",
                        f"{ranteavd_a_år:,} kr",
                        f"{rot_avd_a:,} kr",
                        f"{rut_avd_a:,} kr",
                        f"{totalt_avd_a:,} kr",
                        f"{skatt_efter_a:,} kr",
                    ],
                    namn_b: [
                        f"{årets_skatt_b:,} kr",
                        f"{ranteavd_b_år:,} kr",
                        f"{rot_avd_b:,} kr",
                        f"{rut_avd_b:,} kr",
                        f"{totalt_avd_b:,} kr",
                        f"{skatt_efter_b:,} kr",
                    ],
                }).set_index("")

                # Fånga rätt värden i closure via default-argument
                def _style_avd(row, sa=skatt_efter_a, sb=skatt_efter_b):
                    if row.name == "Skatt efter avdrag":
                        ca = "color: green; font-weight: bold" if sa >= 0 else "color: red; font-weight: bold"
                        cb = "color: green; font-weight: bold" if sb >= 0 else "color: red; font-weight: bold"
                        return [ca, cb]
                    return ["", ""]

                st.dataframe(df_avd.style.apply(_style_avd, axis=1), use_container_width=True)

                for _namn, _avd, _sk in [
                    (namn_a, totalt_avd_a, årets_skatt_a),
                    (namn_b, totalt_avd_b, årets_skatt_b),
                ]:
                    if _avd > _sk:
                        st.warning(
                            f"⚠️ {_namn}s skatteavdrag ({_avd:,} kr) överstiger betald skatt "
                            f"{ar} ({_sk:,} kr). Överskjutande avdrag på "
                            f"{_avd - _sk:,} kr kan inte utnyttjas och går förlorade."
                        )

            st.divider()

            # ── Sammanfattning ────────────────────────────────────────
            antal_barn_totalt = st.session_state["antal_barn"] + 1
            rantor_a  = berakna_rantor(st.session_state["lan_belopp_a"], st.session_state["lan_ranta_a"])
            rantor_b  = berakna_rantor(st.session_state["lan_belopp_b"], st.session_state["lan_ranta_b"])
            fk_res_a = berakna_fk_ersattning(lon_a, kommunalskatt=ki_a)
            fk_res_b = berakna_fk_ersattning(lon_b, kommunalskatt=ki_b)
            fl_res_a = fl_r_a
            fl_res_b = fl_r_b

            st.caption(
                f"Totalt antal barn: **{antal_barn_totalt}**  |  "
                f"Räntekostnad {namn_a}: {rantor_a:,} kr/år  |  "
                f"Räntekostnad {namn_b}: {rantor_b:,} kr/år")

            # ── Ersättning per uttaksnivå ─────────────────────────────
            st.subheader("Ersättning vid föräldraledighet (belopp efter skatt)")

            VECKOR_MÅN = 4.33   # genomsnittligt antal veckor per månad

            def _uttaks_tabell(fk_res, fl_res, ki):
                lg_netto = 180 * (1 - ki)   # lägstanivå netto kr/dag efter skatt
                rader = []
                for fk_v in range(1, 8):
                    fk_sgi = min(fk_v, 5)                   # sjukpenningnivå-dagar/vecka
                    fk_lg  = max(fk_v - 5, 0)               # lägstanivå-dagar/vecka (helg)
                    fk_mån = round(
                        (fk_res["fk_netto/dag"] * fk_sgi + lg_netto * fk_lg) * VECKOR_MÅN
                    )
                    if fl_res["max_månader"] > 0:
                        fl_mån = round(
                            fl_res["foraldralon/mån"] * (1 - ki) * fk_sgi / 5
                        )
                    else:
                        fl_mån = 0
                    rader.append({
                        "FK-dagar/vecka":                    fk_v,
                        "FK-ersättning/mån (efter skatt)":   f"{fk_mån:,} kr",
                        "Föräldralön/mån (efter skatt)":     f"{fl_mån:,} kr",
                        "Totalt/mån (efter skatt)":          f"{fk_mån + fl_mån:,} kr",
                    })
                return pd.DataFrame(rader).set_index("FK-dagar/vecka")

            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown(f"**{namn_a}**")
                st.table(_uttaks_tabell(fk_res_a, fl_res_a, ki_a))
            with tc2:
                st.markdown(f"**{namn_b}**")
                st.table(_uttaks_tabell(fk_res_b, fl_res_b, ki_b))
            st.caption(
                "Beloppen är schablonberäknade utifrån ett månadsgenomsnitt (4,33 veckor/månad). "
                "Grafen ovan visar faktiska belopp per kalendermånad."
            )
