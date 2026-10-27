"""Estilo de raster: rampa contínua, classes, valores únicos, relevo sombreado e cinza.

Sem este comando um assistente não tinha como colorir um modelo de elevação,
classificar uma declividade ou dar nome às classes de um raster de uso da
terra: o raster entrava no mapa no cinza padrão do QGIS, com a legenda
"Band 1 (Gray)". Hipsometria e declividade por classes são o par de mapas
mais pedido em laudo ambiental.

As contas que não dependem do QGIS (limites de classe, rótulos, cores das
rampas próprias) ficam em funções puras, testáveis sem PyQGIS.
"""

from __future__ import annotations

import math
from typing import Any  # noqa: F401  (usado nas anotações abaixo)

from ..cartography.maptext import maptext, resolve_language
from ..cartography.qtcompat import QtEnumMissing, qt_enum
from ..cartography.rulebook import NODATA_SENTINELS as _NODATA_SENTINELS
from ..cartography.symbology import STYLE_ORIGIN_USER, mark_style_origin
from ..validators import ValidationError, require_param
from .common import layer_type_name, project

RASTER_STYLE_MODES = ("pseudocolor", "classes", "unique_values", "hillshade", "greyscale")

#: Rampas do próprio SIGMAI, além das do estilo padrão do QGIS. A hipsométrica
#: segue as tintas clássicas (verde nas baixadas, amarelo, castanho no alto);
#: a de declividade vai do verde (plano) ao vermelho escuro (escarpado).
SIGMAI_RAMPS: dict[str, tuple[str, ...]] = {
    "hypsometric": ("#0b6e4f", "#5aa05a", "#b7d98c", "#f2e8a0", "#e0b36a", "#b5713b", "#7a4a2a"),
    "slope": ("#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c", "#7f0000"),
    "heat": ("#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"),
}
#: Cores qualitativas para classes nominais, usadas uma a uma (classes sem
#: ordem não se interpolam): as sete de Okabe & Ito (2008) e quatro
#: complementares, escolhidas para que nenhum par se confunda nas três
#: simulações de daltonismo de CART070. O cinza de Okabe & Ito saiu: sob
#: deuteranopia ele e o verde-azulado ficavam a ΔE 11,9. A décima primeira é
#: um cinza-escuro, e não o preto, que numa unidade de mapa geológico
#: apagava os contornos internos.
QUALITATIVE = ("#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7",
               "#B8E186", "#762A83", "#B2182B", "#666666")

#: Cores com significado para classes de uso e cobertura da terra, solos e
#: afins, pelo nome da classe (português, inglês, espanhol). A ordem importa:
#: "Mosaico de ocupações em área florestal" é mosaico antes de ser floresta.
SEMANTIC_COLOURS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("mosaico", "mosaic"), "#D55E00"),
    (("água", "agua", "water", "hídric", "hidric", "lago", "lagoa", "reservat", "represa", "rio ", "corpo d"), "#0072B2"),
    (("úmida", "umida", "wetland", "brejo", "várzea", "varzea", "humedal", "alagad"), "#56B4E9"),
    (("mangue", "mangrove", "manglar"), "#004040"),
    (("urban", "artificial", "construíd", "construid", "edificad", "built", "cidade", "ciudad"), "#B2182B"),
    (("florest", "forest", "mata ", "tree", "bosque", "arbórea", "arborea"), "#009E73"),
    (("arbust", "shrub", "matorral"), "#E69F00"),
    (("campestre", "grassland", "campo", "herbác", "herbac", "savana", "pastizal", "gramín", "gramin"), "#B8E186"),
    (("pastagem", "pasture", "pasto", "pradera"), "#F0E442"),
    (("agríc", "agric", "crop", "lavoura", "cultivo", "cultura", "cultiv", "plantio"), "#CC79A7"),
    (("solo exposto", "bare", "sparse", "esparsa", "afloramento", "rocha", "desnudo", "mineração", "mineracao"), "#C0A060"),
)


def semantic_colour(value: Any) -> str | None:
    text = f" {str(value).casefold()} "
    for keys, colour in SEMANTIC_COLOURS:
        if any(key in text for key in keys):
            return colour
    return None


