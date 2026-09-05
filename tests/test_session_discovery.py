import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from sigmai.session import build_session_payload, is_safe_session_path  # noqa: E402
from session_discovery import read_session_file, resolve_connection  # noqa: E402
from core.session_paths import generate_pairing_code  # noqa: E402


class SessionDiscoveryTests(unittest.TestCase):
    def test_reads_session_file_from_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps({"host": "127.0.0.1", "port": 8765, "token": "abc"}), encoding="utf-8")
            with patch.dict(os.environ, {"SIGMAI_SESSION_FILE": str(path)}, clear=False):
                session = read_session_file()
                self.assertEqual(session["token"], "abc")

    def test_cli_token_wins_over_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps({"host": "127.0.0.1", "port": 8765, "token": "from-session"}), encoding="utf-8")
            with patch.dict(os.environ, {"SIGMAI_SESSION_FILE": str(path)}, clear=False):
                connection = resolve_connection(token="from-cli")
                self.assertEqual(connection["token"], "from-cli")

    def test_session_file_under_git_is_not_safe(self):
        self.assertFalse(is_safe_session_path(ROOT / ".git" / "current_bridge_session.json"))

    def test_pairing_code_format(self):
        code = generate_pairing_code()
        self.assertRegex(code, r"^SG-\d{4}-[A-Z0-9]{4}$")

    def test_session_payload_schema_03(self):
        payload = build_session_payload(
            host="127.0.0.1",
            port=8765,
            token="abc",
            qgis_version="3.40",
            plugin_version="0.1",
            running=True,
            session_id="SG-1234-ABCD",
        )
        self.assertEqual(payload["schema_version"], "0.3")
        self.assertEqual(payload["session_id"], "SG-1234-ABCD")
        self.assertTrue(payload["local_only"])


if __name__ == "__main__":
    unittest.main()


class FallbackEmbarcadoConcordaComOServidor(unittest.TestCase):
    """O pacote publicado nunca traz core/: é o fallback de session.py que roda.

    Todos os testes carregavam core/ no sys.path, então o caminho que o usuário
    de verdade usa nunca tinha sido exercitado — e divergia do lugar onde o
    servidor MCP procura. Este teste força o ImportError e compara os dois.
    """

    def _session_sem_core(self):
        import builtins
        import importlib
        import sys

        real_import = builtins.__import__

        def bloqueia_core(name, *args, **kwargs):
            if name.startswith("core"):
                raise ImportError("core/ não está no pacote publicado")
            return real_import(name, *args, **kwargs)

        sys.modules.pop("sigmai.session", None)
        builtins.__import__ = bloqueia_core
        try:
            return importlib.import_module("sigmai.session")
        finally:
            builtins.__import__ = real_import
            sys.modules.pop("sigmai.session", None)

    def test_a_pasta_de_sessao_e_uma_das_que_o_servidor_mcp_procura(self) -> None:
        import importlib.util
        from pathlib import Path

        sessao = self._session_sem_core()
        raiz = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("sigmai_mcp_probe", raiz / "sigmai" / "mcp" / "sigmai_mcp.py")
        modulo = importlib.util.module_from_spec(spec)
        import sys

        argv = sys.argv
        sys.argv = ["x"]
        try:
            spec.loader.exec_module(modulo)
        finally:
            sys.argv = argv
        procuradas = {p.resolve() for p in modulo._sessions_dirs()}
        gravada = sessao.session_file_path().parent.resolve()
        self.assertIn(gravada, procuradas, f"o plugin grava em {gravada}, o servidor procura em {sorted(procuradas)}")

    def test_o_fallback_espelha_o_core(self) -> None:
        from core.session_paths import sessions_dir as core_sessions_dir

        sessao = self._session_sem_core()
        self.assertEqual(sessao.session_file_path().parent.resolve(), core_sessions_dir().resolve())
