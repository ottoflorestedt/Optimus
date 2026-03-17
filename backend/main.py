"""
Föräldrakalkylator – FastAPI backend.

Exponerar kalkyllogiken från kalkyl.py som ett REST-API.
Planerings- och månadsberäkningsfunktionerna är portade från app.py (utan Streamlit-beroenden).
"""
from datetime import date, timedelta
from typing import List, Optional, Union, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

from kalkyl import berakna_skatt, berakna_fk_ersattning, berakna_foraldralon, berakna_ranteavdrag
from skattesatser import KOMMUNALSKATT_2026, KYRKOAVGIFT_2026, kommunkod_till_namn
from kollektivavtal import KOLLEKTIVAVTAL  # noqa: F401 – tillgänglig för informationsändamål

# ── FastAPI-app ────────────────────────────────────────────────
app = FastAPI(
    title="Föräldrakalkylator API",
    description="Beräknar veckoplan och skatteavdrag för föräldraledighetsplanering.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
#  Pydantic-modeller – indata
# ══════════════════════════════════════════════════════════════

class Period(BaseModel):
    """En sammanhängande ledighetsperiod för en förälder."""
    model_config = ConfigDict(populate_by_name=True)

    start: date
    slut: date
    fk_v: int = Field(5, ge=0, le=7, alias="dagar_per_vecka", description="FK-dagar per vecka (0–7)")
    sem_dagar: int = Field(0, ge=0, description="Totalt antal semesterdagar i perioden")
    sem_start: Optional[date] = Field(None, description="Semesterperiodens startdatum")
    sem_slut: Optional[date] = Field(None, description="Semesterperiodens slutdatum")


class Lan(BaseModel):
    """Ett lån med belopp och årsränta."""
    belopp: int = Field(0, ge=0, description="Lånebelopp i kr")
    ranta: float = Field(0.0, ge=0.0, le=30.0, description="Årsränta i procent (t.ex. 2.5)")


class AnpassatAvtal(BaseModel):
    """Eget föräldralönsavtal när inget kollektivavtal matchar."""
    procent_under_tak: float = Field(0.10, description="Andel av lön under lönetak (t.ex. 0.10)")
    procent_over_tak: float = Field(0.90, description="Andel av lön över lönetak (t.ex. 0.90)")
    loenetak: int = Field(49333, description="Lönegräns i kr/månad")
    max_manader: int = Field(6, ge=0, description="Max antal månader med föräldralön")
    krav_manader: int = Field(12, ge=0, description="Minsta anställningstid i månader")
    fast_belopp: float = Field(0.0, ge=0.0, description="Fast månatlig föräldralön (kr), åsidosätter procentberäkning")


class SemesterPeriod(BaseModel):
    """En fristående semesterperiod."""
    start: str            # "YYYY-MM-DD"
    slut: Optional[str] = None  # "YYYY-MM-DD"; beräknas från start+dagar om utelämnat
    dagar: int            # antal semesterdagar (arbetsdagar)


class Sjukskrivning(BaseModel):
    """En sjukskrivningsperiod."""
    start: str        # "YYYY-MM-DD"
    slut: str         # "YYYY-MM-DD"
    grad: int = 100   # 25, 50, 75 eller 100 (procent)


class ForaldrarIndata(BaseModel):
    """Alla indata för en förälder."""
    model_config = ConfigDict(populate_by_name=True)

    namn: str = Field("Förälder", description="Förälderns namn (visningsnamn)")
    manadslon: int = Field(40000, ge=1, description="Månadslön brutto (kr)")
    avtal: Union[str, AnpassatAvtal] = Field(
        "Ingen föräldralön",
        alias="kollektivavtal",
        description=(
            "Kollektivavtalsnamn (t.ex. 'Unionen', 'Finansförbundet') "
            "eller 'Ingen föräldralön', eller ett AnpassatAvtal-objekt."
        ),
    )
    anstallning: int = Field(12, ge=0, description="Anställningstid i månader")
    lan: List[Lan] = Field(default_factory=list, description="Lista med lån (max 10)")
    rot: int = Field(0, ge=0, description="Planerade ROT-utgifter per år (kr)")
    rut: int = Field(0, ge=0, description="Planerade RUT-utgifter per år (kr)")
    kyrka: bool = Field(False, description="Betalar kyrkoavgift")
    forsamling: str = Field("", description="Församlingsnamn (används om kyrka=true)")
    kommun_kod: Optional[str] = Field(None, description="SCB-kommunkod (t.ex. '0180')")
    perioder: List[Period] = Field(default_factory=list, description="Ledighetsperioder")
    semester_perioder: List[SemesterPeriod] = Field(default_factory=list, description="Fristående semesterperioder")
    tio_dagar_start: Optional[str] = Field(None, description="Startdatum för 10-dagarna (YYYY-MM-DD)")
    tio_dagar_antal: int = Field(0, ge=0, le=10, description="Antal tio-dagar som ska tas ut (max 10)")
    sjukskrivningar: List[Sjukskrivning] = Field(default_factory=list, description="Sjukskrivningsperioder")
    fast_belopp: float = Field(0.0, ge=0.0, description="Fast månatlig föräldralön (kr) när kollektivavtal='Ange föräldralön själv'")


class Indata(BaseModel):
    """Alla indata till /berakna-endpointen."""
    model_config = ConfigDict(populate_by_name=True)

    foraldrar_a: ForaldrarIndata
    foraldrar_b: ForaldrarIndata
    antal_barn: int = Field(0, ge=0, description="Antal barn utöver det planerade (0 = ett barn)")
    sparade_sgi_a: int = Field(0, ge=0, le=195, description="Sparade SGI-dagar förälder A")
    sparade_sgi_b: int = Field(0, ge=0, le=195, description="Sparade SGI-dagar förälder B")
    sparade_lagsta_a: int = Field(0, ge=0, le=45, description="Sparade lägstanivådagar förälder A")
    sparade_lagsta_b: int = Field(0, ge=0, le=45, description="Sparade lägstanivådagar förälder B")
    kommun: str = Field("Stockholm", description="Hemkommun (används för kommunalskatt, åsidosätts av kommun_kod per förälder)")
    lan: List[Lan] = Field(default_factory=list, description="Gemensamma lån som fördelas till båda föräldrarna")


# ══════════════════════════════════════════════════════════════
#  Hjälpfunktioner (portade från app.py utan Streamlit-beroenden)
# ══════════════════════════════════════════════════════════════

def _berakna_rantor(lan_lista: List[Lan]) -> int:
    return round(sum(l.belopp * l.ranta / 100 for l in lan_lista if l.belopp > 0 and l.ranta > 0))


def _berakna_rot_rut_avdrag(rot: int, rut: int):
    """
    ROT: 30 % av utgifterna, max 50 000 kr.
    RUT: 50 % av utgifterna, max 75 000 kr.
    Kombinerat: max 75 000 kr per person och år.
    Returnerar (rot_avd, rut_avd, kombinerat).
    """
    rot_avd = min(round(rot * 0.30), 50_000)
    rut_avd = min(round(rut * 0.50), 75_000)
    return rot_avd, rut_avd, min(rot_avd + rut_avd, 75_000)


def _get_ki(kommunalskatt_pct: float, kyrka: bool, forsamling: str) -> float:
    """Returnerar kombinerad kommunalskatt+kyrkoavgift som decimal (t.ex. 0.3062)."""
    if kyrka and forsamling and forsamling in KYRKOAVGIFT_2026:
        return KYRKOAVGIFT_2026[forsamling] / 100
    return kommunalskatt_pct / 100


# ASCII-alias för svenska strängar som frontends utan unicode kan skicka
_AVTAL_ALIAS: Dict[str, str] = {
    "Ingen foraldralon":        "Ingen föräldralön",
    "Ange foraldraelon sjaelv": "Ange föräldralön själv",
    "Ange foraldralon sjalv":   "Ange föräldralön själv",
}


def _normalisera_avtal(avtal) -> object:
    """Returnerar avtalet med svenska tecken om ett ASCII-alias matchar."""
    if isinstance(avtal, str):
        return _AVTAL_ALIAS.get(avtal, avtal)
    return avtal


def _avtal_for_calc(f: ForaldrarIndata) -> Union[str, dict]:
    """Konverterar Pydantic-avtalet till vad berakna_foraldralon förväntar sig."""
    avtal = _normalisera_avtal(f.avtal)
    if avtal == "Ingen föräldralön":
        return "Ingen föräldralön"
    if isinstance(avtal, AnpassatAvtal):
        result: Dict[str, Any] = {
            "procent_under_tak": avtal.procent_under_tak,
            "procent_over_tak":  avtal.procent_over_tak,
            "loenetak":          avtal.loenetak,
            "max_manader":       avtal.max_manader,
            "krav_manader":      avtal.krav_manader,
        }
        if avtal.fast_belopp > 0:
            result["fast_belopp"] = avtal.fast_belopp
        return result
    # "Ange föräldralön själv": fast_belopp ligger på ForaldrarIndata-nivå
    if avtal == "Ange föräldralön själv":
        return {
            "procent_under_tak": 0.10,
            "procent_over_tak":  0.90,
            "loenetak":          49333,
            "max_manader":       18,   # täcker typiska föräldraledigheter
            "krav_manader":      0,    # inget krav – användaren anger beloppet explicit
            "fast_belopp":       f.fast_belopp,
        }
    return avtal  # kollektivavtalsnamn, t.ex. "Unionen"


# ── Portad från app.py: _wd_i_vecka ──────────────────────────

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


# ── Portad från app.py: generera_plan_veckor ─────────────────

def _sjuk_faser(wd_start: int, wd_end: int):
    """Delar upp löpande arbetsdagar [wd_start, wd_end] i sjukfaser.
    Returnerar (sjuklön_dagar, fk_dagar, lång_fk_dagar).
    Fas 1: dag 1-14 (sjuklöneperiod), Fas 2: dag 15-90 (FK sjukpenning), Fas 3: dag 91+.
    """
    sjuklon = max(0, min(wd_end, 14) - (wd_start - 1))
    fk_d    = max(0, min(wd_end, 90) - max(wd_start - 1, 14))
    lag     = max(0, wd_end - max(wd_start - 1, 90))
    return sjuklon, fk_d, lag


def _generera_plan_veckor(
    perioder_a: List[Period],
    perioder_b: List[Period],
    semester_perioder_a: Optional[List[SemesterPeriod]] = None,
    semester_perioder_b: Optional[List[SemesterPeriod]] = None,
    tio_start_a: Optional[date] = None,
    tio_antal_a: int = 0,
    tio_start_b: Optional[date] = None,
    tio_antal_b: int = 0,
    sjukskrivningar_a: Optional[List[Sjukskrivning]] = None,
    sjukskrivningar_b: Optional[List[Sjukskrivning]] = None,
) -> List[dict]:
    """
    Skapar en lista av vecko-dicts från ledighetsperioder per förälder.
    Varje rad har nycklarna: vecka, ar, datum_start, datum_slut,
    fk_a, lg_a, sem_a, tio_a, sjuk_lon_a, sjuk_fk_a, sjuk_lag_a,
    sjuk_grad_a, sjuk_karens_a, ledig_a (samt B-varianter).

    semester_perioder_a/b är fristående semesterperioder. Dagar ersätter
    fk-dagar när personen är ledig, eller räknas som semesterdagar annars.
    tio_start_a/b markerar 10-dagar (tillfällig FP), påverkar ej fk.
    sjukskrivningar_a/b: tre faser – sjuklön (dag 1-14), FK (15-90), lång-FK (91+).
    """
    # Parsa sjukskrivningar tidigt för att inkludera i global_start/global_end
    _sk_a = sjukskrivningar_a or []
    _sk_b = sjukskrivningar_b or []
    sk_parsed_a = [(date.fromisoformat(s.start), date.fromisoformat(s.slut), s.grad) for s in _sk_a]
    sk_parsed_b = [(date.fromisoformat(s.start), date.fromisoformat(s.slut), s.grad) for s in _sk_b]
    sk_wd_a = [0] * len(_sk_a)  # löpande räknare: hur många sjuk-arbetsdagar redan konsumerade
    sk_wd_b = [0] * len(_sk_b)

    all_dates = [getattr(p, k) for p in perioder_a + perioder_b for k in ("start", "slut")]
    # Inkludera sjukskrivningsdatum så att veckoplanen täcker hela sjukperioden,
    # även om den börjar/slutar utanför föräldraledighetens datum.
    for ss, se, _ in sk_parsed_a + sk_parsed_b:
        all_dates += [ss, se]
    if not all_dates:
        return []

    global_start = min(all_dates)
    global_end   = max(all_dates)
    monday       = global_start - timedelta(days=global_start.weekday())
    sem_kvar_a   = [p.sem_dagar for p in perioder_a]
    sem_kvar_b   = [p.sem_dagar for p in perioder_b]

    # Parsa fristående semesterperioder till date-objekt och tracka kvarvarande dagar
    _sp_a = semester_perioder_a or []
    _sp_b = semester_perioder_b or []
    def _sp_slut(sp) -> date:
        """Returnerar slutdatum för semesterperiod. Om slut saknas: start + ceil(dagar×7/5) dagar."""
        if sp.slut:
            return date.fromisoformat(sp.slut)
        return date.fromisoformat(sp.start) + timedelta(days=max(sp.dagar * 7 // 5 + 7, 14))

    sp_parsed_a = [(date.fromisoformat(sp.start), _sp_slut(sp)) for sp in _sp_a]
    sp_parsed_b = [(date.fromisoformat(sp.start), _sp_slut(sp)) for sp in _sp_b]
    sp_kvar_a   = [sp.dagar for sp in _sp_a]
    sp_kvar_b   = [sp.dagar for sp in _sp_b]

    # 10-dagar: fönster = [tio_start, tio_start + 59 dagar], max antal arbetsdagar = tio_antal
    tio_slut_a = (tio_start_a + timedelta(days=59)) if tio_start_a else None
    tio_slut_b = (tio_start_b + timedelta(days=59)) if tio_start_b else None
    tio_kvar_a = tio_antal_a
    tio_kvar_b = tio_antal_b

    veckor: List[dict] = []

    while monday <= global_end:
        friday = monday + timedelta(days=4)
        iso    = monday.isocalendar()

        fk_a, s_a, ledig_a = 0, 0, False
        for i, p in enumerate(perioder_a):
            leave = _wd_i_vecka(monday, p.start, p.slut)
            if leave > 0:
                ledig_a = True
                ss = p.sem_start if p.sem_dagar > 0 else None
                se = p.sem_slut  if p.sem_dagar > 0 else None
                s  = min(_wd_i_vecka(monday, ss, se), sem_kvar_a[i], leave)
                sem_kvar_a[i] -= s
                s_a  += s
                fk_a += min(min(p.fk_v, 5), leave - s) + max(p.fk_v - 5, 0)

        # Fristående semesterperioder för A: sem ersätter fk om personen är ledig
        for i, (sp_start, sp_slut) in enumerate(sp_parsed_a):
            overlap = _wd_i_vecka(monday, sp_start, sp_slut)
            take    = min(overlap, sp_kvar_a[i])
            if take > 0:
                sp_kvar_a[i] -= take
                s_a          += take
                fk_a          = max(0, fk_a - take)

        # 10-dagar för A: räknas separat, påverkar ej fk
        t_a = 0
        if tio_start_a and tio_kvar_a > 0:
            overlap = _wd_i_vecka(monday, tio_start_a, tio_slut_a)
            take    = min(overlap, tio_kvar_a)
            if take > 0:
                tio_kvar_a -= take
                t_a         = take

        fk_b, s_b, ledig_b = 0, 0, False
        for i, p in enumerate(perioder_b):
            leave = _wd_i_vecka(monday, p.start, p.slut)
            if leave > 0:
                ledig_b = True
                ss = p.sem_start if p.sem_dagar > 0 else None
                se = p.sem_slut  if p.sem_dagar > 0 else None
                s  = min(_wd_i_vecka(monday, ss, se), sem_kvar_b[i], leave)
                sem_kvar_b[i] -= s
                s_b  += s
                fk_b += min(min(p.fk_v, 5), leave - s) + max(p.fk_v - 5, 0)

        # Fristående semesterperioder för B: sem ersätter fk om personen är ledig
        for i, (sp_start, sp_slut) in enumerate(sp_parsed_b):
            overlap = _wd_i_vecka(monday, sp_start, sp_slut)
            take    = min(overlap, sp_kvar_b[i])
            if take > 0:
                sp_kvar_b[i] -= take
                s_b          += take
                fk_b          = max(0, fk_b - take)

        # 10-dagar för B: räknas separat, påverkar ej fk
        t_b = 0
        if tio_start_b and tio_kvar_b > 0:
            overlap = _wd_i_vecka(monday, tio_start_b, tio_slut_b)
            take    = min(overlap, tio_kvar_b)
            if take > 0:
                tio_kvar_b -= take
                t_b         = take

        # Sjukskrivningar A: dela upp per fas, karens på dag 1
        sjuk_lon_a = sjuk_fk_a_v = sjuk_lag_a = 0
        sjuk_grad_a_v = 100
        sjuk_karens_a = False
        for i, (ss, se, grad) in enumerate(sk_parsed_a):
            overlap = _wd_i_vecka(monday, ss, se)
            if overlap > 0:
                wd_start = sk_wd_a[i] + 1
                wd_end   = sk_wd_a[i] + overlap
                sl, fkd, lg = _sjuk_faser(wd_start, wd_end)
                sjuk_lon_a   += sl
                sjuk_fk_a_v  += fkd
                sjuk_lag_a   += lg
                sjuk_grad_a_v = grad
                if wd_start == 1:
                    sjuk_karens_a = True
                sk_wd_a[i] += overlap

        # Sjukskrivningar B: dela upp per fas, karens på dag 1
        sjuk_lon_b = sjuk_fk_b_v = sjuk_lag_b = 0
        sjuk_grad_b_v = 100
        sjuk_karens_b = False
        for i, (ss, se, grad) in enumerate(sk_parsed_b):
            overlap = _wd_i_vecka(monday, ss, se)
            if overlap > 0:
                wd_start = sk_wd_b[i] + 1
                wd_end   = sk_wd_b[i] + overlap
                sl, fkd, lg = _sjuk_faser(wd_start, wd_end)
                sjuk_lon_b   += sl
                sjuk_fk_b_v  += fkd
                sjuk_lag_b   += lg
                sjuk_grad_b_v = grad
                if wd_start == 1:
                    sjuk_karens_b = True
                sk_wd_b[i] += overlap

        veckor.append({
            "vecka":          int(iso[1]),
            "ar":             int(iso[0]),
            "datum_start":    monday,
            "datum_slut":     friday,
            "fk_a":           int(fk_a),
            "lg_a":           0,
            "sem_a":          int(s_a),
            "tio_a":          int(t_a),
            "sjuk_lon_a":     int(sjuk_lon_a),
            "sjuk_fk_a":      int(sjuk_fk_a_v),
            "sjuk_lag_a":     int(sjuk_lag_a),
            "sjuk_grad_a":    int(sjuk_grad_a_v),
            "sjuk_karens_a":  sjuk_karens_a,
            "ledig_a":        ledig_a,
            "fk_b":           int(fk_b),
            "lg_b":           0,
            "sem_b":          int(s_b),
            "tio_b":          int(t_b),
            "sjuk_lon_b":     int(sjuk_lon_b),
            "sjuk_fk_b":      int(sjuk_fk_b_v),
            "sjuk_lag_b":     int(sjuk_lag_b),
            "sjuk_grad_b":    int(sjuk_grad_b_v),
            "sjuk_karens_b":  sjuk_karens_b,
            "ledig_b":        ledig_b,
        })
        monday += timedelta(weeks=1)

    return veckor


# ── DataFrame-adapter (ersätter pandas.DataFrame i _komponenter_manad) ──

class _Row:
    def __init__(self, d: dict): self._d = d
    def __getitem__(self, key): return self._d[key]


class _DF:
    """Minimalt gränssnitt som efterliknar Pandas DataFrame för _komponenter_manad."""
    def __init__(self, rows: List[dict]): self._rows = rows

    @property
    def iloc(self):
        rows = self._rows
        class _Iloc:
            def __getitem__(self_, i): return _Row(rows[i])  # noqa: N805
        return _Iloc()


# ── Portad från app.py: _komponenter_manad ───────────────────

def _komponenter_manad(ar, man, veckor, df, lon, nettolön_mån, ki,
                       fl_r, fl_bool,
                       col_fk, col_lg, col_sem, col_tio,
                       col_sjuk_lon, col_sjuk_fk, col_sjuk_lag, col_sjuk_grad, col_sjuk_karens,
                       col_ledig, barnbidrag):
    """Beräknar en månads inkomstkomponenter för en förälder givet veckoplan.

    netto_dag = nettolön_mån / 21 inkluderar progressiv statlig inkomstskatt,
    vilket ger korrekt nettolön även för höginkomsttagare.
    Sjuklön/FK/FL använder kommunalskattefaktorn (1-ki) separat, då dessa
    ersättningar normalt understiger statsskattegränsen.
    """
    fk_r = berakna_fk_ersattning(lon, ki)
    # Räkna faktiska arbetsdagar i månaden – används för föräldralön per dag
    _d = date(ar, man, 1)
    wd_i_man = 0
    while _d.month == man:
        if _d.weekday() < 5:
            wd_i_man += 1
        _d += timedelta(days=1)
    # Dagslön baserad på nettolön_mån/21 – inkluderar statlig skatt för höginkomsttagare.
    # brutto_dag används för skatteberäkning (total_b - total_n = faktisk skatt).
    netto_dag  = nettolön_mån / 21
    brutto_dag = lon / 21
    fk_ndag = fk_r["fk_netto/dag"]
    fk_bdag = fk_r["fk_brutto/dag"]
    lg_ndag = 180 * (1 - ki)
    lg_bdag = 180
    fl_ndag = (fl_r["foraldralon/mån"] * (1 - ki) / wd_i_man) if (fl_bool and fl_r["max_månader"] > 0 and wd_i_man) else 0
    fl_bdag = (fl_r["foraldralon/mån"] / wd_i_man) if (fl_bool and fl_r["max_månader"] > 0 and wd_i_man) else 0
    # 10-dagar: timlöneavdrag = lon/21 per dag (brutto)
    tio_avdrag_n = (lon / 21) * (1 - ki)  # netto löneavdrag per tio-dag
    tio_avdrag_b = lon / 21               # brutto löneavdrag per tio-dag
    # Sjuk FK-sjukpenning: SGI * 0.64 / 365 (= 80% av 80% av SGI/365)
    sgi          = min(lon * 12, 592_000)
    fk_sp_brutto = sgi * 0.64 / 365
    fk_sp_netto  = fk_sp_brutto * (1 - ki)
    # AG-tillägg vid FK-sjukpenning (dag 15-90, om kollektivavtal)
    ag_brutto    = (0.10 * min(lon, 49_333) + 0.90 * max(lon - 49_333, 0)) / 21
    ag_netto     = ag_brutto * (1 - ki)
    # Karensavdrag = 20% av genomsnittlig veckolön (en dag)
    karens_brutto = lon * 0.20 / 5
    karens_netto  = karens_brutto * (1 - ki)

    lon_n = lon_b = sem_b = 0.0
    fk_n = fk_b = fl_n = fl_b = sem_n = tio_n = tio_b_sum = sjuk_n = sjuk_b_sum = 0.0
    for i in range(len(veckor)):
        fk  = int(df.iloc[i][col_fk])
        lg  = int(df.iloc[i][col_lg])
        sem = int(df.iloc[i][col_sem])
        tio = int(df.iloc[i][col_tio])
        sk_lon    = int(df.iloc[i][col_sjuk_lon])
        sk_fk     = int(df.iloc[i][col_sjuk_fk])
        sk_lag    = int(df.iloc[i][col_sjuk_lag])
        sk_grad   = int(df.iloc[i][col_sjuk_grad])
        sk_karens = bool(df.iloc[i][col_sjuk_karens])
        n = sum(1 for d in range(5)
                if (veckor[i]["datum_start"] + timedelta(days=d)).year == ar
                and (veckor[i]["datum_start"] + timedelta(days=d)).month == man)
        if n == 0:
            continue
        frac       = n / 5
        ledig      = bool(veckor[i][col_ledig])
        fk_wd      = min(fk, 5)
        total_sjuk = sk_lon + sk_fk + sk_lag
        arb        = 0 if ledig else max(0, 5 - fk_wd - lg - sem - tio - total_sjuk)
        tillagg    = lon * 0.0043 * sem * frac
        lon_n += arb * netto_dag  * frac
        lon_b += arb * brutto_dag * frac
        sem_n += sem * netto_dag  * frac + tillagg
        sem_b += sem * brutto_dag * frac + tillagg
        fk_n  += (fk_ndag * fk_wd + lg_ndag * max(fk - 5, 0) + lg_ndag * lg) * frac
        fk_b  += (fk_bdag * fk_wd + lg_bdag * max(fk - 5, 0) + lg_bdag * lg) * frac
        if fl_bool and fk > 0:
            fl_n += fl_ndag * fk_wd * frac
            fl_b += fl_bdag * fk_wd * frac
        # 10-dagar: partiell lön (netto_dag - avdrag) + FK, ingen FL
        if tio > 0:
            tio_n     += (netto_dag  - tio_avdrag_n + fk_ndag) * tio * frac
            tio_b_sum += (brutto_dag - tio_avdrag_b + fk_bdag) * tio * frac
        # Fas 1 – sjuklön (dag 1-14): arbetsgivaren betalar 80% av lön.
        # Sjuklönen ÄR lön → bidrar till lon_n, inte sjuk_n.
        if sk_lon > 0:
            grad_f       = sk_grad / 100
            sjlon_b_dag  = grad_f * 0.80 * lon / 21
            sjlon_n_dag  = sjlon_b_dag * (1 - ki)
            lon_n += sjlon_n_dag * sk_lon * frac
            lon_b += sjlon_b_dag * sk_lon * frac
            if sk_karens:
                lon_n -= karens_netto  * frac
                lon_b -= karens_brutto * frac
        # Fas 2 – FK sjukpenning (dag 15-90): FK + AG-tillägg om avtal
        if sk_fk > 0:
            sjuk_n     += fk_sp_netto  * sk_fk * frac
            sjuk_b_sum += fk_sp_brutto * sk_fk * frac
            if fl_bool:
                sjuk_n     += ag_netto  * sk_fk * frac
                sjuk_b_sum += ag_brutto * sk_fk * frac
        # Fas 3 – lång-FK (dag 91+): FK sjukpenning utan AG-tillägg
        if sk_lag > 0:
            sjuk_n     += fk_sp_netto  * sk_lag * frac
            sjuk_b_sum += fk_sp_brutto * sk_lag * frac
    total_n = lon_n + fk_n + fl_n + sem_n + tio_n + sjuk_n + barnbidrag
    total_b = lon_b + fk_b + fl_b + sem_b + tio_b_sum + sjuk_b_sum + barnbidrag
    return {
        "lon_netto":   round(lon_n),
        "sem_netto":   round(sem_n),
        "fk_netto":    round(fk_n),
        "fl_netto":    round(fl_n),
        "tio_netto":   round(tio_n),
        "sjuk_netto":  round(sjuk_n),
        "bb":          barnbidrag,
        "skatt":       round(total_b - total_n),
        "netto_total": round(total_n),
    }


# ── Hjälpfunktion: FK+FL-tabell per antal dagar ──────────────

def _ersattning_tabell(manadslon: int, avtal: str, anstallning: int, ki: float) -> List[dict]:
    """
    Returnerar en lista med 7 rader (dagar 1–7) med fk_netto, fl_netto och totalt per månad.

    FK-dagar 1–5 ger SGI-baserad ersättning.
    FK-dagar 6–7 ger lägstanivå (180 kr/dag brutto).
    Föräldralön betalas enbart för dagar 1–5 (ej helgdagar).
    """
    fk_r  = berakna_fk_ersattning(manadslon, ki)
    fl_r  = berakna_foraldralon(manadslon, avtal, anstallning)

    fk_ndag = fk_r["fk_netto/dag"]
    lg_ndag = 180 * (1 - ki)
    dpm_per_dag = 365 / 7 / 12          # dagar per månad per veckodag ≈ 4.345

    fl_netto_full = fl_r["foraldralon/mån"] * (1 - ki) if fl_r["max_månader"] > 0 else 0.0

    rows: List[dict] = []
    for d in range(1, 8):
        sgi_dagar = min(d, 5) * dpm_per_dag
        lg_dagar  = max(d - 5, 0) * dpm_per_dag
        fk_netto  = round(fk_ndag * sgi_dagar + lg_ndag * lg_dagar)
        fl_netto  = round(fl_netto_full * min(d, 5) / 5)
        rows.append({"dagar": d, "fk_netto": fk_netto, "fl_netto": fl_netto, "totalt": fk_netto + fl_netto})
    return rows


# ══════════════════════════════════════════════════════════════
#  Endpoints
# ══════════════════════════════════════════════════════════════

@app.get("/health", summary="Hälsokontroll")
def health():
    return {"status": "ok"}


@app.get("/ersattning_per_dag", summary="FK-ersättning och föräldralön per antal FK-dagar/vecka")
def ersattning_per_dag(
    manadslon_a: int = 40000,
    avtal_a: str = "Ingen föräldralön",
    kommun_kod_a: Optional[str] = None,
    anstallning_a: int = 12,
    manadslon_b: int = 40000,
    avtal_b: str = "Ingen föräldralön",
    kommun_kod_b: Optional[str] = None,
    anstallning_b: int = 12,
    kommun: str = "Stockholm",
):
    """
    Returnerar en tabell (dagar 1–7 per vecka) med fk_netto, fl_netto och totalt
    för varje förälder. Används för att visa förväntad månadsersättning per ambitionsnivå.
    """
    def _ki(kommun_kod: Optional[str]) -> float:
        namn = kommunkod_till_namn(kommun_kod) if kommun_kod else kommun
        return KOMMUNALSKATT_2026.get(namn, KOMMUNALSKATT_2026["Stockholm"]) / 100

    ki_a = _ki(kommun_kod_a)
    ki_b = _ki(kommun_kod_b)

    return {
        "foraldrar_a": _ersattning_tabell(manadslon_a, avtal_a, anstallning_a, ki_a),
        "foraldrar_b": _ersattning_tabell(manadslon_b, avtal_b, anstallning_b, ki_b),
    }


@app.post("/berakna", summary="Beräkna veckoplan och skatteavdragstabell")
def berakna(indata: Indata):
    """
    Tar emot alla indata-parametrar och returnerar:
    - `plan_veckor`: en rad per vecka med FK/LG/semester-dagar per förälder
    - `manadsinkomst_a` / `manadsinkomst_b`: nettoinkomst per månad uppdelad per komponent
    - `skatteavdrag`: betald skatt, ränteavdrag, ROT/RUT och skatt efter avdrag per kalenderår
    """
    # ── Kommunal- och kyrkoavgift ─────────────────────────────
    def _resolve_kommunalskatt(f: ForaldrarIndata) -> float:
        if f.kommun_kod:
            namn = kommunkod_till_namn(f.kommun_kod)
            return KOMMUNALSKATT_2026.get(namn, KOMMUNALSKATT_2026["Stockholm"])
        return KOMMUNALSKATT_2026.get(indata.kommun, KOMMUNALSKATT_2026["Stockholm"])

    kommunalskatt_a = _resolve_kommunalskatt(indata.foraldrar_a)
    kommunalskatt_b = _resolve_kommunalskatt(indata.foraldrar_b)
    ki_a = _get_ki(kommunalskatt_a, indata.foraldrar_a.kyrka, indata.foraldrar_a.forsamling)
    ki_b = _get_ki(kommunalskatt_b, indata.foraldrar_b.kyrka, indata.foraldrar_b.forsamling)
    kyrkoavg_a = max(0.0, ki_a - kommunalskatt_a / 100)
    kyrkoavg_b = max(0.0, ki_b - kommunalskatt_b / 100)

    lon_a = indata.foraldrar_a.manadslon
    lon_b = indata.foraldrar_b.manadslon

    # ── Föräldralön ───────────────────────────────────────────
    avtal_a = _avtal_for_calc(indata.foraldrar_a)
    avtal_b = _avtal_for_calc(indata.foraldrar_b)
    fl_r_a  = berakna_foraldralon(lon_a, avtal_a, indata.foraldrar_a.anstallning)
    fl_r_b  = berakna_foraldralon(lon_b, avtal_b, indata.foraldrar_b.anstallning)
    fl_a    = fl_r_a["max_månader"] > 0
    fl_b    = fl_r_b["max_månader"] > 0

    # ── Nettolön heltid ───────────────────────────────────────
    nettolön_mån_a = berakna_skatt(lon_a, ki_a, kyrkoavg_a)["nettolön/mån"]
    nettolön_mån_b = berakna_skatt(lon_b, ki_b, kyrkoavg_b)["nettolön/mån"]

    # ── Veckoplan ─────────────────────────────────────────────
    def _parse_tio_start(f: ForaldrarIndata) -> Optional[date]:
        return date.fromisoformat(f.tio_dagar_start) if f.tio_dagar_start else None

    veckor = _generera_plan_veckor(
        indata.foraldrar_a.perioder,
        indata.foraldrar_b.perioder,
        indata.foraldrar_a.semester_perioder,
        indata.foraldrar_b.semester_perioder,
        tio_start_a=_parse_tio_start(indata.foraldrar_a),
        tio_antal_a=indata.foraldrar_a.tio_dagar_antal,
        tio_start_b=_parse_tio_start(indata.foraldrar_b),
        tio_antal_b=indata.foraldrar_b.tio_dagar_antal,
        sjukskrivningar_a=indata.foraldrar_a.sjukskrivningar,
        sjukskrivningar_b=indata.foraldrar_b.sjukskrivningar,
    )
    if not veckor:
        return {"plan_veckor": [], "manadsinkomst_a": [], "manadsinkomst_b": [], "skatteavdrag": {}}

    df = _DF(veckor)

    # ── Månadsberäkning ───────────────────────────────────────
    bb_mån = round(1250 * indata.antal_barn / 2)
    # Basera y0/m0 på faktiska startdatum för perioder/sjukskrivningar, inte
    # veckoplaneringsveckans måndag (som kan ligga månaden INNAN ledigheten börjar
    # och ge månaden felaktig partiell täckning istället för normal inkomst).
    _event_starts: List[date] = (
        [p.start for p in indata.foraldrar_a.perioder + indata.foraldrar_b.perioder]
        + [date.fromisoformat(s.start) for s in indata.foraldrar_a.sjukskrivningar + indata.foraldrar_b.sjukskrivningar]
    )
    _first_event = min(_event_starts) if _event_starts else veckor[0]["datum_start"]
    y0, m0 = _first_event.year, _first_event.month
    # Sista månaden = sista datum bland perioder OCH sjukskrivningar
    _all_period_ends = [p.slut for p in indata.foraldrar_a.perioder + indata.foraldrar_b.perioder]
    _all_sjuk_ends   = [date.fromisoformat(s.slut)
                        for s in indata.foraldrar_a.sjukskrivningar + indata.foraldrar_b.sjukskrivningar]
    _all_ends = _all_period_ends + _all_sjuk_ends
    _last_day  = max(_all_ends) if _all_ends else veckor[-1]["datum_start"]
    y1, m1 = _last_day.year, _last_day.month
    months_list: List[tuple] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        months_list.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1

    MAN = ["Jan","Feb","Mar","Apr","Maj","Jun","Jul","Aug","Sep","Okt","Nov","Dec"]
    komp_a: List[dict] = []
    komp_b: List[dict] = []
    for ar, man in months_list:
        ka = _komponenter_manad(ar, man, veckor, df, lon_a, nettolön_mån_a, ki_a,
                                fl_r_a, fl_a, "fk_a", "lg_a", "sem_a", "tio_a",
                                "sjuk_lon_a", "sjuk_fk_a", "sjuk_lag_a", "sjuk_grad_a", "sjuk_karens_a",
                                "ledig_a", bb_mån)
        kb = _komponenter_manad(ar, man, veckor, df, lon_b, nettolön_mån_b, ki_b,
                                fl_r_b, fl_b, "fk_b", "lg_b", "sem_b", "tio_b",
                                "sjuk_lon_b", "sjuk_fk_b", "sjuk_lag_b", "sjuk_grad_b", "sjuk_karens_b",
                                "ledig_b", bb_mån)
        komp_a.append({"ar": ar, "man": man, "manad": f"{MAN[man-1]} {ar}", **ka})
        komp_b.append({"ar": ar, "man": man, "manad": f"{MAN[man-1]} {ar}", **kb})

    # ── 6 månader normalinkomst före och efter ledigheten ─────
    def _add_months(yr: int, mo: int, n: int):
        mo += n
        yr += (mo - 1) // 12
        mo = (mo - 1) % 12 + 1
        return yr, mo

    def _normalmanad(ar, man, lon_netto, skatt, bb):
        return {
            "ar": ar, "man": man,
            "manad":     f"{MAN[man-1]} {ar}",
            "lon_netto":  lon_netto,
            "sem_netto":  0,
            "fk_netto":   0,
            "fl_netto":   0,
            "tio_netto":  0,
            "sjuk_netto": 0,
            "bb":         bb,
            "skatt":     skatt,
            "netto_total": lon_netto + bb,
        }

    skatt_a = berakna_skatt(lon_a, ki_a, kyrkoavg_a)["total_skatt/mån"]
    skatt_b = berakna_skatt(lon_b, ki_b, kyrkoavg_b)["total_skatt/mån"]

    fore_a  = [_normalmanad(*_add_months(y0, m0, i - 6), nettolön_mån_a, skatt_a, 0) for i in range(6)]
    fore_b  = [_normalmanad(*_add_months(y0, m0, i - 6), nettolön_mån_b, skatt_b, 0) for i in range(6)]
    efter_a = [_normalmanad(*_add_months(y1, m1, i + 1), nettolön_mån_a, skatt_a, bb_mån) for i in range(6)]
    efter_b = [_normalmanad(*_add_months(y1, m1, i + 1), nettolön_mån_b, skatt_b, bb_mån) for i in range(6)]

    komp_a = fore_a + komp_a + efter_a
    komp_b = fore_b + komp_b + efter_b

    # ── Skatteavdragstabell ───────────────────────────────────
    plan_skatt_a = {(ar, man): k["skatt"] for k, (ar, man) in zip(komp_a, months_list)}
    plan_skatt_b = {(ar, man): k["skatt"] for k, (ar, man) in zip(komp_b, months_list)}
    heltid_skatt_a = berakna_skatt(lon_a, ki_a, kyrkoavg_a)["total_skatt/mån"]
    heltid_skatt_b = berakna_skatt(lon_b, ki_b, kyrkoavg_b)["total_skatt/mån"]

    lan_a      = list(indata.foraldrar_a.lan) + list(indata.lan)
    lan_b      = list(indata.foraldrar_b.lan) + list(indata.lan)
    rantor_a   = _berakna_rantor(lan_a)
    rantor_b   = _berakna_rantor(lan_b)
    ranteavd_a = berakna_ranteavdrag(rantor_a)["skatteminskning/år"]
    ranteavd_b = berakna_ranteavdrag(rantor_b)["skatteminskning/år"]
    rot_avd_a, rut_avd_a, rotrut_a = _berakna_rot_rut_avdrag(indata.foraldrar_a.rot, indata.foraldrar_a.rut)
    rot_avd_b, rut_avd_b, rotrut_b = _berakna_rot_rut_avdrag(indata.foraldrar_b.rot, indata.foraldrar_b.rut)
    totalt_avd_a = ranteavd_a + rotrut_a
    totalt_avd_b = ranteavd_b + rotrut_b

    years_in_plan = sorted(set(ar for ar, _ in months_list))
    skatteavdrag: Dict[str, dict] = {}
    for ar in years_in_plan:
        arets_skatt_a = sum(plan_skatt_a.get((ar, mn), heltid_skatt_a) for mn in range(1, 13))
        arets_skatt_b = sum(plan_skatt_b.get((ar, mn), heltid_skatt_b) for mn in range(1, 13))
        skatteavdrag[str(ar)] = {
            "a": {
                "namn":              indata.foraldrar_a.namn,
                "betald_skatt":      arets_skatt_a,
                "ranteavdrag":       ranteavd_a,
                "rot_avdrag":        rot_avd_a,
                "rut_avdrag":        rut_avd_a,
                "totalt_avdrag":     totalt_avd_a,
                "skatt_efter_avdrag": arets_skatt_a - totalt_avd_a,
                "varning": (
                    f"Avdrag ({totalt_avd_a:,} kr) overstiger betald skatt ({arets_skatt_a:,} kr)"
                    if totalt_avd_a > arets_skatt_a else None
                ),
            },
            "b": {
                "namn":              indata.foraldrar_b.namn,
                "betald_skatt":      arets_skatt_b,
                "ranteavdrag":       ranteavd_b,
                "rot_avdrag":        rot_avd_b,
                "rut_avdrag":        rut_avd_b,
                "totalt_avdrag":     totalt_avd_b,
                "skatt_efter_avdrag": arets_skatt_b - totalt_avd_b,
                "varning": (
                    f"Avdrag ({totalt_avd_b:,} kr) overstiger betald skatt ({arets_skatt_b:,} kr)"
                    if totalt_avd_b > arets_skatt_b else None
                ),
            },
        }

    # ── Serialisera datum → ISO-strängar i plan_veckor ────────
    plan_veckor = [
        {**v, "datum_start": v["datum_start"].isoformat(), "datum_slut": v["datum_slut"].isoformat()}
        for v in veckor
    ]

    # ── Dagssaldo ─────────────────────────────────────────────
    sp_anvanda_a = sum(v["fk_a"] for v in veckor)
    lg_anvanda_a = sum(v["lg_a"] for v in veckor)
    sp_anvanda_b = sum(v["fk_b"] for v in veckor)
    lg_anvanda_b = sum(v["lg_b"] for v in veckor)
    sp_tot_a = indata.sparade_sgi_a + 195
    lg_tot_a = indata.sparade_lagsta_a + 45
    sp_tot_b = indata.sparade_sgi_b + 195
    lg_tot_b = indata.sparade_lagsta_b + 45

    dagssaldo = {
        "a": {
            "sp_totalt":  sp_tot_a,
            "sp_anvanda": sp_anvanda_a,
            "sp_kvar":    sp_tot_a - sp_anvanda_a,
            "lg_totalt":  lg_tot_a,
            "lg_anvanda": lg_anvanda_a,
            "lg_kvar":    lg_tot_a - lg_anvanda_a,
        },
        "b": {
            "sp_totalt":  sp_tot_b,
            "sp_anvanda": sp_anvanda_b,
            "sp_kvar":    sp_tot_b - sp_anvanda_b,
            "lg_totalt":  lg_tot_b,
            "lg_anvanda": lg_anvanda_b,
            "lg_kvar":    lg_tot_b - lg_anvanda_b,
        },
    }

    return {
        "plan_veckor":     plan_veckor,
        "manadsinkomst_a": komp_a,
        "manadsinkomst_b": komp_b,
        "skatteavdrag":    skatteavdrag,
        "dagssaldo":       dagssaldo,
    }
