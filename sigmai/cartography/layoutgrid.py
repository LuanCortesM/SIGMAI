"""Solucionador de layout: distribui os papéis cartográficos numa página.

Os templates do SIGMAI 0.1.1 eram tabelas de milímetros absolutos escritas à
mão para uma única página A4 em paisagem. Trocar para A3, retrato ou um formato
customizado colocava a legenda fora da folha sem nenhum aviso, porque nada no
código sabia onde a página terminava.

Aqui o template descreve *proporções e prioridades*; o solucionador recebe um
``PageSpec`` e devolve retângulos em milímetros que, por construção, cabem na
área útil. O arranjo muda conforme a razão de aspecto da página: página larga
ganha uma coluna lateral de apoio, página alta ganha uma faixa inferior — é a
mesma decisão que um cartógrafo toma ao escolher onde pôr a legenda.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .pagespec import PageSpec, resolve_page


@dataclass(frozen=True)
class Rect:
    """Retângulo em milímetros, origem no canto superior esquerdo da página."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0

    def inset(self, amount: float) -> "Rect":
        return Rect(self.x + amount, self.y + amount, max(0.0, self.width - 2 * amount), max(0.0, self.height - 2 * amount))

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
        }


#: Cada template define proporções, não milímetros. ``side_column_fraction`` é a
#: largura da coluna de apoio como fração da área útil; ``title_fraction`` e
#: companhia são frações da altura da área útil.
TEMPLATES: dict[str, dict[str, Any]] = {
    "cientifico": {
        "description": "Mapa técnico para dissertação e artigo: título sóbrio, coluna de apoio à direita, rodapé de procedência.",
        "title_fraction": 0.058,
        "subtitle_fraction": 0.034,
        "footer_fraction": 0.048,
        "side_column_fraction": 0.24,
        "gutter_mm": 4.0,
        "title_font_pt": 15.0,
        "subtitle_font_pt": 9.5,
        "footer_font_pt": 7.0,
        "legend_font_pt": 8.0,
        "scale_text_font_pt": 8.5,
    },
    "publicacao": {
        "description": "Máximo de área de mapa; apoio compacto. Para figuras de artigo em coluna única.",
        "title_fraction": 0.050,
        "subtitle_fraction": 0.028,
        "footer_fraction": 0.042,
        "side_column_fraction": 0.20,
        "gutter_mm": 3.5,
        "title_font_pt": 13.0,
        "subtitle_font_pt": 8.5,
        "footer_font_pt": 6.5,
        "legend_font_pt": 7.5,
        "scale_text_font_pt": 8.0,
    },
    "relatorio_ambiental": {
        "description": "Relatório técnico: rodapé generoso para fonte, responsável técnico e organização.",
        "title_fraction": 0.062,
        "subtitle_fraction": 0.036,
        "footer_fraction": 0.070,
        "side_column_fraction": 0.26,
        "gutter_mm": 4.5,
        "title_font_pt": 15.0,
        "subtitle_font_pt": 10.0,
        "footer_font_pt": 7.5,
        "legend_font_pt": 8.5,
        "scale_text_font_pt": 9.0,
    },
    "minimalista": {
        "description": "Só o essencial: título, mapa, escala e fonte. Para apresentações.",
        "title_fraction": 0.055,
        "subtitle_fraction": 0.0,
        "footer_fraction": 0.040,
        "side_column_fraction": 0.18,
        "gutter_mm": 3.0,
        "title_font_pt": 14.0,
        "subtitle_font_pt": 9.0,
        "footer_font_pt": 6.5,
        "legend_font_pt": 7.5,
        "scale_text_font_pt": 8.0,
    },
}

DEFAULT_TEMPLATE = "cientifico"

#: Acima desta razão de aspecto a coluna lateral compensa; abaixo, o apoio vai
#: para uma faixa inferior, senão sobra uma tira estreita e inútil.
SIDE_COLUMN_MIN_ASPECT = 1.15

#: Alturas mínimas em milímetros para que os itens continuem legíveis mesmo em
#: páginas pequenas como A5.
MIN_TITLE_MM = 6.0
MIN_SUBTITLE_MM = 4.0
MIN_FOOTER_MM = 5.0
MIN_NORTH_MM = 11.0
MIN_SCALEBAR_MM = 7.0


@dataclass(frozen=True)
class LayoutPlan:
    """Onde cada papel cartográfico vai parar na página."""

    page: PageSpec
    template: str
    arrangement: str
    slots: dict[str, Rect]
    fonts: dict[str, float]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page.to_dict(),
            "template": self.template,
            "arrangement": self.arrangement,
            "slots": {name: rect.to_dict() for name, rect in self.slots.items()},
            "fonts_pt": self.fonts,
            "notes": list(self.notes),
        }

    def map_frame(self) -> Rect:
        return self.slots["map"]


