# -*- coding: utf-8 -*-
"""A promessa de ``dry_run``: nada muda. Testes dos dois defeitos críticos
encontrados na auditoria de publicação, os dois com a mesma causa raiz — um
atalho de simulação que era honrado só por alguns manipuladores, não por
todos.

Como o resto da suíte, roda sem PyQGIS: ``apply_default_symbology`` precisa
de ``qgis.core`` só para construir símbolos de verdade, e isso é substituído
aqui por objetos equivalentes (ver ``_FAKE_IMPORTS`` abaixo) — o que importa
para estes testes é o CONTROLE (chamou ``setRenderer`` ou não?), não o
desenho do símbolo.
"""

from __future__ import annotations

import atexit
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sigmai.bridge_server import SIGMAIServer  # noqa: E402
from sigmai.cartography import symbology  # noqa: E402
from sigmai.consent import (  # noqa: E402
    MODE_ALLOW_SESSION,
    MODE_ASK,
    MODE_READ_ONLY,
    NEVER_AUTO_APPROVED,
)


# ---------------------------------------------------------------------------
# Defeito 1 — apply_default_symbology (chamada por compose_map) mutava o
# renderizador antes mesmo de compose_map checar seu próprio dry_run.
# ---------------------------------------------------------------------------


class _FakeGeometryType:
    Polygon = "Polygon"
    Line = "Line"
    Point = "Point"


class _FakeQgis:
    GeometryType = _FakeGeometryType


class _FakeWkbTypes:
    GeometryType = _FakeGeometryType


class _FakeColor:
    def __init__(self, value: str):
        self._value = value

    def name(self) -> str:
        return self._value


class _FakeSymbol:
    def __init__(self, props: dict):
        self.props = dict(props)
        self.opacity = 1.0

    def setOpacity(self, value: float) -> None:
        self.opacity = value

    def color(self) -> _FakeColor:
        return _FakeColor(self.props.get("color") or self.props.get("line_color") or "")


class _FakeFillSymbol(_FakeSymbol):
    @classmethod
    def createSimple(cls, props: dict) -> "_FakeFillSymbol":
        return cls(props)


class _FakeLineSymbol(_FakeSymbol):
    @classmethod
    def createSimple(cls, props: dict) -> "_FakeLineSymbol":
        return cls(props)


class _FakeMarkerSymbol(_FakeSymbol):
    @classmethod
    def createSimple(cls, props: dict) -> "_FakeMarkerSymbol":
        return cls(props)


class QgsSingleSymbolRenderer:  # nome literal: has_default_symbology compara
    """type(layer.renderer()).__name__, então o nome da classe importa."""

    def __init__(self, symbol: _FakeSymbol | None = None):
        self._symbol = symbol

    def symbol(self) -> _FakeSymbol | None:
        return self._symbol


_FAKE_IMPORTS = {
    "Qgis": _FakeQgis,
    "QgsWkbTypes": _FakeWkbTypes,
    "QgsFillSymbol": _FakeFillSymbol,
    "QgsLineSymbol": _FakeLineSymbol,
    "QgsMarkerSymbol": _FakeMarkerSymbol,
    "QgsSingleSymbolRenderer": QgsSingleSymbolRenderer,
}


class _FakeLayer:
    """Cobre só a superfície de QgsVectorLayer que apply_default_symbology usa."""

    def __init__(self, name: str, geometry: str, cor_inicial: str = "#10956f"):
        self._name = name
        self._geometry = geometry
        self._renderer = QgsSingleSymbolRenderer(_FakeFillSymbol({"color": cor_inicial}))
        self.set_renderer_calls = 0

    def name(self) -> str:
        return self._name

    def geometryType(self) -> str:
        return self._geometry

    def renderer(self) -> QgsSingleSymbolRenderer:
        return self._renderer

    def setRenderer(self, renderer: QgsSingleSymbolRenderer) -> None:
        self.set_renderer_calls += 1
        self._renderer = renderer

    def triggerRepaint(self) -> None:
        pass


