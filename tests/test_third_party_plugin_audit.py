# -*- coding: utf-8 -*-
"""Auditar e executar um plugin de TERCEIRO — o caso de quem desenvolve um.

A corrente é: pessoa pede → IA traduz → SIGMAI dirige o QGIS → o plugin do
terceiro executa. Estes testes fixam os dois defeitos que impediam o último
elo, achados exercitando um plugin de ensaio que registra um provedor de
Processing de verdade (``tools/exercise_third_party_plugin.py``).
"""

from __future__ import annotations

import unittest

from sigmai.qgis_actions.plugin_tools import (
    DEDICATED_PLUGIN_ADAPTERS,
    _matches_plugin_provider,
    run_plugin_algorithm_safe,
)
from sigmai.validators import ValidationError


class AdaptadorDedicado(unittest.TestCase):
    """A recusa não dizia que existia outro caminho."""

    def test_a_recusa_aponta_o_caminho_generico(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            run_plugin_algorithm_safe({"algorithm_id": "meuplugin:meualgoritmo"}, {})
        mensagem = str(ctx.exception)
        # Sem isto, quem audita o próprio plugin conclui — com razão — que o
        # SIGMAI não executa plugin de terceiro.
        self.assertIn("run_plugin_algorithm_generic_safe", mensagem)
        self.assertIn("meuplugin:meualgoritmo", mensagem)

    def test_a_recusa_carrega_o_caminho_alternativo_nos_detalhes(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            run_plugin_algorithm_safe({"algorithm_id": "x:y"}, {})
        self.assertEqual(ctx.exception.details.get("use_instead"), "run_plugin_algorithm_generic_safe")
        self.assertEqual(ctx.exception.code, "PLUGIN_ALGORITHM_NOT_ALLOWED")

    def test_a_lista_de_adaptadores_e_pequena_e_explicita(self) -> None:
        # Um adaptador dedicado só se justifica com verificação caso a caso;
        # a lista crescer sozinha seria o contrário disso.
        self.assertIsInstance(DEDICATED_PLUGIN_ADAPTERS, frozenset)
        self.assertLessEqual(len(DEDICATED_PLUGIN_ADAPTERS), 5)
        for identificador in DEDICATED_PLUGIN_ADAPTERS:
            with self.subTest(identificador=identificador):
                self.assertIn(":", identificador)

    def test_algoritmo_sem_id_e_recusado(self) -> None:
        with self.assertRaises(ValidationError):
            run_plugin_algorithm_safe({}, {})


class ProcessingSemOPluginProcessing(unittest.TestCase):
    """O executor genérico fazia ``import processing`` cru.

    ``processing`` é o *plugin* Processing. Com ele desativado — ou num QGIS
    sem interface — o import falha e a resposta era "QGIS Processing is not
    available", como se o QGIS não tivesse Processing, quando o núcleo tem
    tudo. O caminho comum já usava o bootstrap; este tinha ficado para trás, e
    o efeito era não executar algoritmo de plugin nenhum nesse cenário.
    """

    def test_o_executor_generico_usa_o_bootstrap(self) -> None:
        import inspect

        from sigmai.qgis_actions import plugin_tools

        fonte = inspect.getsource(plugin_tools.run_plugin_algorithm_generic_safe)
        self.assertIn("processing_bootstrap", fonte)
        # O import cru é justamente o defeito: não pode voltar.
        self.assertNotIn("import processing  # type: ignore", fonte)

    def test_o_bootstrap_expoe_o_que_o_executor_precisa(self) -> None:
        from sigmai.qgis_actions import processing_bootstrap

        for nome in ("ensure_processing_ready", "resolve_algorithm", "run_algorithm"):
            with self.subTest(nome=nome):
                self.assertTrue(callable(getattr(processing_bootstrap, nome)))


class CasamentoDePluginComProvedor(unittest.TestCase):
    """Descobrir quais algoritmos são daquele plugin."""

    def test_casa_pelo_id_do_provedor(self) -> None:
        self.assertTrue(_matches_plugin_provider("trilhateste", "TrilhaTeste", "trilhateste", "TrilhaTeste"))

    def test_casa_pelo_nome_de_exibicao(self) -> None:
        self.assertTrue(_matches_plugin_provider("qgis2web", "qgis2web", "qgis2web", "qgis2web"))

    def test_nao_casa_plugin_diferente(self) -> None:
        self.assertFalse(_matches_plugin_provider("trilhateste", "TrilhaTeste", "gdal", "GDAL"))

    def test_nome_vazio_nao_casa_com_tudo(self) -> None:
        # Um needle vazio está contido em qualquer string: sem o filtro, um
        # plugin sem nome reivindicaria todos os algoritmos do QGIS.
        self.assertFalse(_matches_plugin_provider("", "", "gdal", "GDAL"))


if __name__ == "__main__":
    unittest.main()
