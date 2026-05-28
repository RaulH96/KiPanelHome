"""
Tests para las reglas de espejado por método.

Estas son LAS reglas más fáciles de equivocar del proyecto.
Si esto falla, las PCBs salen al revés y se desperdicia material.

Regla clave: KiCad plotea B.Cu desde la vista superior (ya espejada en X).
Por eso, para métodos donde el soporte va boca-abajo (Toner Transfer y Film UV
Convención A), el flip físico y el flip implícito de KiCad en B.Cu se cancelan:
  - F.Cu: SÍ espejada  (1 flip físico → compensar con pre-espejado)
  - B.Cu: NO espejada  (2 flips = KiCad + físico → se cancelan)
"""
import pytest
from kipanelh.core.methods import should_mirror
from kipanelh.core.models import TransferMethod, LayerSelection


@pytest.fixture
def empty_selection():
    return LayerSelection()


class TestTonerTransfer:
    """Planchado: papel boca-abajo. Top espejado, bottom normal."""

    def test_fcu_is_mirrored(self, empty_selection):
        assert should_mirror("F.Cu", TransferMethod.TONER_TRANSFER, empty_selection) is True

    def test_bcu_not_mirrored(self, empty_selection):
        assert should_mirror("B.Cu", TransferMethod.TONER_TRANSFER, empty_selection) is False

    def test_fsilks_mirrored_like_top(self, empty_selection):
        assert should_mirror("F.SilkS", TransferMethod.TONER_TRANSFER, empty_selection) is True

    def test_bsilks_not_mirrored(self, empty_selection):
        assert should_mirror("B.SilkS", TransferMethod.TONER_TRANSFER, empty_selection) is False


class TestFilmUV_ConvA:
    """
    Film UV Convención A — emulsión boca-abajo (recomendada).
    Mismo flip físico que toner transfer → mismo espejado.
    """

    def test_fcu_is_mirrored(self, empty_selection):
        assert should_mirror("F.Cu", TransferMethod.FILM_UV, empty_selection) is True

    def test_bcu_not_mirrored(self, empty_selection):
        assert should_mirror("B.Cu", TransferMethod.FILM_UV, empty_selection) is False

    def test_fsilks_mirrored_like_top(self, empty_selection):
        assert should_mirror("F.SilkS", TransferMethod.FILM_UV, empty_selection) is True

    def test_bsilks_not_mirrored(self, empty_selection):
        assert should_mirror("B.SilkS", TransferMethod.FILM_UV, empty_selection) is False


class TestFilmUV_ConvB:
    """
    Film UV Convención B — emulsión boca-arriba.
    Sin flip físico → lógica invertida: top normal, bottom espejada.
    """

    def test_fcu_not_mirrored(self, empty_selection):
        assert should_mirror("F.Cu", TransferMethod.FILM_UV_B, empty_selection) is False

    def test_bcu_is_mirrored(self, empty_selection):
        assert should_mirror("B.Cu", TransferMethod.FILM_UV_B, empty_selection) is True


class TestEdgeCuts:
    """Edge.Cuts nunca se espeja, es referencia geométrica."""

    def test_edge_cuts_toner(self, empty_selection):
        assert should_mirror("Edge.Cuts", TransferMethod.TONER_TRANSFER, empty_selection) is False

    def test_edge_cuts_film_a(self, empty_selection):
        assert should_mirror("Edge.Cuts", TransferMethod.FILM_UV, empty_selection) is False

    def test_edge_cuts_film_b(self, empty_selection):
        assert should_mirror("Edge.Cuts", TransferMethod.FILM_UV_B, empty_selection) is False


class TestCustom:
    """Custom respeta el override manual."""

    def test_custom_uses_override(self):
        sel = LayerSelection(mirror_override={"F.Cu": True, "B.Cu": False})
        assert should_mirror("F.Cu", TransferMethod.CUSTOM, sel) is True
        assert should_mirror("B.Cu", TransferMethod.CUSTOM, sel) is False

    def test_custom_default_no_mirror(self):
        sel = LayerSelection()
        assert should_mirror("F.Cu", TransferMethod.CUSTOM, sel) is False


class TestMirrorOverride:
    """mirror_override siempre tiene prioridad sobre la lógica del método."""

    def test_override_beats_toner_transfer(self):
        sel = LayerSelection(mirror_override={"B.Cu": True})
        # Por defecto Toner Transfer: B.Cu=False, pero override=True
        assert should_mirror("B.Cu", TransferMethod.TONER_TRANSFER, sel) is True

    def test_override_beats_film_uv(self):
        sel = LayerSelection(mirror_override={"F.Cu": False})
        # Por defecto Film UV Conv A: F.Cu=True, pero override=False
        assert should_mirror("F.Cu", TransferMethod.FILM_UV, sel) is False
