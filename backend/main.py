"""
Föräldrakalkylator – FastAPI backend.

Exponerar kalkyllogiken från kalkyl.py som ett REST-API.
Planerings- och månadsberäkningsfunktionerna är portade från app.py (utan Streamlit-beroenden).
"""
import calendar as _cal
from datetime import date, timedelta
from typing import List, Optional, Union, Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict, field_validator

from kalkyl import berakna_skatt, berakna_fk_ersattning, berakna_foraldralon, berakna_ranteavdrag
from skattesatser import KOMMUNALSKATT_2026, KYRKOAVGIFT_2026, kommunkod_till_namn
from kollektivavtal import KOLLEKTIVAVTAL, max_fl_man, FL_FINANSFORBUNDET_MAX_DAGAR  # noqa: F401

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
    dubbeldagar: bool = Field(False, description="Om True: båda föräldrarna får ta FK samtidigt denna period (max 60 dubbeldagar totalt)")
    fk_grad: int = Field(100, ge=25, le=100, description="FK-uttag i procent: 25, 50, 75 eller 100. En hel FK-dag konsumeras oavsett grad.")

    @field_validator("fk_grad")
    @classmethod
    def validera_fk_grad(cls, v):
        if v not in (25, 50, 75, 100):
            raise ValueError("fk_grad måste vara 25, 50, 75 eller 100")
        return v


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
    anstallningstid_manader: Optional[int] = Field(None, ge=0, description="Anställningstid i månader (None = okänd → generöst default, dvs max FL-månader)")


class Indata(BaseModel):
    """Alla indata till /berakna-endpointen."""
    model_config = ConfigDict(populate_by_name=True)

    foraldrar_a: ForaldrarIndata
    foraldrar_b: ForaldrarIndata
    antal_barn: int = Field(0, ge=0, description="Antal barn utöver det planerade (0 = ett barn)")
    antal_foster: int = Field(1, ge=1, le=4, description="Antal foster vid denna graviditet (1=singel, 2=tvillingar)")
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
    "Ingen foraldralon":            "Ingen föräldralön",
    "Ange foraldraelon sjaelv":     "Ange föräldralön själv",
    "Ange foraldralon sjalv":       "Ange föräldralön själv",
    "Byggforetagen (tjansteman)":   "Byggföretagen (tjänstemän)",
    "Svensk Handel (tjansteman)":   "Svensk Handel (tjänstemän)",
    "Stal och metall (tjansteman)": "Stål och metall (tjänstemän)",
    "Vardforbundet (region)":       "Vårdförbundet (region)",   # fix: ö borttaget ur nyckel
    "Innovationsforetagen":         "Innovationsföretagen",
    "Finansforbundet":              "Finansförbundet",
    "Lakarforbundet":               "Läkarförbundet",
    "AFA FPT (arbetare)":           "AFA FPT (arbetare)",
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


def _get_utbetalare(avtal_namn: str) -> str:
    """Returnerar 'afa' om avtalet är AFA FPT, annars 'arbetsgivare'."""
    avtal = KOLLEKTIVAVTAL.get(avtal_namn, {})
    return avtal.get("utbetalare", "arbetsgivare")


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


# ── B-01: Kalenderdagsavdrag vs dagsavdrag ────────────────────

