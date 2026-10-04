"""Conformidade do servidor MCP com a especificação.

O servidor anterior lia ``{"tool": ..., "arguments": ...}`` de stdin — um
formato próprio que nenhum cliente MCP fala. Estes testes existem para que a
regressão não passe despercebida: eles sobem o servidor como um cliente real
faria e conversam JSON-RPC 2.0 por stdio.

Referência: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import weakref
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "sigmai" / "mcp" / "sigmai_mcp.py"
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


class MCPClient:
    """Cliente mínimo o bastante para exercitar o protocolo."""

    def __init__(self):
        # O ambiente é o do interpretador que roda a suíte (no Windows, o
        # python.exe do OSGeo4W precisa do PYTHONHOME dele, e todo processo
        # precisa de SYSTEMROOT), com as pastas onde o servidor procura sessões
        # apontadas para uma pasta vazia: nenhuma ponte real da máquina atende.
        isolada = tempfile.mkdtemp(prefix="sigmai_mcp_")
        weakref.finalize(self, shutil.rmtree, isolada, True)
        env = {chave: valor for chave, valor in os.environ.items() if not chave.upper().startswith("SIGMAI_")}
        env.update({
            "PYTHONUNBUFFERED": "1", "SIGMAI_SESSION_FILE": os.path.join(isolada, "nao_existe.json"),
            "HOME": isolada, "USERPROFILE": isolada, "LOCALAPPDATA": isolada,
            "TEMP": isolada, "TMP": isolada, "TMPDIR": isolada,
        })
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, env=env,
        )

    def send(self, message: dict) -> None:
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def send_raw(self, line: str) -> None:
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def receive(self) -> dict | None:
        line = self.process.stdout.readline()
        return json.loads(line) if line.strip() else None

    def request(self, method: str, params: dict | None = None, message_id: int = 1) -> dict:
        payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.send(payload)
        return self.receive()

    def initialize(self, version: str = "2025-06-18") -> dict:
        result = self.request("initialize", {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": {"name": "SIGMAI test client", "version": "1.0.0"},
        })
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def close(self) -> int:
        self.process.stdin.close()
        return self.process.wait(timeout=10)


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        self.client = MCPClient()

    def tearDown(self):
        try:
            self.client.close()
        except Exception:
            self.client.process.kill()

    def test_initialize_echoes_the_requested_version(self):
        response = self.client.initialize("2025-06-18")
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")

    def test_every_published_version_is_accepted(self):
        for version in ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"):
            with self.subTest(version=version):
                client = MCPClient()
                try:
                    self.assertEqual(client.initialize(version)["result"]["protocolVersion"], version)
                finally:
                    client.close()

    def test_unknown_version_is_answered_not_rejected(self):
        # Devolver erro aqui derruba a conexão com clientes mais novos que o
        # servidor. A especificação manda responder com uma versão própria.
        response = self.client.request("initialize", {"protocolVersion": "1999-01-01", "clientInfo": {"name": "x", "version": "1"}})
        self.assertIn("result", response)
        self.assertIn(response["result"]["protocolVersion"], ("2025-06-18",))

    def test_declares_the_tools_capability_and_server_identity(self):
        result = self.client.initialize()["result"]
        self.assertIn("tools", result["capabilities"])
        self.assertTrue(result["serverInfo"]["name"])
        self.assertTrue(result["serverInfo"]["version"])
        self.assertTrue(result["instructions"])

    def test_notifications_never_get_a_reply(self):
        self.client.initialize()
        self.client.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 99}})
        response = self.client.request("ping", message_id=42)
        self.assertEqual(response["id"], 42)
        self.assertEqual(response["result"], {})

    def test_exits_when_stdin_closes(self):
        self.client.initialize()
        self.assertEqual(self.client.close(), 0)


class ToolListTests(unittest.TestCase):
    def setUp(self):
        self.client = MCPClient()
        self.client.initialize()
        self.tools = self.client.request("tools/list", message_id=2)["result"]["tools"]

    def tearDown(self):
        self.client.close()

    def test_publishes_the_expected_tools(self):
        names = {tool["name"] for tool in self.tools}
        for expected in (
            "sigmai_status", "sigmai_project_overview", "sigmai_cartographic_rulebook",
            "sigmai_plan_map", "sigmai_compose_map", "sigmai_audit_layout", "sigmai_run_command",
            # 1.1.0
            "sigmai_briefing", "sigmai_spatial_relationship", "sigmai_add_context_annotations",
            "sigmai_campaign_map", "sigmai_export_coordinate_table", "sigmai_map_recipe",
            "sigmai_recompose_from_recipe", "sigmai_methods_paragraph", "sigmai_undo",
        ):
            self.assertIn(expected, names)
        self.assertEqual(len(self.tools), 20, sorted(names))

    def test_tool_shape_follows_the_specification(self):
        for tool in self.tools:
            with self.subTest(tool=tool["name"]):
                self.assertRegex(tool["name"], TOOL_NAME_PATTERN)
                self.assertTrue(tool["description"])
                self.assertEqual(tool["inputSchema"]["type"], "object")
                self.assertNotIn("handler", tool)

    def test_read_only_tools_declare_their_annotations(self):
        # Sem annotations explícitas, o cliente assume o pior caso — escreve,
        # é destrutiva, não é idempotente — e pede confirmação para tudo.
        by_name = {tool["name"]: tool for tool in self.tools}
        self.assertTrue(by_name["sigmai_status"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["sigmai_plan_map"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["sigmai_compose_map"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["sigmai_briefing"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["sigmai_spatial_relationship"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["sigmai_methods_paragraph"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["sigmai_undo"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["sigmai_campaign_map"]["annotations"]["readOnlyHint"])

    def test_order_is_deterministic(self):
        again = self.client.request("tools/list", message_id=3)["result"]["tools"]
        self.assertEqual([tool["name"] for tool in self.tools], [tool["name"] for tool in again])

    def test_single_page_has_no_cursor(self):
        result = self.client.request("tools/list", message_id=4)["result"]
        self.assertNotIn("nextCursor", result)


class ErrorSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.client = MCPClient()
        self.client.initialize()

    def tearDown(self):
        self.client.close()

    def test_unknown_tool_is_a_protocol_error(self):
        response = self.client.request("tools/call", {"name": "nao_existe", "arguments": {}}, message_id=5)
        self.assertEqual(response["error"]["code"], -32602)

    def test_unknown_method_is_a_protocol_error(self):
        self.assertEqual(self.client.request("metodo/inventado", message_id=6)["error"]["code"], -32601)

    def test_malformed_line_is_a_parse_error_with_null_id(self):
        self.client.send_raw("isto nao e json")
        response = self.client.receive()
        self.assertEqual(response["error"]["code"], -32700)
        self.assertIsNone(response["id"])

    def test_bridge_unavailable_is_a_tool_error_not_a_protocol_error(self):
        # Erro de execução precisa chegar ao modelo como isError para que ele
        # possa se corrigir; como erro JSON-RPC vira uma falha opaca na UI.
        response = self.client.request("tools/call", {"name": "sigmai_status", "arguments": {}}, message_id=7)
        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("SIGMAI", response["result"]["content"][0]["text"])

    def test_result_carries_both_text_and_structured_content(self):
        response = self.client.request("tools/call", {"name": "sigmai_status", "arguments": {}}, message_id=8)
        result = response["result"]
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertIn("structuredContent", result)


class TransportTests(unittest.TestCase):
    def test_stdout_carries_only_protocol_messages(self):
        client = MCPClient()
        try:
            client.initialize()
            client.request("tools/list", message_id=2)
            client.request("tools/call", {"name": "sigmai_status", "arguments": {}}, message_id=3)
            client.process.stdin.close()
            remaining = client.process.stdout.read()
            client.process.wait(timeout=10)
        finally:
            if client.process.poll() is None:
                client.process.kill()
        for line in remaining.splitlines():
            if line.strip():
                json.loads(line)  # levanta se algo não-protocolo vazou para stdout


if __name__ == "__main__":
    unittest.main()
