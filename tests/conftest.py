"""Ajuste da suíte por plataforma."""

from __future__ import annotations

import os
import sys

_status = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _status["code"] = int(exitstatus)


def pytest_unconfigure(config):
    # Fora do Windows, o QGIS cai ao destruir os objetos estáticos depois que o
    # Python termina: no macOS do conda-forge, "mutex lock failed" (134); no
    # QGIS 4 das imagens oficiais em Linux, falha de segmentação (139). Nos
    # dois casos com a suíte inteira aprovada. Sai antes disso, com o código
    # que o pytest decidiu e o resumo já impresso.
    if os.name != "nt" and "qgis.core" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_status["code"])
