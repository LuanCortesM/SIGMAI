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

#: Preenchimentos de polígono, na ordem em que as camadas de polígono
#: aparecem (a primeira é normalmente o assunto, desenhada por cima).
#: Cada entrada é (matiz da paleta, quanto clarear em direção ao branco).
#:
#: Até a 1.0.3 todo preenchimento era o matiz clareado 82 % — e a própria
#: regra CART070 reprovava o mapa que o SIGMAI compunha: perto do branco os
#: matizes convergem e, nas simulações de Machado, Oliveira & Fernandes
#: (2009), azul-claro e verde-claro ficam a ΔE*ab 2,9 sob tritanopia. O que
#: sobrevive à simulação é a diferença de luminosidade, não a de matiz; a
#: sequência abaixo alterna claridades e matizes de eixos opostos, e os
#: quatro primeiros preenchimentos ficam a ΔE*ab ≥ 19 entre si em qualquer
#: das três simulações (o quinto cai a 14 — com cinco camadas de polígono
#: sobrepostas o aviso da regra é legítimo e o remédio são padrões).
#: A figura (assunto) recebe o laranja mais firme; o fundo, azul quase branco.
POLYGON_FILLS: tuple[tuple[str, float], ...] = (
    ("#D55E00", 0.45),  # assunto: laranja firme
    ("#0072B2", 0.85),  # contexto: azul quase branco
    ("#E69F00", 0.75),  # amarelo claro
    ("#009E73", 0.40),  # verde-azulado médio
    ("#56B4E9", 0.45),  # azul claro médio
    ("#CC79A7", 0.60),  # rosa
    ("#F0E442", 0.40),  # amarelo
    ("#000000", 0.80),  # cinza
)

#: Estilos por tipo de geometria. Preenchimentos claros e traços escuros:
#: mantêm o contraste figura/fundo sem competir com rótulos.
GEOMETRY_DEFAULTS: dict[str, dict[str, Any]] = {
    "Polygon": {"fill": "#CFE3EF", "stroke": "#0B4F6C", "stroke_width": 0.35, "opacity": 0.85},
    "Line": {"stroke": "#2A6F97", "stroke_width": 0.45, "opacity": 0.95},
    "Point": {"fill": "#D55E00", "stroke": "#4A2100", "stroke_width": 0.25, "size": 2.2, "opacity": 0.95},
}


#: Modos de cor da composição. ``"greyscale"`` existe porque periódicos
#: imprimem em tons de cinza e cobram a cor impressa: a *Transactions in GIS*
#: pede gráficos de linha em preto e branco e cobra £150 pela primeira figura
#: colorida no papel. Um mapa colorido convertido depois perde a distinção
#: entre preenchimentos de mesma luminosidade; composto em cinza, não.
COLOUR_MODES: tuple[str, ...] = ("colour", "greyscale")
_COLOUR_MODE_ALIASES = {
    "colour": "colour", "color": "colour", "cor": "colour", "colorido": "colour",
    "greyscale": "greyscale", "grayscale": "greyscale", "grey": "greyscale", "gray": "greyscale",
    "cinza": "greyscale", "tons_de_cinza": "greyscale", "monochrome": "greyscale",
    "black_and_white": "greyscale", "preto_e_branco": "greyscale", "bw": "greyscale",
}