class SimulacaoDeSimbologiaNaoMuta(unittest.TestCase):
    """A cor do símbolo de uma camada mudou de #10956f para #d1e6f1 numa
    chamada de simulação, comprovado com QGIS real (ver relatório). A causa:
    compose_map chamava apply_default_symbology antes de checar seu próprio
    dry_run, e apply_default_symbology sempre chamava layer.setRenderer.
    """

    def _layer(self) -> _FakeLayer:
        return _FakeLayer("camada_do_usuario", "Polygon", cor_inicial="#10956f")

    def test_dry_run_nunca_chama_set_renderer(self) -> None:
        layer = self._layer()
        with patch.object(symbology, "_imports", return_value=_FAKE_IMPORTS):
            relatorio = symbology.apply_default_symbology([layer], "missing", dry_run=True)

        self.assertEqual(layer.set_renderer_calls, 0)
        self.assertEqual(layer.renderer().symbol().color().name(), "#10956f")
        self.assertEqual(relatorio[0]["action"], "seria_estilizada")
        # A simulação relata O QUE faria — inclusive a cor — sem fazer.
        self.assertIn("color", relatorio[0])

    def test_sem_dry_run_continua_estilizando_de_verdade(self) -> None:
        # Controle: sem isto, o teste acima passaria mesmo se a função nunca
        # estilizasse nada — o que provaria só que ela não faz nada, não que
        # dry_run é quem impede.
        layer = self._layer()
        with patch.object(symbology, "_imports", return_value=_FAKE_IMPORTS):
            relatorio = symbology.apply_default_symbology([layer], "missing", dry_run=False)

        self.assertEqual(layer.set_renderer_calls, 1)
        self.assertNotEqual(layer.renderer().symbol().color().name(), "#10956f")
        self.assertEqual(relatorio[0]["action"], "estilizada")

    def test_modo_none_nunca_muta_com_ou_sem_dry_run(self) -> None:
        # apply_style="none" já devolvia [] antes desta correção; confirma
        # que a adição do parâmetro dry_run não mudou esse contrato.
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                layer = self._layer()
                with patch.object(symbology, "_imports", return_value=_FAKE_IMPORTS):
                    relatorio = symbology.apply_default_symbology([layer], "none", dry_run=dry_run)
                self.assertEqual(relatorio, [])
                self.assertEqual(layer.set_renderer_calls, 0)


# ---------------------------------------------------------------------------
# Defeito 2 — _check_consent devolvia None para QUALQUER dry_run antes de
# sequer olhar para NEVER_AUTO_APPROVED.
# ---------------------------------------------------------------------------


def _server() -> SIGMAIServer:
    # A pasta do log sai no fim da suíte: cada chamada deixava uma no %TEMP%.
    pasta = tempfile.mkdtemp(prefix="sigmai_dryrun_")
    atexit.register(shutil.rmtree, pasta, True)
    return SIGMAIServer(token="t", log_dir=Path(pasta) / "logs")


class NeverAutoApprovedAntesDoAtalhoDeDryRun(unittest.TestCase):
    """NEVER_AUTO_APPROVED existe para que instalar/habilitar/desabilitar/
    recarregar plugin e executar Python arbitrário sempre exijam um clique —
    em QUALQUER modo de consentimento, dry_run incluído. O bug: dry_run:true
    retornava em _check_consent sem nunca consultar essa lista.
    """

    def test_simular_acao_da_lista_continua_permitido_em_qualquer_modo(self) -> None:
        # Simular é legítimo — nada é escrito — então isto não pode passar a
        # negar o que já era permitido antes da correção.
        for modo in (MODE_READ_ONLY, MODE_ASK, MODE_ALLOW_SESSION):
            for acao in sorted(NEVER_AUTO_APPROVED):
                with self.subTest(modo=modo, acao=acao):
                    server = _server()
                    server.consent.set_mode(modo)
                    recusa = server._check_consent(
                        {"action": acao, "dry_run": True, "params": {"plugin_name": "x"}},
                        "127.0.0.1",
                        time.perf_counter(),
                    )
                    self.assertIsNone(recusa)

    def test_simulacao_da_lista_fica_registrada_na_auditoria(self) -> None:
        # Antes da correção isto não aparecia em lugar nenhum: dry_run
        # retornava antes de qualquer chamada a self.consent. Uma dispensa
        # do clique para esta lista específica precisa ficar rastreável.
        server = _server()
        server.consent.set_mode(MODE_ALLOW_SESSION)
        server._check_consent(
            {"action": "enable_plugin", "dry_run": True, "params": {"plugin_name": "x"}},
            "127.0.0.1",
            time.perf_counter(),
        )
        eventos = [entrada["event"] for entrada in server.consent.recent_audit(10)]
        self.assertIn("dry_run_bypassed_never_auto_approved", eventos)

    def test_execucao_real_da_lista_e_negada_mesmo_em_liberado_na_sessao(self) -> None:
        # O modo mais permissivo que existe. Se a lista puder ser contornada
        # aqui, pode ser contornada em qualquer modo — por isso o teste usa
        # justamente o pior caso.
        for acao in sorted(NEVER_AUTO_APPROVED):
            with self.subTest(acao=acao):
                server = _server()
                server.consent.set_mode(MODE_ALLOW_SESSION)
                recusa = server._check_consent(
                    {
                        "action": acao,
                        "dry_run": False,
                        "params": {"plugin_name": "x", "confirm_plugin_write": True, "confirm_dev_python": "SIM"},
                    },
                    "127.0.0.1",
                    time.perf_counter(),
                )
                self.assertIsNotNone(recusa)
                self.assertEqual(recusa["errors"][0]["code"], "CONSENT_REQUIRED")

    def test_modo_somente_leitura_continua_deixando_simular_acoes_comuns(self) -> None:
        # O atalho de dry_run para ações FORA de NEVER_AUTO_APPROVED não pode
        # ter ficado mais restritivo — é o comportamento que o painel promete
        # ("Simule com dry_run para mostrar o que faria").
        server = _server()  # padrão: MODE_READ_ONLY
        recusa = server._check_consent(
            {"action": "compose_map", "dry_run": True, "params": {}},
            "127.0.0.1",
            time.perf_counter(),
        )
        self.assertIsNone(recusa)

    def test_modo_somente_leitura_continua_recusando_escrita_comum_de_verdade(self) -> None:
        server = _server()
        recusa = server._check_consent(
            {"action": "compose_map", "dry_run": False, "params": {"output_path": "/tmp/x.png"}},
            "127.0.0.1",
            time.perf_counter(),
        )
        self.assertIsNotNone(recusa)
        self.assertEqual(recusa["errors"][0]["code"], "CONSENT_REQUIRED")