def lightness_positions(colours: list[str], count: int) -> list[float]:
    """Posições 0–1 de uma rampa em que a claridade (L*) cai em passos iguais.

    Amostrar a rampa em posições iguais deixava as classes claras quase
    iguais (as rampas do ColorBrewer comprimem o claro): a 1ª e a 2ª classe
    de Blues ficavam a ΔE 14 e CART070 reprovava. ``colours`` é a rampa
    amostrada em posições iguais (pelo menos 21 amostras). Rampa que não é
    monótona em claridade (Spectral) fica com as posições iguais.
    """
    from ..cartography.vision import parse_hex, to_lab

    if count <= 1:
        return [0.0]
    lightness = [to_lab(parse_hex(colour))[0] for colour in colours]
    steps = len(lightness) - 1
    increasing = all(b >= a - 0.5 for a, b in zip(lightness, lightness[1:]))
    decreasing = all(b <= a + 0.5 for a, b in zip(lightness, lightness[1:]))
    if not (increasing or decreasing) or abs(lightness[-1] - lightness[0]) < 10:
        return [k / float(count - 1) for k in range(count)]
    positions = []
    for k in range(count):
        target = lightness[0] + (lightness[-1] - lightness[0]) * k / float(count - 1)
        for index in range(steps):
            a, b = lightness[index], lightness[index + 1]
            if (a - target) * (b - target) <= 0 and a != b:
                positions.append((index + (target - a) / (b - a)) / steps)
                break
        else:
            positions.append(k / float(count - 1))
    return positions
RAMP_ALIASES = {"qualitativa": "qualitative", "categorias": "qualitative", "hipsometrica": "hypsometric", "hipsométrica": "hypsometric", "elevation": "hypsometric",
                "elevacao": "hypsometric", "elevação": "hypsometric", "declividade": "slope", "calor": "heat"}

#: Classes de relevo da Embrapa (Santos et al., 2018, Sistema Brasileiro de
#: Classificação de Solos, 5. ed.) pela declividade em porcentagem.
SLOPE_PRESETS: dict[str, dict[str, Any]] = {
    "declividade_embrapa": {
        "breaks": [0.0, 3.0, 8.0, 20.0, 45.0, 75.0, None],
        "unit": "%",
        "labels": {
            "pt-BR": ["Plano (0–3 %)", "Suave ondulado (3–8 %)", "Ondulado (8–20 %)", "Forte ondulado (20–45 %)",
                      "Montanhoso (45–75 %)", "Escarpado (> 75 %)"],
            "en": ["Flat (0–3%)", "Gently undulating (3–8%)", "Undulating (8–20%)", "Strongly undulating (20–45%)",
                   "Mountainous (45–75%)", "Steep (> 75%)"],
            "es": ["Plano (0–3 %)", "Suavemente ondulado (3–8 %)", "Ondulado (8–20 %)", "Fuertemente ondulado (20–45 %)",
                   "Montañoso (45–75 %)", "Escarpado (> 75 %)"],
        },
        "ramp": "slope",
    },
}
PRESET_ALIASES = {"embrapa": "declividade_embrapa", "slope_embrapa": "declividade_embrapa"}


# --- funções puras ---------------------------------------------------------

def ramp_name(value: Any) -> str:
    name = str(value or "").strip()
    return RAMP_ALIASES.get(name.lower(), name)


def interpolate_hex(stops: tuple[str, ...] | list[str], position: float) -> str:
    """Cor (hex) na posição 0–1 de uma rampa dada por paradas igualmente espaçadas."""
    position = min(1.0, max(0.0, float(position)))
    if len(stops) == 1:
        return stops[0]
    scaled = position * (len(stops) - 1)
    index = min(int(scaled), len(stops) - 2)
    frac = scaled - index
    a, b = stops[index].lstrip("#"), stops[index + 1].lstrip("#")
    channels = [round(int(a[k:k + 2], 16) + (int(b[k:k + 2], 16) - int(a[k:k + 2], 16)) * frac) for k in (0, 2, 4)]
    return "#" + "".join(f"{c:02x}" for c in channels)