#: Preenchimentos em cinza, na mesma ordem de POLYGON_FILLS: (cinza, padrão).
#: Quatro claridades a ΔL* ≥ 18 entre si (91, 73, 48 e 21) — o que sobra numa
#: figura sem matiz; da quinta camada em diante o tom se repete e a distinção
#: passa ao padrão de hachura. O assunto recebe o cinza médio e o contexto o
#: quase branco, como na paleta colorida.
GREY_POLYGON_FILLS: tuple[tuple[str, str], ...] = (
    ("#737373", "solid"),       # assunto: cinza médio (L* 48)
    ("#E6E6E6", "solid"),       # contexto: quase branco (L* 91)
    ("#B2B2B2", "solid"),       # cinza claro (L* 73)
    ("#333333", "solid"),       # cinza escuro (L* 21)
    ("#000000", "b_diagonal"),  # hachura diagonal
    ("#000000", "cross"),       # hachura cruzada
)
GREY_GEOMETRY_DEFAULTS: dict[str, dict[str, Any]] = {
    "Polygon": {"fill": "#E6E6E6", "stroke": "#1A1A1A", "stroke_width": 0.35, "opacity": 1.0},
    "Line": {"stroke": "#000000", "stroke_width": 0.5, "opacity": 1.0},
    "Point": {"fill": "#000000", "stroke": "#FFFFFF", "stroke_width": 0.3, "size": 2.4, "opacity": 1.0},
}
#: Espessura do contorno destacado de um polígono que contém outros (mm).
OUTLINE_STROKE_MM = 0.7
#: Contorno de uma subdivisão (municípios sobre a APA): fino, para não pesar.
OUTLINE_SUBDIVISION_STROKE_MM = 0.3
#: Cores dos contornos, uma por camada: dois contornos no mesmo cinza-escuro
#: eram indistinguíveis no mapa e na legenda (CART070).
OUTLINE_COLOURS = ("#1A1A1A", "#7B3294", "#B2182B", "#2166AC")
#: Curvas de nível em sépia, como nas cartas topográficas.
CONTOUR_COLOUR = "#8C510A"


def _dense_line_width(layer: Any, default: float) -> float:
    """Traço mais fino para camadas de linha densas: curvas de nível, malha viária estadual."""
    try:
        count = int(layer.featureCount())
    except Exception:
        return default
    if count > 2000:
        return min(default, 0.18)
    if count > 300:
        return min(default, 0.28)
    return default


def _semantic_layer_colour(layer: Any) -> str | None:
    """Cor pelo nome da camada (água, área urbana, floresta...), ou None."""
    try:
        from ..qgis_actions.raster_style import semantic_colour

        return semantic_colour(layer.name())
    except Exception:
        return None


def _is_contour_layer(layer: Any) -> bool:
    try:
        name = str(layer.name()).lower()
        if any(term in name for term in ("curva", "contour", "isolinha", "isoipsa", "höhenlinie", "courbe")):
            return True
        return layer.fields().indexOf("ELEV") >= 0
    except Exception:
        return False

#: Traços e pontos em cinza: preto, cinza escuro e cinza médio.
GREY_ACCENTS: tuple[str, ...] = ("#000000", "#4D4D4D", "#808080")


def normalize_colour_mode(value: Any) -> str:
    """``"colour"`` ou ``"greyscale"``; recusa qualquer outro valor com a lista."""
    key = str(value if value is not None else "colour").strip().lower().replace("-", "_").replace(" ", "_")
    if not key:
        return "colour"
    if key in _COLOUR_MODE_ALIASES:
        return _COLOUR_MODE_ALIASES[key]
    raise ParameterError(
        f"colour_mode desconhecido: {value!r}. Valores aceitos: {', '.join(COLOUR_MODES)} "
        "(também grayscale, grey, cinza, black_and_white)."
    )


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


#: Propriedade da camada em que o SIGMAI registra quem definiu o estilo atual.
#: ``"user"``: uma ação de simbologia da ponte (apply_single_symbol, estilo
#: graduado, QML carregado…) — intenção declarada, ``apply_style="missing"``
#: preserva. ``"sigmai_palette"``: a paleta segura de compose_map — também
#: preservada na composição seguinte, para que o mesmo mapa refeito não mude
#: de cor. Sem a propriedade, um símbolo único é o sorteio do QGIS ao carregar.
STYLE_ORIGIN_PROPERTY = "sigmai/style_origin"
STYLE_ORIGIN_USER = "user"
STYLE_ORIGIN_PALETTE = "sigmai_palette"


def mark_style_origin(layer: Any, origin: str) -> None:
    try:
        layer.setCustomProperty(STYLE_ORIGIN_PROPERTY, origin)
    except Exception:
        pass


