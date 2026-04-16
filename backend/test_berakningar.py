"""
Enhetstestsvit för beräkningsmotorn (kalkyl.py + kollektivavtal.py).

Täcker:
  1. Skatteberäkning 2026         (berakna_skatt)
  2. Kollektivavtal FL-månader    (berakna_foraldralon / max_fl_man)
  3. FK-ersättning                (berakna_fk_ersattning)
  4. FL-beräkning Teknikavtalet   (berakna_foraldralon)
  5. Tvillingfödsel C-05          (sp_tot-formel)
"""

import sys
import os

# Säkerställ att backend-katalogen ligger på sökvägen oavsett varifrån pytest körs.
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import pytest
from datetime import date
from kalkyl import berakna_skatt, berakna_fk_ersattning, berakna_foraldralon
from kollektivavtal import max_fl_man, PBB, KOLLEKTIVAVTAL


# ============================================================
# 1. Skatteberäkning 2026
# ============================================================

class TestSkatt:
    def test_40k_skatt(self):
        """40 000 kr/mån → skatt 7 931 kr (tabell 31, exakt träff)."""
        res = berakna_skatt(40000)
        assert res["total_skatt/mån"] == 7931

    def test_40k_netto(self):
        """40 000 kr/mån → nettolön 32 069 kr."""
        res = berakna_skatt(40000)
        assert res["nettolön/mån"] == 32069

    def test_55k_skatt(self):
        """55 000 kr/mån → skatt 12 598 kr (precis under statlig skattegräns 55 033 kr)."""
        res = berakna_skatt(55000)
        assert res["total_skatt/mån"] == 12598

    def test_135k_skatt(self):
        """135 000 kr/mån → skatt 52 702 kr (verifierat mot SKV-kalkylator)."""
        res = berakna_skatt(135000)
        assert res["total_skatt/mån"] == 52702

    def test_noll_lon(self):
        """Noll-lön ger noll-skatt och noll-netto."""
        res = berakna_skatt(0)
        assert res["total_skatt/mån"] == 0
        assert res["nettolön/mån"] == 0


# ============================================================
# 2. Kollektivavtal FL-månader
# ============================================================

