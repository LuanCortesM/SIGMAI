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

from .params import ParameterError

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


#: Renderizadores que não expressam classificação feita pelo usuário no QGIS.
#: ``QgsEmbeddedSymbolRenderer`` é o que o QGIS usa quando o próprio arquivo traz
#: o estilo — o caso dos KML de órgãos ambientais, que chegam com um traço fino
#: sem preenchimento, herdado do Google Earth, e que não produz amostra na
#: legenda. Preservar isso entrega um mapa com uma entrada de legenda vazia.
RESTYLABLE_RENDERERS = ("QgsSingleSymbolRenderer", "QgsEmbeddedSymbolRenderer")


def has_default_symbology(layer: Any) -> bool:
    """A camada ainda está sem intenção temática declarada no projeto?"""
    try:
        renderer = layer.renderer()
    except Exception:
        return False
    return type(renderer).__name__ in RESTYLABLE_RENDERERS


#: Únicos valores que ``apply_style`` entende. Fora daqui era tratado como
#: sinônimo de ``"all"`` — o pior dos três, porque força a reestilização de
#: TODAS as camadas, inclusive as que o usuário já classificou. Um erro de
#: digitação ("tout", "todo", "sólido") não podia ter esse efeito colateral.
APPLY_STYLE_MODES: tuple[str, ...] = ("missing", "all", "none")


def apply_default_symbology(layers: list[Any], mode: str = "missing", dry_run: bool = False) -> list[dict[str, Any]]:
    """Aplica a paleta padrão às camadas elegíveis.

    ``mode`` aceita ``"missing"`` (só camadas com símbolo único), ``"all"``
    (força em todas) e ``"none"`` (não faz nada). Qualquer outro valor é
    recusado explicitamente — a validação vem antes de qualquer import do
    PyQGIS para que continue possível testá-la em CI puro.

    ``dry_run=True`` calcula e devolve exatamente o mesmo relatório — quais
    camadas seriam reestilizadas, com que geometria e cor — mas nunca chama
    ``layer.setRenderer(...)``. Existe porque ``compose_map`` chamava esta
    função incondicionalmente antes de checar seu próprio ``dry_run``: uma
    simulação anotada como somente leitura reestilizava de verdade as
    camadas do projeto aberto na tela do usuário. A causa era aqui, não em
    ``compose_map`` — por isso a correção também é aqui: quem decide se algo
    é mutado é quem de fato muta.
    """
    if mode not in APPLY_STYLE_MODES:
        import difflib

        near = difflib.get_close_matches(str(mode), APPLY_STYLE_MODES, n=1, cutoff=0.4)
        suggestion = f" Você quis dizer {near[0]!r}?" if near else ""
        raise ParameterError(
            f"apply_style desconhecido: {mode!r}.{suggestion} "
            f"Valores aceitos: {', '.join(APPLY_STYLE_MODES)}."
        )
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
        if kind == "Polygon":
            # Preenchimento derivado do próprio matiz: com um azul-claro fixo
            # para todos, duas camadas de polígono ficavam da mesma cor e só o
            # traço as distinguia — no papel, nada as distinguia.
            style["fill"] = _tint(accent, 0.82)
        # Cor que de fato aparece no mapa: o preenchimento para polígono, o
        # próprio matiz para linha e ponto. Reportada em ambos os modos —
        # é o que permite a uma simulação dizer "com que cor" sem aplicá-la.
        display_color = style.get("fill", accent)
        origem = type(layer.renderer()).__name__ if hasattr(layer, "renderer") else ""

        if dry_run:
            # Só relata o que SERIA feito. Nenhuma chamada a _build_symbol,
            # setRenderer ou triggerRepaint aqui: é a garantia de que uma
            # simulação não deixa a camada do usuário com uma cor diferente
            # da que tinha.
            registro = {"layer": layer.name(), "action": "seria_estilizada", "geometry": kind, "accent": accent, "color": display_color}
            if origem == "QgsEmbeddedSymbolRenderer":
                registro["note"] = (
                    "o estilo vem embutido no arquivo (KML/KMZ) e não gera amostra na legenda; "
                    "passe apply_style='none' para mantê-lo"
                )
            applied.append(registro)
            continue

        symbol = _build_symbol(kind, style, accent, imports)
        if symbol is None:
            continue
        try:
            layer.setRenderer(imports["QgsSingleSymbolRenderer"](symbol))
            layer.triggerRepaint()
            registro = {"layer": layer.name(), "action": "estilizada", "geometry": kind, "accent": accent, "color": display_color}
            if origem == "QgsEmbeddedSymbolRenderer":
                registro["note"] = (
                    "o estilo vinha embutido no arquivo (KML/KMZ) e não gerava amostra na legenda; "
                    "passe apply_style='none' para mantê-lo"
                )
            applied.append(registro)
        except Exception:
            continue

    return applied


def _tint(hex_color: str, amount: float) -> str:
    """Clareia uma cor em direção ao branco, mantendo o matiz.

    ``amount`` 0 devolve a cor original; 1 devolve branco. Serve para tirar do
    matiz de destaque um preenchimento que não compita com os rótulos.
    """
    texto = hex_color.lstrip("#")
    if len(texto) != 6:
        return hex_color
    try:
        canais = [int(texto[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return hex_color
    fator = max(0.0, min(1.0, amount))
    claros = [round(canal + (255 - canal) * fator) for canal in canais]
    return "#" + "".join(f"{canal:02X}" for canal in claros)


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
