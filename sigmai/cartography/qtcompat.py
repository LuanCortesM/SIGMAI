"""Acesso a enums do Qt e do QGIS que funciona em Qt5 e Qt6.

O PyQt5 expõe os enums tanto no escopo da classe (``Qt.NoBrush``) quanto,
nas versões recentes, no escopo qualificado (``Qt.BrushStyle.NoBrush``). O
PyQt6 removeu a forma curta. O QGIS 4 usa Qt6, e o SIGMAI declara
``qgisMaximumVersion=4.99``, então qualquer acesso na forma curta é uma falha
esperando o usuário atualizar.

O código do plugin acessava esses valores por um dicionário de imports
(``imports["QgsWkbTypes"].PolygonGeometry``), o que escondia o problema de
qualquer varredura estática. Este módulo centraliza a resolução: tenta a forma
qualificada, depois a curta, e falha com uma mensagem que diz qual símbolo
faltou em vez de um ``AttributeError`` nu.
"""

from __future__ import annotations

from typing import Any


class QtEnumMissing(AttributeError):
    """Nenhuma das variantes conhecidas do enum foi encontrada."""


def qt_enum(owner: Any, scope: str, member: str, *fallback_members: str) -> Any:
    """Resolve ``owner.scope.member`` com queda para ``owner.member``.

    ``fallback_members`` permite nomes alternativos entre versões do QGIS —
    por exemplo ``LayoutMillimeters`` (QgsUnitTypes, ≤3.28) e ``Millimeters``
    (Qgis.LayoutUnit, ≥3.30).
    """
    candidates = (member, *fallback_members)
    scoped = getattr(owner, scope, None)
    if scoped is not None:
        for name in candidates:
            value = getattr(scoped, name, None)
            if value is not None:
                return value
    for name in candidates:
        value = getattr(owner, name, None)
        if value is not None:
            return value
    raise QtEnumMissing(
        f"Nenhum de {candidates} encontrado em {getattr(owner, '__name__', owner)}"
        f" (escopo tentado: {scope})."
    )


def layout_unit_mm(qgis_module: Any, unit_types: Any) -> Any:
    """Unidade de milímetro de layout, do QGIS 3.28 ao 4.x.

    ``QgsUnitTypes.LayoutMillimeters`` está depreciado desde o QGIS 3.30 em
    favor de ``Qgis.LayoutUnit.Millimeters``; no Qt6 a forma antiga some.
    """
    try:
        return qt_enum(qgis_module, "LayoutUnit", "Millimeters")
    except QtEnumMissing:
        return qt_enum(unit_types, "LayoutUnit", "LayoutMillimeters", "Millimeters")


def distance_unit(qgis_module: Any, unit_types: Any, name: str) -> Any:
    """Unidade de distância pelo nome curto (``Kilometers``, ``Meters``...)."""
    try:
        return qt_enum(qgis_module, "DistanceUnit", name)
    except QtEnumMissing:
        return qt_enum(unit_types, "DistanceUnit", f"Distance{name}", name)


def geometry_type(qgis_module: Any, wkb_types: Any, name: str) -> Any:
    """Tipo de geometria (``Point``, ``Line``, ``Polygon``) em qualquer versão."""
    try:
        return qt_enum(qgis_module, "GeometryType", name)
    except QtEnumMissing:
        return qt_enum(wkb_types, "GeometryType", f"{name}Geometry", name)
