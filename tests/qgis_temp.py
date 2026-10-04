"""Pasta temporária para testes que abrem arquivos no QGIS.

No Windows um arquivo aberto por uma camada não pode ser apagado, e o
``tempfile.TemporaryDirectory`` falhava na saída com WinError 32 depois que o
teste já tinha passado — a suíte com PyQGIS nunca tinha rodado no Windows. Aqui
as camadas e os layouts do projeto são soltos antes da limpeza, e o que o QGIS
ainda segurar (o OGR mantém conexões em pool) fica para o sistema apagar.
``ignore_cleanup_errors`` resolveria, mas só existe a partir do Python 3.10, e
o QGIS 3.28 no Windows traz o 3.9.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import sys
import tempfile
from typing import Iterator


@contextlib.contextmanager
def pasta_temporaria() -> Iterator[str]:
    pasta = tempfile.mkdtemp(prefix="sigmai_teste_")
    try:
        yield pasta
    finally:
        _soltar_arquivos_do_projeto()
        shutil.rmtree(pasta, ignore_errors=True)
        if os.path.exists(pasta):  # ainda presa: tenta de novo quando o processo terminar
            atexit.register(shutil.rmtree, pasta, True)


def _soltar_arquivos_do_projeto() -> None:
    # Só se o teste já iniciou o QGIS: criar o QgsProject daqui, sem
    # QgsApplication, deixaria o singleton num estado que quebra os seguintes.
    if "qgis.core" not in sys.modules:
        return
    try:
        from qgis.core import QgsApplication, QgsProject

        if QgsApplication.instance() is None:
            return
        projeto = QgsProject.instance()
        projeto.layoutManager().clear()
        projeto.removeAllMapLayers()
    except Exception:  # noqa: BLE001 — limpeza não pode reprovar o teste
        pass