def solve_layout(
    page: str | dict[str, Any] | PageSpec | None = None,
    template: str = DEFAULT_TEMPLATE,
    include_legend: bool = True,
    include_scale_bar: bool = True,
    include_scale_text: bool = True,
    include_north_arrow: bool = True,
    include_subtitle: bool = True,
    include_logo: bool = False,
    include_inset: bool = False,
    grid_annotation_gutter_mm: float = 0.0,
) -> LayoutPlan:
    """Resolve o template escolhido para a página informada."""
    spec = resolve_page(page)
    template_key = template if template in TEMPLATES else DEFAULT_TEMPLATE
    config = TEMPLATES[template_key]
    notes: list[str] = []
    if template != template_key:
        notes.append(f"Template {template!r} desconhecido; usado {template_key!r}.")

    content_x = spec.content_x_mm
    content_y = spec.content_y_mm
    content_w = spec.content_width_mm
    content_h = spec.content_height_mm
    gutter = float(config["gutter_mm"])

    slots: dict[str, Rect] = {}

    # --- bandas horizontais: título, subtítulo, rodapé -----------------
    title_h = max(MIN_TITLE_MM, content_h * float(config["title_fraction"]))
    subtitle_h = (
        max(MIN_SUBTITLE_MM, content_h * float(config["subtitle_fraction"]))
        if include_subtitle and float(config["subtitle_fraction"]) > 0
        else 0.0
    )
    footer_h = max(MIN_FOOTER_MM, content_h * float(config["footer_fraction"]))

    cursor = content_y
    slots["title"] = Rect(content_x, cursor, content_w, title_h)
    cursor += title_h
    if subtitle_h:
        slots["subtitle"] = Rect(content_x, cursor, content_w, subtitle_h)
        cursor += subtitle_h
    cursor += gutter

    footer_y = content_y + content_h - footer_h
    slots["footer"] = Rect(content_x, footer_y, content_w, footer_h)

    body_y = cursor
    body_h = footer_y - gutter - body_y
    if body_h <= 20.0:
        # Página pequena demais para as bandas pedidas: comprime tudo para que
        # o mapa ainda exista, e avisa em vez de gerar itens fora da página.
        notes.append("Página pequena para o template; bandas de título e rodapé comprimidas.")
        body_h = max(20.0, content_h * 0.55)
        body_y = content_y + content_h - footer_h - gutter - body_h

    needs_support = include_legend or include_scale_bar or include_scale_text or include_north_arrow or include_logo or include_inset
    arrangement = "coluna_lateral" if (spec.aspect >= SIDE_COLUMN_MIN_ASPECT and needs_support) else "faixa_inferior"
    if not needs_support:
        arrangement = "mapa_cheio"

    if arrangement == "mapa_cheio":
        slots["map"] = Rect(content_x, body_y, content_w, body_h)
    elif arrangement == "coluna_lateral":
        side_w = content_w * float(config["side_column_fraction"])
        map_w = content_w - side_w - gutter
        slots["map"] = Rect(content_x, body_y, map_w, body_h)
        _fill_support_column(
            slots,
            Rect(content_x + map_w + gutter, body_y, side_w, body_h),
            gutter=gutter,
            include_legend=include_legend,
            include_scale_bar=include_scale_bar,
            include_scale_text=include_scale_text,
            include_north_arrow=include_north_arrow,
            include_logo=include_logo,
            include_inset=include_inset,
        )
    else:
        support_h = min(body_h * 0.30, max(26.0, body_h * 0.22))
        map_h = body_h - support_h - gutter
        slots["map"] = Rect(content_x, body_y, content_w, map_h)
        _fill_support_band(
            slots,
            Rect(content_x, body_y + map_h + gutter, content_w, support_h),
            gutter=gutter,
            include_legend=include_legend,
            include_scale_bar=include_scale_bar,
            include_scale_text=include_scale_text,
            include_north_arrow=include_north_arrow,
            include_logo=include_logo,
            include_inset=include_inset,
        )

    # Os rótulos da grade são desenhados FORA do quadro do mapa e invadem o
    # que estiver ao lado. Encolher o quadro é o que impede a colisão com o
    # subtítulo e com a coluna de apoio.
    if grid_annotation_gutter_mm > 0 and "map" in slots:
        gutter = float(grid_annotation_gutter_mm)
        raw = slots["map"]
        slots["map"] = Rect(
            raw.x + gutter,
            raw.y + gutter,
            max(20.0, raw.width - 2 * gutter),
            max(20.0, raw.height - 2 * gutter),
        )
        notes.append(f"Quadro do mapa recuado {gutter:g} mm para acomodar os rótulos da grade.")

    fonts = {
        "title": float(config["title_font_pt"]),
        "subtitle": float(config["subtitle_font_pt"]),
        "footer": float(config["footer_font_pt"]),
        "legend": float(config["legend_font_pt"]),
        "scale_text": float(config["scale_text_font_pt"]),
    }
    fonts = _scale_fonts(fonts, spec)

    return LayoutPlan(page=spec, template=template_key, arrangement=arrangement, slots=slots, fonts=fonts, notes=notes)