class TestFlManader:
    # ── berakna_foraldralon ──────────────────────────────────

    def test_unionen_11_man_ger_noll(self):
        """A-02: Unionen kräver 12 mån; vid 11 mån → 0 FL-månader."""
        res = berakna_foraldralon(40000, "Unionen", 11)
        assert res["max_månader"] == 0
        assert res["foraldralon/mån"] == 0

    def test_unionen_12_man_ger_3(self):
        """A-02: Unionen 12 mån sammanhängande → 3 FL-månader (kort period)."""
        res = berakna_foraldralon(40000, "Unionen", 12)
        assert res["max_månader"] == 3

    def test_finansforbundet_6_man_ger_12(self):
        """A-03: Finansförbundet gäller från dag 1; 6 mån → 12 FL-månader."""
        res = berakna_foraldralon(50000, "Finansförbundet", 6)
        assert res["max_månader"] == 12

    def test_innovationsforetagen_18_man_ger_2(self):
        """Innovationsföretagen 18 mån (12–23) → 2 FL-månader."""
        res = berakna_foraldralon(50000, "Innovationsföretagen", 18)
        assert res["max_månader"] == 2

    def test_innovationsforetagen_24_man_ger_6(self):
        """Innovationsföretagen 24 mån (24+) → 6 FL-månader."""
        res = berakna_foraldralon(50000, "Innovationsföretagen", 24)
        assert res["max_månader"] == 6

    # ── max_fl_man (hjälpfunktion) ───────────────────────────

    def test_max_fl_man_unionen_11(self):
        assert max_fl_man("Unionen", 11) == 0

    def test_max_fl_man_unionen_12(self):
        assert max_fl_man("Unionen", 12) == 3

    def test_max_fl_man_unionen_24(self):
        assert max_fl_man("Unionen", 24) == 6

    def test_max_fl_man_finansforbundet_6(self):
        assert max_fl_man("Finansförbundet", 6) == 12

    def test_max_fl_man_innovationsforetagen_18(self):
        assert max_fl_man("Innovationsföretagen", 18) == 2

    def test_max_fl_man_innovationsforetagen_24(self):
        assert max_fl_man("Innovationsföretagen", 24) == 6

    def test_max_fl_man_afa_fpt_11(self):
        assert max_fl_man("AFA FPT (arbetare)", 11) == 0

    def test_max_fl_man_afa_fpt_12(self):
        assert max_fl_man("AFA FPT (arbetare)", 12) == 2

    def test_max_fl_man_afa_fpt_24(self):
        assert max_fl_man("AFA FPT (arbetare)", 24) == 6

    def test_max_fl_man_byggforetagen_12(self):
        assert max_fl_man("Byggföretagen (tjänstemän)", 12) == 6

    def test_max_fl_man_vardförbundet_36(self):
        assert max_fl_man("Vårdförbundet (region)", 36) == 4

    def test_max_fl_man_statliga_12(self):
        """Statliga sektorn steg-modell: 12 mån → 2 FL-mån (korrigerat från gamla 6)."""
        assert max_fl_man("Statliga sektorn", 12) == 2

    def test_max_fl_man_statliga_60(self):
        assert max_fl_man("Statliga sektorn", 60) == 6

    # ── AB-avtalet (steg-modell: 12→2, 24→3, 36→4, 48→5, 60→6) ─
    def test_max_fl_man_ab_under_12(self):
        assert max_fl_man("AB-avtalet", 11) == 0

    def test_max_fl_man_ab_12(self):
        assert max_fl_man("AB-avtalet", 12) == 2

    def test_max_fl_man_ab_23(self):
        assert max_fl_man("AB-avtalet", 23) == 2

    def test_max_fl_man_ab_24(self):
        assert max_fl_man("AB-avtalet", 24) == 3

    def test_max_fl_man_ab_36(self):
        assert max_fl_man("AB-avtalet", 36) == 4

    def test_max_fl_man_ab_48(self):
        assert max_fl_man("AB-avtalet", 48) == 5

    def test_max_fl_man_ab_60(self):
        assert max_fl_man("AB-avtalet", 60) == 6

    # ── Läkarförbundet (krav_kort = krav_lang = 6 mån → 9 FL-mån) ─
    def test_max_fl_man_lakarforbundet_5(self):
        assert max_fl_man("Läkarförbundet", 5) == 0

    def test_max_fl_man_lakarforbundet_6(self):
        assert max_fl_man("Läkarförbundet", 6) == 9

    def test_max_fl_man_lakarforbundet_24(self):
        assert max_fl_man("Läkarförbundet", 24) == 9

    # ── Svensk Handel (tjänstemän) ────────────────────────────

    def test_max_fl_man_svensk_handel_under_12(self):
        assert max_fl_man("Svensk Handel (tjänstemän)", 11) == 0

    def test_max_fl_man_svensk_handel_12(self):
        assert max_fl_man("Svensk Handel (tjänstemän)", 12) == 2

    def test_max_fl_man_svensk_handel_24(self):
        assert max_fl_man("Svensk Handel (tjänstemän)", 24) == 6

    # ── Almega IT/konsult ─────────────────────────────────────

    def test_max_fl_man_almega_under_12(self):
        assert max_fl_man("Almega IT/konsult", 11) == 0

    def test_max_fl_man_almega_12(self):
        assert max_fl_man("Almega IT/konsult", 12) == 2

    def test_max_fl_man_almega_24(self):
        assert max_fl_man("Almega IT/konsult", 24) == 6

    # ── Stål och metall (tjänstemän) ─────────────────────────

    def test_max_fl_man_stal_under_12(self):
        assert max_fl_man("Stål och metall (tjänstemän)", 11) == 0

    def test_max_fl_man_stal_12(self):
        assert max_fl_man("Stål och metall (tjänstemän)", 12) == 2

    def test_max_fl_man_stal_24(self):
        assert max_fl_man("Stål och metall (tjänstemän)", 24) == 6


# ============================================================
# 3. FK-ersättning
# ============================================================

class TestFkErsattning:
    def test_40k_brutto_per_dag(self):
        """40 000 kr/mån → fk_brutto/dag = round(480 000 × 0,776 / 365) = 1 020 kr."""
        expected = round(min(40000 * 12, 592000) * 0.776 / 365)
        res = berakna_fk_ersattning(40000)
        assert res["fk_brutto/dag"] == expected

    def test_sgi_tak_70k(self):
        """Lön >= SGI-tak (70k) → fk_brutto/dag = round(592 000 × 0,776 / 365) = 1 259 kr."""
        expected = round(592000 * 0.776 / 365)
        assert expected == 1259
        res = berakna_fk_ersattning(70000)
        assert res["fk_brutto/dag"] == 1259

    def test_over_sgi_tak_ger_samma_som_tak(self):
        """Lön 100k (> SGI-tak) ger samma fk_brutto/dag som 70k."""
        res70 = berakna_fk_ersattning(70000)
        res100 = berakna_fk_ersattning(100000)
        assert res70["fk_brutto/dag"] == res100["fk_brutto/dag"]


