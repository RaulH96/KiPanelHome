"""
Reglas de espejado por método de transferencia.

La regla fundamental:
  KiCad plotea B.Cu desde la vista superior (= ya espejada en X respecto a la
  cara física de abajo). Por tanto, para ambos métodos, el flip físico del
  acetato/papel (boca-abajo al transferir) y el flip implícito de KiCad en B.Cu
  se CANCELAN → B.Cu nunca necesita espejado adicional.

Toner Transfer y Film UV Convención A comparten la misma lógica de espejado:
  - F.Cu (cara superior): SÍ espejada  (1 flip al voltear → pre-espejado compensa)
  - B.Cu (cara inferior): NO espejada  (KiCad ya incluye 1 flip; 2 flips = correcto)

Film UV Convención B (acetato boca-arriba, emulsión lejos de la placa):
  - F.Cu: NO espejada  (no hay flip físico, la imagen llega directa)
  - B.Cu: SÍ espejada  (KiCad ya incluye 1 flip; sin flip físico = necesita corrección)
"""
from __future__ import annotations
from .models import TransferMethod, LayerSelection


# Capas de cobre conocidas y su lado físico
TOP_CU_LAYERS = {"F.Cu", "F.SilkS", "F.Mask", "F.Paste"}
BOTTOM_CU_LAYERS = {"B.Cu", "B.SilkS", "B.Mask", "B.Paste"}


def _is_top_layer(layer_name: str) -> bool:
    return layer_name.startswith("F.") or layer_name in TOP_CU_LAYERS


def _is_bottom_layer(layer_name: str) -> bool:
    return layer_name.startswith("B.") or layer_name in BOTTOM_CU_LAYERS


def should_mirror(layer_name: str, method: TransferMethod,
                  layer_selection: LayerSelection) -> bool:
    """
    Decide si la capa se imprime espejada.

    mirror_override tiene siempre prioridad sobre la lógica del método.
    """
    # Override explícito de la UI (cualquier método)
    if layer_name in layer_selection.mirror_override:
        return layer_selection.mirror_override[layer_name]

    if method == TransferMethod.CUSTOM:
        return False  # sin override y sin default: no espejar

    # Edge.Cuts y capas internas: no se espejan, son referencia
    if layer_name == "Edge.Cuts":
        return False
    if "In" in layer_name and ".Cu" in layer_name:
        return False

    if method in (TransferMethod.TONER_TRANSFER, TransferMethod.FILM_UV):
        # Ambos métodos colocan el soporte boca-abajo sobre el cobre
        # (papel para toner, acetato emulsión-abajo para film UV Convención A).
        # El flip físico + el flip implícito de KiCad en B.Cu se cancelan.
        if _is_top_layer(layer_name):
            return True   # F.Cu: espejar para compensar el flip físico
        if _is_bottom_layer(layer_name):
            return False  # B.Cu: KiCad ya incluye el flip; dos flips = correcto

    if method == TransferMethod.FILM_UV_B:
        # Convención B: acetato boca-arriba, emulsión alejada de la placa.
        # No hay flip físico → la lógica se invierte respecto a Convención A.
        if _is_top_layer(layer_name):
            return False
        if _is_bottom_layer(layer_name):
            return True

    # Default: no espejar si no se reconoce la capa
    return False


def describe_method(method: TransferMethod) -> str:
    """Texto descriptivo del método, útil para UI y manifest."""
    descriptions = {
        TransferMethod.TONER_TRANSFER: (
            "Planchado: imprime en papel couché/fotográfico, plancha boca-abajo. "
            "F.Cu espejada, B.Cu normal."
        ),
        TransferMethod.FILM_UV: (
            "Film UV — Convención A (emulsión hacia el cobre): acetato boca-abajo "
            "tocando la placa. Mejor contacto, sin difracción. "
            "F.Cu espejada, B.Cu normal (igual que planchado)."
        ),
        TransferMethod.FILM_UV_B: (
            "Film UV — Convención B (emulsión hacia arriba): cara limpia del acetato "
            "toca la placa. Mayor difracción. F.Cu normal, B.Cu espejada."
        ),
        TransferMethod.CUSTOM: (
            "Custom: el usuario define espejado por capa manualmente."
        ),
    }
    return descriptions.get(method, "")
