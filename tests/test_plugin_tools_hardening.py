# -*- coding: utf-8 -*-
"""Quatro defeitos achados numa auditoria de `sigmai/qgis_actions/plugin_tools.py`.

O estilo segue `test_third_party_plugin_audit.py`: cada classe é um defeito,
o docstring diz por que a regra existe, e os testes usam o caso real sempre
que ele existe (o próprio metadata.txt do SIGMAI, o padrão de resposta que
as outras ações de plugin já seguem) em vez de só um exemplo sintético.
"""

from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sigmai.qgis_actions import plugin_tools  # noqa: E402
from sigmai.validators import ValidationError  # noqa: E402


def _criar_plugin(root: Path, name: str, extra_metadata: str = "") -> Path:
    """Um plugin mínimo, do jeito que um de terceiro chegaria no disco."""
    plugin = root / name
    plugin.mkdir()
    (plugin / "metadata.txt").write_text(
        "[general]\n"
        "name=Plugin de Teste\n"
        "description=Descrição de teste\n"
        "version=1.0\n"
        "qgisminimumversion=3.28\n"
        "author=Alguém\n"
        "experimental=False\n" + extra_metadata,
        encoding="utf-8",
    )
    (plugin / "__init__.py").write_text("", encoding="utf-8")
    return plugin


def _pyqgis_disponivel() -> bool:
    """PyQGIS só existe dentro de uma instalação do QGIS.

    Sem esta guarda, quem clona o repositório e roda a suíte numa máquina sem
    QGIS vê falha onde não há defeito — e uma suíte que mente sobre o estado do
    código é pior do que uma suíte menor.
    """
    import importlib.util

    return importlib.util.find_spec("qgis") is not None



