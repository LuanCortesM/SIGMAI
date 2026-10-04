"""Opções renomeadas continuam valendo para quem as tinha salvo.

Na 1.1.4 a opção ``persist_token`` virou ``persist_access_key``: o scanner de
segurança do repositório de plugins do QGIS (Bandit, B105) bloqueava a versão
por causa do nome. Quem tinha ligado "manter o mesmo token" não pode perder a
escolha na atualização.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sigmai.plugin import SETTINGS_DEFAULTS, migrate_legacy_settings  # noqa: E402


class ConfiguracoesFalsas:
    """O pedaço do ``QgsSettings`` que a migração usa."""

    def __init__(self, valores: dict[str, object]) -> None:
        self.valores = dict(valores)

    def contains(self, chave: str) -> bool:
        return chave in self.valores

    def value(self, chave: str, padrao: object = None, type: type = str) -> object:  # noqa: A002
        valor = self.valores.get(chave, padrao)
        if type is bool and isinstance(valor, str):
            return valor.lower() == "true"
        return valor

    def setValue(self, chave: str, valor: object) -> None:  # noqa: N802 (API do Qt)
        self.valores[chave] = valor

    def remove(self, chave: str) -> None:
        self.valores.pop(chave, None)


class MigracaoDaOpcaoDeManterOToken(unittest.TestCase):
    def test_opcao_ligada_continua_ligada_com_o_nome_novo(self) -> None:
        configuracoes = ConfiguracoesFalsas({"SIGMAI/persist_token": "true"})
        migrate_legacy_settings(configuracoes)
        self.assertEqual(configuracoes.valores, {"SIGMAI/persist_access_key": True})

    def test_opcao_desligada_continua_desligada(self) -> None:
        configuracoes = ConfiguracoesFalsas({"SIGMAI/persist_token": False})
        migrate_legacy_settings(configuracoes)
        self.assertEqual(configuracoes.valores, {"SIGMAI/persist_access_key": False})

    def test_nome_novo_ja_gravado_prevalece(self) -> None:
        configuracoes = ConfiguracoesFalsas({"SIGMAI/persist_token": True, "SIGMAI/persist_access_key": False})
        migrate_legacy_settings(configuracoes)
        self.assertEqual(configuracoes.valores, {"SIGMAI/persist_access_key": False})

    def test_sem_opcao_antiga_nada_muda(self) -> None:
        configuracoes = ConfiguracoesFalsas({"SIGMAI/ui_language": "en"})
        migrate_legacy_settings(configuracoes)
        self.assertEqual(configuracoes.valores, {"SIGMAI/ui_language": "en"})

    def test_padrao_continua_desligado(self) -> None:
        self.assertIs(SETTINGS_DEFAULTS["persist_access_key"], False)
        self.assertNotIn("persist_token", SETTINGS_DEFAULTS)


class MigracaoComQgsSettingsDeVerdade(unittest.TestCase):
    """O mesmo, contra o ``QgsSettings`` real, gravando num ``.ini`` temporário.

    Um ``QgsSettings()`` sem argumentos só grava depois que algum teste
    iniciou o ``QgsApplication``; com arquivo próprio o teste não depende da
    ordem da suíte nem toca nas configurações do usuário.
    """

    def setUp(self) -> None:
        try:
            from qgis.core import QgsSettings
            from qgis.PyQt.QtCore import QSettings
        except ImportError:
            self.skipTest("PyQGIS indisponível")
        pasta = tempfile.TemporaryDirectory(prefix="sigmai_settings_")
        self.addCleanup(pasta.cleanup)
        formato = getattr(getattr(QSettings, "Format", QSettings), "IniFormat")
        arquivo = str(Path(pasta.name) / "QGIS.ini")
        self.abrir = lambda: QgsSettings(arquivo, formato)

    def test_opcao_ligada_sobrevive_a_atualizacao(self) -> None:
        antes = self.abrir()
        antes.setValue("SIGMAI/persist_token", True)
        antes.sync()
        del antes
        migrar = self.abrir()
        migrate_legacy_settings(migrar)
        migrar.sync()
        del migrar
        depois = self.abrir()
        self.assertFalse(depois.contains("SIGMAI/persist_token"))
        self.assertTrue(depois.value("SIGMAI/persist_access_key", False, type=bool))


if __name__ == "__main__":
    unittest.main()