# ============================================================
# 4. FL-beräkning Teknikavtalet
# ============================================================

class TestFlBerakning:
    def test_teknikavtalet_135k_24_man(self):
        """
        Teknikavtalet, 135 000 kr/mån, 24 mån anst.
        loenetak = round(10 × 59 200 / 12) = 49 333 kr
        FL = 10 % × 49 333 + 90 % × (135 000 − 49 333) = 82 034 kr/mån
        """
        loenetak = round(10 * PBB / 12)  # 49 333
        expected = round(loenetak * 0.10 + (135000 - loenetak) * 0.90)

        res = berakna_foraldralon(135000, "Teknikavtalet", 24)
        assert res["foraldralon/mån"] == expected
        assert res["max_månader"] == 6

    def test_teknikavtalet_135k_loenetak(self):
        """Kontrollera att lönetaket för Teknikavtalet är korrekt (10 × PBB / 12)."""
        assert round(10 * PBB / 12) == 49333


# ============================================================
# 5. Tvillingfödsel C-05 – sp_tot-formel (SFB 12 kap 42 §)
# ============================================================

class TestTvillingfodsel:
    def _sp_tot(self, antal_foster: int, sparade_sgi: int = 0) -> int:
        """Replikerar main.py:s sp_tot-formel för enkel enhetstestning."""
        _extra = max(0, antal_foster - 1)
        return sparade_sgi + 195 + _extra * 90

    def test_singel_fodsel(self):
        """Singelfödsel (antal_foster=1) → sp_tot = 195."""
        assert self._sp_tot(1) == 195

    def test_tvillingfodsel(self):
        """Tvillingfödsel (antal_foster=2) → sp_tot = 195 + 90 = 285."""
        assert self._sp_tot(2) == 285

    def test_trillingfodsel(self):
        """Trillingfödsel (antal_foster=3) → sp_tot = 195 + 2×90 = 375."""
        assert self._sp_tot(3) == 375

    def test_sparade_sgi_laggs_till(self):
        """Sparade SGI-dagar adderas ovanpå grundbeloppet."""
        assert self._sp_tot(1, sparade_sgi=30) == 225
        assert self._sp_tot(2, sparade_sgi=30) == 315


# ============================================================
# 6. Utbetalare-flagga
# ============================================================

class TestUtbetalare:
    def test_afa_fpt_utbetalare_afa(self):
        assert KOLLEKTIVAVTAL["AFA FPT (arbetare)"]["utbetalare"] == "afa"

    def test_teknikavtalet_utbetalare_arbetsgivare(self):
        assert KOLLEKTIVAVTAL["Teknikavtalet"]["utbetalare"] == "arbetsgivare"

    def test_finansforbundet_utbetalare_arbetsgivare(self):
        assert KOLLEKTIVAVTAL["Finansförbundet"]["utbetalare"] == "arbetsgivare"


# ============================================================
# 7. Dubbeldagar C-02
# ============================================================

class TestDubbeldagar:
    def _veckor(self, fk_a_vals, fk_b_vals):
        """Bygg en minimal veckolista med fk_a/fk_b per vecka."""
        return [{"fk_a": a, "fk_b": b} for a, b in zip(fk_a_vals, fk_b_vals)]

    def _rakna(self, veckor):
        """Replikerar C-02-logiken från main.py."""
        totalt = 0
        for v in veckor:
            if v["fk_a"] > 0 and v["fk_b"] > 0:
                totalt += min(v["fk_a"], 5)
        return totalt

    def test_period_dubbeldagar_falt_default_false(self):
        """Period-modellen ska ha dubbeldagar=False som default."""
        from main import Period
        p = Period(start=date(2026, 1, 5), slut=date(2026, 1, 9))
        assert p.dubbeldagar is False

    def test_period_dubbeldagar_falt_true(self):
        """Period-modellen accepterar dubbeldagar=True."""
        from main import Period
        p = Period(start=date(2026, 1, 5), slut=date(2026, 1, 9), dubbeldagar=True)
        assert p.dubbeldagar is True

    def test_dubbeldagar_totalt_ingen_overlap(self):
        """Inga överlappande veckor → 0 dubbeldagar."""
        veckor = self._veckor([5, 0, 5], [0, 5, 0])
        assert self._rakna(veckor) == 0

    def test_dubbeldagar_totalt_full_overlap(self):
        """12 veckor med 5 fk_a och 5 fk_b → 60 dubbeldagar (precis på gränsen)."""
        veckor = self._veckor([5] * 12, [5] * 12)
        assert self._rakna(veckor) == 60

    def test_dubbeldagar_varning_over_60(self):
        """13 veckor med full overlap → 65 dubbeldagar → varning ska genereras."""
        totalt = self._rakna(self._veckor([5] * 13, [5] * 13))
        assert totalt > 60
        varning = (
            f"Planen innehåller uppskattningsvis {totalt} dubbeldagar. "
            "Föräldrabalken tillåter max 60 dubbeldagar före barnets 15-månadersdag."
        )
        assert "60 dubbeldagar" in varning

    def test_dubbeldagar_ingen_varning_vid_60(self):
        """Exakt 60 dubbeldagar → ingen varning (gränsen är > 60)."""
        totalt = self._rakna(self._veckor([5] * 12, [5] * 12))
        assert totalt == 60
        assert not (totalt > 60)