class ConfigParserSemInterpolacao(unittest.TestCase):
    """`_read_metadata` usava `configparser.ConfigParser()` com a
    interpolação padrão ligada. Ela trata "%" como início de substituição
    printf-style — e o changelog do PRÓPRIO metadata.txt do SIGMAI tem
    "...25%..." e "...14% do quadro...". Sem `interpolation=None`, ler
    esse arquivo (ou o de qualquer plugin de terceiro com "%" cru) sobe
    `InterpolationSyntaxError` não tratado, que vira INTERNAL_ERROR em
    quinze ações diferentes — entre elas self_inspect, self_health_check,
    self_validate_update e (por herança) self_generate_report.
    """

    def test_o_proprio_metadata_txt_do_sigmai_tem_porcento_cru(self):
        # Não é um exemplo sintético: é o arquivo real que o plugin publica.
        texto = (plugin_tools._current_plugin_path() / "metadata.txt").read_text(encoding="utf-8")
        self.assertIn("25%", texto)

    def test_le_o_proprio_metadata_txt_do_sigmai_sem_quebrar(self):
        metadata = plugin_tools._read_metadata(plugin_tools._current_plugin_path())
        self.assertTrue(metadata.get("version"))
        self.assertIn("changelog", metadata)

    def test_le_metadata_de_terceiro_com_porcento_cru(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = _criar_plugin(
                Path(tmp), "plugin_terceiro",
                extra_metadata="changelog=Cobre 25% da área e falha em 14% dos casos raros\n",
            )
            metadata = plugin_tools._read_metadata(plugin)
        self.assertIn("25%", metadata["changelog"])

    def test_configparser_e_construido_com_interpolation_none(self):
        fonte = inspect.getsource(plugin_tools._read_metadata)
        self.assertIn("interpolation=None", fonte)

    def test_self_inspect_sobrevive_ao_changelog_do_proprio_metadata(self):
        # self_inspect é o primeiro dos quatro citados no defeito.
        resultado = plugin_tools.self_inspect({}, {"registered_actions": []})
        self.assertEqual(resultado["plugin_name"], "sigmai")
        self.assertIn("version", resultado["summary"]["metadata"])

    def test_self_health_check_sobrevive_ao_changelog_do_proprio_metadata(self):
        # validate_metadata_txt (chamado por self_health_check) localiza o
        # plugin "sigmai" varrendo _plugin_roots() — fora de um QGIS real
        # isso não acha nada, então aponta a raiz de plugins para a pasta
        # real do próprio SIGMAI, exatamente como test_plugin_management.py faz.
        with patch.object(plugin_tools, "_plugin_roots", return_value=[plugin_tools._current_plugin_path().parent]):
            resultado = plugin_tools.self_health_check({}, {"registered_actions": []})
        self.assertIn("checks", resultado)
        self.assertTrue(resultado["checks"]["metadata"]["metadata"].get("version"))

    def test_inspect_plugin_de_terceiro_com_porcento_cru_nao_derruba_a_acao(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _criar_plugin(root, "plugin_com_porcento",
                           extra_metadata="changelog=Reduziu o erro em 25%\n")
            with patch.object(plugin_tools, "_plugin_roots", return_value=[root]):
                resultado = plugin_tools.inspect_plugin({"plugin_name": "plugin_com_porcento"}, {})
        self.assertIn("25%", resultado["metadata"]["changelog"])

    def test_list_installed_plugins_com_porcento_cru_nao_derruba_a_acao(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _criar_plugin(root, "plugin_com_porcento",
                           extra_metadata="changelog=Corrige 25% dos casos\n")
            with patch.object(plugin_tools, "_plugin_roots", return_value=[root]):
                resultado = plugin_tools.list_installed_plugins({}, {})
        nomes = [item["name"] for item in resultado["plugins"]]
        self.assertIn("plugin_com_porcento", nomes)


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS não instalado")
class DryRunEmOperacoesDeRuntimeDePlugin(unittest.TestCase):
    """enable_plugin/disable_plugin/reload_plugin nunca consultavam
    context["dry_run"] e iam direto para qgis.utils.loadPlugin/unloadPlugin/
    startPlugin. Como a ponte dispensa o controle de acesso quando dry_run é
    verdadeiro (`bridge_server._check_consent`), uma única requisição HTTP
    com dry_run:true — em modo somente leitura, sem confirmação nenhuma —
    ligava, desligava e recarregava qualquer plugin instalado de verdade,
    e a resposta nem sequer dizia "dry_run": true. permissions.py já
    declarava supports_dry_run=True para as três; só a implementação não
    honrava.
    """

    def test_enable_plugin_com_dry_run_nao_toca_qgis_utils(self):
        with patch("qgis.utils.loadPlugin") as load, patch("qgis.utils.startPlugin") as start:
            resultado = plugin_tools.enable_plugin({"plugin_name": "plugin_terceiro"}, {"dry_run": True})
        load.assert_not_called()
        start.assert_not_called()
        self.assertTrue(resultado["dry_run"])
        self.assertFalse(resultado["applied"])
        self.assertEqual(resultado["would_call"], ["loadPlugin", "startPlugin"])

    def test_disable_plugin_com_dry_run_nao_toca_qgis_utils(self):
        with patch("qgis.utils.unloadPlugin") as unload:
            resultado = plugin_tools.disable_plugin({"plugin_name": "plugin_terceiro"}, {"dry_run": True})
        unload.assert_not_called()
        self.assertTrue(resultado["dry_run"])
        self.assertEqual(resultado["would_call"], ["unloadPlugin"])

    def test_reload_plugin_com_dry_run_nao_toca_qgis_utils(self):
        with patch("qgis.utils.loadPlugin") as load, \
             patch("qgis.utils.unloadPlugin") as unload, \
             patch("qgis.utils.startPlugin") as start:
            resultado = plugin_tools.reload_plugin({"plugin_name": "plugin_terceiro"}, {"dry_run": True})
        load.assert_not_called()
        unload.assert_not_called()
        start.assert_not_called()
        self.assertTrue(resultado["dry_run"])
        self.assertEqual(resultado["would_call"], ["unloadPlugin", "loadPlugin", "startPlugin"])

    def test_sem_dry_run_enable_plugin_ainda_executa_de_verdade(self):
        # Regressão: honrar dry_run não pode virar a única forma de executar.
        with patch("qgis.utils.loadPlugin", return_value=True) as load, \
             patch("qgis.utils.startPlugin") as start:
            resultado = plugin_tools.enable_plugin({"plugin_name": "plugin_terceiro"}, {"dry_run": False})
        load.assert_called_once_with("plugin_terceiro")
        start.assert_called_once_with("plugin_terceiro")
        self.assertTrue(resultado["applied"])
        self.assertFalse(resultado["dry_run"])

    def test_dry_run_ausente_do_context_tambem_executa_de_verdade(self):
        # O caminho de produção (command_registry.execute) sempre põe a
        # chave "dry_run" no context, mas o handler não pode presumir isso.
        with patch("qgis.utils.unloadPlugin") as unload:
            plugin_tools.disable_plugin({"plugin_name": "plugin_terceiro"}, {})
        unload.assert_called_once_with("plugin_terceiro")

    def test_dry_run_no_proprio_sigmai_continua_bloqueado_e_agora_e_explicito(self):
        with patch.object(plugin_tools, "_is_self_plugin", return_value=True):
            with patch("qgis.utils.loadPlugin") as load:
                resultado = plugin_tools.enable_plugin({"plugin_name": "sigmai"}, {"dry_run": True})
        load.assert_not_called()
        self.assertFalse(resultado["applied"])
        self.assertTrue(resultado["dry_run"])


class SelfRollbackExtraiComProtecao(unittest.TestCase):
    """self_rollback fazia
    `zipfile.ZipFile(backup_path).extractall(plugin_path.parent)` sem a
    proteção contra escape de caminho que `_safe_extract_plugin_zip` já
    fornece e que o fluxo de instalação usa. `backup_path` só passa por
    `_safe_output_path` (resolve para absoluto, não restringe a pasta) mais
    existir e terminar em ".zip" — nada impedia um ZIP malicioso apontado
    por esse parâmetro de ser extraído sem checagem.
    """

    def test_self_rollback_usa_o_guarda_existente_e_nao_extractall_cru(self):
        fonte = inspect.getsource(plugin_tools.self_rollback)
        self.assertIn("_safe_extract_plugin_zip", fonte)
        self.assertNotIn("archive.extractall", fonte)
        self.assertNotIn(".extractall(", fonte)

    def test_self_rollback_recusa_zip_com_membro_de_caminho_perigoso(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raiz_plugins = root / "plugins_dir"
            raiz_plugins.mkdir()
            plugin_path = raiz_plugins / "sigmai"
            plugin_path.mkdir()
            backup_malicioso = root / "backup_malicioso.zip"
            with zipfile.ZipFile(backup_malicioso, "w") as archive:
                archive.writestr("../fora_da_pasta_de_plugins.txt", "conteudo malicioso")

            with patch.object(plugin_tools, "_current_plugin_path", return_value=plugin_path):
                with self.assertRaises(ValidationError) as ctx:
                    plugin_tools.self_rollback({"backup_path": str(backup_malicioso)}, {})

            self.assertEqual(ctx.exception.code, "BAD_PLUGIN_ZIP")
            # Nada deve ter sido gravado fora da pasta de plugins — a
            # checagem tem de acontecer ANTES de qualquer extração.
            self.assertFalse((root / "fora_da_pasta_de_plugins.txt").exists())

    def test_self_rollback_restaura_um_backup_bem_formado(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raiz_plugins = root / "plugins_dir"
            raiz_plugins.mkdir()
            plugin_path = raiz_plugins / "sigmai"
            plugin_path.mkdir()
            (plugin_path / "metadata.txt").write_text("[general]\nversion=0.2.1\n", encoding="utf-8")

            # A mesma estrutura que _zip_plugin/_backup_plugin produzem: um
            # único diretório-raiz (o nome do plugin) contendo o metadata.txt.
            backup_bom = root / "backup_bom.zip"
            with zipfile.ZipFile(backup_bom, "w") as archive:
                archive.writestr("sigmai/metadata.txt", "[general]\nversion=0.9.9-restaurado\n")
                archive.writestr("sigmai/__init__.py", "# restaurado\n")

            with patch.object(plugin_tools, "_current_plugin_path", return_value=plugin_path):
                resultado = plugin_tools.self_rollback({"backup_path": str(backup_bom)}, {})

            self.assertEqual(resultado["restored_from"], str(backup_bom))
            self.assertIn("0.9.9-restaurado", (plugin_path / "metadata.txt").read_text(encoding="utf-8"))
            self.assertTrue((plugin_path / "__init__.py").exists())

    def test_self_rollback_com_dry_run_continua_sem_extrair_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_path = root / "sigmai"
            plugin_path.mkdir()
            backup = root / "backup.zip"
            with zipfile.ZipFile(backup, "w") as archive:
                archive.writestr("sigmai/metadata.txt", "[general]\nversion=1.0\n")

            with patch.object(plugin_tools, "_current_plugin_path", return_value=plugin_path):
                resultado = plugin_tools.self_rollback({"backup_path": str(backup)}, {"dry_run": True})

            self.assertTrue(resultado["dry_run"])
            # Simulação: a pasta do plugin tem de continuar vazia — nada
            # pode ter sido extraído de verdade.
            self.assertEqual(list(plugin_path.iterdir()), [])


class UserAgentComAVersaoReal(unittest.TestCase):
    """O cabeçalho HTTP das requisições ao repositório oficial do QGIS
    dizia "SIGMAI/0.1 QGIS-plugin-manager", cravado, enquanto a versão real
    (metadata.txt) é outra — publicar uma versão nova nunca atualizaria
    esse texto. `bridge_server.plugin_version()` já resolve isso, mas
    importar dali criaria um ciclo real (bridge_server importa
    qgis_actions, que importa este arquivo — verificado batendo em
    ImportError); a versão é lida aqui mesmo, reaproveitando
    `_read_metadata`.
    """

    def test_user_agent_usa_a_versao_do_metadata_txt_do_proprio_sigmai(self):
        versao_esperada = plugin_tools._read_metadata(plugin_tools._current_plugin_path())["version"]
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sem rede no teste")) as urlopen_mock:
            with self.assertRaises(ValidationError):
                plugin_tools._fetch_url_bytes("https://plugins.qgis.org/x")
        requisicao_enviada = urlopen_mock.call_args[0][0]
        self.assertEqual(
            requisicao_enviada.headers["User-agent"],
            f"SIGMAI/{versao_esperada} QGIS-plugin-manager",
        )

    def test_versao_nao_esta_mais_cravada_no_codigo_fonte(self):
        fonte = inspect.getsource(plugin_tools)
        self.assertNotIn("SIGMAI/0.1 QGIS-plugin-manager", fonte)

    def test_leitura_da_versao_nao_importa_bridge_server_no_topo_do_modulo(self):
        # Um import de sigmai.bridge_server no topo deste arquivo reabre o
        # ciclo: bridge_server -> qgis_actions -> plugin_tools -> bridge_server.
        linhas_de_import = [
            linha for linha in Path(plugin_tools.__file__).read_text(encoding="utf-8").splitlines()
            if linha.startswith(("import ", "from "))
        ]
        self.assertFalse(any("bridge_server" in linha for linha in linhas_de_import))

    def test_self_plugin_version_le_do_metadata_txt_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp)
            (plugin / "metadata.txt").write_text("[general]\nversion=9.9.9-teste\n", encoding="utf-8")
            with patch.object(plugin_tools, "_current_plugin_path", return_value=plugin):
                self.assertEqual(plugin_tools._self_plugin_version(), "9.9.9-teste")

    def test_self_plugin_version_tem_fallback_quando_metadata_falta(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(plugin_tools, "_current_plugin_path", return_value=Path(tmp)):
                self.assertEqual(plugin_tools._self_plugin_version(), "0.0.0")


if __name__ == "__main__":
    unittest.main()
