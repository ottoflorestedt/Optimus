import sys
sys.argv = ["kalkyl", "demo"]  # Förhindra interaktivt läge vid import

import pytest
from kalkyl import berakna_skatt, berakna_fk_ersattning, berakna_foraldralon, berakna_vecka


# ============================================================
#  berakna_skatt
# ============================================================

class TestBeraknaSkatt:
    def test_nettolön_40000(self):
        r = berakna_skatt(40000)
        assert r["nettolön/mån"] == 32380

    def test_nettolön_115000(self):
        r = berakna_skatt(115000)
        assert r["nettolön/mån"] == 72422

    def test_total_skatt_40000(self):
        r = berakna_skatt(40000)
        assert r["total_skatt/mån"] == 7620

    def test_total_skatt_115000(self):
        r = berakna_skatt(115000)
        assert r["total_skatt/mån"] == 42578

    def test_nettolön_plus_skatt_equals_brutto(self):
        for lon in [40000, 70000, 115000]:
            r = berakna_skatt(lon)
            assert r["nettolön/mån"] + r["total_skatt/mån"] == lon

    def test_kyrkoavgift_minskar_nettolön(self):
        utan = berakna_skatt(60000, kyrkoavgift=0.0)
        med  = berakna_skatt(60000, kyrkoavgift=0.01)
        assert med["nettolön/mån"] < utan["nettolön/mån"]

    def test_under_tabellintervall_netto_plus_skatt_equals_brutto(self):
        # lon = 20 000 kr ligger under tabellens nedre gräns (38 000 kr)
        r = berakna_skatt(20000)
        assert r["nettolön/mån"] + r["total_skatt/mån"] == 20000

    def test_over_tabellintervall_netto_plus_skatt_equals_brutto(self):
        # lon = 150 000 kr ligger över tabellens övre gräns (120 000 kr)
        r = berakna_skatt(150000)
        assert r["nettolön/mån"] + r["total_skatt/mån"] == 150000

    def test_effektiv_skattesats_ökar_monotont(self):
        r50  = berakna_skatt(50000)
        r100 = berakna_skatt(100000)
        r150 = berakna_skatt(150000)
        assert r50["effektiv_skattesats"] < r100["effektiv_skattesats"] < r150["effektiv_skattesats"]


# ============================================================
#  berakna_fk_ersattning
# ============================================================

class TestBeraknaFkErsattning:
    def test_fk_netto_dag_40000(self):
        r = berakna_fk_ersattning(40000, kommunalskatt=0.2999)
        assert r["fk_netto/dag"] == 714

    def test_fk_netto_dag_115000(self):
        r = berakna_fk_ersattning(115000, kommunalskatt=0.2999)
        assert r["fk_netto/dag"] == 881

    def test_sgi_tak_115000(self):
        r = berakna_fk_ersattning(115000)
        assert r["sgi/år"] == 592000

    def test_sgi_under_tak_40000(self):
        # SGI = lön × 12 (utan 97 %-faktor, per FK:s beräkningsmetod)
        r = berakna_fk_ersattning(40000)
        assert r["sgi/år"] == 40000 * 12

    def test_hög_lön_begränsas_av_tak(self):
        r_hög  = berakna_fk_ersattning(200000)
        r_115  = berakna_fk_ersattning(115000)
        assert r_hög["sgi/år"] == r_115["sgi/år"] == 592000


# ============================================================
#  berakna_foraldralon
# ============================================================

class TestBeraknaForaldralon:
    def test_finansförbundet_115000_36mån(self):
        # 360 dagar = 12 månader per Finansförbundets avtal
        r = berakna_foraldralon(115000, "Finansförbundet", 36)
        assert r["foraldralon/mån"] == 57467
        assert r["max_månader"] == 12

    def test_ingen_föräldralön_ger_noll(self):
        r = berakna_foraldralon(40000, "Ingen föräldralön", 24)
        assert r["foraldralon/mån"] == 0
        assert r["max_månader"] == 0

    def test_finansförbundet_gäller_från_dag_ett(self):
        # Finansförbundet gäller från dag 1 som tillsvidareanställd
        r = berakna_foraldralon(60000, "Finansförbundet", 1)
        assert r["foraldralon/mån"] > 0
        assert r["max_månader"] == 12

    def test_kort_anställning_ger_kort_period(self):
        # Unionen: krav 9 mån → 3 mån, krav 12 mån → 6 mån
        r = berakna_foraldralon(60000, "Unionen", 9)
        assert r["max_månader"] == 3

    def test_okänt_kollektivavtal(self):
        r = berakna_foraldralon(60000, "Okänt avtal", 24)
        assert r["foraldralon/mån"] == 0
        assert r["max_månader"] == 0

    def test_ab_under_krav_ger_noll(self):
        # 11 månader → under lägsta krav (12 mån)
        r = berakna_foraldralon(60000, "AB-avtalet", 11)
        assert r["max_månader"] == 0

    def test_ab_steg_1(self):
        # 12 månader → steg 1: 2 månaders föräldralön
        r = berakna_foraldralon(60000, "AB-avtalet", 12)
        assert r["max_månader"] == 2

    def test_ab_steg_3(self):
        # 36 månader → steg 3: 4 månaders föräldralön
        r = berakna_foraldralon(60000, "AB-avtalet", 36)
        assert r["max_månader"] == 4

    def test_ab_steg_5(self):
        # 60 månader → steg 5: 6 månaders föräldralön
        r = berakna_foraldralon(60000, "AB-avtalet", 60)
        assert r["max_månader"] == 6


# ============================================================
#  berakna_vecka – 0-7 FK-dagar per vecka
# ============================================================

class TestBeraknaVecka:
    """FK-ersättning betalas för lördag och söndag vid 6 eller 7 dagars uttag."""

    def _vecka(self, sp_a, sp_b=0, arb_b=5):
        return berakna_vecka(
            40000, 0.2999, "Ingen föräldralön", 24,
            sp_a, 0, 0, max(0, 5 - min(sp_a, 5)), False,
            40000, 0.2999, "Ingen föräldralön", 24,
            sp_b, 0, 0, arb_b, False,
        )

    def test_7_fk_dagar_ger_ingen_error(self):
        r = self._vecka(sp_a=7)
        assert r["nettoinkomst_a"] > 0

    def test_7_fk_dagar_ger_mer_inkomst_än_5(self):
        r5 = self._vecka(sp_a=5)
        r7 = self._vecka(sp_a=7)
        assert r7["nettoinkomst_a"] > r5["nettoinkomst_a"]

    def test_7_fk_dagar_är_7x_dagsnetto(self):
        # varav_fk_a ska vara exakt 7 × fk_netto/dag (inga avrundningsfel)
        fk = berakna_fk_ersattning(40000, kommunalskatt=0.2999)
        r  = self._vecka(sp_a=7)
        assert r["varav_fk_a"] == fk["fk_netto/dag"] * 7

    def test_6_fk_dagar_är_6x_dagsnetto(self):
        fk = berakna_fk_ersattning(40000, kommunalskatt=0.2999)
        r  = self._vecka(sp_a=6)
        assert r["varav_fk_a"] == fk["fk_netto/dag"] * 6