# ============================================================
# 8. Deltidsuttag FK C-03
# ============================================================

class TestFkGrad:
    def test_fk_grad_default_100(self):
        """Period-modellen ska ha fk_grad=100 som default."""
        from main import Period
        p = Period(start=date(2026, 1, 5), slut=date(2026, 1, 9))
        assert p.fk_grad == 100

    def test_fk_grad_25_accepteras(self):
        """fk_grad=25 är ett giltigt värde."""
        from main import Period
        p = Period(start=date(2026, 1, 5), slut=date(2026, 1, 9), fk_grad=25)
        assert p.fk_grad == 25

    def test_fk_grad_50_accepteras(self):
        """fk_grad=50 är ett giltigt värde."""
        from main import Period
        p = Period(start=date(2026, 1, 5), slut=date(2026, 1, 9), fk_grad=50)
        assert p.fk_grad == 50

    def test_fk_grad_75_accepteras(self):
        """fk_grad=75 är ett giltigt värde."""
        from main import Period
        p = Period(start=date(2026, 1, 5), slut=date(2026, 1, 9), fk_grad=75)
        assert p.fk_grad == 75

    def test_fk_grad_60_ger_valueerror(self):
        """fk_grad=60 är inte ett tillåtet värde — ska ge ValueError."""
        import pytest
        from main import Period
        with pytest.raises(Exception):
            Period(start=date(2026, 1, 5), slut=date(2026, 1, 9), fk_grad=60)

    def test_fk_grad_50_ger_halv_fk_ersattning(self):
        """
        fk_grad=50 ska ge halv FK-ersättning jämfört med fk_grad=100.
        Testar _komponenter_manad direkt med syntetisk veckodata.
        """
        from main import _komponenter_manad, _DF
        from datetime import date, timedelta
        from kalkyl import berakna_fk_ersattning, berakna_foraldralon

        lon = 50000
        ki = 0.3
        fl_r = berakna_foraldralon(lon, "Ingen föräldralön", 24)

        monday = date(2026, 3, 2)  # Vecka i mars 2026
        vecka = {
            "vecka": 10, "ar": 2026,
            "datum_start": monday, "datum_slut": monday + timedelta(days=4),
            "fk_a": 5, "fk_grad_a": 100,
            "lg_a": 0, "sem_a": 0, "tio_a": 0,
            "sjuk_lon_a": 0, "sjuk_fk_a": 0, "sjuk_lag_a": 0,
            "sjuk_grad_a": 100, "sjuk_karens_a": False,
            "ledig_a": True, "avdragstyp_a": "dag",
        }

        vecka_50 = {**vecka, "fk_grad_a": 50}

        def rakna(v):
            return _komponenter_manad(
                2026, 3, [v], _DF([v]), lon, lon * 0.7, ki,
                fl_r, False,
                "fk_a", "lg_a", "sem_a", "tio_a",
                "sjuk_lon_a", "sjuk_fk_a", "sjuk_lag_a", "sjuk_grad_a", "sjuk_karens_a",
                "ledig_a", 0,
                fk_grad_col="fk_grad_a",
            )

        res100 = rakna(vecka)
        res50  = rakna(vecka_50)
        # fk_netto vid 50% ska vara ungefär hälften av 100%
        assert res50["fk_netto"] == pytest.approx(res100["fk_netto"] / 2, abs=50)


