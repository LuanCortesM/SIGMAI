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


class PlanoDeTesteDoBriefing(unittest.TestCase):
    """O briefing traz a ordem de passos que não quebra nada.

    Um assistente sem plano começa pela execução, que é o passo mais caro de
    errar. A ordem — estrutura, imports, simulação, execução — é a mesma que um
    revisor humano seguiria, e é montada a partir do que aquele plugin tem.
    """

    def test_plugin_com_algoritmo_termina_em_execucao(self) -> None:
        from sigmai.qgis_actions.plugin_tools import _briefing_test_plan

        plano = _briefing_test_plan("x", [{"id": "x:alg"}], {})
        acoes = [passo["acao"] for passo in plano]
        self.assertEqual(acoes[0], "check_plugin_structure")
        self.assertEqual(acoes[1], "check_plugin_imports")
        self.assertIn("dry_run_plugin_algorithm_generic", acoes[2])
        self.assertIn("run_plugin_algorithm_generic_safe", acoes[3])
        # A simulação vem SEMPRE antes da execução.
        self.assertLess(
            next(i for i, a in enumerate(acoes) if "dry_run" in a),
            next(i for i, a in enumerate(acoes) if "generic_safe" in a),
        )

    def test_plugin_sem_algoritmo_nao_sugere_executar(self) -> None:
        from sigmai.qgis_actions.plugin_tools import _briefing_test_plan

        acoes = [p["acao"] for p in _briefing_test_plan("x", [], {})]
        self.assertNotIn("run_plugin_algorithm_generic_safe", " ".join(acoes))
        self.assertIn("list_plugin_processing_algorithms", acoes)

    def test_plugin_de_interface_avisa_que_nao_ha_o_que_acionar(self) -> None:
        from sigmai.qgis_actions.plugin_tools import _briefing_test_plan

        for superficie in ("menu_actions", "dialogs", "dock_widgets"):
            with self.subTest(superficie=superficie):
                plano = _briefing_test_plan("x", [], {superficie: True})
                self.assertTrue(any("só de interface" in p["acao"] for p in plano))

    def test_cada_passo_diz_por_que_existe(self) -> None:
        from sigmai.qgis_actions.plugin_tools import _briefing_test_plan

        for plano in (_briefing_test_plan("x", [{"id": "x:a"}], {}), _briefing_test_plan("x", [], {})):
            for passo in plano:
                with self.subTest(passo=passo["acao"]):
                    self.assertTrue(passo["porque"].strip())


class BriefingEhLeituraPura(unittest.TestCase):
    """O briefing não altera nada e não vaza código-fonte."""

    def test_e_declarado_somente_leitura(self) -> None:
        from sigmai.permissions import READ_ONLY, permission_for

        permissao = permission_for("brief_plugin")
        self.assertIsNotNone(permissao)
        self.assertEqual(permissao.permission_level, READ_ONLY)
        self.assertFalse(permissao.requires_confirmation)

    def test_o_limite_de_contrato_completo_e_modesto(self) -> None:
        from sigmai.qgis_actions.plugin_tools import BRIEFING_FULL_CONTRACT_LIMIT

        # Contexto gasto é resposta pior: um plugin com cem algoritmos não pode
        # despejar cem contratos inteiros na janela do assistente.
        self.assertLessEqual(BRIEFING_FULL_CONTRACT_LIMIT, 25)
        self.assertGreaterEqual(BRIEFING_FULL_CONTRACT_LIMIT, 5)

    def test_a_acao_esta_registrada_no_catalogo(self) -> None:
        import inspect

        from sigmai.qgis_actions import register_actions

        self.assertIn("brief_plugin", inspect.getsource(register_actions))