def _period_sammanhangande_wd(p_start: date, p_slut: date) -> int:
    """Räknar arbetsdagar (mån-fre) i perioden [p_start, p_slut]."""
    count = 0
    d = p_start
    while d <= p_slut:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def _bygg_atyp_karta(perioder: List["Period"]) -> List[tuple]:
    """
    Bygger en lista av (start, slut, avdragstyp)-segment för en förälders perioder.

    Regler:
      - fk_v < 5 (deltidsledig): alltid "dag" (bryts varje vecka)
      - Semesterperiod bryter kedjan; del-segmenten bedöms separat.
      - Sammanhängande wd > 5 och fk_v >= 5 → "kalender", annars "dag".
    """
    segments: List[tuple] = []
    for p in perioder:
        if p.fk_v < 5:
            segments.append((p.start, p.slut, "dag"))
            continue
        if p.sem_start and p.sem_slut and p.sem_dagar > 0:
            # Segment före semester
            seg1_slut = p.sem_start - timedelta(days=1)
            if seg1_slut >= p.start:
                wd1 = _period_sammanhangande_wd(p.start, seg1_slut)
                segments.append((p.start, seg1_slut, "kalender" if wd1 > 5 else "dag"))
            # Semesterdagarna räknas inte som FK-avdrag – hoppas över
            # Segment efter semester
            seg2_start = p.sem_slut + timedelta(days=1)
            if seg2_start <= p.slut:
                wd2 = _period_sammanhangande_wd(seg2_start, p.slut)
                segments.append((seg2_start, p.slut, "kalender" if wd2 > 5 else "dag"))
        else:
            wd = _period_sammanhangande_wd(p.start, p.slut)
            segments.append((p.start, p.slut, "kalender" if wd > 5 else "dag"))
    return segments


def _atyp_for_week(monday: date, karta: List[tuple]) -> str:
    """Returnerar avdragstyp ('dag'/'kalender') för veckan startad på monday."""
    friday = monday + timedelta(days=4)
    for seg_start, seg_slut, atyp in karta:
        if monday <= seg_slut and friday >= seg_start:
            return atyp
    return "dag"


def _kal_days_i_manad(ar: int, man: int, atyp_karta: List[tuple]) -> int:
    """
    Summerar faktiska kalenderdagar i 'kalender'-segment som faller i given månad.
    Inkluderar helger – korrekt för perioder som börjar/slutar på helg (t.ex. T6).
    """
    last_dom = _cal.monthrange(ar, man)[1]
    first = date(ar, man, 1)
    last  = date(ar, man, last_dom)
    total = 0
    for seg_start, seg_slut, atyp in atyp_karta:
        if atyp != "kalender":
            continue
        d = max(seg_start, first)
        e = min(seg_slut, last)
        if d <= e:
            total += (e - d).days + 1
    return total


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

    # B-01: Bygg avdragstyp-karta en gång per period (inte per vecka)
    atyp_karta_a = _bygg_atyp_karta(perioder_a)
    atyp_karta_b = _bygg_atyp_karta(perioder_b)

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

        # C-03: FK-grad för veckan (tar lägsta graden om perioder har olika grader)
        fk_grad_a_v = 100
        for p in perioder_a:
            if _wd_i_vecka(monday, p.start, p.slut) > 0:
                fk_grad_a_v = min(fk_grad_a_v, p.fk_grad)
        fk_grad_b_v = 100
        for p in perioder_b:
            if _wd_i_vecka(monday, p.start, p.slut) > 0:
                fk_grad_b_v = min(fk_grad_b_v, p.fk_grad)

        veckor.append({
            "vecka":          int(iso[1]),
            "ar":             int(iso[0]),
            "datum_start":    monday,
            "datum_slut":     friday,
            "fk_grad_a":      fk_grad_a_v,
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
            "avdragstyp_a":   _atyp_for_week(monday, atyp_karta_a),  # B-01
            "fk_grad_b":      fk_grad_b_v,
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
            "avdragstyp_b":   _atyp_for_week(monday, atyp_karta_b),  # B-01
        })
        monday += timedelta(weeks=1)

    return veckor


# ── DataFrame-adapter (ersätter pandas.DataFrame i _komponenter_manad) ──

class _Row:
    def __init__(self, d: dict): self._d = d
    def __getitem__(self, key): return self._d[key]
    def get(self, key, default=None): return self._d.get(key, default)