def style_origin(layer: Any) -> str:
    try:
        return str(layer.customProperty(STYLE_ORIGIN_PROPERTY, "") or "")
    except Exception:
        return ""


def has_default_symbology(layer: Any) -> bool:
    """A camada ainda está sem intenção temática declarada no projeto?

    Um símbolo único que uma ação do SIGMAI acabou de aplicar (ou que a paleta
    da composição anterior definiu) NÃO é "padrão": antes, apply_single_symbol
    seguido de compose_map com apply_style='missing' reestilizava a camada
    que o assistente tinha acabado de estilizar — e o relatório dizia
    "estilizada", contradizendo a promessa da documentação.
    """
    try:
        renderer = layer.renderer()
    except Exception:
        return False
    if style_origin(layer) in (STYLE_ORIGIN_USER, STYLE_ORIGIN_PALETTE):
        return False
    return type(renderer).__name__ in RESTYLABLE_RENDERERS


#: Únicos valores que ``apply_style`` entende. Fora daqui era tratado como
#: sinônimo de ``"all"`` — o pior dos três, porque força a reestilização de
#: TODAS as camadas, inclusive as que o usuário já classificou. Um erro de
#: digitação ("tout", "todo", "sólido") não podia ter esse efeito colateral.
APPLY_STYLE_MODES: tuple[str, ...] = ("missing", "all", "none")


