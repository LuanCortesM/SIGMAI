"""Encerramento seguro do QGIS em scripts autônomos (fora do QGIS).

Motivo
------
Um ``QgsVectorLayer``/``QgsRasterLayer`` criado num script e **não** adicionado
ao projeto pertence ao Python. O interpretador só destrói esse objeto no
encerramento, ou seja, **depois** de ``QgsApplication.exitQgis()`` já ter
derrubado o registro de provedores — e o destrutor em C++ então acessa memória
liberada, o que produz uma falha de segmentação silenciosa *após* o script já
ter impresso todos os seus resultados.

Isso não afeta o plugin dentro do QGIS: lá o ciclo de vida do QgsApplication
pertence ao próprio QGIS e as camadas criadas pelo SIGMAI são entregues ao
projeto (``addMapLayer``), portanto pertencem ao C++.

Uso::

    from tools.qgis_lifecycle import shutdown_qgis
    try:
        ...
    finally:
        shutdown_qgis(app)
"""

from __future__ import annotations

import gc
from contextlib import contextmanager
from typing import Any, Iterator


def _clear_project() -> None:
    try:
        from qgis.core import QgsProject  # type: ignore

        QgsProject.instance().clear()
    except Exception:
        pass


def shutdown_qgis(app: Any) -> None:
    """Limpa o projeto, coleta camadas órfãs e só então encerra o QGIS."""
    _clear_project()
    # Duas passagens: a primeira quebra ciclos, a segunda recolhe o que sobrou.
    gc.collect()
    gc.collect()
    try:
        app.exitQgis()
    except Exception:
        pass


@contextmanager
def standalone_qgis(prefix: str = "/usr") -> Iterator[Any]:
    """Inicializa e encerra o QGIS com a ordem de destruição correta."""
    from qgis.core import QgsApplication  # type: ignore

    QgsApplication.setPrefixPath(prefix, True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        yield app
    finally:
        shutdown_qgis(app)
