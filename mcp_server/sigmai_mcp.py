#!/usr/bin/env python3
"""Atalho para o servidor MCP, que vive dentro do pacote do plugin.

Mantido para quem já configurou o caminho antigo. O arquivo canônico é
``sigmai/mcp/sigmai_mcp.py``, porque é ele que viaja dentro do .zip instalado
no QGIS.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sigmai" / "mcp"))

from sigmai_mcp import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