def apply_default_symbology(
    layers: list[Any], mode: str = "missing", dry_run: bool = False, colour_mode: str = "colour",
    outline_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
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
    greyscale = normalize_colour_mode(colour_mode) == "greyscale"
    from .qtcompat import geometry_type

    imports = _imports()
    applied: list[dict[str, Any]] = []
    # Preenchimentos de polígono já em uso pelas camadas que vão ser
    # preservadas (estilo do usuário ou de uma composição anterior). Um
    # preenchimento novo tem de ser distinguível deles: sem isto, a camada
    # preservada de um mapa anterior e a camada nova de agora saíam no
    # mesmo laranja — e CART070 reprovava o mapa que o SIGMAI compôs.
    fills_in_use: list[str] = []
    outlines_in_use: set[str] = set()
    if mode == "missing":
        for layer in layers:
            if hasattr(layer, "renderer") and hasattr(layer, "geometryType") and not has_default_symbology(layer):
                colour = _polygon_fill_of(layer, imports)
                if colour:
                    fills_in_use.append(colour)
                elif not _is_filled(layer):
                    # Contorno de uma composição anterior: outra camada que
                    # vire contorno agora não pode sair na mesma cor.
                    try:
                        outlines_in_use.add(layer.renderer().symbol().symbolLayer(0).strokeColor().name().upper())
                    except Exception:
                        pass
    polygon_slot = 0
    outline_slot = 0

    for index, layer in enumerate(layers):
        if not hasattr(layer, "renderer") or not hasattr(layer, "geometryType"):
            # Raster: a paleta não o toca, mas numa figura em cinza a cor dele
            # também sai no papel — converte mantendo as classes.
            if greyscale and hasattr(layer, "renderer"):
                converted = greyscale_layer_style(layer, dry_run=dry_run)
                if converted:
                    applied.append({"layer": layer.name(), "action": "preservada", "reason": "raster",
                                    "style_origin": style_origin(layer) or "project", "note": converted})
            continue  # raster ou camada sem simbologia vetorial
        needs_outline = bool(outline_ids) and layer.id() in outline_ids
        # A paleta de uma composição anterior é do próprio SIGMAI: refaz-se
        # quando agora o polígono tem de ser contorno, ou quando a figura
        # passou a ser em cinza e a paleta anterior era colorida.
        own_palette_outdated = style_origin(layer) == STYLE_ORIGIN_PALETTE and (
            (needs_outline and _is_filled(layer)) or (greyscale and _renderer_has_colour(layer)))
        if mode == "missing" and not has_default_symbology(layer) and not own_palette_outdated:
            origem_estilo = style_origin(layer)
            reason = {
                STYLE_ORIGIN_USER: "estilo definido por uma ação de simbologia (apply_single_symbol, graduado, categorizado ou QML)",
                STYLE_ORIGIN_PALETTE: "paleta aplicada numa composição anterior",
            }.get(origem_estilo, "simbologia temática já definida")
            entry = {"layer": layer.name(), "action": "preservada", "reason": reason, "style_origin": origem_estilo or "project"}
            if greyscale:
                converted = greyscale_layer_style(layer, dry_run=dry_run)
                if converted:
                    entry["note"] = converted
            applied.append(entry)
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

        style = dict((GREY_GEOMETRY_DEFAULTS if greyscale else GEOMETRY_DEFAULTS)[kind])
        # Camadas de mesmo tipo recebem matizes distintos da paleta segura.
        accent = OKABE_ITO[index % len(OKABE_ITO)]
        outline = kind == "Polygon" and bool(outline_ids) and layer.id() in outline_ids
        if outline:
            # Polígono que contém outros do mapa (o estado sobre os municípios):
            # preenchido, ele cobre o que contém — os municípios sumiam sob o
            # estado e continuavam na legenda. Vira contorno destacado, por cima.
            subdivision = False
            try:
                subdivision = int(layer.featureCount()) > 20
            except Exception:
                pass
            style.update({"fill": "255,255,255,0", "pattern": "no",
                          "stroke_width": OUTLINE_SUBDIVISION_STROKE_MM if subdivision else OUTLINE_STROKE_MM})
            free = [colour for colour in OUTLINE_COLOURS if colour.upper() not in outlines_in_use] or list(OUTLINE_COLOURS)
            accent = "#000000" if greyscale else free[outline_slot % len(free)]
            outlines_in_use.add(accent.upper())
            outline_slot += 1
        elif kind == "Line" and _is_contour_layer(layer):
            accent = "#4D4D4D" if greyscale else CONTOUR_COLOUR
            style["stroke_width"] = _dense_line_width(layer, 0.25)
        elif greyscale:
            accent = GREY_ACCENTS[index % len(GREY_ACCENTS)]
            if kind == "Polygon":
                fill, pattern = GREY_POLYGON_FILLS[polygon_slot % len(GREY_POLYGON_FILLS)]
                polygon_slot += 1
                style["fill"] = fill
                style["pattern"] = pattern
                accent = style["stroke"]
                fills_in_use.append(fill)
        elif kind == "Polygon":
            # Preenchimento derivado do próprio matiz: com um azul-claro fixo
            # para todos, duas camadas de polígono ficavam da mesma cor e só o
            # traço as distinguia — no papel, nada as distinguia. A sequência
            # POLYGON_FILLS alterna claridade e matiz para que as camadas de
            # polígono continuem distintas nas simulações de daltonismo.
            meaning = _semantic_layer_colour(layer)
            if meaning and _tint(meaning, 0.55) not in fills_in_use:
                # Camada cujo nome diz o que ela é: massas d'água em azul,
                # área urbana em vermelho — pela paleta em sequência elas
                # saíam laranja e azul-claro.
                accent = meaning
                style["fill"] = _tint(meaning, 0.55)
            else:
                accent, amount, polygon_slot = _next_polygon_fill(polygon_slot, fills_in_use)
                style["fill"] = _tint(accent, amount)
            fills_in_use.append(style["fill"])
        # Cor que de fato aparece no mapa: o preenchimento para polígono, o
        # próprio matiz para linha e ponto. Reportada em ambos os modos —
        # é o que permite a uma simulação dizer "com que cor" sem aplicá-la.
        if kind == "Line":
            style["stroke_width"] = _dense_line_width(layer, float(style.get("stroke_width", 0.45)))
        display_color = accent if outline else style.get("fill", accent)
        origem = type(layer.renderer()).__name__ if hasattr(layer, "renderer") else ""

        if dry_run:
            # Só relata o que SERIA feito. Nenhuma chamada a _build_symbol,
            # setRenderer ou triggerRepaint aqui: é a garantia de que uma
            # simulação não deixa a camada do usuário com uma cor diferente
            # da que tinha.
            registro = {"layer": layer.name(), "action": "seria_estilizada", "geometry": kind, "accent": accent, "color": display_color}
            if outline:
                registro["outline"] = True
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
            mark_style_origin(layer, STYLE_ORIGIN_PALETTE)
            layer.triggerRepaint()
            registro = {"layer": layer.name(), "action": "estilizada", "geometry": kind, "accent": accent, "color": display_color}
            if outline:
                registro["outline"] = True
            if origem == "QgsEmbeddedSymbolRenderer":
                registro["note"] = (
                    "o estilo vinha embutido no arquivo (KML/KMZ) e não gerava amostra na legenda; "
                    "passe apply_style='none' para mantê-lo"
                )
            applied.append(registro)
        except Exception:
            continue

    return applied


def _is_filled(layer: Any) -> bool:
    """O símbolo único da camada tem algum preenchimento (o contrário de um contorno)."""
    try:
        from qgis.PyQt.QtCore import Qt  # type: ignore

        from .qtcompat import qt_enum

        no_brush = qt_enum(Qt, "BrushStyle", "NoBrush")
        symbol = layer.renderer().symbol()
        return any(hasattr(symbol.symbolLayer(i), "brushStyle") and symbol.symbolLayer(i).brushStyle() != no_brush
                   for i in range(symbol.symbolLayerCount()))
    except Exception:
        return False


#: Claridade (0–255) dos cinzas de uma classificação convertida: do quase
#: branco ao quase preto. Cinco classes ficam a ΔL* ≥ 18 entre vizinhas.
GREY_CLASS_LIGHT, GREY_CLASS_DARK = 236, 38
#: Classes nominais além desta quantidade recebem hachuras em vez de mais cinzas.
GREY_CLASS_MAX_SOLID = 5
_GREY_HATCHES = ("b_diagonal", "f_diagonal", "cross", "horizontal", "vertical", "diagonal_x", "dense5", "dense3")
_HATCH_BRUSH = {"b_diagonal": "BDiagPattern", "f_diagonal": "FDiagPattern", "cross": "CrossPattern",
                "horizontal": "HorPattern", "vertical": "VerPattern", "diagonal_x": "DiagCrossPattern",
                "dense5": "Dense5Pattern", "dense3": "Dense3Pattern"}


def _renderer_has_colour(layer: Any) -> bool:
    """O símbolo único da camada tem matiz (não é cinza)."""
    try:
        return _has_colour(layer.renderer().symbol())
    except Exception:
        return False


def _luminance(colour: Any) -> float:
    return 0.2126 * colour.red() + 0.7152 * colour.green() + 0.0722 * colour.blue()


def _grey_levels(count: int) -> list[int]:
    """``count`` cinzas espaçados por igual, do claro para o escuro."""
    if count <= 1:
        return [128]
    step = (GREY_CLASS_LIGHT - GREY_CLASS_DARK) / float(count - 1)
    return [int(round(GREY_CLASS_LIGHT - step * i)) for i in range(count)]


def _grey_symbol(symbol: Any, level: int, hatch: str | None = None) -> Any:
    """O símbolo no cinza dado (preenchimento, traço ou marcador); o contorno vira cinza escuro."""
    from qgis.PyQt.QtCore import Qt  # type: ignore
    from qgis.PyQt.QtGui import QColor  # type: ignore

    from .qtcompat import qt_enum

    clone = symbol.clone()
    clone.setColor(QColor(level, level, level, clone.color().alpha()))
    for index in range(clone.symbolLayerCount()):
        symbol_layer = clone.symbolLayer(index)
        try:
            if hasattr(symbol_layer, "strokeColor") and hasattr(symbol_layer, "setStrokeColor"):
                stroke = symbol_layer.strokeColor()
                value = min(60, int(round(_luminance(stroke))))
                symbol_layer.setStrokeColor(QColor(value, value, value, stroke.alpha()))
            if hatch and hasattr(symbol_layer, "setBrushStyle"):
                symbol_layer.setBrushStyle(qt_enum(Qt, "BrushStyle", _HATCH_BRUSH[hatch]))
                symbol_layer.setColor(QColor(0, 0, 0))
        except Exception:
            continue
    return clone


def _has_colour(symbol: Any) -> bool:
    try:
        colours = [symbol.color()]
        for index in range(symbol.symbolLayerCount()):
            symbol_layer = symbol.symbolLayer(index)
            if hasattr(symbol_layer, "strokeColor"):
                colours.append(symbol_layer.strokeColor())
        return any(max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) >= 12 for c in colours)
    except Exception:
        return False


