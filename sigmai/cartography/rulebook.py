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

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_ADVICE = "advice"

#: Peso de cada severidade na pontuação de 0 a 100.
SEVERITY_PENALTY = {SEVERITY_ERROR: 15.0, SEVERITY_WARNING: 5.0, SEVERITY_ADVICE: 1.5}

STATUS_PASS = "pass"
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
    return CheckOutcome(STATUS_PASS, detail, evidence)


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
    return [item for item in _items(observation) if item.get("type") == "label"]


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
    if not extra:
        return _pass("A legenda não lista camadas ausentes do mapa.")
    return _fail(
        "A legenda lista " + ", ".join(repr(name) for name in extra) + ", que não aparece(m) no mapa.",
        phantom_layers=extra,
    )


def _check_scale_indication(observation: dict[str, Any]) -> CheckOutcome:
    has_bar = bool(observation.get("scalebar", {}).get("item_id"))
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
    if not collisions:
        return _pass("Nenhuma sobreposição entre itens do layout.")
    described = ", ".join(f"{item['a']}/{item['b']}" for item in collisions)
    return _fail(f"Itens sobrepostos: {described}.", collisions=collisions)


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


def _check_map_not_blank(observation: dict[str, Any]) -> CheckOutcome:
    map_info = _map(observation)
    ink = map_info.get("rendered_ink_fraction")
    if ink is None:
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
         "QGIS Documentation — Layout Manager: map composition elements",
         _check_title),
    Rule("CART002", "elementos", SEVERITY_ERROR,
         "Legenda presente", "Legend present",
         "Com mais de uma camada visível, sem legenda o leitor não decodifica os símbolos.",
         "Chame add_layout_legend informando linked_map_item_id.",
         "QGIS Documentation — Layout legend item",
         _check_legend),
    Rule("CART020", "elementos", SEVERITY_ERROR,
         "A legenda explica todas as camadas visíveis", "Legend covers every visible layer",
         "Feição desenhada sem entrada correspondente na legenda é ruído: o leitor vê e não sabe o que é. "
         "É a falha mais comum em mapas gerados automaticamente, porque a legenda costuma ser "
         "montada com a camada principal apenas.",
         "Passe legend_layers com TODAS as camadas do mapa, ou deixe compose_map derivá-las do quadro.",
         "Slocum et al., Thematic Cartography and Geovisualization — legend design",
         _check_legend_covers_visible_layers),
    Rule("CART021", "elementos", SEVERITY_WARNING,
         "A legenda não lista camadas ausentes", "Legend lists no phantom layers",
         "Entrada de legenda sem contrapartida no mapa faz o leitor procurar algo que não existe.",
         "Ative filter_to_map_layers ou remova as camadas extras de legend_layers.",
         "QGIS Documentation — Legend: filter by map content",
         _check_legend_has_no_phantoms),
    Rule("CART003", "escala", SEVERITY_ERROR,
         "Escala indicada", "Scale indicated",
         "Sem escala não é possível medir nada; a peça deixa de ser mapa e vira ilustração.",
         "Chame add_layout_scale_bar e acrescente a escala numérica como rótulo.",
         "ABNT NBR 6027 / convenção cartográfica para documentos técnicos",
         _check_scale_indication),
    Rule("CART005", "escala", SEVERITY_WARNING,
         "Escala numérica presente", "Numeric scale present",
         "A barra sobrevive ao redimensionamento, mas é a escala numérica que se cita no texto "
         "e que permite comparar com outras folhas.",
         "Acrescente um rótulo 'Escala 1:N'; compose_map faz isso automaticamente.",
         "Convenção de mapeamento sistemático",
         _check_scale_text),
    Rule("CART022", "escala", SEVERITY_WARNING,
         "Barra de escala proporcional ao quadro", "Scale bar proportional to frame",
         "Uma barra ocupando menos de 15% do quadro não permite estimar distâncias a olho; "
         "acima de 45% ela compete com o mapa.",
         "Deixe o SIGMAI dimensionar a barra (scalebar_spec) em vez de fixar units_per_segment.",
         "Brewer, Designing Better Maps — scale bar proportion",
         _check_scalebar_proportion),
    Rule("CART024", "escala", SEVERITY_ERROR,
         "Barra de escala válida para o CRS", "Scale bar valid for the map CRS",
         "Barra de escala sobre mapa em coordenadas geográficas mede uma distância que muda "
         "com a latitude; o número impresso está errado em quase toda a folha.",
         "Reprojete o mapa para um CRS projetado adequado (ex.: UTM da zona) antes de exportar.",
         "QGIS Documentation — Scale bar item and map units",
         _check_scalebar_geographic_crs),
    Rule("CART006", "orientacao", SEVERITY_WARNING,
         "Orientação indicada", "Orientation indicated",
         "Sem rosa dos ventos nem grade anotada, nada garante ao leitor que o norte está para cima.",
         "Chame add_layout_north_arrow ou habilite a grade com anotações.",
         "QGIS Documentation — North arrow item",
         _check_north_indication),
    Rule("CART025", "orientacao", SEVERITY_WARNING,
         "Rosa dos ventos é símbolo, não texto", "North arrow is a symbol, not text",
         "Um rótulo de texto não gira com o mapa: basta rotacionar o quadro ou usar uma projeção "
         "com convergência meridiana para a indicação ficar errada. O QGIS traz símbolos de norte "
         "que acompanham o norte da grade automaticamente.",
         "Use add_layout_north_arrow com um SVG de norte e north_mode='grid'.",
         "QGIS Documentation — Picture item, north arrow synchronisation",
         _check_north_is_symbol),
    Rule("CART007", "procedencia", SEVERITY_ERROR,
         "Fonte e autoria declaradas", "Source and authorship declared",
         "Mapa sem procedência não é citável nem auditável, e a autoria do mapa não se confunde "
         "com a autoria do software que o gerou.",
         "Preencha data_source e map_author; compose_map monta a linha de crédito.",
         "SIGMAI — Política de autoria de mapas (docs/MAP_AUTHORSHIP_POLICY.md)",
         _check_source_credit),
    Rule("CART008", "procedencia", SEVERITY_ERROR,
         "Sistema de referência declarado", "Reference system declared",
         "Coordenadas sem datum e projeção declarados não são reprodutíveis; a mesma coordenada "
         "cai em lugares diferentes em SIRGAS 2000 e em Córrego Alegre.",
         "Acrescente um rótulo com o CRS; compose_map insere automaticamente.",
         "ABNT NBR 13133 / IBGE — Especificações para representação cartográfica",
         _check_crs_declared),
    Rule("CART009", "procedencia", SEVERITY_WARNING,
         "Data de elaboração presente", "Production date present",
         "Sem data não se sabe a que safra de dados o mapa corresponde.",
         "Passe production_date ou deixe compose_map usar a data corrente.",
         "Convenção de documentação técnica",
         _check_date),
    Rule("CART010", "grade", SEVERITY_WARNING,
         "Grade de coordenadas habilitada", "Coordinate grid enabled",
         "A grade é o que permite localizar uma feição no terreno a partir do papel.",
         "Chame add_layout_grid com um intervalo calculado.",
         "QGIS Documentation — Map grids",
         _check_graticule_enabled),
    Rule("CART026", "grade", SEVERITY_ERROR,
         "Intervalo da grade maior que zero", "Grid interval greater than zero",
         "O intervalo padrão do QGIS é 0.0. Habilitar a grade sem definir intervalo produz "
         "uma grade que existe nos metadados e não aparece no papel — e o orquestrador "
         "ainda a reporta como criada.",
         "Use graticule_interval() para derivar o intervalo da extensão antes de habilitar a grade.",
         "QGIS API — QgsLayoutItemMapGrid::setIntervalX/setIntervalY",
         _check_graticule_interval),
    Rule("CART027", "grade", SEVERITY_ADVICE,
         "Grade anotada", "Grid annotated",
         "Linhas sem valores de coordenada dividem a folha mas não localizam nada.",
         "Ative show_annotations em add_layout_grid.",
         "QGIS Documentation — Grid annotations",
         _check_graticule_annotations),
    Rule("CART067", "elementos", SEVERITY_WARNING,
         "O inserto localiza", "Inset locates the frame",
         "O inserto existe para responder 'onde fica'. Se ele corta a camada de contexto ao meio, ou "
         "se o recorte principal cai fora dele, o leitor vê um segundo mapa solto, não um localizador.",
         "Passe inset_layer_ids com o limite (estado, município, bacia) inteiro; compose_map ajusta o inserto "
         "à extensão inteira dessa camada.",
         "QGIS Documentation — Overview frames; Brewer, Designing Better Maps — locator maps",
         _check_inset_locates),
    Rule("CART040", "geometria", SEVERITY_ERROR,
         "Itens dentro da página", "Items inside the page",
         "Item posicionado fora da página simplesmente não é impresso, e o layout parece "
         "correto na estrutura de dados.",
         "Recalcule as posições a partir do PageSpec em vez de usar milímetros fixos.",
         "QGIS Documentation — Layout page properties",
         _check_items_inside_page),
    Rule("CART041", "geometria", SEVERITY_WARNING,
         "Itens dentro das margens", "Items inside the margins",
         "A faixa de margem é a primeira a ser cortada por impressoras e encadernação.",
         "Reposicione os itens dentro da área útil do PageSpec.",
         "Boas práticas de preparação para impressão",
         _check_items_inside_margins),
    Rule("CART042", "geometria", SEVERITY_WARNING,
         "Sem sobreposição entre itens", "No overlapping items",
         "Itens sobrepostos escondem informação de forma imprevisível conforme a ordem de desenho.",
         "Use o solucionador de grade do SIGMAI, que aloca faixas exclusivas para cada papel.",
         "Brewer, Designing Better Maps — visual hierarchy",
         _check_no_overlaps),
    Rule("CART043", "geometria", SEVERITY_ADVICE,
         "O mapa domina a página", "Map dominates the page",
         "Se o quadro do mapa ocupa menos de um terço da área útil, os elementos de apoio "
         "viraram o assunto principal.",
         "Reduza a coluna da legenda ou escolha um template com quadro maior.",
         "Brewer, Designing Better Maps — figure/ground and layout balance",
         _check_map_dominance),
    Rule("CART044", "tipografia", SEVERITY_WARNING,
         "Tamanho mínimo de fonte", "Minimum font size",
         "Texto abaixo de 6 pt desaparece na impressão e reprova em qualquer revisão editorial.",
         "Aumente a fonte ou reduza a quantidade de texto no layout.",
         "Boas práticas tipográficas para impressão técnica",
         _check_font_sizes),
    Rule("CART045", "tipografia", SEVERITY_ADVICE,
         "Hierarquia tipográfica", "Typographic hierarchy",
         "Título e subtítulo do mesmo tamanho eliminam a ordem de leitura.",
         "Garanta que o título tenha corpo maior que o subtítulo.",
         "Brewer, Designing Better Maps — type hierarchy",
         _check_title_hierarchy),
    Rule("CART060", "projecao", SEVERITY_WARNING,
         "CRS projetado para medidas métricas", "Projected CRS for metric measurement",
         "Em coordenadas geográficas, um grau não tem comprimento constante; áreas e "
         "distâncias calculadas sobre graus estão erradas.",
         "Reprojete para o UTM da zona ou para uma projeção equivalente à finalidade do mapa.",
         "Snyder, Map Projections: A Working Manual (USGS PP 1395)",
         _check_projected_crs),
    Rule("CART066", "escala", SEVERITY_ERROR,
         "Painéis comparáveis anunciam suas escalas", "Comparison panels declare their scales",
         "Dois quadros de mapa na mesma folha convidam à comparação visual de tamanhos. Em escalas "
         "diferentes e com uma indicação de escala única, essa comparação é falsa e o leitor não tem "
         "como perceber.",
         "Iguale os painéis com comparison_same_scale=true, ou deixe cada legenda de painel anunciar "
         "a própria escala — compose_map faz isso automaticamente.",
         "Brewer, Designing Better Maps — multiple map frames and comparability",
         _check_comparison_panels),
    Rule("CART064", "projecao", SEVERITY_WARNING,
         "Projeção adequada à extensão", "Projection suits the extent",
         "Uma zona UTM tem 6° de largura e só mantém o fator de escala dentro de 1/1000 perto do "
         "meridiano central. Esticada sobre um estado inteiro, a distorção nas bordas passa de meio "
         "por cento e as coordenadas saem da faixa válida da zona — a barra de escala deixa de valer "
         "para parte da folha.",
         "Escolha uma projeção cônica ou a Policônica do Brasil (EPSG:5880) para recortes estaduais; "
         "compose_map faz isso sozinho quando auto_projected_crs está ligado.",
         "Snyder, Map Projections: A Working Manual (USGS PP 1395) — Transverse Mercator",
         _check_crs_suits_extent),
    Rule("CART061", "dados", SEVERITY_ERROR,
         "A extensão contém os dados", "Extent contains the data",
         "Extensão que corta os dados produz um mapa que responde a uma pergunta diferente da pedida.",
         "Use fit_extent_to_frame a partir da extensão combinada das camadas visíveis.",
         "QGIS API — QgsLayoutItemMap::setExtent / zoomToExtent",
         _check_extent_contains_data),
    Rule("CART062", "dados", SEVERITY_ERROR,
         "O quadro do mapa não está em branco", "Map frame is not blank",
         "Exportação bem-sucedida com quadro vazio é o modo de falha mais perigoso: "
         "todos os códigos de retorno dizem sucesso.",
         "Verifique visibilidade das camadas, extensão e compatibilidade de CRS.",
         "SIGMAI — verificação visual do raster exportado",
         _check_map_not_blank),
    Rule("CART063", "dados", SEVERITY_ERROR,
         "Arquivo de saída gravado", "Output file written",
         "Sem arquivo no disco não há entrega, por mais que o comando tenha retornado ok.",
         "Confira permissões da pasta e o parâmetro de formato.",
         "QGIS API — QgsLayoutExporter results",
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
            "passed": sum(1 for entry in results if entry["status"] == STATUS_PASS),
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
        },
        "categories": by_category,
    }
