#!/usr/bin/env python3
"""Valida metadata.txt e a estrutura do pacote antes de publicar.

As regras vêm de https://plugins.qgis.org/publish/ e do validador do
QGIS-Django. Rodar isto em CI evita a viagem de descobrir um metadado
inválido só depois do upload.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "sigmai"

REQUIRED_FIELDS = ("name", "qgisMinimumVersion", "description", "about", "version", "author", "email", "repository")
REQUIRED_FILES = ("__init__.py", "metadata.txt", "LICENSE")
FORBIDDEN_NAMES = {"__pycache__", ".git", "__MACOSX"}
VERSION_PATTERN = re.compile(r"^\d+\.\d+(\.\d+)?$")


def read_metadata(path: Path) -> dict[str, str]:
    """Lê metadata.txt preservando valores multilinha (changelog)."""
    values: dict[str, str] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("[") or not raw.strip():
            continue
        if raw[:1] in " \t" and current:
            values[current] += "\n" + raw.strip()
            continue
        if "=" in raw:
            key, value = raw.split("=", 1)
            current = key.strip()
            values[current] = value.strip()
    return values


def main() -> int:
    problems: list[str] = []

    metadata_path = PACKAGE / "metadata.txt"
    if not metadata_path.exists():
        print("ERRO: sigmai/metadata.txt não existe.")
        return 1
    metadata = read_metadata(metadata_path)

    for field in REQUIRED_FIELDS:
        if not metadata.get(field):
            problems.append(f"metadata.txt: campo obrigatório ausente ou vazio: {field}")

    version = metadata.get("version", "")
    if version and not VERSION_PATTERN.match(version):
        problems.append(f"metadata.txt: versão fora do formato pontuado: {version!r}")

    # supportsQt6 foi removido do QGIS; o que declara compatibilidade com o
    # QGIS 4 hoje é qgisMaximumVersion.
    if "supportsQt6" in metadata:
        problems.append("metadata.txt: supportsQt6 foi removido do QGIS; declare qgisMaximumVersion=4.99.")
    maximum = metadata.get("qgisMaximumVersion", "")
    if maximum and not maximum.startswith("4"):
        problems.append(f"metadata.txt: qgisMaximumVersion={maximum} exclui o QGIS 4, que é a linha estável.")

    for name in REQUIRED_FILES:
        if not (PACKAGE / name).exists():
            problems.append(f"pacote: arquivo obrigatório ausente: sigmai/{name}")

    if (PACKAGE / "LICENSE").suffix:
        problems.append("pacote: o LICENSE deve ser texto plano sem extensão.")

    # __pycache__ e .pyc existem em qualquer árvore de trabalho e estão no
    # .gitignore; o que importa é que o empacotador os exclua. .git e
    # __MACOSX dentro do pacote, esses sim, são erro.
    for path in PACKAGE.rglob("*"):
        if path.name in FORBIDDEN_NAMES - {"__pycache__"}:
            problems.append(f"pacote: pasta proibida no .zip: {path.relative_to(ROOT)}")
            break
    packager = ROOT / "tools" / "package_qgis_plugin_zip.py"
    if packager.exists() and "__pycache__" not in packager.read_text(encoding="utf-8"):
        problems.append("tools/package_qgis_plugin_zip.py precisa excluir __pycache__ do .zip.")

    # A versão não pode estar escrita à mão em outro lugar: foi assim que o
    # pacote publicado (0.1.1) e o repositório (0.1.0) divergiram.
    hardcoded = []
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'"(\d+\.\d+\.\d+)"', text):
            if match.group(1) == version:
                hardcoded.append(f"{path.relative_to(ROOT)}:{text[:match.start()].count(chr(10)) + 1}")
    if hardcoded:
        problems.append("versão repetida no código em vez de lida do metadata.txt: " + ", ".join(hardcoded))

    mcp_server = PACKAGE / "mcp" / "sigmai_mcp.py"
    if not mcp_server.exists():
        problems.append("pacote: o servidor MCP precisa viajar dentro do .zip (sigmai/mcp/sigmai_mcp.py).")

    if problems:
        print(f"{len(problems)} problema(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"metadata.txt e estrutura do pacote válidos (SIGMAI {version}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
