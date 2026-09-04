"""Simbologia sóbria e segura para daltônicos, aplicada só quando faz sentido.

Ao carregar um vetor, o QGIS atribui uma cor aleatória. É de onde vêm os
polígonos rosa-choque e as drenagens em verde-limão dos mapas gerados
automaticamente. Ao mesmo tempo, sobrescrever a simbologia de quem já
classificou uma camada seria destrutivo.

O critério adotado aqui: só reestiliza camadas cujo renderizador ainda é um
símbolo único — ou seja, nenhuma intenção temática foi expressa. Camadas
categorizadas, graduadas ou com regras ficam intocadas.

A paleta segue a proposta de Okabe & Ito para distinção segura sob as três
formas comuns de daltonismo, com as saturações rebaixadas para uso em fundo de
mapa.
"""

from __future__ import annotations

from typing import Any

#: Paleta qualitativa segura para daltônicos (Okabe & Ito), adaptada.
OKABE_ITO = (
    "#0072B2",  # azul
    "#D55E00",  # vermelho-alaranjado
    "#009E73",  # verde-azulado
    "#CC79A7",  # rosa
    "#E69F00",  # laranja
    "#56B4E9",  # azul claro
    "#F0E442",  # amarelo
    "#000000",  # preto
)

#: Estilos por tipo de geometria. Preenchimentos claros e traços escuros:
#: mantêm o contraste figura/fundo sem competir com rótulos.
GEOMETRY_DEFAULTS: dict[str, dict[str, Any]] = {
    "Polygon": {"fill": "#CFE3EF", "stroke": "#0B4F6C", "stroke_width": 0.35, "opacity": 0.85},
    "Line": {"stroke": "#2A6F97", "stroke_width": 0.45, "opacity": 0.95},
    "Point": {"fill": "#D55E00", "stroke": "#4A2100", "stroke_width": 0.25, "size": 2.2, "opacity": 0.95},
}


def _imports() -> dict[str, Any]:
    from qgis.PyQt.QtGui import QColor  # type: ignore
    from qgis.core import (  # type: ignore
        Qgis,
        QgsFillSymbol,
        QgsLineSymbol,
        QgsMarkerSymbol,
        QgsSingleSymbolRenderer,
        QgsWkbTypes,
    )

    resolved = dict(locals())
    return resolved


def has_default_symbology(layer: Any) -> bool:
    """A camada ainda usa um símbolo único, sem intenção temática declarada?"""
    try:
        renderer = layer.renderer()
    except Exception:
        return False
    return type(renderer).__name__ == "QgsSingleSymbolRenderer"


def apply_default_symbology(layers: list[Any], mode: str = "missing") -> list[dict[str, Any]]:
    """Aplica a paleta padrão às camadas elegíveis.

    ``mode`` aceita ``"missing"`` (só camadas com símbolo único), ``"all"``
    (força em todas) e ``"none"`` (não faz nada).
    """
    if mode == "none":
        return []
    from .qtcompat import geometry_type

    imports = _imports()
    applied: list[dict[str, Any]] = []

    for index, layer in enumerate(layers):
        if not hasattr(layer, "renderer") or not hasattr(layer, "geometryType"):
            continue  # raster ou camada sem simbologia vetorial
        if mode == "missing" and not has_default_symbology(layer):
            applied.append({"layer": layer.name(), "action": "preservada", "reason": "simbologia temática já definida"})
            continue

        try:
            geometry = layer.geometryType()
        except Exception:
            continue

        kind = None
        for name in ("Polygon", "Line", "Point"):
            try:
                if geometry == geometry_type(imports["Qgis"], imports["QgsWkbTypes"], name):
                    kind = name
                    break
            except Exception:
                continue
        if kind is None:
            continue

        style = dict(GEOMETRY_DEFAULTS[kind])
        # Camadas de mesmo tipo recebem matizes distintos da paleta segura.
        accent = OKABE_ITO[index % len(OKABE_ITO)]
        symbol = _build_symbol(kind, style, accent, imports)
        if symbol is None:
            continue
        try:
            layer.setRenderer(imports["QgsSingleSymbolRenderer"](symbol))
            layer.triggerRepaint()
            applied.append({"layer": layer.name(), "action": "estilizada", "geometry": kind, "accent": accent})
        except Exception:
            continue

    return applied


def _build_symbol(kind: str, style: dict[str, Any], accent: str, imports: dict[str, Any]) -> Any:
    if kind == "Polygon":
        symbol = imports["QgsFillSymbol"].createSimple({
            "color": style["fill"],
            "outline_color": accent,
            "outline_width": str(style["stroke_width"]),
            "style": "solid",
        })
    elif kind == "Line":
        symbol = imports["QgsLineSymbol"].createSimple({
            "line_color": accent,
            "line_width": str(style["stroke_width"]),
        })
    else:
        symbol = imports["QgsMarkerSymbol"].createSimple({
            "name": "circle",
            "color": accent,
            "outline_color": style["stroke"],
            "outline_width": str(style["stroke_width"]),
            "size": str(style["size"]),
        })
    try:
        symbol.setOpacity(float(style.get("opacity", 1.0)))
    except Exception:
        pass
    return symbol