def greyscale_layer_style(layer: Any, dry_run: bool = False) -> str:
    """Converte para tons de cinza o estilo que a camada já tem, mantendo as classes.

    Numa figura pedida em cinza, uma camada com estilo próprio — uma
    classificação graduada ou categorizada, um raster em pseudocor — saía
    colorida e reprovava CART073; e o remédio de "reestilizar tudo" trocava
    as classes por um cinza único, apagando o mapa temático. Aqui cada
    classe recebe um cinza: do claro para o escuro numa graduação, na ordem
    da claridade original numa categorização (com hachuras além de seis
    classes). Devolve a nota do que foi (ou seria) feito, ou "".
    """
    try:
        renderer = layer.renderer()
    except Exception:
        return ""
    if renderer is None:
        return ""
    kind = str(renderer.type()) if callable(getattr(renderer, "type", None)) else ""
    verb = "seria convertida" if dry_run else "convertida"
    try:
        if not hasattr(layer, "geometryType"):
            return _greyscale_raster(layer, renderer, dry_run, verb)
        if kind == "graduatedSymbol":
            ranges = renderer.ranges()
            if not any(_has_colour(item.symbol()) for item in ranges):
                return ""
            if not dry_run:
                for index, (level, item) in enumerate(zip(_grey_levels(len(ranges)), ranges)):
                    renderer.updateRangeSymbol(index, _grey_symbol(item.symbol(), level))
            note = f"{verb} para tons de cinza mantendo as {len(ranges)} classes (do claro para o escuro)"
        elif kind == "categorizedSymbol":
            categories = renderer.categories()
            if not any(_has_colour(c.symbol()) for c in categories if c.symbol() is not None):
                return ""
            if not dry_run:
                order = sorted(range(len(categories)), key=lambda i: -_luminance(categories[i].symbol().color()))
                solid = min(len(order), GREY_CLASS_MAX_SOLID)
                levels = _grey_levels(solid)
                for rank, index in enumerate(order):
                    symbol = categories[index].symbol()
                    if symbol is None:
                        continue
                    if rank < solid:
                        renderer.updateCategorySymbol(index, _grey_symbol(symbol, levels[rank]))
                    else:
                        hatch = _GREY_HATCHES[(rank - solid) % len(_GREY_HATCHES)]
                        renderer.updateCategorySymbol(index, _grey_symbol(symbol, 255, hatch))
            note = f"{verb} para tons de cinza mantendo as {len(categories)} categorias"
        elif kind == "RuleRenderer":
            rules = [rule for rule in renderer.rootRule().descendants() if rule.symbol() is not None]
            if not any(_has_colour(rule.symbol()) for rule in rules):
                return ""
            if not dry_run:
                ordered = sorted(rules, key=lambda rule: -_luminance(rule.symbol().color()))
                for level, rule in zip(_grey_levels(len(ordered)), ordered):
                    rule.setSymbol(_grey_symbol(rule.symbol(), level))
            note = f"{verb} para tons de cinza mantendo as {len(rules)} regras"
        elif kind == "singleSymbol":
            symbol = renderer.symbol()
            if symbol is None or not _has_colour(symbol):
                return ""
            if not dry_run:
                renderer.setSymbol(_grey_symbol(symbol, int(round(_luminance(symbol.color())))))
            note = f"{verb} para cinza na claridade da cor original"
        else:
            return ""
    except Exception:
        return ""
    if not dry_run:
        layer.triggerRepaint()
    return note


