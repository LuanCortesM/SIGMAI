"""Escala, ajuste de extensão, barra de escala e grade de coordenadas.

Python puro, sem PyQGIS, para poder rodar em CI. Concentra as decisões
numéricas que separam um mapa técnico de uma captura de tela:

* a escala impressa é um valor da série cartográfica, não ``1:37.412``;
* a extensão é ajustada à razão de aspecto do quadro, para que a margem
  pedida seja a margem realmente obtida nos dois eixos;
* a barra de escala ocupa uma fração legível do quadro e termina num número
  redondo;
* o intervalo da grade cai em valores que uma pessoa consegue ler.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

#: Série de escalas usada em cartografia técnica e acadêmica. Combina os
#: valores da série 1/2/2,5/5 × 10ⁿ com as escalas de mapeamento sistemático
#: mais comuns (1:15.000, 1:75.000, 1:150.000...).
SCALE_LADDER: tuple[int, ...] = (
    100, 200, 250, 500,
    1_000, 1_500, 2_000, 2_500, 5_000, 7_500,
    10_000, 15_000, 20_000, 25_000, 50_000, 75_000,
    100_000, 150_000, 200_000, 250_000, 500_000, 750_000,
    1_000_000, 1_500_000, 2_000_000, 2_500_000, 5_000_000,
    10_000_000, 25_000_000, 50_000_000, 100_000_000,
)

#: Fração do quadro do mapa que uma barra de escala deve ocupar. Abaixo de
#: ~15% ela vira enfeite ilegível; acima de ~45% compete com o mapa.
SCALEBAR_TARGET_FRACTION = 0.28
SCALEBAR_MIN_FRACTION = 0.15
SCALEBAR_MAX_FRACTION = 0.45

#: Intervalos de grade aceitáveis em graus decimais, ancorados em frações
#: sexagesimais (1', 5', 10', 15', 30') para que os rótulos sejam legíveis.
DEGREE_INTERVALS: tuple[float, ...] = (
    1 / 3600, 2 / 3600, 5 / 3600, 10 / 3600, 15 / 3600, 30 / 3600,
    1 / 60, 2 / 60, 5 / 60, 10 / 60, 15 / 60, 30 / 60,
    1.0, 2.0, 5.0, 10.0, 15.0, 30.0,
)

_MM_PER_METRE = 1000.0


class ExtentError(ValueError):
    """Extensão geometricamente inválida."""


# ---------------------------------------------------------------------------
# Números "bonitos"
# ---------------------------------------------------------------------------

def nice_number(value: float, round_mode: str = "nearest") -> float:
    """Aproxima ``value`` para 1, 2, 2,5 ou 5 vezes uma potência de dez.

    É a heurística clássica de Heckbert para eixos de gráfico, com o degrau
    extra de 2,5 que a cartografia usa (1:2.500, 1:25.000).

    ``round_mode`` aceita ``"nearest"``, ``"up"`` e ``"down"``.
    """
    if value <= 0 or not math.isfinite(value):
        raise ValueError("nice_number requer um valor positivo e finito.")

    exponent = math.floor(math.log10(value))
    fraction = value / (10 ** exponent)
    steps = (1.0, 2.0, 2.5, 5.0, 10.0)

    if round_mode == "up":
        chosen = next((step for step in steps if fraction <= step * (1 + 1e-9)), 10.0)
    elif round_mode == "down":
        chosen = 1.0
        for step in steps:
            if step <= fraction * (1 + 1e-9):
                chosen = step
    else:
        chosen = min(steps, key=lambda step: abs(step - fraction))

    return chosen * (10 ** exponent)


def _snap_to_ladder(value: float, ladder: Iterable[float], round_mode: str) -> float:
    ordered = sorted(ladder)
    if round_mode == "up":
        return next((item for item in ordered if item >= value), ordered[-1])
    if round_mode == "down":
        below = [item for item in ordered if item <= value]
        return below[-1] if below else ordered[0]
    return min(ordered, key=lambda item: abs(math.log10(item) - math.log10(value)))


# ---------------------------------------------------------------------------
# Escala
# ---------------------------------------------------------------------------

def scale_from_extent(
    extent_width_map_units: float,
    frame_width_mm: float,
    map_units_per_metre: float = 1.0,
) -> float:
    """Denominador de escala bruto para uma extensão dentro de um quadro.

    ``map_units_per_metre`` é 1 para CRS métricos. Para CRS geográficos o
    chamador deve converter graus em metros antes (a conversão depende da
    latitude), e não usar esta função com graus crus.
    """
    if frame_width_mm <= 0:
        raise ValueError("A largura do quadro deve ser positiva.")
    if extent_width_map_units <= 0:
        raise ExtentError("A largura da extensão deve ser positiva.")
    ground_metres = extent_width_map_units / map_units_per_metre
    return (ground_metres * _MM_PER_METRE) / frame_width_mm


def round_scale(raw_scale: float, round_mode: str = "up") -> int:
    """Encaixa uma escala bruta na série cartográfica."""
    if raw_scale <= 0 or not math.isfinite(raw_scale):
        raise ValueError("A escala deve ser positiva e finita.")
    if raw_scale > SCALE_LADDER[-1]:
        return int(nice_number(raw_scale, "up"))
    if raw_scale < SCALE_LADDER[0]:
        return SCALE_LADDER[0]
    return int(_snap_to_ladder(raw_scale, SCALE_LADDER, round_mode))


def _round_up_significant(value: float, digits: int = 2) -> int:
    """Arredonda para cima mantendo ``digits`` algarismos significativos."""
    if value <= 0:
        raise ValueError("O valor deve ser positivo.")
    exponent = math.floor(math.log10(value)) - (digits - 1)
    step = 10 ** exponent
    return int(math.ceil(value / step) * step)


def choose_publication_scale(
    minimum_scale: float,
    target_scale: float,
    max_effective_margin_percent: float = 25.0,
) -> tuple[int, str]:
    """Escolhe a escala impressa entre o mínimo que contém os dados e o alvo.

    ``minimum_scale`` é a escala em que a extensão dos dados encosta na borda
    do quadro; qualquer escala menor cortaria dados. ``target_scale`` é essa
    mesma escala com a margem pedida.

    A série cartográfica tem degraus largos no topo (250.000 salta direto para
    500.000). Arredondar cegamente "para cima" a partir do alvo dobrava a
    extensão e transformava 5% de margem em 57%. Aqui a preferência é pelo
    valor da série mais próximo do alvo que ainda contenha os dados; se nem
    esse couber dentro de ``max_effective_margin_percent``, o motor abandona a
    série e usa uma escala de dois algarismos significativos, que continua
    legível ("1:290.000") sem desperdiçar meia folha.

    Devolve ``(escala, justificativa)``.
    """
    if minimum_scale <= 0 or target_scale <= 0:
        raise ValueError("As escalas devem ser positivas.")
    target_scale = max(target_scale, minimum_scale)

    candidates = [value for value in SCALE_LADDER if value >= minimum_scale]
    if candidates:
        chosen = min(candidates, key=lambda value: abs(math.log10(value) - math.log10(target_scale)))
        margin = (chosen / minimum_scale - 1.0) / 2.0 * 100.0
        if margin <= max_effective_margin_percent:
            return int(chosen), "serie_cartografica"

    fallback = _round_up_significant(target_scale, 2)
    if fallback < minimum_scale:
        fallback = _round_up_significant(minimum_scale, 2)
    return int(fallback), "dois_algarismos_significativos"


# ---------------------------------------------------------------------------
# Ajuste de extensão
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FittedExtent:
    """Resultado do ajuste de uma extensão a um quadro de mapa."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float
    scale_denominator: int
    raw_scale_denominator: float
    frame_aspect: float
    effective_margin_percent: float
    notes: list[str]

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    def to_dict(self) -> dict[str, Any]:
        return {
            "xmin": self.xmin,
            "ymin": self.ymin,
            "xmax": self.xmax,
            "ymax": self.ymax,
            "width": self.width,
            "height": self.height,
            "scale_denominator": self.scale_denominator,
            "raw_scale_denominator": round(self.raw_scale_denominator, 1),
            "frame_aspect": round(self.frame_aspect, 4),
            "effective_margin_percent": round(self.effective_margin_percent, 2),
            "notes": list(self.notes),
        }


