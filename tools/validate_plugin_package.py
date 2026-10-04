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

# "tracker" entra porque o validador oficial do repositório do QGIS o exige e o
# nosso não conferia: uma submissão sem ele volta reprovada sem diagnóstico.
REQUIRED_FIELDS = ("name", "qgisMinimumVersion", "description", "about", "version",
                   "author", "email", "repository", "tracker")
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


# --- verificações acrescentadas depois da auditoria de publicação ----------
# Todas nasceram de um defeito real que passou batido: número citado na
# documentação que não bate com o código, link relativo apontando para arquivo
# que não existe, ícone declarado e ausente, e a versão divergindo entre o
# metadata e os documentos.

DOC_GLOBS = ("README.md", "CITATION.cff", "sigmai/README.md", "docs/**/*.md")
MAX_PACKAGE_BYTES = 25 * 1024 * 1024  # teto oficial do repositório do QGIS


def _documentos(raiz: Path) -> list[Path]:
    encontrados: list[Path] = []
    for padrao in DOC_GLOBS:
        encontrados.extend(sorted(raiz.glob(padrao)))
    return [caminho for caminho in encontrados if caminho.is_file()]


def checar_versao_nos_documentos(raiz: Path, versao: str) -> list[str]:
    """A versão do plugin, onde é DECLARADA, tem de ser a do metadata.

    Só olha declarações — `version: x`, `version = {x}`, `SIGMAI x` — e não
    qualquer número pontuado no texto. Um documento que explica o que a 0.1.1
    fazia de errado está citando história, não declarando versão, e o
    validador não pode reprovar por isso. `cff-version` é a versão do formato
    CITATION, não do plugin.
    """
    import re

    declaracoes = (
        r"(?<!cff-)version:\s*v?(\d+\.\d+\.\d+)",
        r"version\s*=\s*\{?v?(\d+\.\d+\.\d+)",
        r"SIGMAI[\s_-]v?(\d+\.\d+\.\d+)",
    )
    problemas: list[str] = []
    for caminho in _documentos(raiz):
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        for padrao in declaracoes:
            for achado in re.finditer(padrao, texto, re.IGNORECASE):
                if achado.group(1) == versao:
                    continue
                linha = texto[: achado.start()].count("\n") + 1
                contexto = texto.splitlines()[linha - 1].strip()[:100]
                problemas.append(f"{caminho}:{linha} declara {achado.group(1)}, mas o plugin está em {versao}: {contexto}")
    return problemas


def checar_links_relativos(raiz: Path) -> list[str]:
    import re

    problemas: list[str] = []
    for caminho in _documentos(raiz):
        if caminho.suffix != ".md":
            continue
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        for achado in re.finditer(r"\[[^\]]*\]\(([^)#][^)]*)\)", texto):
            alvo = achado.group(1).split("#")[0].strip()
            if not alvo or alvo.startswith(("http://", "https://", "mailto:")):
                continue
            if not (caminho.parent / alvo).resolve().exists():
                linha = texto[: achado.start()].count("\n") + 1
                problemas.append(f"{caminho}:{linha} aponta para {alvo}, que não existe")
    return problemas


def checar_icone(pacote: Path, metadata: dict) -> list[str]:
    icone = str(metadata.get("icon", "")).strip()
    if not icone:
        return ["metadata.txt não declara icon"]
    if not (pacote / icone).exists():
        return [f"icon={icone} não existe dentro do pacote"]
    return []


