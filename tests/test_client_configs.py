"""A configuração copiada precisa ser colável sem edição."""

import json
import unittest
from pathlib import Path

from sigmai.ui.client_configs import AI_CLIENTS, build_client_config, config_file_hint, mcp_server_path


class ClientConfigTests(unittest.TestCase):
    def test_every_known_client_produces_a_snippet(self):
        for client in AI_CLIENTS:
            with self.subTest(client=client):
                config = build_client_config(client)
                self.assertTrue(config["snippet"].strip())
                self.assertTrue(config["config_path"])
                self.assertTrue(config["note"])

    def test_note_label_and_path_hint_follow_the_interface_language(self):
        from sigmai.ui.strings import LANGUAGES

        seen = set()
        for code, _ in LANGUAGES:
            config = build_client_config("generic", language=code)
            self.assertTrue(config["note"] and config["label"] and config["config_path"])
            seen.add((config["note"], config["label"]))
        # Nove línguas, nove textos diferentes: nenhuma cai em inglês por
        # falta de tradução da nota do cliente.
        self.assertEqual(len(seen), len(LANGUAGES))
        self.assertEqual(build_client_config("claude_code", language="ja")["config_path"],
                         "プロジェクトのルートの .mcp.json、または ~/.claude.json")

    def test_json_clients_emit_valid_json_with_absolute_paths(self):
        for client in ("claude_desktop", "cursor", "generic"):
            with self.subTest(client=client):
                payload = json.loads(build_client_config(client)["snippet"])
                entry = payload["mcpServers"]["sigmai"]
                # Caminho relativo quebra: o cliente lança o processo com um
                # diretório de trabalho que não é o do plugin.
                self.assertTrue(Path(entry["args"][0]).is_absolute())
                self.assertIn("PYTHONUTF8", entry["env"])

    def test_codex_block_is_toml_shaped(self):
        snippet = build_client_config("codex")["snippet"]
        self.assertIn("[mcp_servers.sigmai]", snippet)
        self.assertIn("command =", snippet)

    def test_claude_code_block_is_a_command(self):
        self.assertTrue(build_client_config("claude_code")["snippet"].startswith("claude mcp add"))

    def test_session_file_is_pinned_when_supplied(self):
        config = build_client_config("claude_desktop", session_file="/tmp/sessao.json")
        self.assertIn("/tmp/sessao.json", config["snippet"])

    def test_unknown_client_falls_back_instead_of_raising(self):
        self.assertTrue(build_client_config("editor-inexistente")["snippet"])

    def test_server_path_points_at_the_bundled_file(self):
        self.assertTrue(mcp_server_path().endswith("sigmai_mcp.py"))
        self.assertTrue(Path(mcp_server_path()).exists())

    def test_config_hint_is_platform_specific(self):
        self.assertTrue(config_file_hint("claude_desktop"))


if __name__ == "__main__":
    unittest.main()
