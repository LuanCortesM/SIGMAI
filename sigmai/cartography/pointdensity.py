"""Pontos empilhados: quantos registros um mapa de pontos deixa de mostrar.

Um mapa de 362.210 registros do GBIF no Parque Nacional do Itatiaia saiu do
compositor com pontos de 2,2 mm, opacos, e a auditoria só reclamou porque o
parque, coberto, também era assunto do mapa. Com 10.000 registros a nota era
A, embora 98 % deles caíssem sobre outros: os registros do GBIF se repetem
nas mesmas coordenadas (pontos de observação, trilhas), e um local com 1.790
registros aparecia igual a um local com um só. O leitor via cerca de 250
pontos onde a legenda dizia "registros".

A medida aqui é geométrica, e não sobre a imagem: os pontos, já em
milímetros do quadro, são agrupados em células do tamanho do símbolo. Numa
célula com k pontos, só os primeiros ``saturation_depth(opacidade)`` mudam a
imagem — para um símbolo opaco, só o primeiro; com 35 % de opacidade, sete
camadas levam a tinta a 95 %. Os demais são *ocultos*: estão na legenda e na
contagem, mas não no mapa.

Python puro de propósito, como ``scaling`` e ``rulebook``: são decisões
cartográficas, e precisam ser verificáveis em CI sem QGIS.
"""

from __future__ import annotations

import math
from typing import Iterable

#: Tinta acumulada a partir da qual mais um símbolo por cima não muda a imagem.
SATURATION = 0.95

#: Símbolos de ponto que o compositor tenta, do mais visível ao mais discreto:
#: (diâmetro em mm, opacidade, com contorno). O primeiro é o padrão da paleta.
POINT_SYMBOL_STEPS: tuple[tuple[float, float, bool], ...] = (
    (2.2, 0.95, True),
    (1.6, 0.8, True),
    (1.2, 0.65, False),
    (0.9, 0.5, False),
    (0.6, 0.35, False),
    (0.45, 0.25, False),
)
#: Os passos a partir deste só servem a nuvens densas, em que os pontos formam
#: uma textura: a 0,45 mm e 25 % um registro isolado some, inclusive na amostra
#: da legenda. Só se chega a eles quando os anteriores cobrem demais o fundo —
#: nunca para separar pontos aglomerados (100 registros do GBIF iam parar ali).
DENSE_ONLY_FROM_STEP = 4

#: Lado, em mm, da grade grossa que mede a área ocupada pelos pontos.
FOOTPRINT_CELL_MM = 5.0

#: O compositor para no primeiro símbolo que deixa no máximo esta fração dos
#: pontos oculta ...
COMPOSER_HIDDEN_TARGET = 0.25
#: ... e cobre de tinta no máximo esta fração da área ocupada pelos pontos —
#: acima disso o que está embaixo (o limite da unidade de conservação) some.
#: Decisões de projeto do SIGMAI, calibradas no experimento de 26/10/2026
#: (docs/experiments/2026-10-26_pontos_empilhados/).
COMPOSER_COVERAGE_TARGET = 0.25

#: CART076: o mapa de pontos esconde a contagem quando mais desta fração dos
#: pontos do quadro fica oculta...
STACKING_HIDDEN_MAX = 0.5
#: ... e só a partir deste número de pontos no quadro. Abaixo disso o leitor
#: conta os pontos, e um local repetido não muda a leitura do mapa.
STACKING_MIN_POINTS = 50


def saturation_depth(opacity: float) -> int:
    """Quantos símbolos empilhados ainda mudam a imagem antes de a tinta chegar a ``SATURATION``."""
    opacity = float(opacity)
    if opacity >= SATURATION:
        return 1
    if opacity <= 0.0:
        return 1
    return max(1, math.ceil(math.log(1.0 - SATURATION) / math.log(1.0 - opacity)))


def stacking(points_mm: Iterable[tuple[float, float]], diameter_mm: float, opacity: float) -> dict[str, float | int]:
    """Quantos dos pontos (em mm do quadro) o símbolo deixa de mostrar.

    Devolve ``points`` (pontos medidos), ``cells`` (células do tamanho do
    símbolo com algum ponto), ``max_per_cell``, ``saturation_depth``,
    ``hidden_fraction`` (pontos além da saturação, sobre o total) e
    ``ink_coverage``: a tinta dos símbolos (o disco de cada célula, com a
    opacidade acumulada dos pontos dela) sobre a área ocupada pelos pontos,
    medida em células de ``FOOTPRINT_CELL_MM``. É uma estimativa: discos de
    células vizinhas que se tocam contam duas vezes, e o resultado é limitado a 1.
    """
    size = float(diameter_mm)
    if not size > 0:
        raise ValueError(f"diâmetro do símbolo inválido: {diameter_mm!r}")
    alpha = min(max(float(opacity), 0.0), 1.0)
    cells: dict[tuple[int, int], int] = {}
    footprint: set[tuple[int, int]] = set()
    for x, y in points_mm:
        key = (int(math.floor(x / size)), int(math.floor(y / size)))
        cells[key] = cells.get(key, 0) + 1
        footprint.add((int(math.floor(x / FOOTPRINT_CELL_MM)), int(math.floor(y / FOOTPRINT_CELL_MM))))
    total = sum(cells.values())
    depth = saturation_depth(opacity)
    hidden = sum(max(0, count - depth) for count in cells.values())
    disc = math.pi * size * size / 4.0
    ink = sum(disc * (1.0 - (1.0 - alpha) ** count) for count in cells.values())
    area = len(footprint) * FOOTPRINT_CELL_MM * FOOTPRINT_CELL_MM
    return {
        "points": total,
        "cells": len(cells),
        "max_per_cell": max(cells.values()) if cells else 0,
        "saturation_depth": depth,
        "hidden_fraction": round(hidden / total, 4) if total else 0.0,
        "ink_coverage": round(min(1.0, ink / area), 4) if area else 0.0,
    }