def fit_extent_to_frame(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    frame_width_mm: float,
    frame_height_mm: float,
    margin_percent: float = 5.0,
    snap_to_round_scale: bool = True,
    map_units_per_metre: float = 1.0,
    max_effective_margin_percent: float = 25.0,
) -> FittedExtent:
    """Ajusta a extensão ao quadro e, opcionalmente, a uma escala redonda.

    O motor antigo aplicava a margem percentual em cada eixo e entregava a
    extensão ao QGIS, que então a expandia no eixo mais curto para casar com a
    razão de aspecto do quadro. O resultado era uma margem assimétrica que
    ninguém pediu. Aqui a expansão para a razão de aspecto vem *primeiro*, a
    margem é aplicada depois sobre a caixa já ajustada, e o centro é
    preservado.
    """
    if xmax <= xmin or ymax <= ymin:
        raise ExtentError("A extensão precisa de xmax > xmin e ymax > ymin.")
    if frame_width_mm <= 0 or frame_height_mm <= 0:
        raise ValueError("As dimensões do quadro devem ser positivas.")

    notes: list[str] = []
    centre_x = (xmin + xmax) / 2.0
    centre_y = (ymin + ymax) / 2.0
    width = xmax - xmin
    height = ymax - ymin
    frame_aspect = frame_width_mm / frame_height_mm

    # 1. Expande para a razão de aspecto do quadro, sempre crescendo, nunca
    #    cortando o eixo que já cabe.
    if width / height < frame_aspect:
        width = height * frame_aspect
        notes.append("Extensão alargada no eixo X para casar com a razão de aspecto do quadro.")
    elif width / height > frame_aspect:
        height = width / frame_aspect
        notes.append("Extensão alargada no eixo Y para casar com a razão de aspecto do quadro.")

    # Escala mínima: a extensão dos dados, já ajustada ao quadro, encostando na
    # borda. Nada abaixo disso pode ser usado sem cortar dados.
    minimum_scale = scale_from_extent(width, frame_width_mm, map_units_per_metre)

    margin = max(0.0, float(margin_percent)) / 100.0
    target_scale = minimum_scale * (1.0 + 2.0 * margin)
    raw_scale = target_scale
    scale = int(round(target_scale))
    basis = "margem_solicitada"

    if snap_to_round_scale:
        scale, basis = choose_publication_scale(minimum_scale, target_scale, max_effective_margin_percent)
        if basis == "dois_algarismos_significativos":
            notes.append(
                f"A série cartográfica não oferece um degrau próximo de 1:{int(round(target_scale)):,} "
                f"sem inflar a margem; usada a escala redonda 1:{scale:,}.".replace(",", ".")
            )

    growth = scale / minimum_scale
    width *= growth
    height *= growth
    effective_margin = (growth - 1.0) / 2.0 * 100.0
    if abs(effective_margin - float(margin_percent)) > 0.5:
        notes.append(
            f"Margem efetiva de {effective_margin:.1f}% (pedida: {float(margin_percent):.1f}%) "
            f"para fechar na escala 1:{scale:,}.".replace(",", ".")
        )

    return FittedExtent(
        xmin=centre_x - width / 2.0,
        ymin=centre_y - height / 2.0,
        xmax=centre_x + width / 2.0,
        ymax=centre_y + height / 2.0,
        scale_denominator=scale,
        raw_scale_denominator=raw_scale,
        frame_aspect=frame_aspect,
        effective_margin_percent=effective_margin,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Barra de escala
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScaleBarSpec:
    """Uma barra de escala dimensionada para o quadro do mapa."""

    unit: str
    unit_label: str
    units_per_segment: float
    segments_right: int
    segments_left: int
    total_ground_metres: float
    bar_width_mm: float
    frame_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "unit_label": self.unit_label,
            "units_per_segment": self.units_per_segment,
            "segments_right": self.segments_right,
            "segments_left": self.segments_left,
            "total_ground_metres": round(self.total_ground_metres, 3),
            "bar_width_mm": round(self.bar_width_mm, 2),
            "frame_fraction": round(self.frame_fraction, 3),
        }