def decimals_for(width: float) -> int:
    """Casas decimais que a largura de uma classe justifica."""
    width = abs(float(width))
    if width >= 10 or width == 0:
        return 0
    if width >= 1:
        return 1
    if width >= 0.1:
        return 2
    return 3


def format_number(value: float, decimals: int, language: str = "pt-BR") -> str:
    """Número com o separador de milhar e o decimal da língua do mapa."""
    thousands = maptext(language, "separador_milhar")
    decimal = "," if thousands == "." else "."
    text = f"{float(value):,.{int(decimals)}f}"
    return text.replace(",", "\x00").replace(".", decimal).replace("\x00", thousands)


def class_labels(breaks: list[float | None], unit: str = "", language: str = "pt-BR") -> list[str]:
    """Rótulos "a–b unidade" para limites de classe; ``None`` no fim é classe aberta ("> a")."""
    finite = [b for b in breaks if b is not None]
    widths = [b - a for a, b in zip(finite, finite[1:]) if b > a]
    whole = all(float(b).is_integer() for b in finite)
    decimals = 0 if whole or not widths else decimals_for(min(widths))
    suffix = f" {unit}" if unit and unit != "%" else unit
    labels = []
    for low, high in zip(breaks, breaks[1:]):
        if high is None:
            labels.append(f"> {format_number(low, decimals, language)}{suffix}")
        else:
            labels.append(f"{format_number(low, decimals, language)}–{format_number(high, decimals, language)}{suffix}")
    return labels


def equal_breaks(minimum: float, maximum: float, classes: int) -> list[float]:
    step = (maximum - minimum) / float(classes)
    return [minimum + step * k for k in range(classes)] + [maximum]


def quantile_breaks(values: list[float], classes: int) -> list[float]:
    ordered = sorted(values)
    n = len(ordered)
    cuts = [ordered[min(n - 1, int(round(n * k / classes)))] for k in range(1, classes)]
    edges = [ordered[0]] + cuts + [ordered[-1]]
    merged = [edges[0]]
    for edge in edges[1:]:
        if edge > merged[-1]:
            merged.append(edge)
    return merged


#: Valores de preenchimento tratados como sem dado (ver rulebook.NODATA_SENTINELS).
NODATA_SENTINELS = _NODATA_SENTINELS
#: Um extremo conta como pico isolado — e a rampa para no percentil, não
#: nele — quando está mais longe do percentil 0,5/99,5 do que esta fração da
#: amplitude entre os dois percentis. Num MDE limpo o máximo fica a ~6 %
#: dessa amplitude do percentil 99,5; um pixel de 9.000 m, a ~290 %.
RANGE_OUTLIER_GAP = 0.25


def _percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        raise ValueError("sem valores")
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def robust_range(values: list[float], declared_nodata: float | None = None) -> dict[str, Any]:
    """Mínimo e máximo da rampa: sem valores-sentinela de "sem dado" e sem picos isolados.

    Devolve ``min``, ``max``, ``sentinels`` (valores tratados como sem dado,
    com a contagem na amostra) e ``clipped`` (lados em que um pico isolado
    ficou fora da rampa, com o valor do pico). Puro, para teste sem QGIS.
    """
    finite = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    sentinels: dict[float, int] = {}
    kept: list[float] = []
    for value in finite:
        if declared_nodata is not None and value == declared_nodata:
            continue
        if any(value == s for s in NODATA_SENTINELS):
            sentinels[value] = sentinels.get(value, 0) + 1
        else:
            kept.append(value)
    if not kept:
        raise ValueError("todos os valores amostrados são sem dado")
    kept.sort()
    low, high = _percentile(kept, 0.005), _percentile(kept, 0.995)
    span = max(high - low, 1e-12)
    minimum, maximum = kept[0], kept[-1]
    clipped: dict[str, float] = {}
    if low - minimum > RANGE_OUTLIER_GAP * span:
        clipped["low"], minimum = minimum, low
    if maximum - high > RANGE_OUTLIER_GAP * span:
        clipped["high"], maximum = maximum, high
    return {"min": minimum, "max": maximum, "sentinels": sorted(sentinels.items()), "clipped": clipped}


