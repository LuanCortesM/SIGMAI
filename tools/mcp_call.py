#!/usr/bin/env python3
"""Um cliente MCP de uma chamada só — a única porta do "assistente remoto".

Faz o que o Claude Desktop, o Cursor ou o Codex fazem ao chamar uma
ferramenta: lança o servidor MCP do SIGMAI como subprocesso (JSON-RPC 2.0
por stdio), faz o handshake, executa UMA chamada e imprime a resposta em
JSON. Não lê arquivo do projeto, não importa o pacote ``sigmai``, não toca
no QGIS: tudo o que sabe do computador é o que a ferramenta devolve.

Uso::

    python3.12 tools/mcp_call.py list
    python3.12 tools/mcp_call.py call sigmai_project_overview
    python3.12 tools/mcp_call.py call sigmai_compose_map '{"layer_ids": ["..."], "title": "..."}'

A ponte é encontrada pelo arquivo de sessão (SIGMAI_SESSION_FILE) — o mesmo
mecanismo que os clientes de verdade usam.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "sigmai" / "mcp" / "sigmai_mcp.py"


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"list", "call"}:
        print(__doc__)
        return 2
    if argv[1] == "call" and len(argv) < 3:
        print("uso: mcp_call.py call <ferramenta> ['{json}']")
        return 2
    arguments = {}
    if argv[1] == "call" and len(argv) >= 4:
        try:
            arguments = json.loads(argv[3])
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"argumentos não são JSON válido: {exc}"}, ensure_ascii=False))
            return 2

    # O que um cliente MCP real repassa: a lista DEFAULT_INHERITED_ENV_VARS
    # dos SDKs oficiais, mais as variáveis do SIGMAI. Sem SYSTEMROOT o Winsock
    # não carrega no Windows (WinError 10106) e o servidor não alcança a ponte.
    herdadas = (
        {"APPDATA", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH", "PROCESSOR_ARCHITECTURE",
         "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "USERNAME", "USERPROFILE", "PROGRAMFILES"}
        if os.name == "nt" else {"HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER"}
    )
    herdadas |= {"SIGMAI_SESSION_FILE", "SIGMAI_HOST", "SIGMAI_PORT", "SIGMAI_TOKEN"}
    env = {k: v for k, v in os.environ.items() if k.upper() in herdadas}
    env.update({"PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"})
    process = subprocess.Popen(
        [sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1, env=env,
    )

    def request(ident: int, method: str, params: dict | None = None) -> dict:
        payload: dict = {"jsonrpc": "2.0", "id": ident, "method": method}
        if params is not None:
            payload["params"] = params
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("o servidor MCP encerrou sem responder: " + process.stderr.read()[-800:])
        return json.loads(line)

    try:
        request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "assistente remoto (emulação)", "version": "1"}})
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        process.stdin.flush()
        if argv[1] == "list":
            response = request(2, "tools/list")
            tools = response.get("result", {}).get("tools", [])
            # As descrições saem inteiras: uma versão anterior cortava em 300
            # caracteres e o assistente perdia justamente o trecho que dizia o
            # que fazer — um defeito do cliente que parecia ser do plugin.
            print(json.dumps([{"name": t["name"], "description": t.get("description", ""),
                               "inputSchema": t.get("inputSchema", {})} for t in tools], ensure_ascii=False, indent=1))
            return 0
        response = request(2, "tools/call", {"name": argv[2], "arguments": arguments})
        if "error" in response:
            print(json.dumps({"error": response["error"]}, ensure_ascii=False, indent=1))
            return 1
        result = response["result"]
        payload = result.get("structuredContent")
        if payload is None:
            try:
                payload = json.loads(result["content"][0]["text"])
            except Exception:
                payload = result.get("content")
        print(json.dumps({"isError": bool(result.get("isError")), "result": payload}, ensure_ascii=False, indent=1, default=str))
        return 1 if result.get("isError") else 0
    finally:
        try:
            process.stdin.close()
            process.wait(timeout=10)
        except Exception:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