def scalebar_spec(
    scale_denominator: float,
    frame_width_mm: float,
    prefer_unit: str | None = None,
    max_width_mm: float | None = None,
) -> ScaleBarSpec:
    """Escolhe unidade, comprimento do segmento e nº de segmentos.

    O comprimento total procura ~28% da largura do quadro e sempre termina num
    número redondo. O SIGMAI 0.1.1 fixava ``units_per_segment`` em 10 km, o que
    produzia barras de 4% do quadro em mapas municipais e barras maiores que o
    mapa em plantas de detalhe.
    """
    if scale_denominator <= 0:
        raise ValueError("O denominador de escala deve ser positivo.")
    if frame_width_mm <= 0:
        raise ValueError("A largura do quadro deve ser positiva.")

    target_ground_metres = (SCALEBAR_TARGET_FRACTION * frame_width_mm / _MM_PER_METRE) * scale_denominator

    unit_options = _scalebar_unit_options(target_ground_metres, prefer_unit)

    best: tuple[float, ScaleBarSpec] | None = None
    for unit_rank, (unit, factor, label) in enumerate(unit_options):
      target_in_unit = target_ground_metres / factor
      for segments in (4, 2, 5, 3):
        # O QGIS desenha um segmento à esquerda do zero quando há segmentos
        # suficientes à direita; ele faz parte da barra e conta no comprimento.
        # Ignorá-lo subestimava a barra em 25% — a barra estourava a faixa
        # reservada e a fração medida na auditoria não batia com a planejada.
        segments_left = 1 if segments >= 4 else 0
        drawn_segments = segments + segments_left
        try:
            per_segment = nice_number(target_in_unit / drawn_segments, "nearest")
        except ValueError:
            continue
        if per_segment <= 0:
            continue
        total_ground = per_segment * drawn_segments * factor
        bar_mm = (total_ground / scale_denominator) * _MM_PER_METRE
        fraction = bar_mm / frame_width_mm
        if not (SCALEBAR_MIN_FRACTION <= fraction <= SCALEBAR_MAX_FRACTION):
            continue
        # A barra não pode estourar a faixa reservada no layout: o item do QGIS
        # cresce para caber os rótulos e acabaria sobrepondo a legenda.
        if max_width_mm is not None and bar_mm > float(max_width_mm):
            continue
        # Preferência: perto do alvo, depois 4 segmentos, depois 2.
        penalty = abs(fraction - SCALEBAR_TARGET_FRACTION) + {4: 0.0, 2: 0.02, 5: 0.06, 3: 0.06}[segments]
        if per_segment < 1.0:
            # "0,25 km" é pior de ler que "250 m": penaliza segmentos fracionários.
            penalty += 0.30
        elif per_segment != int(per_segment):
            # "0 2,5 5 7,5 10 km" é legível, mas "0 5 10 15 km" é melhor.
            penalty += 0.05
        # "0 2500 5000 m" é pior que "0 2,5 5 km": prefere a unidade natural
        # para a ordem de grandeza da escala.
        penalty += 0.04 * unit_rank
        candidate = ScaleBarSpec(
            unit=unit,
            unit_label=label,
            units_per_segment=per_segment,
            segments_right=segments,
            segments_left=segments_left,
            total_ground_metres=total_ground,
            bar_width_mm=bar_mm,
            frame_fraction=fraction,
        )
        if best is None or penalty < best[0]:
            best = (penalty, candidate)

    unit, factor, label = unit_options[0]
    target_in_unit = target_ground_metres / factor
    if best is not None:
        return best[1]

    # Recurso final: dois segmentos com o valor bonito mais próximo, mesmo fora
    # da faixa ideal. Melhor uma barra imperfeita do que nenhuma — mas o teto
    # de largura continua valendo, senão a barra invade o vizinho no layout.
    ceiling = target_in_unit
    if max_width_mm is not None:
        ceiling = ((float(max_width_mm) / _MM_PER_METRE) * scale_denominator) / factor
    per_segment = nice_number(max(min(target_in_unit, ceiling) / 2.0, 1e-12), "down")
    total_ground = per_segment * 2 * factor
    bar_mm = (total_ground / scale_denominator) * _MM_PER_METRE
    return ScaleBarSpec(
        unit=unit,
        unit_label=label,
        units_per_segment=per_segment,
        segments_right=2,
        segments_left=0,
        total_ground_metres=total_ground,
        bar_width_mm=bar_mm,
        frame_fraction=bar_mm / frame_width_mm,
    )