def validate_breaks(raw: Any) -> list[float | None]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise ValidationError("BAD_REQUEST", "breaks precisa ser uma lista com pelo menos dois limites.", {"breaks": raw})
    out: list[float | None] = []
    for index, value in enumerate(raw):
        if value is None and index == len(raw) - 1 and index > 0:
            out.append(None)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("BAD_REQUEST", "breaks só aceita números (e null no fim, para classe aberta).",
                                  {"breaks": raw}) from exc
        if not math.isfinite(number):
            raise ValidationError("BAD_REQUEST", "breaks não aceita infinito; use null no fim.", {"breaks": raw})
        out.append(number)
    finite = [b for b in out if b is not None]
    if any(b <= a for a, b in zip(finite, finite[1:])):
        raise ValidationError("BAD_REQUEST", "breaks precisa ser estritamente crescente.", {"breaks": raw})
    return out


# --- QGIS -------------------------------------------------------------------

def _raster(layer_id: str) -> Any:
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    if layer_type_name(layer) != "raster":
        raise ValidationError("RASTER_LAYER_REQUIRED", "This command requires a raster layer.", {"layer_id": layer_id})
    if not layer.isValid():
        raise ValidationError("INVALID_RASTER_LAYER", "Raster layer is invalid.", {"layer_id": layer_id})
    return layer


def qgis_ramp(name: str, invert: bool = False) -> Any:
    """Rampa do QGIS pelo nome (estilo padrão) ou uma das rampas do SIGMAI."""
    from qgis.core import QgsGradientColorRamp, QgsGradientStop, QgsStyle  # type: ignore
    from qgis.PyQt.QtGui import QColor  # type: ignore

    key = ramp_name(name)
    if key in SIGMAI_RAMPS:
        stops = SIGMAI_RAMPS[key]
        inner = [QgsGradientStop(k / float(len(stops) - 1), QColor(stops[k])) for k in range(1, len(stops) - 1)]
        ramp = QgsGradientColorRamp(QColor(stops[0]), QColor(stops[-1]), False, inner)
    else:
        style = QgsStyle.defaultStyle()
        names = list(style.colorRampNames())
        match = next((n for n in names if n.lower() == key.lower()), None)
        if match is None:
            raise ValidationError(
                "BAD_REQUEST",
                f"Rampa de cores desconhecida: {name!r}. Use uma do SIGMAI ({', '.join(SIGMAI_RAMPS)}) "
                f"ou do estilo do QGIS ({', '.join(sorted(names)[:40])}).",
                {"color_ramp": name},
            )
        ramp = style.colorRamp(match)
    if invert:
        try:
            ramp.invert()
        except Exception:
            pass
    return ramp


def _statistics(layer: Any, band: int) -> tuple[float, float]:
    from qgis.core import Qgis, QgsRasterBandStats, QgsRectangle  # type: ignore

    try:
        flag = qt_enum(Qgis, "RasterBandStatistic", "All")
    except QtEnumMissing:
        flag = qt_enum(QgsRasterBandStats, "Stats", "All")
    stats = layer.dataProvider().bandStatistics(band, flag, QgsRectangle(), 250000)
    return float(stats.minimumValue), float(stats.maximumValue)


def _sample(layer: Any, band: int, size: int = 400) -> list[float]:
    provider = layer.dataProvider()
    block = provider.block(band, layer.extent(), size, size)
    no_data = provider.sourceNoDataValue(band) if provider.sourceHasNoDataValue(band) else None
    values = []
    for row in range(block.height()):
        for col in range(block.width()):
            if block.isNoData(row, col):
                continue
            value = block.value(row, col)
            if no_data is not None and value == no_data:
                continue
            if math.isfinite(value):
                values.append(float(value))
    return values