# ---------------------------------------------------------------------------
# Rede de segurança do despachante: mesmo que um manipulador específico não
# honre dry_run — o defeito real encontrado em enable_plugin/disable_plugin/
# reload_plugin (sigmai/qgis_actions/plugin_tools.py, fora do escopo desta
# correção) —, uma simulação que muda o projeto tem de ser barrada na saída.
# ---------------------------------------------------------------------------


class DespachanteBarraSimulacaoQueMudouOProjeto(unittest.TestCase):
    """_execute_command confere, só para dry_run, que o projeto QGIS não
    saiu diferente de como entrou. Isola a lógica de comparação de
    _dry_run_project_snapshot() (que precisa de QGIS de verdade) chamando
    _execute_command com as duas funções substituídas.
    """

    def test_simulacao_que_muda_o_projeto_vira_recusa(self) -> None:
        server = _server()
        fotos = iter([
            {"layers": {"camada_a": "QgsSingleSymbolRenderer:#10956f"}, "layouts": []},
            {"layers": {"camada_a": "QgsSingleSymbolRenderer:#d1e6f1"}, "layouts": []},
        ])
        server._dry_run_project_snapshot = lambda: next(fotos)
        server.registry.execute = lambda command: {
            "schema_version": "0.2", "request_id": "", "ok": True,
            "action": command["action"], "data": {}, "warnings": [], "errors": [], "meta": {},
        }

        resposta = server._execute_command({"action": "manipulador_com_defeito", "dry_run": True})

        self.assertFalse(resposta["ok"])
        self.assertEqual(resposta["errors"][0]["code"], "DRY_RUN_INVARIANT_VIOLATED")

    def test_simulacao_que_nao_muda_nada_passa_normalmente(self) -> None:
        server = _server()
        foto = {"layers": {"camada_a": "QgsSingleSymbolRenderer:#10956f"}, "layouts": []}
        server._dry_run_project_snapshot = lambda: dict(foto)
        server.registry.execute = lambda command: {
            "schema_version": "0.2", "request_id": "", "ok": True,
            "action": command["action"], "data": {"exemplo": True}, "warnings": [], "errors": [], "meta": {},
        }

        resposta = server._execute_command({"action": "manipulador_correto", "dry_run": True})

        self.assertTrue(resposta["ok"])
        self.assertEqual(resposta["data"], {"exemplo": True})

    def test_execucao_real_nunca_paga_o_custo_da_fotografia(self) -> None:
        # A checagem é só para dry_run — despachar uma escrita de verdade não
        # pode ficar mais lento por causa da rede de segurança.
        server = _server()
        chamadas = []
        server._dry_run_project_snapshot = lambda: chamadas.append("foto") or {}
        server.registry.execute = lambda command: {
            "schema_version": "0.2", "request_id": "", "ok": True,
            "action": command["action"], "data": {}, "warnings": [], "errors": [], "meta": {},
        }

        server._execute_command({"action": "qualquer_escrita_real", "dry_run": False})

        self.assertEqual(chamadas, [])

    def test_sem_qgis_disponivel_a_checagem_se_desliga_sem_falso_positivo(self) -> None:
        # _dry_run_project_snapshot devolve None quando qgis.core não importa
        # (testes puros, CI sem QGIS). Nesse caso a checagem não roda — não
        # há como comparar nada — em vez de recusar tudo por precaução.
        server = _server()
        server._dry_run_project_snapshot = lambda: None
        server.registry.execute = lambda command: {
            "schema_version": "0.2", "request_id": "", "ok": True,
            "action": command["action"], "data": {}, "warnings": [], "errors": [], "meta": {},
        }

        resposta = server._execute_command({"action": "qualquer_acao", "dry_run": True})

        self.assertTrue(resposta["ok"])


if __name__ == "__main__":
    unittest.main()