def _scalebar_unit_options(
    target_ground_metres: float,
    prefer_unit: str | None,
) -> list[tuple[str, float, str]]:
    """Unidades candidatas, da mais provável para a menos provável.

    Devolver uma lista em vez de uma unidade única permite que o seletor de
    segmentos escolha entre "0,5 km" e "500 m" pelo critério de legibilidade,
    em vez de ficar preso ao limiar de 1 km.
    """
    units = {"cm": (0.01, "cm"), "m": (1.0, "m"), "km": (1000.0, "km")}
    if prefer_unit and prefer_unit.lower() in units:
        key = prefer_unit.lower()
        factor, label = units[key]
        return [(key, factor, label)]
    if target_ground_metres >= 2000.0:
        return [("km", 1000.0, "km"), ("m", 1.0, "m")]
    if target_ground_metres >= 1.0:
        return [("m", 1.0, "m"), ("km", 1000.0, "km")]
    return [("cm", 0.01, "cm"), ("m", 1.0, "m")]


# ---------------------------------------------------------------------------
# Grade de coordenadas
# ---------------------------------------------------------------------------

def graticule_interval(
    extent_span: float,
    target_divisions: int = 4,
    geographic: bool = False,
) -> float:
    """Intervalo legível para a grade de coordenadas.

    O ``add_layout_grid`` do SIGMAI 0.1.1 habilitava a grade sem definir
    intervalo. O padrão do QGIS é ``0.0``, então nenhuma linha era desenhada —
    e mesmo assim o orquestrador anunciava a grade como criada.
    """
    if extent_span <= 0:
        raise ExtentError("O span da extensão deve ser positivo.")
    target_divisions = max(2, int(target_divisions))
    raw = extent_span / target_divisions
    if geographic:
        return float(_snap_to_ladder(raw, DEGREE_INTERVALS, "nearest"))
    return float(nice_number(raw, "nearest"))