def checar_numeros_da_documentacao(raiz: Path) -> list[str]:
    """Os números citados nos documentos contra os do código.

    Um README que promete 26 regras num motor que tem 28 é a mesma família de
    defeito que esta versão inteira combateu: anunciar o que não corresponde.
    """
    import re
    import sys

    sys.path.insert(0, str(raiz))
    try:
        from sigmai.cartography.rulebook import RULES
        from sigmai.permissions import COMMAND_PERMISSIONS
    except Exception as exc:  # pragma: no cover - só fora de um checkout completo
        return [f"não foi possível conferir os números contra o código: {exc}"]

    esperado = {
        r"(\d+)\s+(?:catalogued commands|comandos catalogados)": len(COMMAND_PERMISSIONS),
        r"(\d+)\s+(?:rules|regras)\b": len(RULES),
    }
    problemas: list[str] = []
    for caminho in _documentos(raiz):
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        for padrao, valor in esperado.items():
            for achado in re.finditer(padrao, texto):
                citado = int(achado.group(1))
                if citado != valor:
                    linha = texto[: achado.start()].count("\n") + 1
                    problemas.append(f"{caminho}:{linha} cita {citado}, o código tem {valor}")
    return problemas


def checar_artefato(raiz: Path) -> list[str]:
    """Valida o zip de verdade, montado pelo MESMO empacotador que a ação usa.

    Antes o validador montava um zip próprio, com uma lista de exclusões
    diferente da de ``_zip_plugin``: o CI validava um artefato que não era o
    que saía. Um log esquecido em sigmai/logs/ entrava num e não no outro.
    """
    import io
    import sys
    import tempfile
    import zipfile

    sys.path.insert(0, str(raiz))
    try:
        from sigmai.qgis_actions.plugin_tools import _zip_plugin
    except Exception as exc:  # pragma: no cover
        return [f"não foi possível importar o empacotador real: {exc}"]

    problemas: list[str] = []
    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta) / "sigmai.zip"
        manifesto = _zip_plugin(raiz / "sigmai", destino)
        tamanho = destino.stat().st_size
        if tamanho > MAX_PACKAGE_BYTES:
            problemas.append(f"o pacote tem {tamanho / 1048576:.1f} MiB, acima do teto de 25 MiB do repositório")
        with zipfile.ZipFile(destino) as arquivo:
            nomes = arquivo.namelist()
        raizes = {nome.split("/")[0] for nome in nomes}
        if raizes != {"sigmai"}:
            problemas.append(f"o zip precisa ter uma única pasta raiz chamada sigmai; tem {sorted(raizes)}")
        if "sigmai/metadata.txt" not in nomes:
            problemas.append("o zip não contém sigmai/metadata.txt")
        # O que não pode sair no pacote publicado, aconteça o que acontecer.
        for nome in nomes:
            if any(marca in nome for marca in ("__pycache__", ".pyc", "/logs/", ".jsonl", "token", "current_bridge_session")):
                problemas.append(f"o zip carrega um arquivo que não deveria sair: {nome}")
    return problemas



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

    # O pacote tem de levar o texto integral da licença que o metadata.txt
    # declara — um aviso de uma linha não basta, nem para a MIT (que exige
    # a nota de permissão em toda cópia) nem para a GPL.
    licenca = PACKAGE / "LICENSE"
    declarada = metadata.get("license", "")
    if licenca.exists():
        texto = licenca.read_text(encoding="utf-8", errors="ignore")
        if declarada.upper().startswith("MIT"):
            if "Permission is hereby granted" not in texto or 'THE SOFTWARE IS PROVIDED "AS IS"' not in texto:
                problems.append("pacote: metadata.txt declara MIT, mas sigmai/LICENSE não traz o texto integral da MIT.")
        elif declarada.upper().startswith("GPL") and "TERMS AND CONDITIONS" not in texto:
            problems.append("pacote: sigmai/LICENSE tem só o aviso; a GPL exige o texto integral da licença.")
    raiz = ROOT / "LICENSE"
    if raiz.exists() and licenca.exists() and raiz.read_text(encoding="utf-8", errors="ignore") != licenca.read_text(encoding="utf-8", errors="ignore"):
        problems.append("LICENSE da raiz e sigmai/LICENSE divergem: o repositório e o pacote declarariam licenças diferentes.")

    problems.extend(checar_icone(PACKAGE, metadata))
    problems.extend(checar_versao_nos_documentos(ROOT, version))
    problems.extend(checar_links_relativos(ROOT))
    problems.extend(checar_numeros_da_documentacao(ROOT))
    problems.extend(checar_artefato(ROOT))

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