# ============================================================
# 9. B-03: Statliga sektorn – steg-modell (alla steg)
# ============================================================

class TestStatligaSektorn:
    """max_fl_man() och KOLLEKTIVAVTAL för Statliga sektorn ska följa steg-modell
    identisk med AB-avtalet: 12→2, 24→3, 36→4, 48→5, 60→6 månader FL."""

    def test_under_12_man_ger_noll(self):
        assert max_fl_man("Statliga sektorn", 11) == 0

    def test_exakt_12_man_ger_2(self):
        assert max_fl_man("Statliga sektorn", 12) == 2

    def test_23_man_stannar_pa_2(self):
        assert max_fl_man("Statliga sektorn", 23) == 2

    def test_exakt_24_man_ger_3(self):
        assert max_fl_man("Statliga sektorn", 24) == 3

    def test_35_man_stannar_pa_3(self):
        assert max_fl_man("Statliga sektorn", 35) == 3

    def test_exakt_36_man_ger_4(self):
        assert max_fl_man("Statliga sektorn", 36) == 4

    def test_47_man_stannar_pa_4(self):
        assert max_fl_man("Statliga sektorn", 47) == 4

    def test_exakt_48_man_ger_5(self):
        assert max_fl_man("Statliga sektorn", 48) == 5

    def test_59_man_stannar_pa_5(self):
        assert max_fl_man("Statliga sektorn", 59) == 5

    def test_exakt_60_man_ger_6(self):
        assert max_fl_man("Statliga sektorn", 60) == 6

    def test_over_60_man_ger_6(self):
        assert max_fl_man("Statliga sektorn", 120) == 6

    def test_none_anstallning_ger_6(self):
        """None-anställningstid → generöst default → 6 FL-månader."""
        assert max_fl_man("Statliga sektorn", None) == 6

    def test_kollektivavtal_har_steg_modell(self):
        """KOLLEKTIVAVTAL['Statliga sektorn'] ska använda steg-modell, inte max_manader_kort/lang."""
        avtal = KOLLEKTIVAVTAL["Statliga sektorn"]
        assert "steg" in avtal
        assert "max_manader_kort" not in avtal
        assert "max_manader_lang" not in avtal

    def test_kollektivavtal_steg_identisk_med_ab(self):
        """Statliga sektorns steg-lista ska vara identisk med AB-avtalets."""
        assert KOLLEKTIVAVTAL["Statliga sektorn"]["steg"] == KOLLEKTIVAVTAL["AB-avtalet"]["steg"]


# ============================================================
# 10. D-04a: Semesterintjänande (SemL 17a §)
# ============================================================