class _DF:
    """Minimalt gränssnitt som efterliknar Pandas DataFrame för _komponenter_manad."""
    def __init__(self, rows: List[dict]): self._rows = rows

    @property
    def iloc(self):
        rows = self._rows
        class _Iloc:
            def __getitem__(self_, i): return _Row(rows[i])  # noqa: N805
        return _Iloc()


# ── Hjälpfunktion: FK-dagar per månad (Finansförbundet) ──────

def _fk_dagar_manad(ar: int, man: int, veckor: List[dict], col_fk: str) -> float:
    """Summerar FK-dagar (max 5 per vecka) som faller i given månad.
    Används för att spåra FL-förbrukning i dagar för Finansförbundet."""
    total = 0.0
    for v in veckor:
        n = sum(
            1 for d in range(5)
            if (v["datum_start"] + timedelta(days=d)).year == ar
            and (v["datum_start"] + timedelta(days=d)).month == man
        )
        if n > 0:
            total += min(int(v[col_fk]), 5) * (n / 5)
    return total


# ── Portad från app.py: _komponenter_manad ───────────────────

def _komponenter_manad(ar, man, veckor, df, lon, nettolön_mån, ki,
                       fl_r, fl_bool,
                       col_fk, col_lg, col_sem, col_tio,
                       col_sjuk_lon, col_sjuk_fk, col_sjuk_lag, col_sjuk_grad, col_sjuk_karens,
                       col_ledig, barnbidrag,
                       avdragstyp_col="avdragstyp_a",   # B-01
                       atyp_karta=None,                  # B-01
                       fk_grad_col="fk_grad_a"):         # C-03
    """Beräknar en månads inkomstkomponenter för en förälder givet veckoplan.

    netto_dag = nettolön_mån / 21 inkluderar progressiv statlig inkomstskatt,
    vilket ger korrekt nettolön även för höginkomsttagare.
    Sjuklön/FK/FL använder kommunalskattefaktorn (1-ki) separat, då dessa
    ersättningar normalt understiger statsskattegränsen.

    B-01: atyp_karta styr om perioden beräknas med kalender- eller dagsavdrag.
    Korrektionsformeln: lon_n += kal_fk_wd×netto_dag − kal_days×nettolön_mån×12/365.
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
    # A-05: TFP SGI-tak = 7.5 PBB 2026 = 444 000 kr (SFB 13 kap 22 §)
    sgi_tfp = min(lon * 12, 444_000)
    tfp_brutto_dag = sgi_tfp * 0.776 / 365
    tfp_netto_dag  = tfp_brutto_dag * (1 - ki)
    tio_avdrag_n = (lon / 21) * (1 - ki)
    tio_avdrag_b = lon / 21
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

    # Snabbväg: ren arbetsmånad – ingen ledighet, FK, LG, semester, tio-dagar
    # eller sjukskrivning i någon vecka som täcker denna månad.
    # Returnera full nettolön_mån direkt för att eliminera /wd-variation.
    har_special = False
    for i in range(len(veckor)):
        if not any(
            (veckor[i]["datum_start"] + timedelta(days=d)).year == ar
            and (veckor[i]["datum_start"] + timedelta(days=d)).month == man
            for d in range(5)
        ):
            continue
        if (bool(veckor[i][col_ledig])
                or int(df.iloc[i][col_fk])       > 0
                or int(df.iloc[i][col_lg])       > 0
                or int(df.iloc[i][col_sem])      > 0
                or int(df.iloc[i][col_tio])      > 0
                or int(df.iloc[i][col_sjuk_lon]) > 0
                or int(df.iloc[i][col_sjuk_fk])  > 0
                or int(df.iloc[i][col_sjuk_lag]) > 0):
            har_special = True
            break
    if not har_special:
        return {
            "lon_netto":   nettolön_mån,
            "sem_netto":   0,
            "fk_netto":    0,
            "fl_netto":    0,
            "tio_netto":   0,
            "sjuk_netto":  0,
            "bb":          barnbidrag,
            "skatt":       round(lon - nettolön_mån),
            "netto_total": nettolön_mån + barnbidrag,
        }

    lon_n = lon_b = sem_b = 0.0
    fk_n = fk_b = fl_n = fl_b = sem_n = tio_n = tio_b_sum = sjuk_n = sjuk_b_sum = 0.0
    # B-01: dag-avdragsackumulatorer för top-down lönberäkning
    dag_fk_n = dag_fk_b = 0.0        # avdrag (netto/brutto) från dag-ledigatveckor
    lon_sjuk_n = lon_sjuk_b = 0.0    # sjuklönsandel (separerat för top-down)
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
        # C-03: FK-grad för denna vecka (25/50/75/100 → 0.25/0.50/0.75/1.00)
        fk_grad    = int(df.iloc[i].get(fk_grad_col, 100)) / 100

        # ── B-01: top-down lönberäkning ──────────────────────────────
        # Beräknar lon_n top-down (nettolön_mån − dag-avdrag − kal-avdrag) i
        # stället för bottom-up (arbetsdagar × netto_dag).
        # Innebär att semesterveckor, gappveckor m.m. ingår korrekt i basen.
        if atyp_karta is not None:
            if ledig:
                atyp = veckor[i].get(avdragstyp_col, "dag")
                if atyp == "dag":
                    # Dag-avdrag skalas med fk_grad: vid 50% FK jobbar föräldern 50% → halv avdrag
                    dag_fk_n += fk_wd * fk_grad * netto_dag  * frac
                    dag_fk_b += fk_wd * fk_grad * brutto_dag * frac
                # kalender: avdrag beräknas efter loopen via _kal_days_i_manad
        else:
            # Bakåtkompatibelt bottom-up-läge (atyp_karta=None)
            # C-03: vid deltids-FK arbetar föräldern fk_grad av dagen → skala avdraget
            arb = 0 if ledig else max(0, 5 - fk_wd * fk_grad - lg - sem - tio - total_sjuk)
            lon_n += arb * netto_dag  * frac
            lon_b += arb * brutto_dag * frac
        # ─────────────────────────────────────────────────────────────

        tillagg    = lon * 0.0043 * sem * frac
        sem_n += sem * netto_dag  * frac + tillagg
        sem_b += sem * brutto_dag * frac + tillagg
        # C-03: FK-ersättning skalas med fk_grad; helgdagar (>5) och LG påverkas inte av grad
        fk_n  += (fk_ndag * fk_wd * fk_grad + lg_ndag * max(fk - 5, 0) + lg_ndag * lg) * frac
        fk_b  += (fk_bdag * fk_wd * fk_grad + lg_bdag * max(fk - 5, 0) + lg_bdag * lg) * frac
        if fl_bool and fk > 0:
            fl_n += fl_ndag * fk_wd * frac
            fl_b += fl_bdag * fk_wd * frac
        # 10-dagar: partiell lön (netto_dag - avdrag) + FK, ingen FL
        if tio > 0:
            # A-05: Använd TFP-ersättning (7.5 PBB-tak) för 10-dagarna
            tio_n     += (netto_dag  - tio_avdrag_n + tfp_netto_dag) * tio * frac
            tio_b_sum += (brutto_dag - tio_avdrag_b + (sgi_tfp * 0.776 / 365)) * tio * frac
        # Fas 1 – sjuklön (dag 1-14): arbetsgivaren betalar 80% av lön.
        # Sjuklönen ÄR lön → bidrar till lon_n, inte sjuk_n.
        if sk_lon > 0:
            grad_f       = sk_grad / 100
            sjlon_b_dag  = grad_f * 0.80 * lon / 21
            sjlon_n_dag  = sjlon_b_dag * (1 - ki)
            if atyp_karta is not None:
                # Spara separat – kombineras med top-down lon_n efter loopen
                lon_sjuk_n += sjlon_n_dag * sk_lon * frac
                lon_sjuk_b += sjlon_b_dag * sk_lon * frac
                if sk_karens:
                    lon_sjuk_n -= karens_netto  * frac
                    lon_sjuk_b -= karens_brutto * frac
            else:
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

    # B-01: top-down löneberäkning efter loopen
    # lon_n = max(0, nettolön_mån − dag-avdrag − kalender-avdrag) + sjuklönsdel
    # Cap: avdrag får aldrig överstiga månadslönen (lon_n/lon_b ≥ 0).
    if atyp_karta is not None:
        kal_days   = _kal_days_i_manad(ar, man, atyp_karta)
        lon_n = max(0.0, nettolön_mån - dag_fk_n - nettolön_mån * 12 / 365 * kal_days) + lon_sjuk_n
        lon_b = max(0.0, lon          - dag_fk_b - lon          * 12 / 365 * kal_days) + lon_sjuk_b

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

def _ersattning_tabell(manadslon: int, avtal: str, anstallning: int, ki: float, fk_grad: int = 100) -> List[dict]:
    """
    Returnerar en lista med 7 rader (dagar 1–7) med fk_netto, fl_netto och totalt per månad.

    A-06: Alla 7 dagar ger sjukpenningnivå (fk_ndag). Lägstanivå används ej i
    ersättningsslider — slidern visar SGI-baserad ersättning för att ge korrekt
    ekonomisk bild av heltids- vs helguttag.
    C-03a: fk_grad (25/50/75/100) skalar FK- och FL-ersättning proportionellt.
    Föräldralön betalas enbart för dagar 1–5 (ej helgdagar).
    """
    fk_r  = berakna_fk_ersattning(manadslon, ki)
    fl_r  = berakna_foraldralon(manadslon, avtal, anstallning)

    fk_ndag = fk_r["fk_netto/dag"]
    dpm_per_dag = 365 / 7 / 12          # dagar per månad per veckodag ≈ 4.345
    grad = fk_grad / 100                # C-03a: skalningsfaktor

    fl_netto_full = fl_r["foraldralon/mån"] * (1 - ki) if fl_r["max_månader"] > 0 else 0.0

    rows: List[dict] = []
    for d in range(1, 8):
        # A-06: alla d dagar på sjukpenningnivå (fk_ndag), inte lägstanivå för dag 6-7
        fk_netto = round(fk_ndag * d * dpm_per_dag * grad)
        # FL gäller dag 1-5 och skalas med grad (C-03a)
        fl_netto = round(fl_netto_full * min(d, 5) / 5 * grad)
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
    fk_grad_a: int = 100,
    manadslon_b: int = 40000,
    avtal_b: str = "Ingen föräldralön",
    kommun_kod_b: Optional[str] = None,
    anstallning_b: int = 12,
    fk_grad_b: int = 100,
    kommun: str = "Stockholm",
):
    """
    Returnerar en tabell (dagar 1–7 per vecka) med fk_netto, fl_netto och totalt
    för varje förälder. Används för att visa förväntad månadsersättning per ambitionsnivå.

    A-06: dag 6–7 beräknas på sjukpenningnivå (ej lägstanivå).
    C-03a: fk_grad_a/fk_grad_b (25/50/75/100) skalar FK- och FL-ersättning.
    """
    def _ki(kommun_kod: Optional[str]) -> float:
        namn = kommunkod_till_namn(kommun_kod) if kommun_kod else kommun
        return KOMMUNALSKATT_2026.get(namn, KOMMUNALSKATT_2026["Stockholm"]) / 100

    ki_a = _ki(kommun_kod_a)
    ki_b = _ki(kommun_kod_b)

    return {
        "foraldrar_a": _ersattning_tabell(manadslon_a, avtal_a, anstallning_a, ki_a, fk_grad_a),
        "foraldrar_b": _ersattning_tabell(manadslon_b, avtal_b, anstallning_b, ki_b, fk_grad_b),
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

    # ── Barnbidrag ────────────────────────────────────────────
    def _bb_total(n: int) -> int:
        """Totalt barnbidrag + flerbarnstillägg för n barn (2025/2026).
        n=1 → 1 250, n=2 → 2 650, n≥3 → 2 650 + (n-2)×1 250.
        """
        if n <= 0:
            return 0
        if n == 1:
            return 1250
        if n == 2:
            return 2650
        return 2650 + (n - 2) * 1250

    # antal_barn = totalt antal barn i familjen (1 = enbart det planerade barnet).
    # bb_mån      = per förälder (halva totalen) under/efter ledigheten.
    # bb_fore     = per förälder innan det planerade barnet föds;
    #               eventuella syskon är redan födda → deras bb gäller från dag 1.
    n_barn   = max(1, indata.antal_barn)   # minst 1 (det planerade barnet)
    bb_mån   = round(_bb_total(n_barn)     / 2)
    bb_fore  = round(_bb_total(n_barn - 1) / 2)  # 0 om n_barn==1 (inga syskon)

    # ── Månadsberäkning ───────────────────────────────────────
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

    # ── FL-kapacitet per förälder ──────────────────────────────
    # avtal_namn_x = det normaliserade avtalsnamnet (sträng) eller "AnpassatAvtal"
    _anst_a = indata.foraldrar_a.anstallningstid_manader
    _anst_b = indata.foraldrar_b.anstallningstid_manader
    _avtal_namn_a = (
        _normalisera_avtal(indata.foraldrar_a.avtal)
        if isinstance(indata.foraldrar_a.avtal, str)
        else "AnpassatAvtal"
    )
    _avtal_namn_b = (
        _normalisera_avtal(indata.foraldrar_b.avtal)
        if isinstance(indata.foraldrar_b.avtal, str)
        else "AnpassatAvtal"
    )
    max_fl_man_a = max_fl_man(_avtal_namn_a, _anst_a)
    max_fl_man_b = max_fl_man(_avtal_namn_b, _anst_b)
    is_fin_a = _avtal_namn_a == "Finansförbundet"
    is_fin_b = _avtal_namn_b == "Finansförbundet"
    fl_man_a = 0    # månader där fl_netto > 0
    fl_man_b = 0
    fl_dag_a = 0.0  # FK-dagar med FL (Finansförbundet)
    fl_dag_b = 0.0

    # B-01: bygg avdragstyp-kartor för kalender-avdrag-korrektion i _komponenter_manad
    _atyp_karta_a = _bygg_atyp_karta(indata.foraldrar_a.perioder)
    _atyp_karta_b = _bygg_atyp_karta(indata.foraldrar_b.perioder)

    komp_a: List[dict] = []
    komp_b: List[dict] = []
    for ar, man in months_list:
        # FL aktiv denna månad? (ny cap kombineras med befintlig fl_bool)
        if is_fin_a:
            fl_active_a = fl_a and max_fl_man_a > 0 and fl_dag_a < FL_FINANSFORBUNDET_MAX_DAGAR
        else:
            fl_active_a = fl_a and (max_fl_man_a == 999 or fl_man_a < max_fl_man_a)
        if is_fin_b:
            fl_active_b = fl_b and max_fl_man_b > 0 and fl_dag_b < FL_FINANSFORBUNDET_MAX_DAGAR
        else:
            fl_active_b = fl_b and (max_fl_man_b == 999 or fl_man_b < max_fl_man_b)

        ka = _komponenter_manad(ar, man, veckor, df, lon_a, nettolön_mån_a, ki_a,
                                fl_r_a, fl_active_a, "fk_a", "lg_a", "sem_a", "tio_a",
                                "sjuk_lon_a", "sjuk_fk_a", "sjuk_lag_a", "sjuk_grad_a", "sjuk_karens_a",
                                "ledig_a", bb_mån,
                                avdragstyp_col="avdragstyp_a", atyp_karta=_atyp_karta_a,
                                fk_grad_col="fk_grad_a")
        kb = _komponenter_manad(ar, man, veckor, df, lon_b, nettolön_mån_b, ki_b,
                                fl_r_b, fl_active_b, "fk_b", "lg_b", "sem_b", "tio_b",
                                "sjuk_lon_b", "sjuk_fk_b", "sjuk_lag_b", "sjuk_grad_b", "sjuk_karens_b",
                                "ledig_b", bb_mån,
                                avdragstyp_col="avdragstyp_b", atyp_karta=_atyp_karta_b,
                                fk_grad_col="fk_grad_b")

        # Uppdatera FL-räknare
        if ka["fl_netto"] > 0:
            # B-04: Proportionell räkning – partialmånad bränner inte en hel FL-månad
            fk_dagar_a = _fk_dagar_manad(ar, man, veckor, "fk_a")
            fl_man_a += min(1.0, fk_dagar_a / 20)
            if is_fin_a:
                fl_dag_a += _fk_dagar_manad(ar, man, veckor, "fk_a")
        if kb["fl_netto"] > 0:
            # B-04: Proportionell räkning
            fk_dagar_b = _fk_dagar_manad(ar, man, veckor, "fk_b")
            fl_man_b += min(1.0, fk_dagar_b / 20)
            if is_fin_b:
                fl_dag_b += _fk_dagar_manad(ar, man, veckor, "fk_b")

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

    fore_a  = [_normalmanad(*_add_months(y0, m0, i - 6), nettolön_mån_a, skatt_a, bb_fore) for i in range(6)]
    fore_b  = [_normalmanad(*_add_months(y0, m0, i - 6), nettolön_mån_b, skatt_b, bb_fore) for i in range(6)]
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
    # C-05: Tvillingfödsel – extra 90 SP + 45 LG per extra foster (SFB 12 kap 42 §)
    _extra = max(0, indata.antal_foster - 1)
    sp_tot_a = indata.sparade_sgi_a + 195 + _extra * 90
    lg_tot_a = indata.sparade_lagsta_a + 45 + _extra * 45
    sp_tot_b = indata.sparade_sgi_b + 195 + _extra * 90
    lg_tot_b = indata.sparade_lagsta_b + 45 + _extra * 45

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

    # ── FL-saldo ──────────────────────────────────────────────
    fl_saldo = {
        "a": {
            "fl_manader_totalt":  max_fl_man_a,
            "fl_manader_anvanda": fl_man_a,
            "fl_manader_kvar":    max(0, max_fl_man_a - fl_man_a) if max_fl_man_a < 999 else 999,
            "utbetalare":         _get_utbetalare(_avtal_namn_a),
        },
        "b": {
            "fl_manader_totalt":  max_fl_man_b,
            "fl_manader_anvanda": fl_man_b,
            "fl_manader_kvar":    max(0, max_fl_man_b - fl_man_b) if max_fl_man_b < 999 else 999,
            "utbetalare":         _get_utbetalare(_avtal_namn_b),
        },
    }

    # C-07: 3-periodersvarning (Föräldraledighetslagen 10 §, max 3 perioder per kalenderår)
    perioder_per_ar_a: dict = {}
    perioder_per_ar_b: dict = {}
    for p in indata.foraldrar_a.perioder:
        for ar_p in range(p.start.year, p.slut.year + 1):
            perioder_per_ar_a[ar_p] = perioder_per_ar_a.get(ar_p, 0) + 1
    for p in indata.foraldrar_b.perioder:
        for ar_p in range(p.start.year, p.slut.year + 1):
            perioder_per_ar_b[ar_p] = perioder_per_ar_b.get(ar_p, 0) + 1
    tre_perioder_varningar = []
    for ar_p, antal in {**perioder_per_ar_a, **{k: v for k, v in perioder_per_ar_b.items()}}.items():
        for forälder_namn, d in [(indata.foraldrar_a.namn, perioder_per_ar_a), (indata.foraldrar_b.namn, perioder_per_ar_b)]:
            if d.get(ar_p, 0) > 3:
                tre_perioder_varningar.append({
                    "typ": "tre_perioder",
                    "forälder": forälder_namn,
                    "ar": ar_p,
                    "antal_perioder": d[ar_p],
                    "meddelande": f"{forälder_namn} har {d[ar_p]} ledighetsperioder år {ar_p}. FL-lagen ger rätt till max 3/år — stäm av med arbetsgivaren.",
                })

    # C-06: FK helgkopplingsvarning (lag fr.o.m. 1 april 2025, SFB 12 kap 14 a §)
    helgkoppling_varningar = []
    for v in veckor:
        for col, namn in [("fk_a", indata.foraldrar_a.namn), ("fk_b", indata.foraldrar_b.namn)]:
            if v[col] > 5 and min(v[col], 5) == 0:
                helgkoppling_varningar.append({
                    "typ": "fk_helgkoppling",
                    "forälder": namn,
                    "vecka": v["vecka"],
                    "ar": v["ar"],
                    "meddelande": f"{namn} har helg-FK v.{v['vecka']}/{v['ar']} utan vardags-FK. FK på helg kräver FK på vardag samma vecka (april 2025).",
                })

    # C-02: Räkna totalt antal dubbeldagar och varna om 60-dagarstaket överskrids
    dubbel_dagar_totalt = 0
    for v in veckor:
        if v["fk_a"] > 0 and v["fk_b"] > 0:
            # Båda har FK denna vecka — räkna överlappande dagar
            dubbel_dagar_totalt += min(v["fk_a"], 5) * 1  # approximation per vecka
    dubbel_varning = None
    if dubbel_dagar_totalt > 60:
        dubbel_varning = f"Planen innehåller uppskattningsvis {dubbel_dagar_totalt} dubbeldagar. Föräldrabalken tillåter max 60 dubbeldagar före barnets 15-månadersdag."

    # ── D-04a: Semesterintjänande (SemL 17a §) ────────────────────
    # FK-dagar (SGI-dagar, max 5/vecka) är semestergrundande upp till 120 per förälder.
    _SEM_GRANS = 120
    _fk_tot_a = sum(min(v["fk_a"], 5) for v in veckor)
    _fk_tot_b = sum(min(v["fk_b"], 5) for v in veckor)
    semesterintjanande = {
        "dagar_a": min(_fk_tot_a, _SEM_GRANS),
        "dagar_b": min(_fk_tot_b, _SEM_GRANS),
        "grans_a": _SEM_GRANS,
        "grans_b": _SEM_GRANS,
        "varning_a": (
            f"{indata.foraldrar_a.namn} har {_fk_tot_a} FK-dagar — gränsen på {_SEM_GRANS} semestergrundande dagar (SemL 17a §) passeras."
            if _fk_tot_a > _SEM_GRANS else None
        ),
        "varning_b": (
            f"{indata.foraldrar_b.namn} har {_fk_tot_b} FK-dagar — gränsen på {_SEM_GRANS} semestergrundande dagar (SemL 17a §) passeras."
            if _fk_tot_b > _SEM_GRANS else None
        ),
    }

    return {
        "plan_veckor":     plan_veckor,
        "manadsinkomst_a": komp_a,
        "manadsinkomst_b": komp_b,
        "skatteavdrag":    skatteavdrag,
        "dagssaldo":       dagssaldo,
        "fl_saldo":        fl_saldo,
        "varningar_perioder": tre_perioder_varningar,
        "varningar_helg": helgkoppling_varningar,
        "dubbeldagar_totalt": dubbel_dagar_totalt,
        "dubbeldagar_varning": dubbel_varning,
        "semesterintjanande": semesterintjanande,
    }