def choose_point_symbol(
    points_mm: list[tuple[float, float]],
    steps: tuple[tuple[float, float, bool], ...] = POINT_SYMBOL_STEPS,
    hidden_target: float = COMPOSER_HIDDEN_TARGET,
    coverage_target: float = COMPOSER_COVERAGE_TARGET,
    min_points: int = STACKING_MIN_POINTS,
) -> dict[str, object]:
    """O símbolo de ponto que o compositor usa para estes pontos.

    1. Com menos de ``min_points`` pontos, o padrão (primeiro passo).
    2. O primeiro passo comum (antes de ``DENSE_ONLY_FROM_STEP``) que deixa no
       máximo ``hidden_target`` dos pontos oculto e cobre no máximo
       ``coverage_target`` da área que eles ocupam (``reached`` verdadeiro).
    3. Se nenhum passo comum atende aos dois, mas algum atende à cobertura, o
       que menos esconde entre esses (no empate, o maior). Registros repetidos
       nas mesmas coordenadas ficam ocultos em qualquer tamanho; encolher o
       símbolo atrás deles só apagaria o mapa. ``reached`` vem falso, e o
       remédio para a contagem é outro (mapa de calor ou símbolo proporcional
       por local), que é o que CART076 vai dizer.
    4. Se nem a cobertura se atinge nos passos comuns — nuvem densa —, o
       primeiro passo de textura que a atinge, ou o último.
    """
    points = list(points_mm)
    measured: list[dict[str, object]] = []

    def measure(index: int) -> dict[str, object]:
        size, opacity, outline = steps[index]
        entry = {"size_mm": size, "opacity": opacity, "outline": outline, **stacking(points, size, opacity), "step": index}
        measured.append(entry)
        return entry

    def fits(entry: dict[str, object], hidden: bool = True) -> bool:
        return (float(entry["ink_coverage"]) <= coverage_target
                and (not hidden or float(entry["hidden_fraction"]) <= hidden_target))

    if len(points) < min_points:
        return {**measure(0), "reached": True, "tried": measured}
    common = min(DENSE_ONLY_FROM_STEP, len(steps))
    for index in range(common):
        entry = measure(index)
        if fits(entry):
            return {**entry, "reached": True, "tried": measured}
    covered = [entry for entry in measured if fits(entry, hidden=False)]
    if covered:
        best = min(covered, key=lambda entry: (float(entry["hidden_fraction"]), int(entry["step"])))
        return {**best, "reached": False, "tried": measured}
    for index in range(common, len(steps)):
        entry = measure(index)
        if fits(entry, hidden=False):
            return {**entry, "reached": fits(entry), "tried": measured}
    return {**measured[-1], "reached": False, "tried": measured}


#: Distância mínima, no papel, entre dois locais de um mapa de símbolos
#: proporcionais: o menor círculo de apply_proportional_symbol_style (1 mm).
#: Locais mais próximos que isso se sobrepõem, e o leitor não os separa.
SITE_SPACING_MM = 1.0


def merge_sites(
    sites: Iterable[tuple[float, float, int]],
    radius: float,
    x_metres: float = 1.0,
    y_metres: float = 1.0,
) -> list[tuple[float, float, int]]:
    """Junta os locais a menos de ``radius`` metros uns dos outros, somando as contagens.

    Os 362.210 registros do GBIF no PARNA do Itatiaia estão em 11.224
    coordenadas distintas; a 1:300.000, 1 mm no papel são 300 m, e 79 % dos
    círculos proporcionais caíam sobre outros. No sul do parque, milhares de
    círculos mínimos com contorno branco formavam uma mancha clara: o lugar
    com mais registros parecia o mais vazio.

    Do local com mais registros para o com menos, cada um vira a sede de um
    grupo ou entra no grupo da primeira sede a menos de ``radius``. A sede
    guarda a sua coordenada, que é real (um ponto de observação, uma trilha),
    e não um centro inventado; e as sedes ficam a pelo menos ``radius`` umas
    das outras. ``x_metres`` e ``y_metres`` convertem as unidades da camada
    em metros (1 num sistema métrico; em graus, o comprimento de um grau na
    latitude dos dados).
    """
    if not radius > 0:
        raise ValueError(f"distância inválida: {radius!r}")
    ordered = sorted(sites, key=lambda site: (-int(site[2]), float(site[0]), float(site[1])))
    grid: dict[tuple[int, int], list[int]] = {}
    seeds: list[list[float]] = []
    limit = float(radius) * float(radius)
    for x, y, count in ordered:
        mx, my = float(x) * x_metres, float(y) * y_metres
        cx, cy = int(math.floor(mx / radius)), int(math.floor(my / radius))
        owner = None
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for index in grid.get((i, j), ()):
                    seed = seeds[index]
                    if (seed[3] - mx) ** 2 + (seed[4] - my) ** 2 < limit and (owner is None or index < owner):
                        owner = index
        if owner is None:
            grid.setdefault((cx, cy), []).append(len(seeds))
            seeds.append([float(x), float(y), int(count), mx, my])
        else:
            seeds[owner][2] += int(count)
    return [(seed[0], seed[1], int(seed[2])) for seed in seeds]