def _shader_type(kind: str) -> Any:
    from qgis.core import Qgis, QgsColorRampShader  # type: ignore

    modern = {"interpolated": "Linear", "discrete": "Discrete", "exact": "Exact"}[kind]
    legacy = {"interpolated": "Interpolated", "discrete": "Discrete", "exact": "Exact"}[kind]
    try:
        return qt_enum(Qgis, "ShaderInterpolationMethod", modern)
    except QtEnumMissing:
        return qt_enum(QgsColorRampShader, "Type", legacy)


def _legend_settings(unit: str, decimals: int, language: str) -> Any:
    from qgis.core import QgsBasicNumericFormat, QgsColorRampLegendNodeSettings  # type: ignore

    settings = QgsColorRampLegendNodeSettings()
    fmt = QgsBasicNumericFormat()
    thousands = maptext(language, "separador_milhar")
    fmt.setShowThousandsSeparator(bool(thousands))
    if thousands:
        fmt.setThousandsSeparator(thousands[0])
    fmt.setDecimalSeparator("," if thousands == "." else ".")
    fmt.setNumberDecimalPlaces(int(decimals))
    fmt.setShowTrailingZeros(False)
    settings.setNumericFormat(fmt)
    if unit:
        settings.setSuffix(f" {unit}" if unit != "%" else "%")
    settings.setUseContinuousLegend(True)
    return settings


def _pseudocolor(layer: Any, band: int, ramp: Any, items: list[tuple[float, str, str]], kind: str,
                 minimum: float, maximum: float, legend: Any | None) -> Any:
    from qgis.core import QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer  # type: ignore
    from qgis.PyQt.QtGui import QColor  # type: ignore

    shader_function = QgsColorRampShader(minimum, maximum)
    shader_function.setColorRampType(_shader_type(kind))
    try:
        shader_function.setSourceColorRamp(ramp.clone())
    except Exception:
        pass
    shader_function.setColorRampItemList(
        [QgsColorRampShader.ColorRampItem(value, QColor(colour), label) for value, colour, label in items])
    if legend is not None:
        try:
            shader_function.setLegendSettings(legend)
        except Exception:
            pass
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_function)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), band, shader)
    renderer.setClassificationMin(minimum)
    renderer.setClassificationMax(maximum)
    return renderer


BLEND_MODES = {"normal": "CompositionMode_SourceOver", "multiply": "CompositionMode_Multiply",
               "overlay": "CompositionMode_Overlay", "soft_light": "CompositionMode_SoftLight",
               "screen": "CompositionMode_Screen", "darken": "CompositionMode_Darken"}


def blend_mode_name(value: Any) -> str:
    name = str(value or "normal").strip().lower().replace("-", "_").replace(" ", "_")
    name = {"multiplicar": "multiply", "multiplicacao": "multiply", "multiplicação": "multiply",
            "sobrepor": "overlay", "luz_suave": "soft_light"}.get(name, name)
    if name not in BLEND_MODES:
        raise ValidationError("BAD_REQUEST", "blend_mode aceita " + ", ".join(BLEND_MODES) + ".", {"blend_mode": value})
    return name


def _blend_mode(name: str) -> Any:
    from qgis.PyQt.QtGui import QPainter  # type: ignore

    return qt_enum(QPainter, "CompositionMode", BLEND_MODES[name])


def _hex(colour: Any) -> str:
    return colour.name() if hasattr(colour, "name") else str(colour)