def _greyscale_raster(layer: Any, renderer: Any, dry_run: bool, verb: str) -> str:
    """Raster: classes de uma paleta viram cinzas distintos; o resto passa por um filtro de luminosidade."""
    from qgis.PyQt.QtGui import QColor  # type: ignore

    kind = str(renderer.type())
    if kind in ("singlebandgray", "hillshade"):
        return ""
    if kind == "paletted":
        classes = list(renderer.classes())
        if not classes:
            return ""
        if not dry_run:
            from qgis.core import QgsPalettedRasterRenderer  # type: ignore

            order = sorted(range(len(classes)), key=lambda i: -_luminance(classes[i].color))
            levels = _grey_levels(len(classes))
            for rank, index in enumerate(order):
                classes[index].color = QColor(levels[rank], levels[rank], levels[rank], classes[index].color.alpha())
            grey = QgsPalettedRasterRenderer(layer.dataProvider(), renderer.band(), classes)
            grey.setOpacity(renderer.opacity())
            layer.setRenderer(grey)
            layer.triggerRepaint()
        return f"{verb} para tons de cinza mantendo as {len(classes)} classes"
    try:
        current = layer.hueSaturationFilter().grayscaleMode()
        off = getattr(getattr(type(layer.hueSaturationFilter()), "GrayscaleMode", None), "GrayscaleOff", 0)
        if current != off:
            return ""
    except Exception:
        pass
    if not dry_run:
        try:
            from qgis.core import QgsHueSaturationFilter  # type: ignore

            from .qtcompat import qt_enum

            layer.hueSaturationFilter().setGrayscaleMode(
                qt_enum(QgsHueSaturationFilter, "GrayscaleMode", "GrayscaleLuminosity"))
            layer.triggerRepaint()
        except Exception:
            return ""
    return f"{verb} para tons de cinza pela luminosidade"


