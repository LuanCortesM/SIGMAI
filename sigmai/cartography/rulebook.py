"""Regulamento cartográfico legível por máquina.

O avaliador do SIGMAI 0.1.1 só conferia a *presença* de itens no layout. Um
mapa com a rosa dos ventos escrita como a letra "N", barra de escala de 4% do
quadro, legenda explicando uma de três camadas e grade invisível recebia
"A — Professional map" e zero avisos. Como esse é o único retorno que o agente
de IA recebe, ele não tinha como saber que precisava corrigir nada: o laço de
realimentação mentia.

Este módulo troca isso por um conjunto explícito de regras. Cada regra carrega
o motivo pelo qual existe, a referência que a sustenta e o comando SIGMAI que a
resolve — é esse texto que o agente lê e usa para decidir o próximo passo.

O módulo é Python puro de propósito. Ele recebe uma *observação* (um dicionário
simples descrevendo o layout, produzido por ``inspector.py``, que fala PyQGIS) e
devolve um laudo. Assim as regras podem ser testadas em CI sem QGIS instalado,
e alguém pode contestar uma regra lendo um arquivo em vez de um traceback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .pointdensity import SATURATION, STACKING_HIDDEN_MAX, STACKING_MIN_POINTS

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_ADVICE = "advice"

#: Peso de cada severidade na pontuação de 0 a 100.
SEVERITY_PENALTY = {SEVERITY_ERROR: 15.0, SEVERITY_WARNING: 5.0, SEVERITY_ADVICE: 1.5}

STATUS_PASSED = "pass"
STATUS_FAIL = "fail"
STATUS_SKIP = "skip"

#: Tamanho mínimo de fonte impressa. Abaixo disso o texto some numa impressão
#: A4 e falha em qualquer revisão editorial séria.
MIN_PRINT_FONT_PT = 6.0

#: Fração do quadro do mapa que a barra de escala deve ocupar.
SCALEBAR_MIN_FRACTION = 0.15
#: Comprimento absoluto a partir do qual uma barra é mensurável no papel,
#: mesmo quando é proporcionalmente curta num formato grande (A2, A1, A0).
SCALEBAR_MIN_LENGTH_MM = 45.0
SCALEBAR_MAX_FRACTION = 0.45

#: Fração mínima da área útil que o quadro do mapa deve ocupar para que a peça
#: continue sendo um mapa, e não uma moldura com um mapa dentro.
MAP_DOMINANCE_MIN = 0.35

#: Tinta máxima na faixa em volta de um item desenhado sobre o quadro para
#: que a sobreposição conte como "num canto vazio" (CART042).
OVERLAY_MAX_SURROUNDINGS_INK = 0.03

#: CART069 divide o quadro em 3x3 e olha as FAIXAS (cada coluna e cada
#: linha inteiras): uma faixa cuja cobertura média por dados de área fica
#: abaixo disto é um terço da folha em branco de ponta a ponta — mar sem
#: camada de oceano, estado vizinho sem malha, extensão aberta demais.
#: Cantos vazios de um estado diagonal não formam faixa e não reprovam;
#: calibrado com a malha do Piauí em retrato (passa) e em paisagem
#: (reprova: 81% da folha vazia) e com o Parque das Carnaúbas (reprova).
FRAME_BAND_EMPTY_MAX = 0.05
#: Sem camada de polígonos a mesma faixa é julgada pela tinta do raster.
FRAME_BAND_EMPTY_INK = 0.02
#: Na tinta só dos dados (cada camada desenhada sem grade nem rótulos),
#: qualquer presença real conta: uma trilha atravessando a faixa norte é o
#: assunto do mapa, e a 2 % — limiar da imagem exportada, que soma grade e
#: rótulos — ela contava como papel em branco.
FRAME_BAND_EMPTY_DATA_INK = 0.0005
#: Folga, em mm, entre o que a legenda precisa e a caixa que tem (CART072).
LEGEND_OVERFLOW_TOLERANCE_MM = 0.5
#: CART073: croma mínimo (maior canal menos o menor, 0–255) para um pixel
#: contar como colorido, e fração máxima da tinta que pode tê-lo numa figura
#: pedida em tons de cinza. 20 deixa passar o ruído de compressão JPEG e pega
#: o azul quase branco (#D9EAF4, croma 27) que a paleta colorida dava ao
#: contexto; 0,5 % tolera um logotipo ou um pixel perdido, não um inserto
#: contornado de vermelho.
#: CART021: uma camada ligada ao quadro conta como escondida quando, do que
#: ela desenha sozinha, menos de 10 % continua visível no mapa — coberta pelas
#: de cima, com no máximo uma lasca de contorno escapando na borda (a lasca de
#: um traço de 1 mm em volta de dois polígonos cobertos deu 7 % no teste).
COVERED_VISIBLE_MAX = 0.10
#: ... a não ser que o pouco que fica à vista ocupe ao menos 1 % do quadro: um
#: oceano coberto pelo continente em 92 % continua sendo o mar do mapa.
COVERED_VISIBLE_SHARE = 0.01
#: CART075: o assunto do mapa precisa ter à vista pelo menos metade do que
#: desenha. Um preenchimento de contexto com 85 % de opacidade por cima de
#: um modelo de elevação deixa 15 % — o relevo some e o mapa perde o assunto.
#: Camadas em modo de mistura diferente do normal (sombreamento em
#: "multiplicar") não contam como cobertura.
SUBJECT_VISIBLE_MIN = 0.5
GREYSCALE_CHROMA_MIN = 20
#: CART077: fração mínima da rampa de um raster contínuo que os pixels do
#: quadro (percentis 2 a 98) devem usar. Um MDE de 372 a 2.793 m com um bloco
#: de -32.768 não declarado usava 7 %; com um pico de 9.000 m, 27 %.
RAMP_USED_MIN = 0.4
#: Valores que gravadores de raster usam como "sem dado" sem declará-lo: o
#: Int16 dos MDE (SRTM, Copernicus), o -9999 do ArcGIS e dos ASCII grid, o
#: menor Float32. Num MDE de 372 a 2.793 m com um bloco de -32.768 não
#: declarado, a rampa ia de -32.768 a 2.764 m e o relevo inteiro saía de uma
#: cor só, com nota A. apply_raster_style os trata como sem dado, e CART077
#: os deixa fora dos percentis.
NODATA_SENTINELS: tuple[float, ...] = (-32768.0, -32767.0, -9999.0, -99999.0, -3.4028234663852886e38)
#: CART078: folga, em graus, em volta da área de uso declarada de um sistema
#: de referência antes de uma coordenada contar como fora dela: meio fuso UTM,
#: para não acusar dados que só passam da divisa do fuso.
AREA_OF_USE_MARGIN_DEGREES = 3.0
#: CART079: o recorte é aberto por pontos isolados quando a diagonal de todos
#: os pontos passa deste múltiplo da diagonal do núcleo (percentis 1 a 99) e
#: os isolados são poucos: no máximo ``OUTLIER_MAX_SHARE`` dos pontos ou
#: ``OUTLIER_MAX_COUNT``, o que for maior. Erro de coordenada é coisa de
#: poucos registros; com 2 % a regra acusava 300 registros legítimos
#: espalhados em volta de um foco de 20.000.
OUTLIER_SPREAD_RATIO = 5.0
OUTLIER_MAX_SHARE = 0.005
OUTLIER_MAX_COUNT = 3
#: CART080: densidade, em fração do máximo da rampa, abaixo da qual o mapa de
#: calor não pinta (a rampa de apply_heatmap_style começa transparente e só
#: ganha cor a partir de 15 %), e fração máxima dos lugares com pontos que
#: podem ficar assim. Calibrado em três mapas: focos de calor do INPE no Piauí
#: (55 % dos lugares abaixo de 2 %, mapa legítimo, com a cauda de baixa
#: densidade em amarelo-claro), registros do GBIF no Itatiaia (93 %) e um foco
#: de 20.000 registros com 300 espalhados (99,6 %). Com 10 % e metade, o mapa
#: de focos — legítimo — era acusado.
HEATMAP_VISIBLE_MIN = 0.02
HEATMAP_FAINT_PLACES_MAX = 0.8
GREYSCALE_MAX_CHROMATIC_FRACTION = 0.005


@dataclass(frozen=True)
class Rule:
    """Uma regra cartográfica verificável."""

    id: str
    category: str
    severity: str
    title_pt: str
    title_en: str
    rationale_pt: str
    fix_pt: str
    reference: str
    check: Callable[[dict[str, Any]], "CheckOutcome"] = field(repr=False, default=None)  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "title_pt": self.title_pt,
            "title_en": self.title_en,
            "rationale_pt": self.rationale_pt,
            "fix_pt": self.fix_pt,
            "reference": self.reference,
        }


@dataclass(frozen=True)
class CheckOutcome:
    """O que uma regra observou."""

    status: str
    detail_pt: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


def _pass(detail: str = "", **evidence: Any) -> CheckOutcome:
    return CheckOutcome(STATUS_PASSED, detail, evidence)


def _fail(detail: str, **evidence: Any) -> CheckOutcome:
    return CheckOutcome(STATUS_FAIL, detail, evidence)


def _skip(detail: str, **evidence: Any) -> CheckOutcome:
    return CheckOutcome(STATUS_SKIP, detail, evidence)


def _num(value: float) -> str:
    """Inteiro com ponto de milhar, em português — só o número, nunca a frase."""
    return f"{float(value):,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# Auxiliares de leitura da observação
# ---------------------------------------------------------------------------

def _items(observation: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in observation.get("items", []) if isinstance(item, dict)]


def _item_by_role(observation: dict[str, Any], role: str) -> dict[str, Any] | None:
    for item in _items(observation):
        if item.get("role") == role:
            return item
    return None


def _map(observation: dict[str, Any]) -> dict[str, Any]:
    return observation.get("map") or {}


def _texts(observation: dict[str, Any]) -> list[dict[str, Any]]:
    """Os rótulos do layout e, numa figura com os créditos na legenda do texto, essa legenda."""
    texts = [item for item in _items(observation) if item.get("type") == "label"]
    caption = _caption(observation)
    if caption.get("text"):
        texts.append({"type": "label", "role": "caption", "id": "caption", "text": str(caption["text"])})
    return texts


def _caption(observation: dict[str, Any]) -> dict[str, Any]:
    """Onde ficaram título e créditos (title_placement) e a legenda do texto, quando o compositor a escreveu."""
    caption = observation.get("caption")
    return caption if isinstance(caption, dict) else {}


def _has_text(observation: dict[str, Any], *needles: str) -> bool:
    lowered = [str(item.get("text", "")).lower() for item in _texts(observation)]
    return any(needle.lower() in blob for blob in lowered for needle in needles)


# ---------------------------------------------------------------------------
# Regras — elementos obrigatórios
# ---------------------------------------------------------------------------

def _check_title(observation: dict[str, Any]) -> CheckOutcome:
    title = _item_by_role(observation, "title")
    if title and str(title.get("text", "")).strip():
        return _pass(f"Título presente: {title['text']!r}.")
    caption = _caption(observation)
    placement = caption.get("title_placement")
    if placement == "caption":
        if str(caption.get("title") or "").strip():
            return _pass(f"Título na legenda do texto, como pedem as revistas: {caption['title']!r}.")
        return _skip("Figura com título e créditos na legenda do texto (title_placement='caption'); o título é o "
                     "que o autor escrever nela.")
    if placement == "none":
        return _skip("Mapa sem título por escolha de quem o fez (title_placement='none'); o título fica no "
                     "documento em que ele entra.")
    return _fail("Nenhum item com papel de título e texto não vazio.")


def _check_legend(observation: dict[str, Any]) -> CheckOutcome:
    legend = observation.get("legend")
    visible = _map(observation).get("visible_layer_names") or []
    if legend and legend.get("item_id"):
        return _pass(f"Legenda presente com {len(legend.get('layer_names') or [])} entrada(s).")
    if len(visible) <= 1:
        return _skip("Mapa com uma única camada; a legenda pode ser dispensada se o título já a identifica.")
    return _fail(f"Mapa exibe {len(visible)} camadas e não há legenda.", visible_layers=visible)


def _all_visible_layer_names(observation: dict[str, Any], include_label_only: bool = True) -> list[str]:
    """Camadas desenhadas em qualquer quadro da folha.

    Numa folha de comparação a legenda responde pelos dois quadros: avaliá-la
    só contra o quadro principal acusava de fantasma uma camada bem visível no
    segundo painel, e deixava passar uma camada do segundo painel sem entrada.

    Com ``include_label_only=False`` ficam de fora as camadas sem símbolo
    (``QgsNullSymbolRenderer``, usadas só para posicionar rótulos): não há o
    que explicar na legenda sobre elas, e exigir uma entrada acusava de
    incompleta uma legenda correta. Elas continuam "visíveis" para a regra dos
    fantasmas — listá-las é supérfluo, não é mentira.
    """
    nomes = [str(name) for name in (_map(observation).get("visible_layer_names") or [])]
    for frame in observation.get("map_frames") or []:
        for name in frame.get("visible_layer_names") or []:
            if str(name) not in nomes:
                nomes.append(str(name))
    if include_label_only:
        return nomes
    so_rotulo = {str(name) for name in (_map(observation).get("label_only_layer_names") or [])}
    for frame in observation.get("map_frames") or []:
        so_rotulo.update(str(name) for name in (frame.get("label_only_layer_names") or []))
    return [name for name in nomes if name not in so_rotulo]


def _check_legend_covers_visible_layers(observation: dict[str, Any]) -> CheckOutcome:
    legend = observation.get("legend")
    if not legend or not legend.get("item_id"):
        return _skip("Sem legenda para avaliar.")
    visible = _all_visible_layer_names(observation, include_label_only=False)
    listed = [str(name) for name in (legend.get("layer_names") or [])]
    if not visible:
        return _skip("Não foi possível determinar as camadas visíveis do mapa.")
    missing = [name for name in visible if name not in listed]
    if not missing:
        return _pass(f"As {len(visible)} camadas visíveis aparecem na legenda.")
    return _fail(
        "A legenda não explica " + ", ".join(repr(name) for name in missing) + ". "
        "O leitor vê feições que a legenda não identifica.",
        missing_layers=missing,
        visible_layers=visible,
        legend_layers=listed,
    )


def _check_legend_has_no_phantoms(observation: dict[str, Any]) -> CheckOutcome:
    legend = observation.get("legend")
    if not legend or not legend.get("item_id"):
        return _skip("Sem legenda para avaliar.")
    visible = _all_visible_layer_names(observation)
    listed = [str(name) for name in (legend.get("layer_names") or [])]
    if not visible:
        return _skip("Não foi possível determinar as camadas visíveis do mapa.")
    extra = [name for name in listed if name not in visible]
    # Ligada ao quadro mas sem nenhum pixel no mapa: coberta pelas de cima.
    # Só num quadro único — numa folha de painéis ela pode aparecer no outro.
    covered: list[str] = []
    empty: list[str] = []
    if len(observation.get("map_frames") or []) <= 1:
        hidden = {str(name) for name in (_map(observation).get("hidden_layer_names") or [])}
        nothing = {str(name) for name in (_map(observation).get("empty_layer_names") or [])}
        covered = [name for name in listed if name in hidden and name not in extra]
        empty = [name for name in listed if name in nothing and name not in extra]
    if not extra and not covered and not empty:
        return _pass("A legenda não lista camadas ausentes do mapa.")
    partes = []
    if extra:
        partes.append("A legenda lista " + ", ".join(repr(name) for name in extra) + ", que não aparece(m) no mapa.")
    if empty:
        partes.append(
            "A legenda lista " + ", ".join(repr(name) for name in empty) + ", ligada(s) ao quadro mas sem nenhuma "
            "feição na extensão do mapa. Tire-a(s) da legenda ou amplie a extensão."
        )
    if covered:
        partes.append(
            "A legenda lista " + ", ".join(repr(name) for name in covered) + ", ligada(s) ao quadro mas "
            "coberta(s) pelas camadas desenhadas por cima: o QGIS desenha a primeira camada da lista por cima. "
            "Reordene as camadas ou desenhe a que cobre como contorno, sem preenchimento."
        )
    return _fail(" ".join(partes), phantom_layers=extra, covered_layers=covered, empty_layers=empty)


def _check_subject_visible(observation: dict[str, Any]) -> CheckOutcome:
    """CART075 — o assunto do mapa não está escondido sob outras camadas."""
    map_info = _map(observation)
    if not map_info.get("subject_layer_ids"):
        return _skip("Assunto do mapa não informado (subject_layer_id).")
    visible = map_info.get("subject_visible_fraction")
    if visible is None:
        return _skip("Não foi possível medir a visibilidade do assunto.")
    if float(visible) >= SUBJECT_VISIBLE_MIN:
        return _pass(f"O assunto do mapa está à vista ({float(visible):.0%} do que ele desenha).")
    crowded = [entry for entry in (map_info.get("point_stacking") or [])
               if float(entry.get("hidden_fraction") or 0.0) > STACKING_HIDDEN_MAX]
    remedy = ("Desenhe o contexto por cima como contorno, sem preenchimento, ou com transparência alta, ou "
              "ponha o assunto acima do contexto.")
    if crowded:
        names = ", ".join(repr(entry["layer"]) for entry in crowded)
        remedy = (f"Quem cobre são os pontos amontoados de {names}: use pontos menores e semitransparentes "
                  "(compose_map já faz isso com a paleta), ou mostre a contagem com apply_heatmap_style ou "
                  "com um símbolo por local (apply_proportional_symbol_style).")
    return _fail(
        f"Só {float(visible):.0%} do que o assunto do mapa desenha fica à vista: camadas desenhadas por cima "
        f"o cobrem. {remedy}",
        subject_visible_fraction=visible,
    )


def _check_raster_ramp_used(observation: dict[str, Any]) -> CheckOutcome:
    """CART077 — a rampa de cores de um raster contínuo mostra os dados."""
    ramps = _map(observation).get("raster_ramps")
    if ramps is None:
        return _skip("Não foi possível medir a rampa dos rasters do quadro.")
    if not ramps:
        return _skip("Nenhum raster com rampa contínua no quadro.")
    worst = min(ramps, key=lambda entry: float(entry.get("used_fraction") or 0.0))
    used = float(worst.get("used_fraction") or 0.0)

    def num(value: Any) -> str:
        return f"{float(value):,.6g}".replace(",", ".")

    described = (f"os pixels de {worst['layer']!r} (percentis 2 a 98: {num(worst['p02'])} a {num(worst['p98'])}) "
                 f"usam {used:.0%} da rampa, que vai de {num(worst['ramp_min'])} a {num(worst['ramp_max'])}")
    if used >= RAMP_USED_MIN:
        return _pass(f"A rampa mostra os dados: {described}.", raster_ramps=ramps)
    return _fail(f"{described[0].upper()}{described[1:]}: o relevo, ou o tema, sai quase de uma cor só. Um extremo "
                 "estica a rampa — um valor sem dado não declarado (-32.768, -9.999) ou um pico isolado.",
                 raster_ramps=ramps)


def _check_coordinates_plausible(observation: dict[str, Any]) -> CheckOutcome:
    """CART078 — as coordenadas cabem no sistema de referência declarado."""
    checks = _map(observation).get("coordinate_checks")
    if checks is None:
        return _skip("Não foi possível conferir as coordenadas das camadas.")
    if not checks:
        return _skip("Nenhuma camada vetorial no quadro.")
    problems: list[str] = []
    for entry in checks:
        name = repr(entry.get("layer"))
        if entry.get("degree_like"):
            problems.append(f"{name} está em {entry.get('crs')}, um sistema em metros, mas todas as coordenadas cabem "
                            "entre -180 e 180 e -90 e 90: parecem graus (latitude e longitude declaradas como UTM)")
        null_island = int(entry.get("null_island") or 0)
        if null_island:
            problems.append(f"{_num(null_island)} ponto(s) de {name} em 0,0 — a coordenada que planilhas e bancos gravam "
                            "quando falta a posição")
        outside = int(entry.get("outside_area_of_use") or 0)
        if outside and not entry.get("degree_like"):
            examples = "; ".join(f"{x}, {y}" for x, y in (entry.get("outside_examples") or []))
            area = entry.get("area_of_use")
            problems.append(f"{_num(outside)} feição(ões) de {name} fora da área de uso de {entry.get('crs')}"
                            + (f" (longitude {area[0]} a {area[2]}, latitude {area[1]} a {area[3]})" if area else "")
                            + (f", por exemplo {examples} (longitude, latitude)" if examples else ""))
    if not problems:
        return _pass("As coordenadas cabem nos sistemas de referência das camadas.")
    return _fail("Coordenadas que não podem estar certas: " + "; ".join(problems) + ".", coordinate_checks=checks)


def _check_extent_outliers(observation: dict[str, Any]) -> CheckOutcome:
    """CART079 — o recorte não é aberto por poucos pontos isolados."""
    layers = _map(observation).get("extent_outliers")
    if layers is None:
        return _skip("Não foi possível medir a dispersão dos pontos.")
    if not layers:
        return _skip("Nenhuma camada de pontos com 20 pontos ou mais no quadro.")
    flagged = [entry for entry in layers
               if entry.get("spread_ratio") is not None and float(entry["spread_ratio"]) > OUTLIER_SPREAD_RATIO
               and 0 < int(entry.get("isolated") or 0)
               <= max(OUTLIER_MAX_COUNT, OUTLIER_MAX_SHARE * int(entry.get("points") or 0))]
    if not flagged:
        return _pass("Nenhum ponto isolado abre o recorte.")
    worst = max(flagged, key=lambda entry: float(entry["spread_ratio"]))
    return _fail(
        f"{_num(worst['isolated'])} de {_num(worst['points'])} pontos de {worst['layer']!r} ficam longe dos demais e "
        f"abrem o recorte {float(worst['spread_ratio']):.0f} vezes além do núcleo dos dados: os outros pontos se "
        "amontoam num canto do quadro. Costuma ser erro de coordenada (0,0, latitude e longitude trocadas, sinal "
        "trocado).", extent_outliers=layers)


def _check_heatmap_visibility(observation: dict[str, Any]) -> CheckOutcome:
    """CART080 — o mapa de calor mostra os lugares que têm pontos."""
    layers = _map(observation).get("heatmap_visibility")
    if layers is None:
        return _skip("Não foi possível medir o mapa de calor.")
    if not layers:
        return _skip("Nenhum mapa de calor no quadro.")
    worst = max(layers, key=lambda entry: int(entry.get("faint_places") or 0) / max(1, int(entry.get("places") or 1)))
    share = int(worst.get("faint_places") or 0) / max(1, int(worst.get("places") or 1))
    described = (f"{_num(worst['faint_places'])} dos {_num(worst['places'])} lugares com pontos de {worst['layer']!r} "
                 f"({_num(worst['faint_points'])} pontos) ficam abaixo de {HEATMAP_VISIBLE_MIN * 100:g} % da densidade "
                 "máxima")
    if share <= HEATMAP_FAINT_PLACES_MAX:
        return _pass(f"O mapa de calor mostra os lugares com pontos: {described}.", heatmap_visibility=layers)
    return _fail(f"{described[0].upper()}{described[1:]} e quase não aparecem: o mapa mostra só os focos.",
                 heatmap_visibility=layers)


def _check_point_stacking(observation: dict[str, Any]) -> CheckOutcome:
    """CART076 — os pontos do mapa não escondem quantos registros há em cada lugar."""
    layers = _map(observation).get("point_stacking")
    if layers is None:
        return _skip("Não foi possível medir os pontos do quadro.")
    if not layers:
        return _skip("Nenhuma camada de pontos com símbolo de tamanho fixo ou proporcional no quadro.")
    measured = [entry for entry in layers if int(entry.get("points") or 0) >= STACKING_MIN_POINTS]
    if not measured:
        return _pass(f"Menos de {STACKING_MIN_POINTS} pontos por camada no quadro: o leitor os conta.")
    worst = max(measured, key=lambda entry: float(entry.get("hidden_fraction") or 0.0))
    hidden = float(worst.get("hidden_fraction") or 0.0)
    if worst.get("proportional"):
        described = (f"{hidden:.0%} dos {_num(worst['points'])} locais de {worst['layer']!r} caem sobre outros no "
                     f"papel (até {_num(worst['max_per_cell'])} num lugar do tamanho do menor círculo, "
                     f"{float(worst['symbol_mm']):g} mm)")
        if hidden <= STACKING_HIDDEN_MAX:
            return _pass(f"Os círculos não escondem os locais: {described}.", point_stacking=layers)
        scale = worst.get("scale")
        source = worst.get("source_layer_id")
        remedy = ("count_points_by_site" + (f" sobre {source!r}" if source else "")
                  + (f" com scale={int(scale)}" if scale else " com scale (o denominador da escala do mapa)")
                  + f" e min_spacing_mm={float(worst['symbol_mm']):g}")
        return _fail(f"{described}. Amontoados, os círculos se fundem: o leitor não separa os locais nem compara "
                     f"os tamanhos, e onde há mais locais o mapa parece ter menos. Agrupe os locais na escala do "
                     f"mapa: {remedy}.", point_stacking=layers)
    described = (f"{hidden:.0%} dos {_num(worst['points'])} pontos de {worst['layer']!r} não aparecem: caem sobre "
                 f"outros (até {_num(worst['max_per_cell'])} num mesmo lugar do tamanho do símbolo, "
                 f"{float(worst['symbol_mm']):g} mm com opacidade {float(worst['opacity']):g})")
    if hidden <= STACKING_HIDDEN_MAX:
        return _pass(f"Os pontos não escondem a contagem: {described}.", point_stacking=layers)
    return _fail(f"{described}. O mapa mostra onde há pontos, mas não quantos.", point_stacking=layers)


def _check_scale_indication(observation: dict[str, Any]) -> CheckOutcome:
    # ``observation["scalebar"]`` existe e vale None quando não há barra:
    # ``.get("scalebar", {})`` devolvia None e a regra quebrava — o motor a
    # marcava "não avaliada" e um mapa sem escala nenhuma passava em silêncio.
    # Achado pela injeção de defeitos do experimento E1 (paper/tgis).
    has_bar = bool((observation.get("scalebar") or {}).get("item_id"))
    has_text = _has_text(observation, "1:", "escala", "scale")
    if has_bar or has_text:
        return _pass(f"Escala indicada (barra={has_bar}, texto={has_text}).")
    return _fail("O mapa não informa a escala nem por barra nem por texto. Sem escala não há mapa, só uma figura.")


def _check_scale_text(observation: dict[str, Any]) -> CheckOutcome:
    if _has_text(observation, "1:"):
        return _pass("Escala numérica presente.")
    return _fail(
        "Falta a escala numérica (ex.: 'Escala 1:250.000'). A barra sobrevive ao "
        "redimensionamento, mas a escala numérica é o que se cita em texto."
    )


def _check_scalebar_proportion(observation: dict[str, Any]) -> CheckOutcome:
    bar = observation.get("scalebar") or {}
    if not bar.get("item_id"):
        return _skip("Sem barra de escala.")
    fraction = bar.get("frame_fraction")
    if fraction is None:
        return _skip("Não foi possível medir a barra em relação ao quadro.")
    if SCALEBAR_MIN_FRACTION <= float(fraction) <= SCALEBAR_MAX_FRACTION:
        return _pass(f"A barra ocupa {float(fraction):.0%} da largura do quadro.")
    length_mm = bar.get("bar_width_mm")
    if float(fraction) < SCALEBAR_MIN_FRACTION:
        # A proporção não é o critério completo. Numa A0 ou A2 o quadro tem
        # 40 cm de largura, e uma barra de 15% teria 60 mm — mas uma de 45 mm
        # já se mede com a régua e com o olho. O que impede estimar distância é
        # a barra curta em termos absolutos, não a barra curta em relação a uma
        # folha grande. Só reprova quando as duas coisas falham.
        if length_mm is not None and float(length_mm) >= SCALEBAR_MIN_LENGTH_MM:
            return _pass(
                f"A barra tem {float(length_mm):.0f} mm ({float(fraction):.0%} do quadro): "
                "proporcionalmente curta por causa do formato grande, mas legível no papel."
            )
        medida = f" ({float(length_mm):.0f} mm no papel)" if length_mm is not None else ""
        return _fail(
            f"A barra ocupa apenas {float(fraction):.0%} da largura do quadro{medida}. "
            "Uma barra curta demais não permite estimar distâncias.",
            frame_fraction=fraction,
            bar_width_mm=length_mm,
        )
    return _fail(
        f"A barra ocupa {float(fraction):.0%} da largura do quadro e compete com o mapa.",
        frame_fraction=fraction,
    )


def _check_scalebar_labels(observation: dict[str, Any]) -> CheckOutcome:
    """CART074 — os números da barra de escala não encostam uns nos outros."""
    from .scaling import scalebar_label_space

    bar = observation.get("scalebar") or {}
    if not bar.get("item_id"):
        return _skip("Sem barra de escala.")
    font_pt, bar_mm = bar.get("label_font_pt"), bar.get("bar_width_mm")
    per_segment = float(bar.get("units_per_segment") or 0.0)
    right, left = int(bar.get("segments") or 0), int(bar.get("segments_left") or 0)
    if not font_pt or not bar_mm or per_segment <= 0 or right <= 0:
        return _skip("Não foi possível medir os rótulos da barra.")
    segment_mm, needed_mm, pair = scalebar_label_space(per_segment, right, left, float(bar_mm), float(font_pt))
    if segment_mm >= needed_mm:
        return _pass(f"Os {right + left + 1} rótulos da barra cabem nos segmentos.")
    return _fail(
        f"Os números da barra se sobrepõem: cada segmento tem {segment_mm:.1f} mm e os rótulos vizinhos "
        f"{pair[0]!r} e {pair[1]!r} em {float(font_pt):g} pt precisam de cerca de {needed_mm:.1f} mm. "
        "Use menos segmentos (2 ou 3, sem o segmento à esquerda do zero) ou segmentos mais longos.",
        segment_mm=round(segment_mm, 2), needed_mm=round(needed_mm, 2), tightest_pair=list(pair),
    )


def _check_scalebar_geographic_crs(observation: dict[str, Any]) -> CheckOutcome:
    bar = observation.get("scalebar") or {}
    if not bar.get("item_id"):
        return _skip("Sem barra de escala.")
    map_info = _map(observation)
    if not map_info.get("crs_is_geographic"):
        return _pass("O mapa está em CRS projetado; a barra métrica é válida.")
    unit = str(bar.get("unit", "")).lower()
    if unit in {"deg", "degree", "degrees", "graus"}:
        return _fail(
            "A barra está em graus. Um grau de longitude mede ~111 km no equador e "
            "zero nos polos, então a barra não representa uma distância constante.",
            crs=map_info.get("crs"),
        )
    return _fail(
        f"Barra métrica sobre mapa em CRS geográfico ({map_info.get('crs')}). "
        "A distância impressa varia com a latitude e não é confiável.",
        crs=map_info.get("crs"),
    )


def _check_north_indication(observation: dict[str, Any]) -> CheckOutcome:
    north = observation.get("north") or {}
    grid = _map(observation).get("grid") or {}
    if north.get("item_id"):
        return _pass(f"Indicação de norte presente (tipo: {north.get('kind')}).")
    if grid.get("enabled") and grid.get("annotations"):
        return _skip("Sem rosa dos ventos, mas a grade anotada já orienta o leitor.")
    if grid.get("enabled") and grid.get("graticule"):
        return _skip("Sem rosa dos ventos, mas a grade em graus mostra o norte em cada ponto da folha.")
    return _fail("O mapa não tem rosa dos ventos nem grade anotada; nada indica a orientação.")


def _check_north_is_symbol(observation: dict[str, Any]) -> CheckOutcome:
    north = observation.get("north") or {}
    if not north.get("item_id"):
        return _skip("Sem indicação de norte.")
    kind = str(north.get("kind", ""))
    if kind == "picture":
        return _pass("A indicação de norte é um símbolo gráfico.")
    return _fail(
        f"A indicação de norte é do tipo {kind!r} (texto {north.get('text')!r}). "
        "O QGIS traz símbolos de norte prontos que giram junto com o norte da grade; "
        "um rótulo de texto não gira e fica errado assim que o mapa é rotacionado.",
        kind=kind,
    )


def _localized_credit_markers(key: str) -> tuple[str, ...]:
    """Deriva marcadores de "Fonte:"/"Elaboração:" de todas as línguas de maptext.py.

    map_language (ver compose.py) traduz "Fonte:"/"Elaboração:" para a língua
    do mapa — um mapa em japonês passa a escrever "出典:"/"作成:" em vez de
    "Fonte:"/"Elaboração:". Sem isto, _check_source_credit só reconhecia os
    marcadores em português e inglês, e acusaria "falta a fonte dos dados"
    num mapa japonês que tem data_source preenchido — a mesma tradução do
    defeito de idioma teria criado um novo defeito na auditoria.
    """
    from .maptext import MAP_TEXT

    # Japonês e chinês pontuam com dois-pontos de largura inteira ("出典：") e
    # o francês põe um espaço antes ("Source : "). Tirar só o ":" ASCII deixava
    # "出典：" e "Source " inteiros, os marcadores viravam "出典：:" e "source :"
    # — que nunca batem — e CART007 acusava falta de fonte em mapas japoneses
    # e franceses com data_source preenchido. Aqui o marcador é a palavra
    # seguida de ":"; _check_source_credit normaliza o texto do mesmo jeito.
    markers: set[str] = set()
    for table in MAP_TEXT.values():
        value = _normalise_credit_text(str(table.get(key, ""))).strip().rstrip(":").strip()
        if value:
            markers.add(f"{value}:")
    return tuple(sorted(markers))


def _normalise_credit_text(text: str) -> str:
    """Minúsculas, dois-pontos ASCII e sem espaço antes dele — para que
    "Source : X", "出典：X" e "Fonte: X" sejam comparáveis com um só marcador."""
    return str(text).lower().replace("：", ":").replace(" :", ":")


#: Marcadores de procedência aceitos na linha de crédito: os originais em pt
#: e en, mais um marcador por língua de maptext.py (ver _localized_credit_markers) —
#: assim a checagem acompanha map_language em vez de travar em português/inglês.
SOURCE_MARKERS = (
    ("fonte:", "fontes:", "source:", "sources:", "dados:", "data source:", "base de dados:")
    # Um bloco de procedência também pode vir como cabeçalho, sem dois-pontos
    # ("FONTES DOS DADOS" seguido de itens). Um mapa feito à mão com esse bloco
    # era acusado de não declarar a fonte.
    + ("fonte de dados", "fontes de dados", "fonte dos dados", "fontes dos dados",
       "data sources", "sources of data", "fuente de datos", "fuentes de datos",
       "source des données", "sources des données", "datenquelle", "datenquellen",
       "fonte dei dati", "fonti dei dati")
    + _localized_credit_markers("fonte")
)
AUTHOR_MARKERS = (
    ("elabora", "autor", "author", "cartografia", "organiza", "credit")
    + _localized_credit_markers("elaboracao")
)

#: O que a própria ferramenta escreve sozinha e, portanto, não conta como
#: procedência: assinatura, data e sistema de referência.
_BOILERPLATE = ("produzido com sigmai", "sigmai/qgis", "qgis")


def _check_source_credit(observation: dict[str, Any]) -> CheckOutcome:
    """A linha de crédito precisa dizer DE ONDE vieram os dados e QUEM fez o mapa.

    A versão anterior só verificava que existia um rótulo de rodapé com algum
    texto. Como o compositor sempre escreve o sistema de referência, a data e
    "Produzido com SIGMAI/QGIS", um mapa sem nenhuma fonte declarada passava com
    nota A — e chegava ao usuário parecendo citável sem ser.
    """
    textos = [_normalise_credit_text(item.get("text", "")) for item in _texts(observation)]
    fonte_item = _item_by_role(observation, "source")
    if fonte_item:
        textos.append(_normalise_credit_text(fonte_item.get("text", "")))
    junto = " · ".join(t for t in textos if t.strip())
    if not junto.strip():
        return _fail("Falta a linha de fonte dos dados e autoria. Sem procedência o mapa não é citável.")

    tem_fonte = any(marcador in junto for marcador in SOURCE_MARKERS)
    tem_autor = any(marcador in junto for marcador in AUTHOR_MARKERS)
    if tem_fonte and tem_autor:
        return _pass("A linha de crédito declara a fonte dos dados e a autoria do mapa.")
    if _caption(observation).get("title_placement") == "caption":
        # Figura de periódico: a autoria é a do artigo; a fonte não pode faltar.
        if tem_fonte:
            return _pass("A legenda do texto declara a fonte dos dados; a autoria da figura é a do artigo.")
        return _fail("A legenda do texto não declara a fonte dos dados (data_source). Sem procedência a figura "
                     "não é citável, e a licença dos dados costuma exigir a citação.", missing=["data_source"])

    faltando = []
    if not tem_fonte:
        faltando.append("a fonte dos dados (data_source)")
    if not tem_autor:
        faltando.append("a autoria do mapa (map_author)")
    return _fail(
        "A linha de crédito não declara " + " nem ".join(faltando) + ". "
        "O sistema de referência, a data e a assinatura da ferramenta não são procedência: "
        "sem dizer de onde vieram os dados e quem fez o mapa, ele não é citável. "
        "Pergunte ao usuário — a autoria do mapa não é a autoria do plugin.",
        missing=faltando,
    )


def _check_crs_declared(observation: dict[str, Any]) -> CheckOutcome:
    map_info = _map(observation)
    crs = str(map_info.get("crs", ""))
    if not crs:
        return _skip("CRS do mapa desconhecido.")
    authid = crs.split(":")[-1]
    if _has_text(observation, crs, authid, "sirgas", "utm", "wgs", "datum", "epsg"):
        return _pass(f"O sistema de referência ({crs}) está declarado no layout.")
    return _fail(
        f"O mapa usa {crs} mas o layout não declara datum/projeção. "
        "Coordenadas sem sistema de referência não são reprodutíveis.",
        crs=crs,
    )


def _check_date(observation: dict[str, Any]) -> CheckOutcome:
    import re

    for item in _texts(observation):
        text = str(item.get("text", ""))
        if re.search(r"\b(19|20)\d{2}\b", text):
            return _pass("O layout informa uma data/ano.")
    return _fail("O layout não informa a data de elaboração, necessária para citação e versionamento.")


# ---------------------------------------------------------------------------
# Regras — grade de coordenadas
# ---------------------------------------------------------------------------

def _check_graticule_enabled(observation: dict[str, Any]) -> CheckOutcome:
    grid = _map(observation).get("grid") or {}
    if grid.get("enabled"):
        return _pass("Grade de coordenadas habilitada.")
    return _fail("O mapa não tem grade de coordenadas; o leitor não consegue localizar nada.")


def _check_graticule_interval(observation: dict[str, Any]) -> CheckOutcome:
    grid = _map(observation).get("grid") or {}
    if not grid.get("enabled"):
        return _skip("Grade desabilitada.")
    interval_x = float(grid.get("interval_x") or 0.0)
    interval_y = float(grid.get("interval_y") or 0.0)
    if interval_x > 0 and interval_y > 0:
        return _pass(f"Intervalo da grade: {interval_x:g} x {interval_y:g}.")
    return _fail(
        "A grade está habilitada com intervalo zero, então o QGIS não desenha "
        "nenhuma linha. É uma grade que existe nos metadados e não no papel.",
        interval_x=interval_x,
        interval_y=interval_y,
    )


def _check_graticule_annotations(observation: dict[str, Any]) -> CheckOutcome:
    grid = _map(observation).get("grid") or {}
    if not grid.get("enabled"):
        return _skip("Grade desabilitada.")
    if grid.get("annotations"):
        return _pass("A grade tem rótulos de coordenadas.")
    if grid.get("graticule"):
        return _skip("Grade em graus de um mapa de pequena escala, sem rótulos: as linhas terminam no contorno do "
                     "globo, não na moldura, e o leitor se localiza pelos continentes.")
    return _fail("A grade não está anotada; linhas sem valores de coordenada não localizam nada.")


# ---------------------------------------------------------------------------
# Regras — inserto de localização
# ---------------------------------------------------------------------------

#: Fração mínima da extensão de cada camada de contexto que o inserto precisa
#: mostrar. Um localizador que corta o estado ao meio não localiza.
INSET_MIN_COVERAGE = 0.95


def _check_inset_locates(observation: dict[str, Any]) -> CheckOutcome:
    inset = observation.get("inset")
    if not inset:
        return _skip("Sem inserto de localização.")
    coverage = inset.get("layer_coverage") or {}
    if not coverage:
        return _skip("Inserto sem camada de contexto mensurável.")
    cortadas = {name: value for name, value in coverage.items() if float(value) < INSET_MIN_COVERAGE}
    if not cortadas:
        detail = "O inserto mostra a extensão inteira das camadas de contexto"
        detail += " e contém o recorte principal." if inset.get("shows_main_frame") else "."
        if inset.get("shows_main_frame") is False:
            return _fail(
                "O inserto mostra o contexto inteiro mas o recorte principal fica fora dele — "
                "o retângulo de localização não aparece no inserto.",
                shows_main_frame=False,
            )
        return _pass(detail)
    return _fail(
        "O inserto corta a camada de contexto: "
        + ", ".join(f"{name!r} ({value:.0%} visível)" for name, value in cortadas.items())
        + ". Um localizador que mostra metade do estado não diz onde o recorte fica.",
        layer_coverage=coverage,
    )


# ---------------------------------------------------------------------------
# Regras — geometria do layout
# ---------------------------------------------------------------------------

def _check_items_inside_page(observation: dict[str, Any]) -> CheckOutcome:
    page = observation.get("page") or {}
    width = float(page.get("width_mm") or 0)
    height = float(page.get("height_mm") or 0)
    if width <= 0 or height <= 0:
        return _skip("Dimensões da página desconhecidas.")
    outside = []
    for item in _items(observation):
        x, y = float(item.get("x", 0)), float(item.get("y", 0))
        w, h = float(item.get("width", 0)), float(item.get("height", 0))
        if x < -0.5 or y < -0.5 or x + w > width + 0.5 or y + h > height + 0.5:
            outside.append(item.get("id"))
    if not outside:
        return _pass("Todos os itens estão dentro da página.")
    return _fail(
        "Itens fora da página: " + ", ".join(str(name) for name in outside) +
        ". Eles não serão impressos.",
        items_outside=outside,
        page_mm=[width, height],
    )


def _check_items_inside_margins(observation: dict[str, Any]) -> CheckOutcome:
    page = observation.get("page") or {}
    content = page.get("content_area_mm") or {}
    if not content:
        return _skip("Área útil da página desconhecida.")
    cx, cy = float(content.get("x", 0)), float(content.get("y", 0))
    cw, ch = float(content.get("width", 0)), float(content.get("height", 0))
    violators = []
    for item in _items(observation):
        x, y = float(item.get("x", 0)), float(item.get("y", 0))
        w, h = float(item.get("width", 0)), float(item.get("height", 0))
        if x < cx - 0.5 or y < cy - 0.5 or x + w > cx + cw + 0.5 or y + h > cy + ch + 0.5:
            violators.append(item.get("id"))
    if not violators:
        return _pass("Todos os itens respeitam as margens.")
    return _fail(
        "Itens invadindo a margem: " + ", ".join(str(name) for name in violators) +
        ". Impressoras costumam cortar essa faixa.",
        items_outside_margins=violators,
    )


def _check_no_overlaps(observation: dict[str, Any]) -> CheckOutcome:
    boxes = []
    for item in _items(observation):
        if item.get("role") == "background":
            continue
        boxes.append((
            str(item.get("id")),
            float(item.get("x", 0)),
            float(item.get("y", 0)),
            float(item.get("x", 0)) + float(item.get("width", 0)),
            float(item.get("y", 0)) + float(item.get("height", 0)),
        ))
    collisions = []
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            overlap_w = min(first[3], second[3]) - max(first[1], second[1])
            overlap_h = min(first[4], second[4]) - max(first[2], second[2])
            if overlap_w > 0.5 and overlap_h > 0.5:
                collisions.append({
                    "a": first[0],
                    "b": second[0],
                    "overlap_mm2": round(overlap_w * overlap_h, 2),
                })
    # Um item desenhado SOBRE o quadro do mapa não é colisão se está num
    # canto vazio: rosa dos ventos, inserto e notas dentro da moldura são
    # convenção aceita em cartas publicadas. O critério é cartográfico — o
    # que importa é não cobrir dados — e é medido no raster: a faixa em volta
    # do item (``surroundings_ink_fraction``, ver inspector) precisa estar
    # praticamente vazia. Sem raster, a sobreposição continua acusada.
    by_id = {str(item.get("id")): item for item in _items(observation)}
    map_ids = {str(item.get("id")) for item in _items(observation) if item.get("role") == "map"}
    overlays: list[dict[str, Any]] = []
    real: list[dict[str, Any]] = []
    for collision in collisions:
        other = None
        if collision["a"] in map_ids and collision["b"] not in map_ids:
            other = by_id.get(collision["b"])
        elif collision["b"] in map_ids and collision["a"] not in map_ids:
            other = by_id.get(collision["a"])
        ring = other.get("surroundings_ink_fraction") if other is not None else None
        if ring is not None and float(ring) < OVERLAY_MAX_SURROUNDINGS_INK:
            overlays.append({**collision, "surroundings_ink_fraction": ring})
        else:
            real.append(collision)
    if not real:
        if overlays:
            described = ", ".join(f"{item['a']}/{item['b']}" for item in overlays)
            return _pass(
                f"Sobreposições aceitas por estarem em área vazia do quadro: {described}.",
                overlays=overlays,
            )
        return _pass("Nenhuma sobreposição entre itens do layout.")
    described = ", ".join(f"{item['a']}/{item['b']}" for item in real)
    return _fail(f"Itens sobrepostos: {described}.", collisions=real, overlays=overlays)


def _check_map_dominance(observation: dict[str, Any]) -> CheckOutcome:
    page = observation.get("page") or {}
    content = page.get("content_area_mm") or {}
    # Numa folha de comparação o assunto são os DOIS quadros; contar só o
    # principal dava 27% e acusava de "apoio consumindo a página" um layout
    # em que os mapas ocupam mais da metade. O inserto não entra: ele é apoio.
    map_items = [item for item in _items(observation) if item.get("role") == "map"]
    if not map_items or not content:
        return _skip("Sem quadro de mapa ou área útil para comparar.")
    content_area = float(content.get("width", 0)) * float(content.get("height", 0))
    map_area = sum(float(item.get("width", 0)) * float(item.get("height", 0)) for item in map_items)
    if content_area <= 0:
        return _skip("Área útil nula.")
    ratio = map_area / content_area
    quadros = "O quadro do mapa ocupa" if len(map_items) == 1 else f"Os {len(map_items)} quadros de mapa ocupam"
    if ratio >= MAP_DOMINANCE_MIN:
        return _pass(f"{quadros} {ratio:.0%} da área útil.")
    return _fail(
        f"{quadros} apenas {ratio:.0%} da área útil. "
        "Os elementos de apoio estão consumindo a página.",
        map_area_ratio=round(ratio, 3),
    )


def _check_font_sizes(observation: dict[str, Any]) -> CheckOutcome:
    small = [
        {"id": item.get("id"), "font_size_pt": item.get("font_size_pt")}
        for item in _texts(observation)
        if item.get("font_size_pt") and float(item["font_size_pt"]) < MIN_PRINT_FONT_PT
    ]
    if not small:
        return _pass(f"Nenhum texto abaixo de {MIN_PRINT_FONT_PT:g} pt.")
    return _fail(
        "Textos abaixo do mínimo legível: " +
        ", ".join(f"{item['id']} ({item['font_size_pt']:g} pt)" for item in small) + ".",
        small_texts=small,
    )


def _check_title_hierarchy(observation: dict[str, Any]) -> CheckOutcome:
    title = _item_by_role(observation, "title")
    subtitle = _item_by_role(observation, "subtitle")
    if not title or not title.get("font_size_pt"):
        return _skip("Sem título medível.")
    if not subtitle or not subtitle.get("font_size_pt"):
        return _skip("Sem subtítulo medível.")
    if float(title["font_size_pt"]) > float(subtitle["font_size_pt"]):
        return _pass("A hierarquia tipográfica entre título e subtítulo está correta.")
    return _fail(
        f"O título ({title['font_size_pt']:g} pt) não é maior que o subtítulo "
        f"({subtitle['font_size_pt']:g} pt); a hierarquia de leitura se perde."
    )


# ---------------------------------------------------------------------------
# Regras — dados e projeção
# ---------------------------------------------------------------------------

def _check_projected_crs(observation: dict[str, Any]) -> CheckOutcome:
    map_info = _map(observation)
    if map_info.get("crs_is_geographic") is None:
        return _skip("CRS do mapa desconhecido.")
    if not map_info.get("crs_is_geographic"):
        return _pass(f"Mapa em CRS projetado ({map_info.get('crs')}).")
    return _fail(
        f"O mapa está em CRS geográfico ({map_info.get('crs')}). Áreas, distâncias "
        "e a barra de escala ficam distorcidas; para escalas maiores que ~1:1.000.000 "
        "use uma projeção adequada à região.",
        crs=map_info.get("crs"),
    )


#: Faixa de coordenada E em que uma zona UTM é utilizável. A zona tem 6° de
#: largura e falso leste de 500.000; fora de ~[100.000, 900.000] o recorte está
#: longe demais do meridiano central.
UTM_EASTING_RANGE = (100_000.0, 900_000.0)


def _check_crs_suits_extent(observation: dict[str, Any]) -> CheckOutcome:
    map_info = _map(observation)
    description = str(map_info.get("crs_description", "")).lower()
    extent = map_info.get("extent") or {}
    if "utm" not in description or not extent:
        return _skip("O mapa não usa UTM; a regra não se aplica.")
    xmin, xmax = float(extent.get("xmin", 0)), float(extent.get("xmax", 0))
    low, high = UTM_EASTING_RANGE
    if low <= xmin and xmax <= high:
        return _pass(f"As coordenadas E ({_num(xmin)} a {_num(xmax)}) estão dentro da faixa da zona.")
    # Os números passam por _num, e não a frase inteira por .replace(",", "."):
    # a versão anterior trocava também a vírgula de ", fora da faixa" por ponto.
    return _fail(
        f"O mapa está em UTM mas cobre coordenadas E de {_num(xmin)} a {_num(xmax)}, fora da faixa "
        f"utilizável da zona ({_num(low)} a {_num(high)}). A escala impressa não vale para toda a folha. "
        "Para recortes estaduais ou maiores use uma projeção cônica ou a Policônica do Brasil.",
        easting_range=[xmin, xmax],
    )


def _check_comparison_panels(observation: dict[str, Any]) -> CheckOutcome:
    frames = observation.get("map_frames") or []
    if len(frames) < 2:
        return _skip("O layout tem um único quadro de mapa.")
    scales = [float(frame.get("scale") or 0.0) for frame in frames if frame.get("scale")]
    if len(scales) < 2:
        return _skip("Não foi possível medir a escala dos quadros.")
    if max(scales) / min(scales) <= 1.02:
        return _pass(f"Os {len(frames)} quadros estão na mesma escala (1:{_num(min(scales))}).")

    has_bar = bool((observation.get("scalebar") or {}).get("item_id"))
    captions = [
        str(item.get("text", "")) for item in _items(observation)
        if item.get("type") == "label" and "1:" in str(item.get("text", ""))
    ]
    if not has_bar and len(captions) >= 2:
        return _pass("Os quadros têm escalas diferentes e cada um anuncia a sua.")
    return _fail(
        f"O layout tem {len(frames)} quadros de mapa em escalas diferentes "
        f"(1:{_num(min(scales))} a 1:{_num(max(scales))}) e uma indicação de escala única. "
        "O leitor vai comparar tamanhos entre os painéis e a comparação não se sustenta.",
        scales=scales,
    )


def _check_comparable_value_scales(observation: dict[str, Any]) -> CheckOutcome:
    """CART081 — painéis comparáveis usam a mesma régua de cor e de tamanho."""
    frames = observation.get("map_frames") or []
    if len(frames) < 2:
        return _skip("O layout tem um único quadro de mapa.")
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for frame in frames:
        for entry in frame.get("value_scales") or []:
            by_key.setdefault((str(entry.get("kind")), str(entry.get("variable") or "")), []).append(
                {**entry, "frame": frame.get("item_id")})
    shared = {key: entries for key, entries in by_key.items() if len({e["frame"] for e in entries}) >= 2}
    if not shared:
        return _skip("Nenhuma camada temática aparece em mais de um painel com a mesma variável.")
    problems: list[str] = []
    for (kind, _variable), entries in shared.items():
        names = ", ".join(sorted({repr(e["layer"]) for e in entries}))
        if kind == "heatmap":
            if any(float(e.get("maximum") or 0.0) <= 0 for e in entries):
                problems.append(f"mapas de calor ({names}) com o máximo automático: cada painel vai do seu menor ao "
                                "seu maior, e o vermelho de um não é o vermelho do outro")
            elif len({round(float(e["maximum"]), 6) for e in entries}) > 1 or len({e.get("radius") for e in entries}) > 1:
                problems.append(f"mapas de calor ({names}) com máximos ou raios diferentes")
        elif kind == "graduated" and len({tuple(e.get("breaks") or []) for e in entries}) > 1:
            problems.append(f"classes graduadas ({names}) com limites diferentes")
        elif kind == "proportional" and len({(tuple(e.get("domain") or []), tuple(e.get("sizes") or [])) for e in entries}) > 1:
            problems.append(f"símbolos proporcionais ({names}) com réguas diferentes: o mesmo tamanho vale números "
                            "diferentes em cada painel")
    if not problems:
        return _pass("Os painéis usam a mesma régua de cor e de tamanho para a mesma variável.")
    return _fail("Painéis lado a lado convidam a comparar, mas " + "; ".join(problems) + ".",
                 value_scales=[{"key": list(k), "entries": v} for k, v in shared.items()])


def _check_extent_contains_data(observation: dict[str, Any]) -> CheckOutcome:
    map_info = _map(observation)
    extent = map_info.get("extent") or {}
    data = map_info.get("data_extent") or {}
    if not extent or not data:
        return _skip("Extensão do mapa ou dos dados desconhecida.")
    contained = (
        float(extent.get("xmin", 0)) <= float(data.get("xmin", 0)) + 1e-6
        and float(extent.get("ymin", 0)) <= float(data.get("ymin", 0)) + 1e-6
        and float(extent.get("xmax", 0)) >= float(data.get("xmax", 0)) - 1e-6
        and float(extent.get("ymax", 0)) >= float(data.get("ymax", 0)) - 1e-6
    )
    if contained:
        return _pass("A extensão do mapa contém toda a extensão dos dados.")
    return _fail("A extensão do mapa corta parte dos dados das camadas visíveis.", extent=extent, data_extent=data)


def _check_labels_placed(observation: dict[str, Any]) -> CheckOutcome:
    """CART068 — nenhum rótulo descartado pelo motor do QGIS."""
    frames = [frame for frame in (observation.get("map_frames") or []) if isinstance(frame.get("labels"), dict)]
    main = _map(observation)
    if not frames and isinstance(main.get("labels"), dict):
        frames = [{"item_id": main.get("item_id"), "labels": main["labels"]}]
    if not frames:
        return _skip("Sem coleta de rótulos (renderização não disponível).")
    placed = sum(int(frame["labels"].get("placed", 0)) for frame in frames)
    unplaced = sum(int(frame["labels"].get("unplaced", 0)) for frame in frames)
    if placed + unplaced == 0:
        return _skip("Nenhuma camada rotulada no quadro.")
    if unplaced == 0:
        return _pass(f"Todos os {placed} rótulos foram colocados.")
    by_layer: dict[str, int] = {}
    samples: list[str] = []
    for frame in frames:
        for layer, counts in (frame["labels"].get("by_layer") or {}).items():
            if int(counts.get("unplaced", 0)):
                by_layer[layer] = by_layer.get(layer, 0) + int(counts["unplaced"])
        for sample in frame["labels"].get("unplaced_sample") or []:
            text = str(sample.get("text", "")).strip()
            if text and text not in samples:
                samples.append(text)
    described = ", ".join(f"{layer} ({count})" for layer, count in by_layer.items())
    example = f" Exemplos: {', '.join(repr(t) for t in samples[:5])}." if samples else ""
    return _fail(
        f"{unplaced} rótulo(s) descartado(s) pelo motor de rótulos — por colisão com outro rótulo ou por "
        f"cruzar a moldura — em: {described}.{example} As feições existem no mapa mas saem sem nome.",
        unplaced=unplaced, placed=placed, by_layer=by_layer, samples=samples[:12],
    )


def _empty_bands(cells: list[list[float]], threshold: float) -> list[str]:
    """Colunas e linhas de uma grade 3x3 cuja média fica abaixo do limiar."""
    if not cells or any(len(row) != len(cells) for row in cells):
        return []
    size = len(cells)
    bands: list[str] = []
    column_names = ("oeste", "centro", "leste")[:size]
    row_names = ("norte", "centro", "sul")[:size]
    for col in range(size):
        if sum(float(cells[row][col]) for row in range(size)) / size < threshold:
            bands.append(f"coluna {column_names[col]}")
    for row in range(size):
        if sum(float(cells[row][col]) for col in range(size)) / size < threshold:
            bands.append(f"linha {row_names[row]}")
    return bands


def _check_frame_coverage(observation: dict[str, Any]) -> CheckOutcome:
    """CART069 — nenhuma faixa inteira do quadro é papel em branco.

    Uma faixa é vazia quando nem dado de área (polígono ou raster) nem tinta
    de dado (linhas e pontos, sem grade nem rótulos) a ocupam: um mapa de
    hidrografia é feito de linhas, e medi-lo só pela área dos polígonos
    acusava de vazio o quadro inteiro.
    """
    map_info = _map(observation)
    coverage = map_info.get("polygon_coverage")
    data_grid = map_info.get("data_ink_grid")
    if isinstance(coverage, dict) and coverage.get("cells"):
        fraction = float(coverage.get("fraction") or 0.0)
        bands = _empty_bands(coverage["cells"], FRAME_BAND_EMPTY_MAX)
        if bands and data_grid:
            inkless = set(_empty_bands(data_grid, FRAME_BAND_EMPTY_DATA_INK))
            bands = [band for band in bands if band in inkless]
        if not bands:
            return _pass(f"Dados de área cobrem {fraction:.0%} do quadro, sem faixa vazia.", coverage=coverage)
        return _fail(
            f"Faixa(s) do quadro sem dado de área: {', '.join(bands)} (cobertura total {fraction:.0%}). "
            "Se o vazio é território vizinho, acrescente a malha dele; se é mar, uma camada de oceano ou "
            "linha de costa; se é sobra de extensão, feche o recorte (subject_layer_id, margin_percent) ou "
            "gire a página (orientation).",
            coverage=coverage, empty_bands=bands,
        )
    grid = data_grid or map_info.get("rendered_ink_grid")
    if not grid:
        return _skip("Sem camada de polígonos e sem raster para medir a ocupação do quadro.")
    bands = _empty_bands(grid, FRAME_BAND_EMPTY_DATA_INK if data_grid else FRAME_BAND_EMPTY_INK)
    if not bands:
        return _pass("Nenhuma faixa do quadro está vazia no raster exportado.", ink_grid=grid)
    return _fail(
        f"Faixa(s) do quadro sem tinta no raster: {', '.join(bands)}. Acrescente contexto ou feche o recorte.",
        ink_grid=grid, empty_bands=bands,
    )


def _check_colour_vision(observation: dict[str, Any]) -> CheckOutcome:
    """CART070 — as cores da legenda continuam distinguíveis para daltônicos."""
    from .vision import CONFUSABLE_DELTA_E, confusable_pairs

    layer_colours = _map(observation).get("layer_colours") or []
    if not layer_colours:
        return _skip("Sem cores de símbolo observáveis.")
    families: dict[str, list[tuple[str, str]]] = {}
    for entry in layer_colours:
        family = str(entry.get("family", "other"))
        for klass in entry.get("classes") or []:
            name = f"{entry.get('layer')}: {klass.get('label')}" if len(entry.get("classes") or []) > 1 else str(entry.get("layer"))
            families.setdefault(family, []).append((name, str(klass.get("colour", ""))))
    total_pairs = 0
    findings: list[dict[str, Any]] = []
    for family, colours in families.items():
        if len(colours) < 2:
            continue
        total_pairs += len(colours) * (len(colours) - 1) // 2
        for finding in confusable_pairs(colours):
            findings.append({**finding, "family": family})
    if total_pairs == 0:
        return _skip("Só uma cor por família de símbolo; não há pares para confundir.")
    if not findings:
        return _pass(f"{total_pairs} par(es) de cores distinguíveis sob protanopia, deuteranopia e tritanomalia.")
    described = "; ".join(
        f"{f['a']} × {f['b']} ({f['colours'][0]}/{f['colours'][1]}: ΔE {f['delta_e_simulated']} sob {f['deficiency']})"
        for f in findings[:6]
    )
    return _fail(
        f"Cores que se confundem para daltônicos (ΔE*ab < {CONFUSABLE_DELTA_E:g} na simulação de Machado et al., 2009): "
        f"{described}.",
        confusable=findings,
    )


def _check_legend_fits_box(observation: dict[str, Any]) -> CheckOutcome:
    """CART072 — o conteúdo da legenda cabe na caixa; o que não cabe é cortado sem aviso."""
    legend = observation.get("legend")
    if not legend or not legend.get("item_id"):
        return _skip("Sem legenda para avaliar.")
    box = legend.get("box_mm") or {}
    content = legend.get("content_mm") or {}
    if not box or not content:
        return _skip("Tamanho do conteúdo da legenda não medido (QgsLegendRenderer indisponível).")
    if legend.get("resize_to_contents"):
        return _pass("A caixa da legenda cresce com o conteúdo (resizeToContents).")
    overflow_w = float(content.get("width", 0.0)) - float(box.get("width", 0.0))
    overflow_h = float(content.get("height", 0.0)) - float(box.get("height", 0.0))
    if overflow_w <= LEGEND_OVERFLOW_TOLERANCE_MM and overflow_h <= LEGEND_OVERFLOW_TOLERANCE_MM:
        return _pass(
            f"Legenda de {content.get('width'):g} x {content.get('height'):g} mm cabe na caixa de "
            f"{box.get('width'):g} x {box.get('height'):g} mm."
        )
    axes = []
    if overflow_w > LEGEND_OVERFLOW_TOLERANCE_MM:
        axes.append(f"{overflow_w:.1f} mm a mais de largura")
    if overflow_h > LEGEND_OVERFLOW_TOLERANCE_MM:
        axes.append(f"{overflow_h:.1f} mm a mais de altura")
    return _fail(
        f"O conteúdo da legenda precisa de {content.get('width'):g} x {content.get('height'):g} mm e a caixa tem "
        f"{box.get('width'):g} x {box.get('height'):g} mm (" + " e ".join(axes) + "): os nomes são cortados na "
        "borda ou desenhados por cima do item de baixo.",
        box_mm=box, content_mm=content,
    )


def _check_fonts_at_print_width(observation: dict[str, Any]) -> CheckOutcome:
    """CART071 — as fontes continuam legíveis na largura em que a figura vai ser impressa."""
    print_width = observation.get("print_width_mm")
    page = observation.get("page") or {}
    page_width = float(page.get("width_mm") or 0.0)
    if not print_width or page_width <= 0:
        return _skip("Largura de impressão não informada; as fontes foram julgadas na página (CART044).")
    factor = float(print_width) / page_width
    if factor >= 0.999:
        return _pass("A figura é impressa no tamanho da página; CART044 já cobre as fontes.")
    small = []
    for item in _texts(observation):
        size = item.get("font_size_pt")
        if not size:
            continue
        effective = float(size) * factor
        if effective < MIN_PRINT_FONT_PT:
            small.append({"id": item.get("id"), "font_size_pt": float(size), "effective_pt": round(effective, 1)})
    if not small:
        return _pass(f"Reduzida a {print_width:g} mm de largura ({factor:.0%}), nenhuma fonte cai abaixo de {MIN_PRINT_FONT_PT:g} pt.")
    return _fail(
        f"Impressa a {print_width:g} mm de largura ({factor:.0%} da página), estas fontes ficam abaixo de "
        f"{MIN_PRINT_FONT_PT:g} pt: " + ", ".join(f"{i['id']} ({i['font_size_pt']:g} → {i['effective_pt']:g} pt)" for i in small) +
        ". Componha a figura já na largura final (figure_width_mm) em vez de reduzir uma página inteira.",
        small_texts=small, factor=round(factor, 3),
    )


def _check_greyscale(observation: dict[str, Any]) -> CheckOutcome:
    """CART073 — figura pedida em tons de cinza sai sem cor."""
    if observation.get("colour_mode") != "greyscale":
        return _skip("A figura não foi pedida em tons de cinza (colour_mode).")
    fraction = (observation.get("output") or {}).get("chromatic_fraction")
    if fraction is None:
        return _skip("Sem raster exportado (PNG, TIFF ou JPEG) em que medir a cor.")
    fraction = float(fraction)
    if fraction <= GREYSCALE_MAX_CHROMATIC_FRACTION:
        return _pass(
            f"{fraction:.2%} da tinta tem cor (limite {GREYSCALE_MAX_CHROMATIC_FRACTION:.1%}): a figura sai em tons de cinza.",
            chromatic_fraction=fraction,
        )
    return _fail(
        f"A figura foi pedida em tons de cinza, mas {fraction:.1%} da tinta tem cor: impressa em cinza, "
        "duas cores de mesma luminosidade viram o mesmo tom. Componha com colour_mode='greyscale': o "
        "compositor troca a paleta, o contorno do inserto e a grade, e converte para cinza as classificações "
        "e os rasters já estilizados mantendo as classes. Não use apply_style='all' numa camada classificada: "
        "ele troca as classes por um cinza único.",
        chromatic_fraction=fraction,
    )


def _check_map_not_blank(observation: dict[str, Any]) -> CheckOutcome:
    map_info = _map(observation)
    # Primeiro, as camadas do quadro renderizadas sozinhas: zero pixel opaco é
    # quadro vazio, por mais que moldura e grade deem tinta ao PNG.
    layer_ink = map_info.get("layer_ink_fraction")
    if layer_ink is not None and float(layer_ink) <= 0.0:
        return _fail(
            "Nenhuma feição das camadas do quadro é desenhada na extensão do mapa: o quadro sai vazio, "
            "com moldura e grade. Provável extensão errada, camada sem feições ali ou CRS incompatível.",
            layer_ink_fraction=layer_ink,
        )
    ink = map_info.get("rendered_ink_fraction")
    if ink is None:
        if layer_ink is not None:
            return _pass(f"As camadas do quadro desenham conteúdo ({float(layer_ink):.1%} da área).")
        return _skip("Sem análise do raster exportado.")
    if float(ink) >= 0.005:
        return _pass(f"O quadro do mapa tem conteúdo renderizado ({float(ink):.1%} de pixels não-fundo).")
    return _fail(
        f"O quadro do mapa está praticamente em branco ({float(ink):.2%} de pixels não-fundo). "
        "Provável extensão errada, camada invisível ou CRS incompatível.",
        ink_fraction=ink,
    )


def _check_output_written(observation: dict[str, Any]) -> CheckOutcome:
    output = observation.get("output") or {}
    if not output.get("path"):
        return _skip("Nenhuma exportação associada a esta avaliação.")
    if not output.get("exists"):
        return _fail("O arquivo de saída não foi criado.", path=output.get("path"))
    size = int(output.get("size_bytes") or 0)
    floor = 10_000 if str(output.get("format", "")).lower() == "png" else 5_000
    if size >= floor:
        return _pass(f"Saída gravada com {_num(size)} bytes.")
    return _fail(f"A saída tem apenas {size} bytes, abaixo do piso de {floor}; provável exportação vazia.", size_bytes=size)


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

RULES: tuple[Rule, ...] = (
    Rule("CART001", "elementos", SEVERITY_ERROR,
         "Título presente", "Title present",
         "Um mapa sem título não informa tema, recorte nem propósito; é a primeira coisa que o leitor procura.",
         "Chame add_layout_label com role='title' ou passe 'title' para compose_map.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 12 (título da folha); Brewer (2016), Designing Better Maps — map elements",
         _check_title),
    Rule("CART002", "elementos", SEVERITY_ERROR,
         "Legenda presente", "Legend present",
         "Com mais de uma camada visível, sem legenda o leitor não decodifica os símbolos.",
         "Chame add_layout_legend informando linked_map_item_id.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 13 (legenda com símbolos e convenções); Slocum et al. (2009), Thematic Cartography and Geovisualization — legend design",
         _check_legend),
    Rule("CART020", "elementos", SEVERITY_ERROR,
         "A legenda explica todas as camadas visíveis", "Legend covers every visible layer",
         "Feição desenhada sem entrada correspondente na legenda é ruído: o leitor vê e não sabe o que é. "
         "É a falha mais comum em mapas gerados automaticamente, porque a legenda costuma ser "
         "montada com a camada principal apenas.",
         "Passe legend_layers com TODAS as camadas do mapa, ou deixe compose_map derivá-las do quadro.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 13; Slocum et al. (2009), Thematic Cartography and Geovisualization — legend design",
         _check_legend_covers_visible_layers),
    Rule("CART072", "elementos", SEVERITY_WARNING,
         "A legenda cabe na caixa", "Legend content fits its box",
         "QgsLayoutItemLegend não avisa quando o conteúdo passa da caixa: corta os nomes na borda e "
         "desenha por cima do que vier abaixo. Numa figura de coluna simples duas entradas com fonte "
         "por camada já não cabiam, e o leitor via '(IBGE, 20' sobre a linha de crédito.",
         "Encurte os nomes das camadas, reduza a fonte da legenda até 6 pt, tire as fontes por camada "
         "(data_source como texto único) ou use uma página maior; compose_map já faz os dois primeiros. "
         "Se são classes demais, apply_categorized_style com limit=8 reúne as menos frequentes em 'Outros'.",
         "Slocum et al. (2009) — legend design; tolerância de 0,5 mm: decisão de projeto do SIGMAI; verificação: QGIS API QgsLegendRenderer::minimumSize",
         _check_legend_fits_box),
    Rule("CART021", "elementos", SEVERITY_WARNING,
         "A legenda não lista camadas ausentes", "Legend lists no phantom layers",
         "Entrada de legenda sem contrapartida no mapa faz o leitor procurar algo que não existe — seja a "
         "camada fora do quadro, seja ligada a ele mas inteiramente coberta por uma camada opaca desenhada por cima.",
         "Ative filter_to_map_layers ou remova as camadas extras de legend_layers; se a camada está coberta, "
         "reordene as camadas (o QGIS desenha a primeira da lista por cima) ou desenhe a que cobre como contorno.",
         "Slocum et al. (2009) — legend design; camada coberta quando menos de 10 % do que ela desenha sozinha fica visível e o que fica ocupa menos de 1 % do quadro: decisão de projeto do SIGMAI; verificação: QGIS Documentation — Legend: filter by map content",
         _check_legend_has_no_phantoms),
    Rule("CART075", "simbologia", SEVERITY_ERROR,
         "O assunto do mapa está à vista", "The map subject is visible",
         "O assunto é a razão do mapa. Coberto por preenchimentos de contexto desenhados por cima — "
         "municípios opacos sobre um modelo de elevação, por exemplo — ele continua na legenda e na "
         "lista de camadas, mas o leitor não o vê.",
         "Desenhe o contexto que fica por cima como contorno (sem preenchimento) ou com transparência alta; "
         "o compositor do SIGMAI já faz isso quando o assunto é um raster.",
         "Brewer (2016) — figure-ground and visual hierarchy; Slocum et al. (2009) — visual hierarchy; ao menos metade do que o assunto desenha à vista: decisão de projeto do SIGMAI",
         _check_subject_visible),
    Rule("CART076", "simbologia", SEVERITY_WARNING,
         "Os pontos não escondem a contagem", "Point symbols do not hide the count",
         "Num mapa de pontos o leitor conta pontos. Quando muitos caem no mesmo lugar — registros de "
         "ocorrência repetidos nas mesmas coordenadas, comuns em dados do GBIF —, um local com milhares "
         "de registros aparece igual a um local com um só, e a legenda continua dizendo que cada ponto "
         "é um registro. Num mapa de símbolos proporcionais, o mesmo acontece com os locais: amontoados "
         "no papel, os círculos se fundem, e onde há mais locais o mapa parece ter menos.",
         "Mostre a contagem: apply_heatmap_style (densidade) ou um símbolo por local com área "
         "proporcional ao número de registros (count_points_by_site com scale, o denominador da escala "
         "do mapa, e apply_proportional_symbol_style). Se os pontos estão só amontoados, e não "
         "repetidos, pontos menores e semitransparentes bastam; compose_map já os ajusta quando a "
         "camada usa a paleta.",
         f"Pontos levados para mm do quadro e contados em células do tamanho do símbolo (do menor "
         f"círculo, no símbolo proporcional); saturação de {SATURATION * 100:g} % de tinta, mais de "
         f"{STACKING_HIDDEN_MAX * 100:g} % dos pontos ocultos e mínimo de {STACKING_MIN_POINTS} pontos: "
         "decisão de projeto do SIGMAI, calibrada em docs/experiments/2026-10-26_pontos_empilhados/",
         _check_point_stacking),
    Rule("CART077", "simbologia", SEVERITY_WARNING,
         "A rampa do raster mostra os dados", "The raster colour ramp shows the data",
         "Uma rampa esticada por um extremo — o -32.768 que um MDE grava onde não tem dado, sem "
         "declará-lo, ou um único pixel errado — deixa os valores reais num trecho curto dela: o "
         "relevo sai de uma cor só, e a legenda anuncia um valor que não existe.",
         "Refaça com apply_raster_style sem min e max: o SIGMAI ignora os valores de preenchimento "
         "conhecidos e os picos isolados, e avisa. Ou declare o valor sem dado da camada, ou passe min e "
         "max que cubram os dados.",
         f"Percentis 2 e 98 dos pixels do quadro contra os limites da rampa; ao menos {RAMP_USED_MIN * 100:g} % "
         "da rampa em uso: decisão de projeto do SIGMAI",
         _check_raster_ramp_used),
    Rule("CART078", "dados", SEVERITY_ERROR,
         "Coordenadas cabem no sistema de referência", "Coordinates fit the declared reference system",
         "Coordenadas fora da área de uso do sistema declarado são erro de dado, não de mapa: graus "
         "importados como se fossem UTM levam os pontos para perto do polo, e o 0,0 que planilhas gravam "
         "quando falta a posição põe um registro no Golfo da Guiné. O mapa sai com a escala e o recorte "
         "errados, e nenhuma outra regra diz por quê.",
         "Corrija o dado: declare o sistema certo da camada (graus: EPSG:4674 ou EPSG:4326), troque "
         "latitude e longitude se estiverem invertidas, ou retire os registros sem coordenada (0,0) antes "
         "de compor.",
         f"Área de uso do sistema de referência no registro EPSG, com {AREA_OF_USE_MARGIN_DEGREES:g}° de "
         "folga; coordenadas entre -180 e 180 e -90 e 90 num sistema projetado; ponto em 0,0: decisão de projeto do "
         "SIGMAI; verificação: QGIS Documentation — QgsCoordinateReferenceSystem.bounds",
         _check_coordinates_plausible),
    Rule("CART079", "dados", SEVERITY_WARNING,
         "Recorte não é aberto por pontos isolados", "Extent is not stretched by isolated points",
         "Um registro com coordenada errada, longe dos demais, abre o recorte para caber nele: os outros "
         "pontos se amontoam num canto, e o mapa passa a ser o mapa do erro.",
         "Confira os pontos isolados (0,0, latitude e longitude trocadas, sinal trocado). Se são erro, "
         "retire-os ou corrija-os; se são dado, faça um mapa para cada região ou um inserto.",
         f"Diagonal de todos os pontos acima de {OUTLIER_SPREAD_RATIO:g} vezes a do núcleo (percentis 1 a 99), com "
         f"no máximo {OUTLIER_MAX_SHARE * 100:g} % (ou {OUTLIER_MAX_COUNT}) de pontos isolados: decisão de "
         "projeto do SIGMAI",
         _check_extent_outliers),
    Rule("CART080", "simbologia", SEVERITY_WARNING,
         "O mapa de calor mostra os lugares com pontos", "The heatmap shows the places that have points",
         "A rampa do mapa de calor vai até a densidade do foco mais cheio. Com um foco de milhares de "
         "registros, os lugares com poucos ficam abaixo do começo da rampa, transparentes: o mapa mostra "
         "o foco e esconde o resto.",
         "Passe max_value menor em apply_heatmap_style (o foco satura e o resto aparece) ou mostre um "
         "símbolo por local (count_points_by_site e apply_proportional_symbol_style).",
         f"Pontos em células do tamanho do raio; célula abaixo de {HEATMAP_VISIBLE_MIN * 100:g} % do máximo é "
         f"apagada; no máximo {HEATMAP_FAINT_PLACES_MAX * 100:g} % dos lugares apagados: decisão de projeto do SIGMAI",
         _check_heatmap_visibility),
    Rule("CART003", "escala", SEVERITY_ERROR,
         "Escala indicada", "Scale indicated",
         "Sem escala não é possível medir nada; a peça deixa de ser mapa e vira ilustração.",
         "Chame add_layout_scale_bar e acrescente a escala numérica como rótulo.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 14 (a escala numérica e a escala gráfica devem ser apresentadas sempre)",
         _check_scale_indication),
    Rule("CART005", "escala", SEVERITY_WARNING,
         "Escala numérica presente", "Numeric scale present",
         "A barra sobrevive ao redimensionamento, mas é a escala numérica que se cita no texto "
         "e que permite comparar com outras folhas.",
         "Acrescente um rótulo 'Escala 1:N'; compose_map faz isso automaticamente.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 14; IBGE (1999), Noções básicas de cartografia, seções 2.2.3–2.2.4 (escala numérica e gráfica)",
         _check_scale_text),
    Rule("CART022", "escala", SEVERITY_WARNING,
         "Barra de escala proporcional ao quadro", "Scale bar proportional to frame",
         "Uma barra ocupando menos de 15% do quadro não permite estimar distâncias a olho; "
         "acima de 45% ela compete com o mapa.",
         "Deixe o SIGMAI dimensionar a barra (scalebar_spec) em vez de fixar units_per_segment.",
         "Brewer (2016), Designing Better Maps — scale bar; faixa de 15 % a 45 % da largura do quadro (ou 45 mm): decisão de projeto do SIGMAI",
         _check_scalebar_proportion),
    Rule("CART074", "escala", SEVERITY_WARNING,
         "Números da barra de escala legíveis", "Scale bar labels do not overlap",
         "Numa barra com muitos segmentos curtos os números encostam uns nos outros e viram uma sequência "
         "ilegível ('25 0 255075100 km'), sobretudo em figuras de coluna de revista; o QGIS desenha assim "
         "mesmo, sem aviso.",
         "Reduza para 2 ou 3 segmentos sem o segmento à esquerda do zero, ou alongue cada segmento; "
         "compose_map já escolhe segmentos em que os números cabem.",
         "Brewer (2016), Designing Better Maps — scale bar; algarismo de 0,6 em e folga de 20 % entre rótulos: decisão de projeto do SIGMAI",
         _check_scalebar_labels),
    Rule("CART024", "escala", SEVERITY_ERROR,
         "Barra de escala válida para o CRS", "Scale bar valid for the map CRS",
         "Barra de escala sobre mapa em coordenadas geográficas mede uma distância que muda "
         "com a latitude; o número impresso está errado em quase toda a folha.",
         "Reprojete o mapa para um CRS projetado adequado (ex.: UTM da zona) antes de exportar.",
         "Snyder (1987), Map Projections: A Working Manual (USGS PP 1395) — o comprimento do grau de longitude varia com a latitude (p. 8 e Tabela 4); verificação: QGIS Documentation — Scale bar item and map units",
         _check_scalebar_geographic_crs),
    Rule("CART006", "orientacao", SEVERITY_WARNING,
         "Orientação indicada", "Orientation indicated",
         "Sem rosa dos ventos nem grade anotada, nada garante ao leitor que o norte está para cima.",
         "Chame add_layout_north_arrow ou habilite a grade com anotações.",
         "Brewer (2016) — map elements; IBGE (1999), seção 2.3.4 (norte verdadeiro, magnético e de quadrícula); exigir a indicação: decisão de projeto do SIGMAI",
         _check_north_indication),
    Rule("CART025", "orientacao", SEVERITY_WARNING,
         "Rosa dos ventos é símbolo, não texto", "North arrow is a symbol, not text",
         "Um rótulo de texto não gira com o mapa: basta rotacionar o quadro ou usar uma projeção "
         "com convergência meridiana para a indicação ficar errada. O QGIS traz símbolos de norte "
         "que acompanham o norte da grade automaticamente.",
         "Use add_layout_north_arrow com um SVG de norte e north_mode='grid'.",
         "Decisão de projeto do SIGMAI: um rótulo 'N' não gira com o quadro nem aponta uma direção; verificação: QGIS Documentation — Picture item, north arrow synchronisation",
         _check_north_is_symbol),
    Rule("CART007", "procedencia", SEVERITY_ERROR,
         "Fonte e autoria declaradas", "Source and authorship declared",
         "Mapa sem procedência não é citável nem auditável, e a autoria do mapa não se confunde "
         "com a autoria do software que o gerou.",
         "Preencha data_source e map_author; compose_map monta a linha de crédito.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 19 (citação de fonte e órgão produtor); Brewer (2016) — map elements; SIGMAI — política de autoria de mapas (docs/MAP_AUTHORSHIP_POLICY.md)",
         _check_source_credit),
    Rule("CART008", "procedencia", SEVERITY_ERROR,
         "Sistema de referência declarado", "Reference system declared",
         "Coordenadas sem datum e projeção declarados não são reprodutíveis; a mesma coordenada "
         "cai em lugares diferentes em SIRGAS 2000 e em Córrego Alegre.",
         "Acrescente um rótulo com o CRS; compose_map insere automaticamente.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), arts. 15 e 21 (referenciais e Sistema Geodésico Brasileiro); IBGE, Resolução PR nº 1/2015 (SIRGAS2000 como referencial único)",
         _check_crs_declared),
    Rule("CART009", "procedencia", SEVERITY_WARNING,
         "Data de elaboração presente", "Production date present",
         "Sem data não se sabe a que safra de dados o mapa corresponde.",
         "Passe production_date ou deixe compose_map usar a data corrente.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 19 (obrigatória a citação do ano de edição e das datas de campo e compilação)",
         _check_date),
    Rule("CART010", "grade", SEVERITY_WARNING,
         "Grade de coordenadas habilitada", "Coordinate grid enabled",
         "A grade é o que permite localizar uma feição no terreno a partir do papel.",
         "Chame add_layout_grid com um intervalo calculado.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 17 (quadriculação quilométrica ou sexagesimal); verificação: QGIS Documentation — Map grids",
         _check_graticule_enabled),
    Rule("CART026", "grade", SEVERITY_ERROR,
         "Intervalo da grade maior que zero", "Grid interval greater than zero",
         "O intervalo padrão do QGIS é 0.0. Habilitar a grade sem definir intervalo produz "
         "uma grade que existe nos metadados e não aparece no papel — e o orquestrador "
         "ainda a reporta como criada.",
         "Use graticule_interval() para derivar o intervalo da extensão antes de habilitar a grade.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 17; verificação: QGIS API QgsLayoutItemMapGrid::setIntervalX/setIntervalY (intervalo zero não desenha nada)",
         _check_graticule_interval),
    Rule("CART027", "grade", SEVERITY_ADVICE,
         "Grade anotada", "Grid annotated",
         "Linhas sem valores de coordenada dividem a folha mas não localizam nada.",
         "Ative show_annotations em add_layout_grid.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 17 (coordenadas dos cantos da folha); verificação: QGIS Documentation — Grid annotations",
         _check_graticule_annotations),
    Rule("CART067", "elementos", SEVERITY_WARNING,
         "O inserto localiza", "Inset locates the frame",
         "O inserto existe para responder 'onde fica'. Se ele corta a camada de contexto ao meio, ou "
         "se o recorte principal cai fora dele, o leitor vê um segundo mapa solto, não um localizador.",
         "Passe inset_layer_ids com o limite (estado, município, bacia) inteiro; compose_map ajusta o inserto "
         "à extensão inteira dessa camada.",
         "Decreto nº 89.817/1984 (Normas Técnicas da Cartografia Nacional), art. 18 (diagrama da situação da folha no Estado, na região ou no país); Brewer (2016) — locator maps; verificação: QGIS Documentation — Overview frames",
         _check_inset_locates),
    Rule("CART040", "geometria", SEVERITY_ERROR,
         "Itens dentro da página", "Items inside the page",
         "Item posicionado fora da página simplesmente não é impresso, e o layout parece "
         "correto na estrutura de dados.",
         "Recalcule as posições a partir do PageSpec em vez de usar milímetros fixos.",
         "Decisão de projeto do SIGMAI: item fora da página não é exportado; verificação: QGIS Documentation — Layout page properties",
         _check_items_inside_page),
    Rule("CART041", "geometria", SEVERITY_WARNING,
         "Itens dentro das margens", "Items inside the margins",
         "A faixa de margem é a primeira a ser cortada por impressoras e encadernação.",
         "Reposicione os itens dentro da área útil do PageSpec.",
         "Decisão de projeto do SIGMAI: margem mínima declarada pelo template (10 mm) ou pela receita da composição",
         _check_items_inside_margins),
    Rule("CART042", "geometria", SEVERITY_WARNING,
         "Sem sobreposição entre itens", "No overlapping items",
         "Itens sobrepostos escondem informação de forma imprevisível conforme a ordem de desenho.",
         "Use o solucionador de grade do SIGMAI, que aloca faixas exclusivas para cada papel.",
         "Brewer (2016), Designing Better Maps — visual hierarchy; anel de 3 mm com menos de 3 % de tinta: decisão de projeto do SIGMAI",
         _check_no_overlaps),
    Rule("CART043", "geometria", SEVERITY_ADVICE,
         "O mapa domina a página", "Map dominates the page",
         "Se o quadro do mapa ocupa menos de um terço da área útil, os elementos de apoio "
         "viraram o assunto principal.",
         "Reduza a coluna da legenda ou escolha um template com quadro maior.",
         "Brewer (2016), Designing Better Maps — figure/ground and layout balance",
         _check_map_dominance),
    Rule("CART068", "elementos", SEVERITY_WARNING,
         "Rótulos colocados", "Labels placed",
         "O motor de rótulos do QGIS descarta em silêncio um rótulo que colide com outro ou cruza a "
         "moldura. O mapa sai 'bem-sucedido' com feições sem nome, e ninguém é avisado.",
         "Reduza label_font_size, aumente o quadro ou a margem (margin_percent) para as feições cortadas "
         "pela moldura, ou rotule só a camada de assunto (label_layer_id).",
         "Decisão de projeto do SIGMAI: rótulo pedido e não colocado é informação perdida em silêncio; verificação: QGIS API QgsLabelingEngineSettings::CollectUnplacedLabels, QgsLabelingResults::allLabels",
         _check_labels_placed),
    Rule("CART069", "dados", SEVERITY_WARNING,
         "O quadro é ocupado pelos dados", "Frame is occupied by data",
         "Um quadro em que mais da metade é papel em branco não mostra contexto nem assunto: ou falta "
         "a camada vizinha (malha do estado ao lado, oceano), ou a extensão está aberta demais.",
         "Acrescente camadas de contexto para o vazio (inclusive uma camada de oceano/linha de costa se for "
         "mar) ou feche o recorte com subject_layer_id e margin_percent.",
         "Brewer (2016), Designing Better Maps — figure/ground; faixa com menos de 5 % de cobertura (2 % de tinta) na grade 3x3: decisão de projeto do SIGMAI",
         _check_frame_coverage),
    Rule("CART070", "simbologia", SEVERITY_WARNING,
         "Cores distinguíveis por daltônicos", "Colours distinguishable under colour-vision deficiency",
         "Cerca de 8% dos homens de ascendência europeia têm deficiência vermelho-verde; um par "
         "verde/laranja que o autor distingue pode ser idêntico para esse leitor.",
         "Use a paleta de Okabe & Ito (apply_style='all' aplica), ou troque uma das cores do par acusado "
         "por outra de luminosidade bem diferente; padrões de preenchimento também resolvem. Com classes "
         "demais nenhuma paleta separa todas: apply_categorized_style com limit=8 deixa as oito mais "
         "frequentes, com cores de Okabe & Ito, e reúne o resto em 'Outros'.",
         "Machado, Oliveira & Fernandes (2009), IEEE TVCG 15(6), severidade 1,0; Robertson (1977), CIE 1976 L*a*b* e ΔE*ab; Okabe & Ito (2008), Color Universal Design; limiar ΔE*ab < 15: decisão de projeto do SIGMAI calibrada nos pares clássicos",
         _check_colour_vision),
    Rule("CART073", "simbologia", SEVERITY_ERROR,
         "Figura em tons de cinza sem cor", "Greyscale figure has no colour",
         "Periódicos imprimem em tons de cinza e cobram a cor impressa; uma figura pedida em cinza que "
         "sai com cor perde, no papel, a distinção entre cores de mesma luminosidade — e quem pediu "
         "cinza não vê o problema na tela.",
         "Componha com colour_mode='greyscale': a paleta, o inserto e a grade saem em cinza, e as "
         "classificações e rasters já estilizados são convertidos para cinza mantendo as classes.",
         "Transactions in GIS, Author Guidelines (gráficos de linha preferencialmente em preto e branco; cor impressa cobrada por figura); croma ≥ 20 em mais de 0,5 % da tinta: decisão de projeto do SIGMAI",
         _check_greyscale),
    Rule("CART071", "tipografia", SEVERITY_WARNING,
         "Fontes legíveis na largura final impressa", "Fonts legible at the final print width",
         "Uma página A4 reduzida a uma coluna de revista (85 mm) encolhe as fontes a 40% do corpo: os 7 pt "
         "que passavam na página viram 3 pt no papel.",
         "Passe print_width_mm (ou figure_width_mm/journal_column em compose_map) e componha a figura já "
         "na largura final, com fontes de pelo menos 6 pt nessa largura.",
         "PLOS ONE, Figure requirements (texto de 8 a 12 pt na largura final); Rodriguésia, Normas para autores (7 cm coluna simples, 15 cm página, 300 dpi); mínimo de 6 pt: decisão de projeto do SIGMAI",
         _check_fonts_at_print_width),
    Rule("CART044", "tipografia", SEVERITY_WARNING,
         "Tamanho mínimo de fonte", "Minimum font size",
         "Texto abaixo de 6 pt desaparece na impressão e reprova em qualquer revisão editorial.",
         "Aumente a fonte ou reduza a quantidade de texto no layout.",
         "Decisão de projeto do SIGMAI: mínimo de 6 pt, abaixo da faixa que os periódicos exigem na largura final (PLOS ONE, Figure requirements: 8 a 12 pt)",
         _check_font_sizes),
    Rule("CART045", "tipografia", SEVERITY_ADVICE,
         "Hierarquia tipográfica", "Typographic hierarchy",
         "Título e subtítulo do mesmo tamanho eliminam a ordem de leitura.",
         "Garanta que o título tenha corpo maior que o subtítulo.",
         "Brewer (2016), Designing Better Maps — type hierarchy",
         _check_title_hierarchy),
    Rule("CART060", "projecao", SEVERITY_WARNING,
         "CRS projetado para medidas métricas", "Projected CRS for metric measurement",
         "Em coordenadas geográficas, um grau não tem comprimento constante; áreas e "
         "distâncias calculadas sobre graus estão erradas.",
         "Reprojete para o UTM da zona ou para uma projeção equivalente à finalidade do mapa; num mapa "
         "continental ou mundial, map_crs=\"auto\" escolhe uma de áreas iguais.",
         "Snyder (1987), Map Projections: A Working Manual (USGS PP 1395); IBGE (1999), seção 2.3.3.5 (UTM no mapeamento sistemático)",
         _check_projected_crs),
    Rule("CART066", "escala", SEVERITY_ERROR,
         "Painéis comparáveis anunciam suas escalas", "Comparison panels declare their scales",
         "Dois quadros de mapa na mesma folha convidam à comparação visual de tamanhos. Em escalas "
         "diferentes e com uma indicação de escala única, essa comparação é falsa e o leitor não tem "
         "como perceber.",
         "Iguale os painéis com comparison_same_scale=true, ou deixe cada legenda de painel anunciar "
         "a própria escala — compose_map faz isso automaticamente.",
         "Brewer (2016), Designing Better Maps — multiple map frames and comparability",
         _check_comparison_panels),
    Rule("CART081", "simbologia", SEVERITY_WARNING,
         "Painéis comparáveis usam a mesma régua de cor e tamanho", "Comparison panels share colour and size scales",
         "Painéis lado a lado convidam o leitor a comparar cor com cor e tamanho com tamanho. Se cada painel "
         "estica a sua rampa até o próprio máximo — o padrão do mapa de calor, das classes e do símbolo "
         "proporcional —, a mesma cor ou o mesmo círculo valem números diferentes, e a comparação engana.",
         "Use a mesma régua nos dois painéis: apply_proportional_symbol_style com min_value e max_value "
         "comuns, apply_graduated_style com as mesmas classes, apply_heatmap_style com o mesmo max_value e o "
         "mesmo raio — ou um símbolo por local (count_points_by_site com scale), que se compara melhor que "
         "densidade.",
         "Brewer (2016) — multiple map frames and comparability; Slocum et al. (2009) — comparing maps with "
         "the same classification; mesma variável em dois ou mais painéis: decisão de projeto do SIGMAI",
         _check_comparable_value_scales),
    Rule("CART064", "projecao", SEVERITY_WARNING,
         "Projeção adequada à extensão", "Projection suits the extent",
         "Uma zona UTM tem 6° de largura e foi feita para o erro de escala não passar de cerca de "
         "1/1000 dentro dela. Esticada sobre um estado inteiro, o erro cresce com a distância ao "
         "meridiano central e as coordenadas saem da faixa válida da zona — a barra de escala deixa "
         "de valer para parte da folha.",
         "Escolha uma projeção cônica ou a Policônica do Brasil (EPSG:5880) para recortes estaduais; "
         "compose_map faz isso sozinho quando auto_projected_crs está ligado.",
         "Snyder (1987), Map Projections: A Working Manual (USGS PP 1395) — Transverse Mercator; IBGE (1999), seção 2.3.3.5 (fusos de 6°); faixa de E de 100.000 a 900.000 m e limites de 4,5° de longitude e 12° de latitude: decisão de projeto do SIGMAI",
         _check_crs_suits_extent),
    Rule("CART061", "dados", SEVERITY_ERROR,
         "A extensão contém os dados", "Extent contains the data",
         "Extensão que corta os dados produz um mapa que responde a uma pergunta diferente da pedida.",
         "Use fit_extent_to_frame a partir da extensão combinada das camadas visíveis.",
         "Decisão de projeto do SIGMAI: o quadro tem de conter os dados pedidos; verificação: QGIS API QgsLayoutItemMap::setExtent / zoomToExtent",
         _check_extent_contains_data),
    Rule("CART062", "dados", SEVERITY_ERROR,
         "O quadro do mapa não está em branco", "Map frame is not blank",
         "Exportação bem-sucedida com quadro vazio é o modo de falha mais perigoso: "
         "todos os códigos de retorno dizem sucesso.",
         "Verifique visibilidade das camadas, extensão e compatibilidade de CRS.",
         "Decisão de projeto do SIGMAI: menos de 0,5 % de tinta no quadro exportado é quadro em branco; verificação: amostragem do PNG",
         _check_map_not_blank),
    Rule("CART063", "dados", SEVERITY_ERROR,
         "Arquivo de saída gravado", "Output file written",
         "Sem arquivo no disco não há entrega, por mais que o comando tenha retornado ok.",
         "Confira permissões da pasta e o parâmetro de formato.",
         "Decisão de projeto do SIGMAI: exportação sem arquivo não é resultado; verificação: QGIS API QgsLayoutExporter results",
         _check_output_written),
)

RULES_BY_ID: dict[str, Rule] = {rule.id: rule for rule in RULES}


# ---------------------------------------------------------------------------
# Avaliação
# ---------------------------------------------------------------------------

def evaluate(observation: dict[str, Any], skip_rules: tuple[str, ...] = ()) -> dict[str, Any]:
    """Roda o regulamento contra uma observação e devolve um laudo explicável."""
    results: list[dict[str, Any]] = []
    penalty = 0.0
    counts = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 0, SEVERITY_ADVICE: 0}

    for rule in RULES:
        if rule.id in skip_rules:
            continue
        try:
            outcome = rule.check(observation)
        except Exception as exc:  # uma regra quebrada não pode derrubar o laudo
            outcome = CheckOutcome(STATUS_SKIP, f"Regra não pôde ser avaliada: {type(exc).__name__}: {exc}")
        entry = {
            "id": rule.id,
            "category": rule.category,
            "severity": rule.severity,
            "status": outcome.status,
            "title_pt": rule.title_pt,
            "title_en": rule.title_en,
            "detail_pt": outcome.detail_pt,
            "evidence": outcome.evidence,
        }
        if outcome.status == STATUS_FAIL:
            entry["rationale_pt"] = rule.rationale_pt
            entry["fix_pt"] = rule.fix_pt
            entry["reference"] = rule.reference
            penalty += SEVERITY_PENALTY[rule.severity]
            counts[rule.severity] += 1
        results.append(entry)

    score = max(0.0, 100.0 - penalty)
    grade, label = _grade(score, counts)
    failures = [entry for entry in results if entry["status"] == STATUS_FAIL]
    order = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_ADVICE: 2}
    failures.sort(key=lambda entry: (order[entry["severity"]], entry["id"]))

    return {
        "score": round(score, 1),
        "grade": grade,
        "label": label,
        "counts": {
            "errors": counts[SEVERITY_ERROR],
            "warnings": counts[SEVERITY_WARNING],
            "advice": counts[SEVERITY_ADVICE],
            "passed": sum(1 for entry in results if entry["status"] == STATUS_PASSED),
            "skipped": sum(1 for entry in results if entry["status"] == STATUS_SKIP),
        },
        "blocking_issues": [entry for entry in failures if entry["severity"] == SEVERITY_ERROR],
        "next_actions": [
            {"rule": entry["id"], "severity": entry["severity"], "problem": entry["detail_pt"], "fix": entry["fix_pt"]}
            for entry in failures[:8]
        ],
        "results": results,
    }


def _grade(score: float, counts: dict[str, int]) -> tuple[str, str]:
    if counts[SEVERITY_ERROR] == 0 and score >= 92:
        return "A", "Mapa publicável"
    if counts[SEVERITY_ERROR] == 0 and score >= 80:
        return "B", "Mapa técnico utilizável, com ajustes menores pendentes"
    if counts[SEVERITY_ERROR] <= 1 and score >= 62:
        return "C", "Mapa incompleto: falta elemento cartográfico obrigatório"
    if score >= 40:
        return "D", "Mapa defeituoso: várias exigências cartográficas não atendidas"
    return "E", "Mapa inválido"


def rulebook_manifest() -> dict[str, Any]:
    """O regulamento como dado, para o agente de IA consultar antes de compor."""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for rule in RULES:
        by_category.setdefault(rule.category, []).append(rule.to_dict())
    return {
        "version": "1.0",
        "rule_count": len(RULES),
        "severity_penalty": SEVERITY_PENALTY,
        "grading": {
            "A": "sem erros e pontuação >= 92",
            "B": "sem erros e pontuação >= 80",
            "C": "no máximo 1 erro e pontuação >= 62",
            "D": "pontuação >= 40",
            "E": "abaixo disso",
        },
        "thresholds": {
            "min_print_font_pt": MIN_PRINT_FONT_PT,
            "scalebar_frame_fraction": [SCALEBAR_MIN_FRACTION, SCALEBAR_MAX_FRACTION],
            "map_dominance_min": MAP_DOMINANCE_MIN,
            "frame_band_empty_max": FRAME_BAND_EMPTY_MAX,
            "frame_band_empty_data_ink": FRAME_BAND_EMPTY_DATA_INK,
            "overlay_max_surroundings_ink": OVERLAY_MAX_SURROUNDINGS_INK,
            "colour_vision_delta_e_min": _colour_vision_threshold(),
            "legend_overflow_tolerance_mm": LEGEND_OVERFLOW_TOLERANCE_MM,
            "inset_min_coverage": INSET_MIN_COVERAGE,
            "greyscale_chroma_min": GREYSCALE_CHROMA_MIN,
            "greyscale_max_chromatic_fraction": GREYSCALE_MAX_CHROMATIC_FRACTION,
            "covered_visible_max": COVERED_VISIBLE_MAX,
            "covered_visible_share": COVERED_VISIBLE_SHARE,
            "subject_visible_min": SUBJECT_VISIBLE_MIN,
            "point_saturation": SATURATION,
            "point_stacking_hidden_max": STACKING_HIDDEN_MAX,
            "point_stacking_min_points": STACKING_MIN_POINTS,
            "raster_ramp_used_min": RAMP_USED_MIN,
            "area_of_use_margin_degrees": AREA_OF_USE_MARGIN_DEGREES,
            "outlier_spread_ratio": OUTLIER_SPREAD_RATIO,
            "outlier_max_share": OUTLIER_MAX_SHARE,
            "outlier_max_count": OUTLIER_MAX_COUNT,
            "heatmap_visible_min": HEATMAP_VISIBLE_MIN,
            "heatmap_faint_places_max": HEATMAP_FAINT_PLACES_MAX,
            "scalebar_digit_em": _scalebar_constant("SCALEBAR_DIGIT_EM"),
            "scalebar_label_clearance": _scalebar_constant("SCALEBAR_LABEL_CLEARANCE"),
        },
        # Os limiares são parâmetros declarados, não medidos com leitores;
        # docs/experiments/2026-09-19_sensibilidade_limiares/ mostra em que
        # faixa de cada um as decisões sobre os mapas de teste não mudam.
        "thresholds_provenance": "declared design parameters; sensitivity analysis in docs/experiments/2026-09-19_sensibilidade_limiares/",
        "categories": by_category,
    }


def _scalebar_constant(name: str) -> float:
    from . import scaling

    return float(getattr(scaling, name))


def _colour_vision_threshold() -> float:
    from .vision import CONFUSABLE_DELTA_E

    return CONFUSABLE_DELTA_E
