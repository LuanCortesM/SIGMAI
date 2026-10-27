"""Ajuste da suíte por plataforma."""

from __future__ import annotations

import os
import sys

_status = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _status["code"] = int(exitstatus)


def pytest_unconfigure(config):
    # No macOS, o QGIS do conda-forge aborta ao destruir os objetos estáticos
    # depois que o Python termina ("mutex lock failed"), e o processo sai com
    # 134 mesmo com a suíte inteira aprovada. Sai antes disso, com o código
    # que o pytest decidiu e o resumo já impresso.
    if sys.platform == "darwin" and "qgis.core" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_status["code"])