def apply_raster_style(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Colore um raster de banda única: rampa, classes, valores únicos, sombreado ou cinza."""
    layer = _raster(require_param(params, "layer_id", str))
    band = int(params.get("band", 1))
    if band < 1 or band > layer.bandCount():
        raise ValidationError("BAD_REQUEST", "band fora do intervalo do raster.", {"band": band, "band_count": layer.bandCount()})
    preset_key = str(params.get("preset") or "").strip().lower()
    preset_key = PRESET_ALIASES.get(preset_key, preset_key)
    if preset_key and preset_key not in SLOPE_PRESETS:
        raise ValidationError("BAD_REQUEST", f"preset desconhecido: {params.get('preset')!r}. Aceitos: {', '.join(SLOPE_PRESETS)}.",
                              {"preset": params.get("preset")})
    preset = SLOPE_PRESETS.get(preset_key, {})
    mode = str(params.get("mode") or ("classes" if preset else "pseudocolor")).strip().lower()
    if mode not in RASTER_STYLE_MODES:
        raise ValidationError("BAD_REQUEST", f"mode desconhecido: {mode!r}. Aceitos: {', '.join(RASTER_STYLE_MODES)}.",
                              {"mode": mode})
    language, _known = resolve_language(str(params.get("map_language") or "pt-BR"))
    unit = str(params.get("unit") if params.get("unit") is not None else preset.get("unit", "")).strip()
    ramp_key = ramp_name(params.get("color_ramp") or preset.get("ramp") or
                         {"pseudocolor": "hypsometric", "classes": "Viridis", "unique_values": "qualitative"}.get(mode, ""))
    invert = bool(params.get("invert", False))
    opacity = max(0.0, min(1.0, float(params.get("opacity", 1.0))))
    blend = blend_mode_name(params.get("blend_mode"))
    plan: dict[str, Any] = {"layer_id": layer.id(), "mode": mode, "band": band, "opacity": opacity, "blend_mode": blend}

    assumed_nodata: list[float] = []
    if mode in ("pseudocolor", "classes", "greyscale"):
        minimum = params.get("min")
        maximum = params.get("max")
        if minimum is None or maximum is None:
            provider = layer.dataProvider()
            declared = provider.sourceNoDataValue(band) if provider.sourceHasNoDataValue(band) else None
            try:
                found = robust_range(_sample(layer, band), declared)
            except ValueError:
                found = None
            if found is None:
                stat_min, stat_max = _statistics(layer, band)
                found = {"min": stat_min, "max": stat_max, "sentinels": [], "clipped": {}}
            minimum = found["min"] if minimum is None else float(minimum)
            maximum = found["max"] if maximum is None else float(maximum)
            assumed_nodata = [value for value, _count in found["sentinels"]]
            notes = []
            if assumed_nodata:
                notes.append(f"O raster não declara valor sem dado, mas tem {', '.join(f'{v:g}' for v in assumed_nodata)} "
                             "— valor de preenchimento de MDE, não um dado; tratado como sem dado nesta camada (o arquivo não muda).")
            for side, value in found["clipped"].items():
                notes.append(f"Pico isolado de {value:g} fora da rampa ({'mínimo' if side == 'low' else 'máximo'} "
                             f"da rampa em {minimum if side == 'low' else maximum:g}); passe min/max para usá-lo.")
            if notes:
                plan["notes"] = notes
            if assumed_nodata:
                plan["assumed_nodata"] = assumed_nodata
        minimum, maximum = float(minimum), float(maximum)
        if maximum <= minimum:
            raise ValidationError("BAD_REQUEST", "O raster não tem variação de valores para colorir.", {"min": minimum, "max": maximum})
        plan.update({"min": minimum, "max": maximum})

    if mode == "pseudocolor":
        classes = int(params.get("classes", 0) or 0)
        method = str(params.get("method") or ("continuous" if classes <= 1 else "equal_interval")).strip().lower()
        if method not in ("continuous", "equal_interval", "quantile"):
            raise ValidationError("BAD_REQUEST", "method aceita continuous, equal_interval ou quantile.", {"method": method})
        if method == "continuous":
            positions = [k / 6.0 for k in range(7)]
            values = [minimum + (maximum - minimum) * p for p in positions]
            breaks = values
            labels = [""] * len(values)
            kind = "interpolated"
        else:
            classes = max(2, min(12, classes or 5))
            sample = _sample(layer, band) if method == "quantile" else []
            breaks = quantile_breaks(sample, classes) if method == "quantile" else equal_breaks(minimum, maximum, classes)
            labels = class_labels(breaks, unit, language)
            kind = "discrete"
            if method == "quantile" and len(breaks) - 1 < classes:
                from .symbology import collapsed_classes_warning

                plan.setdefault("notes", []).append(
                    collapsed_classes_warning(sorted(sample), classes, len(breaks) - 1, method))
        plan.update({"color_ramp": ramp_key, "method": method, "breaks": [round(b, 6) for b in breaks]})
        if method != "continuous":
            plan["labels"] = labels
    elif mode == "classes":
        breaks_raw = params.get("breaks", preset.get("breaks"))
        if breaks_raw is None:
            raise ValidationError("BAD_REQUEST", "mode='classes' precisa de breaks (ou de um preset).", {})
        breaks_checked = validate_breaks(breaks_raw)
        given = params.get("labels")
        if given is not None:
            if not isinstance(given, list) or len(given) != len(breaks_checked) - 1:
                raise ValidationError("BAD_REQUEST", "labels precisa ter um rótulo por classe (len(breaks) - 1).",
                                      {"labels": given, "classes": len(breaks_checked) - 1})
            labels = [str(text) for text in given]
        elif preset:
            labels = list(preset["labels"].get(language) or preset["labels"]["en" if language != "pt-BR" else "pt-BR"])
        else:
            labels = class_labels(breaks_checked, unit, language)
        plan.update({"color_ramp": ramp_key, "breaks": breaks_checked, "labels": labels})
        if preset_key:
            plan["preset"] = preset_key
    elif mode == "unique_values":
        plan["color_ramp"] = ramp_key
    elif mode == "hillshade":
        crs = layer.crs()
        geographic = bool(crs and crs.isValid() and crs.isGeographic())
        z_factor = params.get("z_factor")
        z_factor = float(z_factor) if z_factor is not None else (1.0 / 111120.0 if geographic else 1.0)
        plan.update({"azimuth": float(params.get("azimuth", 315.0)), "altitude": float(params.get("altitude", 45.0)),
                     "z_factor": z_factor, "multidirectional": bool(params.get("multidirectional", False))})
        if geographic and params.get("z_factor") is None:
            plan["note"] = "Raster em graus: z_factor = 1/111120 (metros por grau no equador) para o relevo não sair chapado."

    if context.get("dry_run"):
        return {"dry_run": True, **plan}

    if mode == "pseudocolor":
        ramp = qgis_ramp(ramp_key, invert)
        n = len(breaks)
        if kind == "interpolated":
            items = [(value, _hex(ramp.color(k / float(n - 1))), "") for k, value in enumerate(breaks)]
            legend = _legend_settings(unit, decimals_for((maximum - minimum) / 6.0) if maximum - minimum < 60 else 0, language)
        else:
            count = n - 1
            items = [(breaks[k + 1] if k < count - 1 else float("inf"), _hex(ramp.color(k / float(max(1, count - 1)))),
                      labels[k]) for k in range(count)]
            legend = None
        renderer = _pseudocolor(layer, band, ramp, items, kind, minimum, maximum, legend)
    elif mode == "classes":
        ramp = qgis_ramp(ramp_key, invert)
        count = len(breaks_checked) - 1
        colours = params.get("colors")
        if colours is not None and (not isinstance(colours, list) or len(colours) != count):
            raise ValidationError("BAD_REQUEST", "colors precisa ter uma cor por classe.", {"colors": colours})
        items = []
        for k in range(count):
            upper = breaks_checked[k + 1]
            value = float("inf") if (upper is None or k == count - 1) else float(upper)
            colour = str(colours[k]) if colours else _hex(ramp.color(k / float(max(1, count - 1))))
            items.append((value, colour, labels[k]))
        renderer = _pseudocolor(layer, band, ramp, items, "discrete", minimum, maximum, None)
    elif mode == "unique_values":
        from qgis.core import QgsPalettedRasterRenderer  # type: ignore
        from qgis.PyQt.QtGui import QColor  # type: ignore

        existing = {}
        current = layer.renderer()
        if current is not None and str(current.type()) == "paletted" and params.get("keep_colours", True):
            existing = {float(c.value): c.color for c in current.classes()}
        found = QgsPalettedRasterRenderer.classDataFromRaster(layer.dataProvider(), band)
        names = {str(k): str(v) for k, v in (params.get("labels") or {}).items()} if isinstance(params.get("labels"), dict) else {}
        drop = {float(v) for v in (params.get("hide_values") or [])}
        values = [float(c.value) for c in found if float(c.value) not in drop]
        if not values:
            raise ValidationError("BAD_REQUEST", "O raster não tem valores para classificar.", {})
        if len(values) > 60:
            raise ValidationError("BAD_REQUEST", "Mais de 60 valores distintos: use mode='pseudocolor' ou 'classes'.",
                                  {"distinct_values": len(values)})
        ramp = None if ramp_key == "qualitative" else qgis_ramp(ramp_key, invert)
        classes = []
        for k, value in enumerate(values):
            key = str(int(value)) if value.is_integer() else str(value)
            fallback = (QUALITATIVE[k % len(QUALITATIVE)] if ramp is None
                        else _hex(ramp.color(k / float(max(1, len(values) - 1)))))
            colour = existing.get(value) or QColor(fallback)
            classes.append(QgsPalettedRasterRenderer.Class(value, colour, names.get(key, key)))
        renderer = QgsPalettedRasterRenderer(layer.dataProvider(), band, classes)
        plan["classes"] = [{"value": c.value, "label": c.label, "colour": c.color.name()} for c in classes]
    elif mode == "hillshade":
        from qgis.core import QgsHillshadeRenderer  # type: ignore

        renderer = QgsHillshadeRenderer(layer.dataProvider(), band, plan["azimuth"], plan["altitude"])
        renderer.setZFactor(plan["z_factor"])
        renderer.setMultiDirectional(plan["multidirectional"])
    else:  # greyscale
        from qgis.core import QgsContrastEnhancement, QgsSingleBandGrayRenderer  # type: ignore

        renderer = QgsSingleBandGrayRenderer(layer.dataProvider(), band)
        enhancement = QgsContrastEnhancement(layer.dataProvider().dataType(band))
        enhancement.setContrastEnhancementAlgorithm(
            qt_enum(QgsContrastEnhancement, "ContrastEnhancementAlgorithm", "StretchToMinimumMaximum"))
        enhancement.setMinimumValue(minimum)
        enhancement.setMaximumValue(maximum)
        renderer.setContrastEnhancement(enhancement)

    if assumed_nodata:
        # "Sem dado" do usuário, na camada: sem isso o bloco de -32.768 saía na
        # cor mais baixa da rampa. O arquivo de origem não é alterado.
        from qgis.core import QgsRasterRange  # type: ignore

        layer.dataProvider().setUserNoDataValue(band, [QgsRasterRange(value, value) for value in assumed_nodata])
    renderer.setOpacity(opacity)
    layer.setRenderer(renderer)
    layer.setBlendMode(_blend_mode(blend))
    if mode in ("pseudocolor", "hillshade"):
        _smooth_resampling(layer)
    mark_style_origin(layer, STYLE_ORIGIN_USER)
    layer.triggerRepaint()
    return plan


def _smooth_resampling(layer: Any) -> None:
    """Reamostragem bilinear para um raster contínuo (relevo, sombreamento), na leitura do dado.

    O padrão do QGIS é o vizinho mais próximo. Num mapa a 300 dpi, mais fino
    que os 30 m do Copernicus, o provedor repetia linhas e colunas de pixels
    antes do sombreamento, que via degraus onde o terreno é liso: a encosta
    saía quadriculada de riscas. A reamostragem tem de vir no provedor, antes
    do cálculo; depois dele só suavizaria as riscas já desenhadas. Classes e
    valores únicos continuam no vizinho mais próximo: interpolar uma classe
    inventa outra.
    """
    try:
        from qgis.core import Qgis, QgsRasterDataProvider  # type: ignore

        from ..cartography.qtcompat import qt_enum

        provider = layer.dataProvider()
        try:
            bilinear = qt_enum(Qgis, "RasterResamplingMethod", "Bilinear")
        except Exception:
            bilinear = qt_enum(QgsRasterDataProvider, "ResamplingMethod", "Bilinear")
        provider.enableProviderResampling(True)
        provider.setZoomedInResamplingMethod(bilinear)
        provider.setZoomedOutResamplingMethod(bilinear)
        provider.setMaxOversampling(2.0)
    except Exception:
        pass
