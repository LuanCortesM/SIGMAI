"""Geometria de página para layouts do QGIS.

O motor antigo do SIGMAI trazia as coordenadas dos itens em milímetros
absolutos, calculadas à mão para uma única página A4 em paisagem. Qualquer
outro formato — A3, retrato, um recorte para dissertação — colocava itens fora
da página sem nenhum aviso.

Aqui a página é um objeto explícito com área útil (a página menos as margens),
e os templates passam a descrever posições como frações dessa área útil. O
mesmo template serve para A5 e A0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


#: Formatos ISO 216 e norte-americanos em milímetros, sempre (largura, altura)
#: no sentido *retrato*. A orientação é aplicada depois, por ``resolve_page``.
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "B4": (250.0, 353.0),
    "B5": (176.0, 250.0),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
    "TABLOID": (279.4, 431.8),
}

#: Margem mínima defensável para impressão. Abaixo disso muitas impressoras
#: cortam conteúdo e a maioria das normas de trabalho acadêmico é violada.
MIN_MARGIN_MM = 5.0

ORIENTATIONS = ("portrait", "landscape")


@dataclass(frozen=True)
class PageSpec:
    """Uma página de layout com sua área útil já resolvida."""

    name: str
    width_mm: float
    height_mm: float
    margin_top_mm: float = 10.0
    margin_right_mm: float = 10.0
    margin_bottom_mm: float = 10.0
    margin_left_mm: float = 10.0
    orientation: str = "landscape"

    # ---- área útil -----------------------------------------------------
    @property
    def content_x_mm(self) -> float:
        return self.margin_left_mm

    @property
    def content_y_mm(self) -> float:
        return self.margin_top_mm

    @property
    def content_width_mm(self) -> float:
        return self.width_mm - self.margin_left_mm - self.margin_right_mm

    @property
    def content_height_mm(self) -> float:
        return self.height_mm - self.margin_top_mm - self.margin_bottom_mm

    @property
    def aspect(self) -> float:
        return self.width_mm / self.height_mm if self.height_mm else 1.0

    def contains(self, x: float, y: float, width: float, height: float, tolerance: float = 0.01) -> bool:
        """A caixa cabe dentro da página (não da área útil)?"""
        return (
            x >= -tolerance
            and y >= -tolerance
            and x + width <= self.width_mm + tolerance
            and y + height <= self.height_mm + tolerance
        )

    def within_margins(self, x: float, y: float, width: float, height: float, tolerance: float = 0.01) -> bool:
        """A caixa respeita as margens da página?"""
        return (
            x >= self.content_x_mm - tolerance
            and y >= self.content_y_mm - tolerance
            and x + width <= self.content_x_mm + self.content_width_mm + tolerance
            and y + height <= self.content_y_mm + self.content_height_mm + tolerance
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "orientation": self.orientation,
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
            "margins_mm": {
                "top": self.margin_top_mm,
                "right": self.margin_right_mm,
                "bottom": self.margin_bottom_mm,
                "left": self.margin_left_mm,
            },
            "content_area_mm": {
                "x": round(self.content_x_mm, 2),
                "y": round(self.content_y_mm, 2),
                "width": round(self.content_width_mm, 2),
                "height": round(self.content_height_mm, 2),
            },
        }


def resolve_page(
    page: str | dict[str, Any] | PageSpec | None = None,
    orientation: str | None = None,
    margin_mm: float | dict[str, float] | None = None,
) -> PageSpec:
    """Constrói um :class:`PageSpec` a partir de entrada tolerante.

    Aceita ``"A3"``, ``"a3 portrait"``, ``{"width_mm": 300, "height_mm": 200}``
    ou um ``PageSpec`` já pronto. Entrada desconhecida cai em A4 paisagem, que
    é o que ``QgsPrintLayout.initializeDefaults()`` cria.
    """
    if isinstance(page, PageSpec):
        return page

    width = height = None
    name = "A4"
    resolved_orientation = orientation

    if isinstance(page, dict):
        if page.get("width_mm") and page.get("height_mm"):
            width = float(page["width_mm"])
            height = float(page["height_mm"])
            name = str(page.get("name", "custom"))
        else:
            name = str(page.get("name", page.get("size", "A4")))
        resolved_orientation = resolved_orientation or page.get("orientation")
        if margin_mm is None:
            margin_mm = page.get("margin_mm", page.get("margins_mm"))
    elif isinstance(page, str) and page.strip():
        tokens = page.replace("-", " ").replace("_", " ").split()
        for token in tokens:
            lowered = token.lower()
            if lowered in ORIENTATIONS:
                resolved_orientation = resolved_orientation or lowered
            elif lowered in {"retrato", "vertical"}:
                resolved_orientation = resolved_orientation or "portrait"
            elif lowered in {"paisagem", "horizontal"}:
                resolved_orientation = resolved_orientation or "landscape"
            elif token.upper() in PAGE_SIZES:
                name = token.upper()

    if width is None or height is None:
        width, height = PAGE_SIZES.get(name.upper(), PAGE_SIZES["A4"])
        name = name.upper() if name.upper() in PAGE_SIZES else name

    final_orientation = (resolved_orientation or "landscape").lower()
    if final_orientation not in ORIENTATIONS:
        final_orientation = "landscape"

    # PAGE_SIZES está em retrato; troca os eixos para paisagem.
    if final_orientation == "landscape" and height > width:
        width, height = height, width
    elif final_orientation == "portrait" and width > height:
        width, height = height, width

    top, right, bottom, left = _resolve_margins(margin_mm, width, height)
    return PageSpec(
        name=name,
        width_mm=width,
        height_mm=height,
        margin_top_mm=top,
        margin_right_mm=right,
        margin_bottom_mm=bottom,
        margin_left_mm=left,
        orientation=final_orientation,
    )


def _resolve_margins(
    margin_mm: float | dict[str, float] | None,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    """Margens padrão proporcionais ao formato, com piso de impressão."""
    if isinstance(margin_mm, dict):
        default = float(margin_mm.get("all", 10.0))
        return (
            max(MIN_MARGIN_MM, float(margin_mm.get("top", default))),
            max(MIN_MARGIN_MM, float(margin_mm.get("right", default))),
            max(MIN_MARGIN_MM, float(margin_mm.get("bottom", default))),
            max(MIN_MARGIN_MM, float(margin_mm.get("left", default))),
        )
    if margin_mm is not None:
        value = max(MIN_MARGIN_MM, float(margin_mm))
        return (value, value, value, value)

    # Uma folha A0 com margem de 10 mm parece um pôster mal cortado; uma A5 com
    # margem de 25 mm não sobra mapa. Escala com a menor dimensão.
    smaller = min(width, height)
    value = max(MIN_MARGIN_MM, round(smaller * 0.048, 1))
    return (value, value, value, value)