def _fill_support_column(
    slots: dict[str, Rect],
    column: Rect,
    *,
    gutter: float,
    include_legend: bool,
    include_scale_bar: bool,
    include_scale_text: bool,
    include_north_arrow: bool,
    include_logo: bool,
    include_inset: bool,
) -> None:
    """Empilha os itens de apoio numa coluna, do topo para a base."""
    cursor = column.y
    remaining = column.height

    if include_north_arrow:
        north_h = max(MIN_NORTH_MM, column.height * 0.09)
        north_w = min(column.width * 0.42, north_h * 0.72)
        slots["north"] = Rect(column.x + (column.width - north_w) / 2.0, cursor, north_w, north_h)
        cursor += north_h + gutter
        remaining -= north_h + gutter

    # Reserva a base para escala e logo antes de dar o resto à legenda.
    bottom_reserved = 0.0
    if include_scale_text:
        bottom_reserved += max(5.0, column.height * 0.045) + gutter
    if include_scale_bar:
        bottom_reserved += max(MIN_SCALEBAR_MM, column.height * 0.055) + gutter
    if include_inset:
        bottom_reserved += column.width * 0.62 + gutter
    if include_logo:
        bottom_reserved += max(8.0, column.height * 0.07) + gutter

    if include_legend:
        legend_h = max(14.0, remaining - bottom_reserved)
        slots["legend"] = Rect(column.x, cursor, column.width, legend_h)
        cursor += legend_h + gutter

    bottom = column.bottom
    if include_logo:
        logo_h = max(8.0, column.height * 0.07)
        bottom -= logo_h
        slots["logo"] = Rect(column.x, bottom, column.width, logo_h)
        bottom -= gutter
    if include_inset:
        inset_h = column.width * 0.62
        bottom -= inset_h
        slots["inset"] = Rect(column.x, bottom, column.width, inset_h)
        bottom -= gutter
    if include_scale_bar:
        bar_h = max(MIN_SCALEBAR_MM, column.height * 0.055)
        bottom -= bar_h
        slots["scale_bar"] = Rect(column.x, bottom, column.width, bar_h)
        bottom -= gutter
    if include_scale_text:
        text_h = max(5.0, column.height * 0.045)
        bottom -= text_h
        slots["scale_text"] = Rect(column.x, bottom, column.width, text_h)


def _fill_support_band(
    slots: dict[str, Rect],
    band: Rect,
    *,
    gutter: float,
    include_legend: bool,
    include_scale_bar: bool,
    include_scale_text: bool,
    include_north_arrow: bool,
    include_logo: bool,
    include_inset: bool,
) -> None:
    """Distribui os itens de apoio numa faixa horizontal, da esquerda para a direita."""
    weights: list[tuple[str, float]] = []
    if include_legend:
        weights.append(("legend", 3.0))
    if include_inset:
        weights.append(("inset", 1.4))
    if include_scale_bar or include_scale_text:
        weights.append(("scale_block", 1.6))
    if include_north_arrow:
        weights.append(("north", 0.7))
    if include_logo:
        weights.append(("logo", 0.8))
    if not weights:
        return

    total_weight = sum(weight for _, weight in weights)
    available = band.width - gutter * (len(weights) - 1)
    cursor = band.x

    for name, weight in weights:
        width = available * (weight / total_weight)
        if name == "scale_block":
            block = Rect(cursor, band.y, width, band.height)
            inner_cursor = block.y
            if include_scale_text:
                text_h = max(5.0, block.height * 0.30)
                slots["scale_text"] = Rect(block.x, inner_cursor, block.width, text_h)
                inner_cursor += text_h + gutter * 0.5
            if include_scale_bar:
                bar_h = max(MIN_SCALEBAR_MM, block.bottom - inner_cursor)
                slots["scale_bar"] = Rect(block.x, inner_cursor, block.width, min(bar_h, block.bottom - inner_cursor))
        elif name == "north":
            north_h = min(band.height, max(MIN_NORTH_MM, band.height * 0.85))
            north_w = min(width, north_h * 0.72)
            slots["north"] = Rect(cursor + (width - north_w) / 2.0, band.y + (band.height - north_h) / 2.0, north_w, north_h)
        else:
            slots[name] = Rect(cursor, band.y, width, band.height)
        cursor += width + gutter


def _scale_fonts(fonts: dict[str, float], page: PageSpec) -> dict[str, float]:
    """Ajusta o corpo tipográfico ao tamanho da página.

    Um título de 15 pt numa A0 some; numa A5 ocupa metade da folha. A escala é
    proporcional à raiz da área, que é como o tamanho aparente de fonte se
    comporta a distâncias de leitura diferentes, com piso de 6 pt para não
    violar a regra CART044.
    """
    reference_diagonal = (297.0 ** 2 + 210.0 ** 2) ** 0.5  # A4 paisagem
    diagonal = (page.width_mm ** 2 + page.height_mm ** 2) ** 0.5
    factor = (diagonal / reference_diagonal) ** 0.62
    factor = max(0.72, min(2.6, factor))
    return {name: round(max(6.0, value * factor), 1) for name, value in fonts.items()}