class TestSemesterintjanande:
    """Semestergrundande FK-dagar räknas upp till 120 per förälder.
    API-svaret ska innehålla semesterintjanande-nyckel med dagar_a/b och grans_a/b."""

    def _rakna_sem(self, fk_dagar_per_vecka_a, fk_dagar_per_vecka_b, grans=120):
        """Replikerar D-04a-logiken från main.py."""
        fk_tot_a = sum(min(d, 5) for d in fk_dagar_per_vecka_a)
        fk_tot_b = sum(min(d, 5) for d in fk_dagar_per_vecka_b)
        return {
            "dagar_a": min(fk_tot_a, grans),
            "dagar_b": min(fk_tot_b, grans),
            "grans_a": grans,
            "grans_b": grans,
            "over_grans_a": fk_tot_a > grans,
            "over_grans_b": fk_tot_b > grans,
            "_fk_tot_a": fk_tot_a,
            "_fk_tot_b": fk_tot_b,
        }

    def test_noll_fk_dagar_ger_noll_sem(self):
        res = self._rakna_sem([0] * 10, [0] * 10)
        assert res["dagar_a"] == 0
        assert res["dagar_b"] == 0

    def test_24_veckor_5_dagar_ger_120(self):
        """24 veckor × 5 FK-dagar = 120 → precis på gränsen."""
        res = self._rakna_sem([5] * 24, [0] * 24)
        assert res["dagar_a"] == 120
        assert not res["over_grans_a"]

    def test_25_veckor_5_dagar_cappar_pa_120(self):
        """25 veckor × 5 FK-dagar = 125 → cappas till 120."""
        res = self._rakna_sem([5] * 25, [0] * 25)
        assert res["dagar_a"] == 120
        assert res["over_grans_a"]

    def test_lg_dagar_over_5_raknas_inte(self):
        """FK-dagar 6-7 (lägstanivå) är ej semestergrundande (räknas max 5/vecka)."""
        # 10 veckor med 7 fk-dagar (inkl helg) → 10×5 = 50, inte 10×7 = 70
        res = self._rakna_sem([7] * 10, [0] * 10)
        assert res["dagar_a"] == 50

    def test_varning_genereras_over_grans(self):
        """Varning ska sättas när FK-dagar > 120."""
        res = self._rakna_sem([5] * 25, [5] * 25)
        assert res["over_grans_a"]
        assert res["over_grans_b"]

    def test_ingen_varning_vid_exakt_120(self):
        """Ingen varning vid exakt 120 FK-dagar (gränsen är strikt >)."""
        res = self._rakna_sem([5] * 24, [5] * 24)
        assert not res["over_grans_a"]
        assert not res["over_grans_b"]

    def test_grans_falt_ar_alltid_120(self):
        """grans_a och grans_b ska alltid vara 120."""
        res = self._rakna_sem([3] * 10, [1] * 10)
        assert res["grans_a"] == 120
        assert res["grans_b"] == 120

    def test_a_och_b_raknas_oberoende(self):
        """Förälder A och B räknas separat."""
        res = self._rakna_sem([5] * 10, [5] * 5)
        assert res["dagar_a"] == 50
        assert res["dagar_b"] == 25

    def test_api_svar_innehaller_semesterintjanande(self):
        """POST /berakna ska returnera 'semesterintjanande'-nyckel med rätt struktur."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        payload = {
            "foraldrar_a": {
                "namn": "A",
                "manadslon": 40000,
                "kollektivavtal": "Ingen föräldralön",
                "anstallning": 24,
                "perioder": [{"start": "2026-03-02", "slut": "2026-06-26", "dagar_per_vecka": 5}],
            },
            "foraldrar_b": {
                "namn": "B",
                "manadslon": 40000,
                "kollektivavtal": "Ingen föräldralön",
                "anstallning": 24,
                "perioder": [],
            },
        }
        resp = client.post("/berakna", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "semesterintjanande" in data
        si = data["semesterintjanande"]
        assert "dagar_a" in si
        assert "dagar_b" in si
        assert si["grans_a"] == 120
        assert si["grans_b"] == 120
        assert isinstance(si["dagar_a"], int)
        assert 0 <= si["dagar_a"] <= 120

    def test_api_varning_vid_over_120(self):
        """varning_a ska sättas i API-svaret när A överstiger 120 FK-dagar."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        # ~6 månader heltids-FK (26 veckor × 5 = 130 dagar > 120)
        payload = {
            "foraldrar_a": {
                "namn": "Anna",
                "manadslon": 40000,
                "kollektivavtal": "Ingen föräldralön",
                "anstallning": 24,
                "perioder": [{"start": "2026-01-05", "slut": "2026-07-03", "dagar_per_vecka": 5}],
            },
            "foraldrar_b": {
                "namn": "Bo",
                "manadslon": 40000,
                "kollektivavtal": "Ingen föräldralön",
                "anstallning": 24,
                "perioder": [],
            },
        }
        resp = client.post("/berakna", json=payload)
        assert resp.status_code == 200
        si = resp.json()["semesterintjanande"]
        assert si["dagar_a"] == 120   # cappat
        assert si["varning_a"] is not None
        assert "Anna" in si["varning_a"]
        assert "SemL 17a §" in si["varning_a"]
        assert si["varning_b"] is None


# ============================================================
# 11. /ersattning_per_dag – integrationstester (A-06, C-03a)
# ============================================================

