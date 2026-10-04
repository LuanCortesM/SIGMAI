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
    return _python_executable(
        Path(sys.executable),
        str(getattr(sys, "base_exec_prefix", "") or sys.exec_prefix),
        os.name,
    )


def _python_executable(executable: Path, base_exec_prefix: str, os_name: str) -> str:
    if os_name == "nt":
        # O OSGeo4W (e o instalador do QGIS, que é OSGeo4W) traz DOIS
        # python.exe: ``bin\python.exe`` é um lançador que só funciona com o
        # PYTHONHOME que o ``o4w_env.bat`` define, e ``apps\PythonXXX\python.exe``
        # é o interpretador completo. O cliente de IA lança o comando sem
        # PYTHONHOME, então ``bin\python.exe`` morre antes de importar
        # ``encodings`` — e era ele que esta função devolvia (1.1.2 e
        # anteriores), porque procurava ``python.exe`` subindo a partir de
        # ``bin\qgis-bin.exe``. A casa do interpretador em execução é
        # ``sys.base_exec_prefix``: esse é o que roda sozinho.
        if base_exec_prefix:
            home = Path(base_exec_prefix) / "python.exe"
            if home.is_file():
                return _long_path(home)
        if executable.stem.lower().startswith("python") and not _is_osgeo4w_launcher(executable):
            return str(executable)
        for pattern in ("apps/Python*/python.exe", "Python*/python.exe"):
            for parent in executable.parents:
                matches = sorted(parent.glob(pattern))
                if matches:
                    return _long_path(matches[-1])
        return "python"

    if executable.stem.lower().startswith("python"):
        return str(executable)
    base = Path(base_exec_prefix or sys.prefix)
    for relative in (f"bin/python{sys.version_info.major}.{sys.version_info.minor}", "bin/python3", "bin/python"):
        probe = base / relative
        if probe.exists():
            return str(probe)
    return "python3"


def _is_osgeo4w_launcher(executable: Path) -> bool:
    """``<raiz>\\bin\\python.exe`` com ``<raiz>\\apps\\Python*`` ao lado."""
    root = executable.parent.parent
    return executable.parent.name.lower() == "bin" and any(root.glob("apps/Python*/python.exe"))


def _long_path(path: Path) -> str:
    """Caminho por extenso: o ``sys.prefix`` do OSGeo4W vem em nome curto
    8.3 (``C:\\PROGRA~1\\QGIS40~1.2``), que funciona mas o usuário não reconhece
    ao colar no arquivo de configuração do cliente."""
    try:
        return os.path.realpath(str(path))
    except OSError:
        return str(path)


#: O que um cliente MCP passa ao servidor stdio além do ``env`` da
#: configuração: a lista ``DEFAULT_INHERITED_ENV_VARS`` dos SDKs oficiais do
#: MCP (Claude Desktop e Claude Code usam o de TypeScript). Nada do que o
#: QGIS/OSGeo4W define para o próprio Python — PYTHONHOME, PYTHONPATH — chega
#: ao servidor, e é por isso que ``bin\python.exe`` funcionava dentro do QGIS e
#: morria lançado pelo cliente.
CLIENT_INHERITED_ENV = (
    ("APPDATA", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH", "PROCESSOR_ARCHITECTURE",
     "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "USERNAME", "USERPROFILE", "PROGRAMFILES")
    if os.name == "nt" else ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
)


def client_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """O ambiente de um processo lançado pelo cliente de IA, não pelo QGIS."""
    wanted = {name.upper() for name in CLIENT_INHERITED_ENV}
    env = {key: value for key, value in os.environ.items() if key.upper() in wanted}
    env.update(extra or {})
    return env


def server_environment(session_file: str | None = None) -> dict[str, str]:
    """As variáveis que o bloco de configuração entrega ao servidor MCP."""
    env: dict[str, str] = {"PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"}
    if session_file:
        # Aponta o servidor direto para o arquivo de sessão. Sem isso ele
        # procura nos locais padrão, o que funciona, mas falha em silêncio se o
        # usuário mantém vários perfis do QGIS.
        env["SIGMAI_SESSION_FILE"] = session_file
    return env


def probe_mcp_server(
    executable: str, server: str, *, session_file: str | None = None, expected_port: int | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Lança o servidor MCP como o cliente de IA lançaria e conversa com ele.

    Antes o autoteste só conferia se o arquivo do interpretador existia, e
    dizia "pronto" para uma configuração que não subia. Aqui o servidor é
    iniciado com o interpretador e as variáveis do bloco de configuração, num
    ambiente sem o PYTHONHOME do QGIS; responde ``initialize`` e leva
    ``sigmai_status`` até a ponte. ``stage`` diz onde parou: ``start``
    (interpretador não executa), ``initialize`` (servidor não responde) ou
    ``bridge`` (servidor responde, ponte não).
    """
    import subprocess

    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "SIGMAI self-test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "sigmai_status", "arguments": {}}},
    ]
    payload = "".join(json.dumps(message) + "\n" for message in messages).encode("utf-8")
    extra: dict[str, Any] = {}
    if os.name == "nt":
        # Sem isto cada autoteste piscaria uma janela de console.
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [executable, server], input=payload, capture_output=True, timeout=timeout,
            env=client_environment(server_environment(session_file)), cwd=str(Path.home()), **extra,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "stage": "initialize", "error": f"sem resposta em {timeout:g} s"}
    except OSError as exc:
        return {"ok": False, "stage": "start", "error": str(exc)}

    replies: dict[Any, dict[str, Any]] = {}
    for line in completed.stdout.decode("utf-8", "replace").splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict):
            replies[message.get("id")] = message
    stderr_tail = " ".join(completed.stderr.decode("utf-8", "replace").strip().splitlines()[-2:])[:240]
    initialized = replies.get(1) or {}
    if "result" not in initialized:
        return {"ok": False, "stage": "start" if not completed.stdout else "initialize",
                "error": stderr_tail or f"código de saída {completed.returncode}"}
    version = str(((initialized["result"] or {}).get("serverInfo") or {}).get("version", ""))
    status = (replies.get(2) or {}).get("result") or {}
    if not status or status.get("isError"):
        structured = status.get("structuredContent") or {}
        errors = structured.get("errors") or [{}]
        message = (structured.get("message") or (errors[0] or {}).get("message") or structured.get("error")
                   or stderr_tail or "sigmai_status falhou")
        return {"ok": False, "stage": "bridge", "error": str(message)[:240], "server_version": version}
    # Com dois QGIS abertos, o arquivo de sessão é de quem o gravou por último:
    # o servidor pode responder pela ponte da OUTRA instância.
    reached = ((status.get("structuredContent") or {}).get("data") or {}).get("port")
    if expected_port and reached and int(reached) != int(expected_port):
        return {"ok": False, "stage": "bridge", "server_version": version,
                "error": f"a sessão leva à ponte da porta {reached}, de outra instância do QGIS, e não a esta "
                         f"(porta {expected_port})"}
    return {"ok": True, "stage": "bridge", "server_version": version}


def mcp_server_path(package_root: Path | None = None) -> str:
    """Caminho absoluto do servidor MCP dentro do plugin instalado."""
    root = package_root or Path(__file__).resolve().parents[1]
    return str(root / "mcp" / "sigmai_mcp.py")


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
    env = server_environment(session_file)

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
