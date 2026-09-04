"""Motor cartográfico do SIGMAI.

Este pacote separa o *conhecimento cartográfico* da mecânica do PyQGIS.

Os módulos ``pagespec``, ``scaling`` e ``rulebook`` são Python puro: não
importam PyQGIS e podem ser testados fora do QGIS. Só ``compose`` e ``audit``
tocam a API de layout do QGIS. Essa separação é deliberada — as regras
cartográficas são a contribuição do projeto e precisam ser verificáveis em CI,
onde não há QGIS instalado.
"""

from .pagespec import PageSpec, PAGE_SIZES, resolve_page
from .scaling import (
    SCALE_LADDER,
    fit_extent_to_frame,
    graticule_interval,
    nice_number,
    round_scale,
    scale_from_extent,
    scalebar_spec,
)

__all__ = [
    "PageSpec",
    "PAGE_SIZES",
    "resolve_page",
    "SCALE_LADDER",
    "fit_extent_to_frame",
    "graticule_interval",
    "nice_number",
    "round_scale",
    "scale_from_extent",
    "scalebar_spec",
]