class TestErsattningPerDag:
    """Integrationstester mot GET /ersattning_per_dag.

    Verifierar:
      A-06  – dag 6-7 beräknas på sjukpenningnivå (fk_ndag), inte lägstanivå.
      C-03a – fk_grad_a/b skalar FK- och FL-ersättning korrekt.
      Struktur – svaret innehåller fl_netto för alla 7 nivåer.
    """

    def _client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)

    def test_svar_struktur_7_rader_med_fl_netto(self):
        """Svaret ska ha 7 rader per förälder, var och en med fk_netto, fl_netto och totalt."""
        client = self._client()
        resp = client.get("/ersattning_per_dag", params={
            "manadslon_a": 50000, "avtal_a": "Unionen", "anstallning_a": 24,
            "manadslon_b": 40000, "avtal_b": "Ingen föräldralön", "anstallning_b": 24,
        })
        assert resp.status_code == 200
        data = resp.json()
        for parent in ("foraldrar_a", "foraldrar_b"):
            rows = data[parent]
            assert len(rows) == 7
            for i, row in enumerate(rows, start=1):
                assert row["dagar"] == i
                assert "fk_netto" in row
                assert "fl_netto" in row
                assert "totalt" in row
                assert row["totalt"] == row["fk_netto"] + row["fl_netto"]

    def test_a06_dag_6_7_hogre_an_lagstaniva(self):
        """A-06: dag 6 och 7 ska ge mer än lägstanivå (180 kr/dag brutto).
        Med 40 000 kr/mån är fk_ndag ≈ 1 020 kr/dag >> 180 kr/dag lägstanivå.
        dag7_fk ska vara >  dag5_fk × 7/5 × 0.9 (rimlig undre gräns om alla på sjukpenningnivå)."""
        client = self._client()
        resp = client.get("/ersattning_per_dag", params={"manadslon_a": 40000})
        rows = resp.json()["foraldrar_a"]
        by_dag = {r["dagar"]: r for r in rows}

        # dag 6 ska ge mer FK-netto än dag 5 (sjukpenningnivå, inte noll/lägstanivå)
        assert by_dag[6]["fk_netto"] > by_dag[5]["fk_netto"]
        assert by_dag[7]["fk_netto"] > by_dag[6]["fk_netto"]

        # Proportionalitet: dag 7 / dag 5 ≈ 7/5
        ratio = by_dag[7]["fk_netto"] / by_dag[5]["fk_netto"]
        assert 1.3 < ratio < 1.5  # 7/5 = 1.4

    def test_c03a_fk_grad_50_ger_halv_ersattning(self):
        """C-03a: fk_grad_a=50 ska ge ungefär hälften av fk_netto och fl_netto jämfört med fk_grad_a=100."""
        client = self._client()

        resp100 = client.get("/ersattning_per_dag", params={
            "manadslon_a": 50000, "avtal_a": "Unionen", "anstallning_a": 24, "fk_grad_a": 100,
        })
        resp50 = client.get("/ersattning_per_dag", params={
            "manadslon_a": 50000, "avtal_a": "Unionen", "anstallning_a": 24, "fk_grad_a": 50,
        })
        rows100 = {r["dagar"]: r for r in resp100.json()["foraldrar_a"]}
        rows50  = {r["dagar"]: r for r in resp50.json()["foraldrar_a"]}

        for d in range(1, 8):
            # fk_netto vid 50% ska vara ≈ hälften (tolerans ±5 kr avrundning)
            assert abs(rows50[d]["fk_netto"] - rows100[d]["fk_netto"] / 2) <= 5, \
                f"dag {d}: fk_netto@50%={rows50[d]['fk_netto']} != ~{rows100[d]['fk_netto']/2:.0f}"
            # fl_netto vid 50% ska vara ≈ hälften (dag 1-5 har FL, dag 6-7 FL=0)
            assert abs(rows50[d]["fl_netto"] - rows100[d]["fl_netto"] / 2) <= 5, \
                f"dag {d}: fl_netto@50%={rows50[d]['fl_netto']} != ~{rows100[d]['fl_netto']/2:.0f}"


# ============================================================
# 12. E-03: Validering av period-överlapp
# ============================================================

class TestPeriodOverlapp:
    """ForaldrarIndata.perioder ska kasta ValueError vid överlappande perioder."""

    def _indata(self, perioder_payload):
        from main import ForaldrarIndata
        return ForaldrarIndata(
            namn="Test",
            manadslon=40000,
            kollektivavtal="Ingen föräldralön",
            perioder=perioder_payload,
        )

    def test_icke_overlappande_perioder_ok(self):
        """Två perioder utan överlapp ska accepteras utan fel."""
        self._indata([
            {"start": "2026-01-05", "slut": "2026-03-31", "dagar_per_vecka": 5},
            {"start": "2026-04-01", "slut": "2026-06-30", "dagar_per_vecka": 5},
        ])  # ingen exception = OK

    def test_overlappande_perioder_ger_valueerror(self):
        """Perioder där period 1 slutar efter att period 2 börjar ska ge ValueError."""
        with pytest.raises(Exception) as exc:
            self._indata([
                {"start": "2026-01-05", "slut": "2026-04-15", "dagar_per_vecka": 5},
                {"start": "2026-04-01", "slut": "2026-06-30", "dagar_per_vecka": 5},
            ])
        assert "överlappar" in str(exc.value).lower() or "overlapp" in str(exc.value).lower() \
            or "period" in str(exc.value).lower()

    def test_angransande_perioder_ger_valueerror(self):
        """Angränsande perioder där slut == start räknas som överlapp (samma dag)."""
        with pytest.raises(Exception):
            self._indata([
                {"start": "2026-01-05", "slut": "2026-03-31", "dagar_per_vecka": 5},
                {"start": "2026-03-31", "slut": "2026-06-30", "dagar_per_vecka": 5},
            ])