def _polygon_fill_of(layer: Any, imports: dict[str, Any]) -> str:
    """Cor de preenchimento de uma camada de polígono com símbolo único, ou ''."""
    try:
        from .qtcompat import geometry_type

        if layer.geometryType() != geometry_type(imports["Qgis"], imports["QgsWkbTypes"], "Polygon"):
            return ""
        renderer = layer.renderer()
        if renderer is None or str(renderer.type()) != "singleSymbol" or not _is_filled(layer):
            return ""  # contorno não ocupa cor de preenchimento
        symbol = renderer.symbol()
        return str(symbol.color().name()).upper() if symbol is not None else ""
    except Exception:
        return ""


def _next_polygon_fill(slot: int, fills_in_use: list[str]) -> tuple[str, float, int]:
    """Próximo preenchimento da sequência que não se confunde com os já usados.

    Percorre ``POLYGON_FILLS`` a partir de ``slot`` e devolve o primeiro cujo
    tom não é confundível (CART070, ΔE*ab nas três simulações) com nenhum
    preenchimento já em uso; esgotada a sequência, devolve o próximo da fila
    mesmo assim — a auditoria dirá.
    """
    from .vision import confusable_pairs

    for offset in range(len(POLYGON_FILLS)):
        candidate = POLYGON_FILLS[(slot + offset) % len(POLYGON_FILLS)]
        colour = _tint(candidate[0], candidate[1])
        pairs = [("novo", colour)] + [(f"uso{i}", used) for i, used in enumerate(fills_in_use)]
        if not fills_in_use or not confusable_pairs(pairs):
            return candidate[0], candidate[1], (slot + offset + 1) % len(POLYGON_FILLS)
    candidate = POLYGON_FILLS[slot % len(POLYGON_FILLS)]
    return candidate[0], candidate[1], (slot + 1) % len(POLYGON_FILLS)


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
            "style": style.get("pattern", "solid"),
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
