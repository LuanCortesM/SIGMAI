"""Geração da configuração pronta para colar em cada cliente de IA.

A versão anterior tinha um botão "Copiar Dica MCP" que copiava a string
``SIGMAI pairing code: SG-1234-ABCD``. Isso não é configurável em lugar
nenhum: o usuário recebia um código e nenhuma instrução do que fazer com ele.

Aqui o botão copia o bloco JSON exato que o cliente espera, já com o caminho
absoluto do interpretador Python do QGIS e o caminho absoluto do servidor MCP —
os dois erros mais comuns de configuração, porque o processo que o cliente
lança não herda o PATH do terminal do usuário e não tem diretório de trabalho
previsível.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .strings import translate

#: Clientes conhecidos. ``config_path`` usa placeholders de ambiente porque o
#: caminho real depende do sistema operacional do usuário.
AI_CLIENTS: dict[str, dict[str, str]] = {
    "claude_desktop": {
        "label": "Claude Desktop",
        "kind": "json",
        "config_windows": r"%APPDATA%\Claude\claude_desktop_config.json",
        "config_macos": "~/Library/Application Support/Claude/claude_desktop_config.json",
        "config_linux": "~/.config/Claude/claude_desktop_config.json",
    },
    "claude_code": {
        "label": "Claude Code",
        "kind": "cli",
        # Caminho descrito em prosa, traduzido: chave em ui/strings.
        "config_key": "client_path_claude_code",
    },
    "cursor": {
        "label": "Cursor",
        "kind": "json",
        "config_windows": r"%USERPROFILE%\.cursor\mcp.json",
        "config_macos": "~/.cursor/mcp.json",
        "config_linux": "~/.cursor/mcp.json",
    },
    "codex": {
        "label": "Codex CLI",
        "kind": "toml",
        "config_windows": r"%USERPROFILE%\.codex\config.toml",
        "config_macos": "~/.codex/config.toml",
        "config_linux": "~/.codex/config.toml",
    },
    "generic": {
        # Rótulo traduzido: chave em ui/strings.
        "label_key": "client_generic_label",
        "kind": "json",
        "config_key": "client_path_generic",
    },
}

SERVER_KEY = "sigmai"


def python_executable() -> str:
    """Interpretador que roda o servidor MCP.

    Dentro do QGIS, ``sys.executable`` aponta para ``qgis-bin.exe`` no Windows,
    que não serve para lançar um script. O interpretador utilizável fica ao lado,
    em ``apps/PythonXX/python.exe`` no OSGeo4W, ou é o ``python3`` do sistema no
    Linux e no macOS.
    """
    candidate = Path(sys.executable)
    name = candidate.stem.lower()
    if name.startswith("python"):
        return str(candidate)

    if os.name == "nt":
        # OSGeo4W: .../apps/qgis/bin/qgis-bin.exe -> .../apps/PythonXXX/python.exe
        for parent in candidate.parents:
            for pattern in ("apps/Python*/python.exe", "Python*/python.exe", "python.exe"):
                matches = sorted(parent.glob(pattern))
                if matches:
                    return str(matches[-1])
        return "python"

    base = Path(getattr(sys, "base_prefix", sys.prefix))
    for relative in (f"bin/python{sys.version_info.major}.{sys.version_info.minor}", "bin/python3", "bin/python"):
        probe = base / relative
        if probe.exists():
            return str(probe)
    return "python3"


def mcp_server_path(package_root: Path | None = None) -> str:
    """Caminho absoluto do servidor MCP dentro do plugin instalado."""
    root = package_root or Path(__file__).resolve().parents[1]
    bundled = root / "mcp" / "sigmai_mcp.py"
    if bundled.exists():
        return str(bundled)
    sibling = root.parent / "mcp_server" / "sigmai_mcp.py"
    return str(sibling)


def config_file_hint(client: str, language: str = "pt-BR") -> str:
    """Onde o bloco vai: um caminho real do sistema ou, para os clientes que
    não têm um só arquivo, uma frase traduzida (``config_key``)."""
    spec = AI_CLIENTS.get(client, AI_CLIENTS["generic"])
    if "config_key" in spec:
        return translate(language, spec["config_key"])
    if os.name == "nt":
        return spec["config_windows"]
    if sys.platform == "darwin":
        return spec["config_macos"]
    return spec["config_linux"]


def client_label(client: str, language: str = "pt-BR") -> str:
    spec = AI_CLIENTS.get(client, AI_CLIENTS["generic"])
    if "label_key" in spec:
        return translate(language, spec["label_key"])
    return spec["label"]


def build_client_config(
    client: str,
    *,
    package_root: Path | None = None,
    session_file: str | None = None,
    python_path: str | None = None,
    language: str = "pt-BR",
) -> dict[str, Any]:
    """Bloco de configuração pronto para colar, mais a instrução de onde colar.

    ``language`` escolhe a língua da instrução (``note``), do rótulo e da
    frase de caminho — as nove línguas de ``ui/strings``; antes só havia
    ``note_pt``/``note_en`` e qualquer outra língua da interface lia inglês.
    """
    spec = AI_CLIENTS.get(client, AI_CLIENTS["generic"])
    client_key = client if client in AI_CLIENTS else "generic"
    executable = python_path or python_executable()
    server = mcp_server_path(package_root)

    env: dict[str, str] = {"PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"}
    if session_file:
        # Aponta o servidor direto para o arquivo de sessão. Sem isso ele
        # procura nos locais padrão, o que funciona, mas falha em silêncio se o
        # usuário mantém vários perfis do QGIS.
        env["SIGMAI_SESSION_FILE"] = session_file

    if spec["kind"] == "toml":
        lines = [
            f"[mcp_servers.{SERVER_KEY}]",
            f'command = {json.dumps(executable)}',
            f'args = [{json.dumps(server)}]',
            "",
            f"[mcp_servers.{SERVER_KEY}.env]",
        ]
        lines.extend(f'{key} = {json.dumps(value)}' for key, value in env.items())
        snippet = "\n".join(lines)
    elif spec["kind"] == "cli":
        env_flags = " ".join(f"--env {key}={value}" for key, value in env.items())
        snippet = f'claude mcp add {SERVER_KEY} {env_flags} -- "{executable}" "{server}"'
    else:
        snippet = json.dumps(
            {"mcpServers": {SERVER_KEY: {"command": executable, "args": [server], "env": env}}},
            indent=2,
            ensure_ascii=False,
        )

    return {
        "client": client,
        "label": client_label(client_key, language),
        "kind": spec["kind"],
        "snippet": snippet,
        "config_path": config_file_hint(client_key, language),
        "note": translate(language, f"client_note_{client_key}"),
        "python": executable,
        "server": server,
        "server_exists": Path(server).exists(),
    }