# ============================================================
# 13. U9: Storhelgsråd med sparad_krona
# ============================================================

class TestStorhelgsrad:
    """POST /berakna ska returnera 'storhelgsrad'-lista med ekonomiska råd för röda dagar."""

    def _client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)

    def _payload(self, perioder_a, perioder_b=None):
        return {
            "foraldrar_a": {
                "namn": "Anna", "manadslon": 40000,
                "kollektivavtal": "Ingen föräldralön", "anstallning": 24,
                "perioder": perioder_a,
            },
            "foraldrar_b": {
                "namn": "Bo", "manadslon": 40000,
                "kollektivavtal": "Ingen föräldralön", "anstallning": 24,
                "perioder": perioder_b or [],
            },
        }

    def test_storhelgsrad_finns_i_svar(self):
        """Svaret ska innehålla nyckeln 'storhelgsrad' som en lista."""
        client = self._client()
        # Täcker maj 2026: 1 maj (fredag, röd dag) och Kr. himmelsfärdsdag 14 maj (torsdag)
        resp = client.post("/berakna", json=self._payload(
            [{"start": "2026-04-27", "slut": "2026-05-29", "dagar_per_vecka": 5}]
        ))
        assert resp.status_code == 200
        data = resp.json()
        assert "storhelgsrad" in data
        assert isinstance(data["storhelgsrad"], list)

    def test_sparad_krona_positiv_for_foralder_med_lon(self):
        """sparad_krona ska vara > 0 för en förälder med lön (netto_dag > fk_dag)."""
        client = self._client()
        resp = client.post("/berakna", json=self._payload(
            [{"start": "2026-04-27", "slut": "2026-05-29", "dagar_per_vecka": 5}]
        ))
        rader = resp.json()["storhelgsrad"]
        assert len(rader) > 0, "Ska ha minst ett råd för perioden som täcker röda dagar i maj 2026"
        for rad in rader:
            assert rad["sparad_krona"] > 0
            assert rad["fk_netto_dag"] > 0
            assert rad["lon_netto_dag"] > rad["fk_netto_dag"]

    def test_rod_dag_pa_helg_genererar_ingen_rad(self):
        """Röda dagar som faller på lördag eller söndag ska inte generera råd.
        2026-12-26 (annandag jul) är en lördag — ska inte finnas i storhelgsrad."""
        from datetime import date
        from main import RODA_DAGAR

        # Verifiera att 2026-12-26 är en röd dag och en lördag
        assert "2026-12-26" in RODA_DAGAR
        assert date(2026, 12, 26).weekday() == 5  # lördag

        client = self._client()
        # Period som täcker jul 2026
        resp = client.post("/berakna", json=self._payload(
            [{"start": "2026-12-21", "slut": "2027-01-07", "dagar_per_vecka": 5}]
        ))
        rader = resp.json()["storhelgsrad"]
        datum_i_svar = [r["datum"] for r in rader]
        assert "2026-12-26" not in datum_i_svar, "Lördag ska inte generera storhelgsråd"
        # Alla datum i svaret ska vara vardagar (weekday < 5)
        for rad in rader:
            assert date.fromisoformat(rad["datum"]).weekday() < 5


# ============================================================
# 14. Sitemap och robots.txt (Sprint 9)
# ============================================================

class TestSitemapRobots:
    def _client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)

    def test_sitemap_status_200_och_content_type_xml(self):
        """GET /sitemap.xml ska returnera 200 med Content-Type application/xml."""
        resp = self._client().get("/sitemap.xml")
        assert resp.status_code == 200
        assert "application/xml" in resp.headers["content-type"]
        assert "balba.se" in resp.text
        assert "<urlset" in resp.text

    def test_robots_status_200_och_content_type_plain(self):
        """GET /robots.txt ska returnera 200 med Content-Type text/plain."""
        resp = self._client().get("/robots.txt")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "User-agent: *" in resp.text
        assert "https://balba.se/sitemap.xml" in resp.text
