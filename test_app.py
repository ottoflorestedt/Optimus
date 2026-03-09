# Streamlit m.fl. mockas av conftest.py innan import
from datetime import date, timedelta
from app import berakna_rot_rut_avdrag, generera_plan_veckor, _komponenter_manad


# ============================================================
#  berakna_rot_rut_avdrag
# ============================================================

class TestBeraknaRotRutAvdrag:
    def test_noll(self):
        assert berakna_rot_rut_avdrag(0, 0) == 0

    def test_rot_under_tak(self):
        # 30 % på 100 000 kr → 30 000 kr (under 50 000-taket)
        assert berakna_rot_rut_avdrag(100_000, 0) == 30_000

    def test_rot_over_tak_kapas(self):
        # 30 % på 200 000 kr = 60 000 → kapas till 50 000
        assert berakna_rot_rut_avdrag(200_000, 0) == 50_000

    def test_rut_vid_tak(self):
        # 50 % på 100 000 kr → 50 000 kr (exakt i tak)
        assert berakna_rot_rut_avdrag(0, 100_000) == 50_000

    def test_rot_och_rut_kapas(self):
        # 30 % × 100 000 + 50 % × 100 000 = 80 000 → kapas till 50 000
        assert berakna_rot_rut_avdrag(100_000, 100_000) == 50_000


# ============================================================
#  generera_plan_veckor
# ============================================================

def _period(start, slut, fk_v=5, sem_dagar=0):
    return {"start": start, "slut": slut, "fk_v": fk_v,
            "sem_dagar": sem_dagar, "sem_start": None, "sem_slut": None}


class TestGenereraPlanVeckor:
    def test_tomma_perioder_ger_tom_lista(self):
        assert generera_plan_veckor([], []) == []

    def test_en_vecka_fk_dagar(self):
        # Måndag–fredag 2026-01-05 – 2026-01-09, fk_v=5 → 1 vecka, 5 FK-dagar förälder A
        p = _period(date(2026, 1, 5), date(2026, 1, 9), fk_v=5)
        veckor = generera_plan_veckor([p], [])
        assert len(veckor) == 1
        assert veckor[0]["fk_dagar_a"] == 5
        assert veckor[0]["fk_dagar_b"] == 0
        assert veckor[0]["ledig_a"] is True
        assert veckor[0]["ledig_b"] is False

    def test_tva_veckor_summeras(self):
        # Tvåveckorsperiod → 2 veckoposter, sum fk_dagar_a = 10
        p = _period(date(2026, 1, 5), date(2026, 1, 16), fk_v=5)
        veckor = generera_plan_veckor([p], [])
        assert len(veckor) == 2
        assert sum(v["fk_dagar_a"] for v in veckor) == 10

    def test_bada_foraldrar_samma_vecka(self):
        # Förälder A: fk_v=3, Förälder B: fk_v=2 – samma vecka
        pa = _period(date(2026, 1, 5), date(2026, 1, 9), fk_v=3)
        pb = _period(date(2026, 1, 5), date(2026, 1, 9), fk_v=2)
        veckor = generera_plan_veckor([pa], [pb])
        assert len(veckor) == 1
        assert veckor[0]["fk_dagar_a"] == 3
        assert veckor[0]["fk_dagar_b"] == 2


# ============================================================
#  _komponenter_manad
# ============================================================

class _DF:
    """Minimal DataFrame-ersättare som stödjer edited_df.iloc[i][col]."""
    def __init__(self, rows):
        self._rows = rows

    class _Idx:
        def __init__(self, rows): self._rows = rows
        def __getitem__(self, i): return self._rows[i]

    @property
    def iloc(self): return self._Idx(self._rows)


class TestKomponenterManad:
    def _anropa(self, fk, ledig=True):
        """Hjälpare: en vecka i jan 2026 med givet antal FK-dagar och ledig-flagga."""
        veckor    = [{"datum_start": date(2026, 1, 5), "ledig": ledig}]
        edited_df = _DF([{"fk": fk, "lg": 0, "sem": 0}])
        fl_r      = {"foraldralon/mån": 0, "max_månader": 0}
        return _komponenter_manad(
            ar=2026, man=1,
            veckor=veckor, edited_df=edited_df,
            lon=40000, nettolön_mån=32380, ki=0.2999,
            fl_r=fl_r, fl_bool=False,
            col_fk="fk", col_lg="lg", col_sem="sem", col_ledig="ledig",
            barnbidrag=0,
        )

    def test_5_fk_dagar_fk_positiv_lon_noll(self):
        # En hel vecka i jan 2026 med 5 FK-dagar under ledighet →
        # fk_netto ska vara positivt, lon_netto ska vara noll
        result = self._anropa(fk=5, ledig=True)
        assert result["fk_netto"] > 0
        assert result["lon_netto"] == 0

    def test_ledig_2fk_lägre_inkomst_än_5fk(self):
        # Under ledighet: 2 FK-dagar/vecka ska ge lägre total inkomst än 5 FK-dagar/vecka
        r2 = self._anropa(fk=2, ledig=True)
        r5 = self._anropa(fk=5, ledig=True)
        assert r2["netto_total"] < r5["netto_total"]

    def test_ledig_ger_noll_lon(self):
        # Under ledighet ska lon_netto alltid vara 0 oavsett FK-dagar
        r2 = self._anropa(fk=2, ledig=True)
        assert r2["lon_netto"] == 0

    def test_ej_ledig_ger_lon_vid_lågt_fk(self):
        # Utanför ledighetsperiod: 2 FK-dagar + 3 övriga = 3 arbetsdagar med lön
        result = self._anropa(fk=2, ledig=False)
        assert result["lon_netto"] > 0
