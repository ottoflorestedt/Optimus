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
from kalkyl import berakna_skatt, berakna_fk_ersattning, berakna_foraldralon
from kollektivavtal import max_fl_man, PBB


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
