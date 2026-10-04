"""O caminho do cliente de IA até a ponte, como ele acontece num PC qualquer.

Três defeitos da 1.1.2 que só apareciam fora do ambiente de desenvolvimento:

- o bloco de configuração do passo 2 apontava para ``bin\\python.exe`` do
  OSGeo4W, um lançador que morre sem o PYTHONHOME do QGIS — o servidor MCP
  nunca subia a partir do Claude Desktop, do Cursor ou do Codex;
- o autoteste dizia "pronto" para essa configuração, porque só conferia se o
  arquivo existia;
- no Windows duas instâncias do QGIS ligavam a ponte na mesma porta.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.bridge_server import BridgeHTTPServer, SIGMAIServer  # noqa: E402
from sigmai.security import find_available_port  # noqa: E402
from sigmai.session import build_session_payload  # noqa: E402
from sigmai.ui.client_configs import (  # noqa: E402
    _python_executable, client_environment, mcp_server_path, probe_mcp_server, python_executable,
)


def _arquivo(caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"")
    return caminho


class InterpretadorDoOsgeo4w(unittest.TestCase):
    """Árvore do OSGeo4W/instalador do QGIS no Windows, montada em disco."""

    def setUp(self) -> None:
        self.raiz = Path(tempfile.mkdtemp(prefix="sigmai_osgeo4w_"))
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.qgis_bin = _arquivo(self.raiz / "bin" / "qgis-bin.exe")
        self.lancador = _arquivo(self.raiz / "bin" / "python.exe")
        self.interpretador = _arquivo(self.raiz / "apps" / "Python312" / "python.exe")
        self.home = str(self.raiz / "apps" / "Python312")

    def _mesmo(self, obtido: str, esperado: Path) -> None:
        self.assertEqual(os.path.realpath(obtido), os.path.realpath(str(esperado)))

    def test_dentro_do_qgis_usa_o_interpretador_completo_e_nao_o_lancador(self) -> None:
        self._mesmo(_python_executable(self.qgis_bin, self.home, "nt"), self.interpretador)

    def test_sem_base_exec_prefix_ainda_evita_o_lancador(self) -> None:
        self._mesmo(_python_executable(self.qgis_bin, "", "nt"), self.interpretador)

    def test_rodando_pelo_proprio_lancador_tambem_evita_o_lancador(self) -> None:
        self._mesmo(_python_executable(self.lancador, "", "nt"), self.interpretador)

    def test_python_comum_do_windows_continua_o_mesmo(self) -> None:
        avulso = _arquivo(self.raiz / "Python312" / "python.exe")
        self._mesmo(_python_executable(avulso, str(avulso.parent), "nt"), avulso)


class AmbienteDoCliente(unittest.TestCase):
    def test_tira_o_que_so_o_qgis_define(self) -> None:
        antes = {chave: os.environ.get(chave) for chave in ("PYTHONHOME", "PYTHONPATH", "SIGMAI_TOKEN")}
        os.environ.update({"PYTHONHOME": "C:/QGIS/apps/Python312", "PYTHONPATH": "C:/QGIS/apps/qgis/python",
                           "SIGMAI_TOKEN": "segredo"})
        try:
            env = client_environment({"PYTHONUTF8": "1"})
        finally:
            for chave, valor in antes.items():
                if valor is None:
                    os.environ.pop(chave, None)
                else:
                    os.environ[chave] = valor
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("SIGMAI_TOKEN", env)
        self.assertEqual(env["PYTHONUTF8"], "1")


class SondaDoServidorMcp(unittest.TestCase):
    """O autoteste lança o servidor de verdade e leva ``sigmai_status`` à ponte."""

    def setUp(self) -> None:
        self.pasta = Path(tempfile.mkdtemp(prefix="sigmai_sonda_"))
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.servidor = mcp_server_path(ROOT / "sigmai")

    def test_interpretador_que_nao_executa_para_na_largada(self) -> None:
        r = probe_mcp_server(str(self.pasta / "nao_existe" / "python.exe"), self.servidor)
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "start")

    def test_sem_ponte_o_servidor_responde_e_a_falha_e_da_ponte(self) -> None:
        sessao = self.pasta / "sessao.json"
        sessao.write_text(json.dumps(build_session_payload(
            host="127.0.0.1", port=find_available_port(start=47100), token="t", qgis_version="",
            plugin_version="", running=True)), encoding="utf-8")
        r = probe_mcp_server(python_executable(), self.servidor, session_file=str(sessao))
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["stage"], "bridge", r)
        self.assertTrue(r["server_version"])

    def test_com_a_ponte_no_ar_o_caminho_inteiro_responde(self) -> None:
        ponte = SIGMAIServer(token="token-da-sonda", port=0, log_dir=self.pasta / "logs")
        ponte.start()
        self.addCleanup(ponte.stop)
        sessao = self.pasta / "sessao.json"
        sessao.write_text(json.dumps(build_session_payload(
            host="127.0.0.1", port=ponte._httpd.server_address[1], token="token-da-sonda",
            qgis_version="", plugin_version="", running=True)), encoding="utf-8")
        porta = ponte._httpd.server_address[1]
        r = probe_mcp_server(python_executable(), self.servidor, session_file=str(sessao), expected_port=porta)
        self.assertTrue(r["ok"], r)
        # A sessão leva à ponte de OUTRA instância: o autoteste não pode aprovar.
        r = probe_mcp_server(python_executable(), self.servidor, session_file=str(sessao), expected_port=porta + 1)
        self.assertFalse(r["ok"], r)
        self.assertIn(str(porta), r["error"])


class PortaExclusiva(unittest.TestCase):
    def test_segunda_ponte_na_mesma_porta_desvia_para_outra(self) -> None:
        pasta = Path(tempfile.mkdtemp(prefix="sigmai_porta_"))
        self.addCleanup(shutil.rmtree, pasta, True)
        primeira = SIGMAIServer(token="a", port=0, log_dir=pasta / "a")
        primeira.start()
        self.addCleanup(primeira.stop)
        porta = primeira._httpd.server_address[1]

        segunda = SIGMAIServer(token="b", port=porta, log_dir=pasta / "b")
        segunda.start()
        self.addCleanup(segunda.stop)
        self.assertTrue(segunda.running)
        self.assertNotEqual(segunda.port, porta, "duas pontes na mesma porta: o cliente falaria com qualquer uma")
        self.assertNotEqual(find_available_port(start=porta), porta)

    def test_no_windows_a_porta_nao_e_compartilhavel(self) -> None:
        self.assertEqual(BridgeHTTPServer.allow_reuse_address, os.name != "nt")


class DuasInstancias(unittest.TestCase):
    """Fechar um QGIS não pode encerrar a sessão que o outro gravou."""

    def setUp(self) -> None:
        from sigmai import session

        self.session = session
        pasta = Path(tempfile.mkdtemp(prefix="sigmai_sessoes_"))
        self.addCleanup(shutil.rmtree, pasta, True)
        originais = {nome: getattr(session, nome) for nome in
                     ("sessions_dir", "session_file_path", "fallback_session_file_path", "pairing_session_file")}
        self.addCleanup(lambda: [setattr(session, nome, valor) for nome, valor in originais.items()])
        session.sessions_dir = lambda: pasta
        session.session_file_path = lambda: pasta / "current_bridge_session.json"
        session.fallback_session_file_path = lambda: pasta / "fallback" / "current_bridge_session.json"
        session.pairing_session_file = lambda code: pasta / f"{code}.json"
        self.atual = pasta / "current_bridge_session.json"

    def _grava(self, codigo: str, porta: int) -> None:
        self.session.write_session_file(self.session.build_session_payload(
            host="127.0.0.1", port=porta, token=codigo, qgis_version="", plugin_version="", running=True,
            session_id=codigo))

    def test_a_primeira_fecha_e_a_sessao_da_segunda_continua_ativa(self) -> None:
        self._grava("SG-AAAA-0001", 8765)
        self._grava("SG-BBBB-0002", 8766)  # a segunda instância sobrescreve o arquivo corrente
        self.session.invalidate_session_file("SG-AAAA-0001")
        dados = json.loads(self.atual.read_text(encoding="utf-8"))
        self.assertTrue(dados["active"], "fechar a primeira instância derrubou a sessão da segunda")
        self.assertEqual(dados["port"], 8766)

    def test_a_dona_da_sessao_fecha_e_a_sessao_e_encerrada(self) -> None:
        self._grava("SG-BBBB-0002", 8766)
        self.session.invalidate_session_file("SG-BBBB-0002")
        self.assertFalse(json.loads(self.atual.read_text(encoding="utf-8"))["active"])


if __name__ == "__main__":
    unittest.main()
