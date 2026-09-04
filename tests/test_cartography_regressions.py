# -*- coding: utf-8 -*-
"""Regressões encontradas nas rodadas de estresse do compositor.

Cada teste aqui corresponde a um defeito real observado ao exercitar o
``compose_map`` contra dados de campo. São todos em Python puro (sem PyQGIS)
para rodarem na integração contínua.
"""

from __future__ import annotations

import unittest

from sigmai.cartography.layoutgrid import solve_layout
from sigmai.cartography.pagespec import PAGE_SIZES, resolve_page
from sigmai.cartography.compose import _equalisation_cost_advice
from sigmai.cartography.rulebook import (
    SCALEBAR_MIN_LENGTH_MM,
    _check_scalebar_proportion,
)
from sigmai.cartography.rulebook import (
    _check_legend_covers_visible_layers,
    _check_legend_has_no_phantoms,
    _check_source_credit,
)
from sigmai.cartography.scaling import (
    SCALEBAR_MAX_FRACTION,
    choose_publication_scale,
    scalebar_spec,
)
from sigmai.cartography.symbology import (
    OKABE_ITO,
    RESTYLABLE_RENDERERS,
    _tint,
)


class PageStrictness(unittest.TestCase):
    """Um formato inexistente virava A4 em silêncio."""

    def test_tolerante_por_padrao(self) -> None:
        self.assertEqual(resolve_page("A9 vertical").name, "A4")

    def test_estrito_recusa_formato_desconhecido(self) -> None:
        for entrada in ("A9 vertical", "folha grande", "A4 gigante"):
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValueError) as ctx:
                    resolve_page(entrada, strict=True)
                # A mensagem tem de listar o que é aceito, senão não ajuda.
                self.assertIn("A3", str(ctx.exception))

    def test_estrito_aceita_o_que_existe(self) -> None:
        for entrada in ("A3", "a3 portrait", "A4 paisagem", "LETTER retrato"):
            with self.subTest(entrada=entrada):
                spec = resolve_page(entrada, strict=True)
                self.assertIn(spec.name, PAGE_SIZES)

    def test_sugere_o_formato_proximo(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page("A33 portrait", strict=True)
        self.assertIn("A3", str(ctx.exception))


class ScaleBarLeftSegment(unittest.TestCase):
    """O segmento à esquerda do zero faz parte da barra e conta no comprimento."""

    def test_comprimento_declarado_bate_com_o_desenhado(self) -> None:
        for escala in (10_000, 100_000, 1_000_000, 6_900_000):
            with self.subTest(escala=escala):
                spec = scalebar_spec(escala, 200.0)
                desenhado = spec.units_per_segment * (spec.segments_right + spec.segments_left)
                self.assertAlmostEqual(
                    spec.total_ground_metres / (spec.total_ground_metres / desenhado),
                    desenhado,
                    places=6,
                )
                # É esta a verificação que importa: a largura anunciada tem de
                # corresponder ao total de segmentos efetivamente desenhados.
                esperado_mm = (spec.total_ground_metres / escala) * 1000.0
                self.assertAlmostEqual(spec.bar_width_mm, esperado_mm, places=6)

    def test_respeita_o_teto_de_largura(self) -> None:
        for teto in (30.0, 45.0, 60.0):
            with self.subTest(teto=teto):
                spec = scalebar_spec(1_000_000, 200.0, max_width_mm=teto)
                self.assertLessEqual(spec.bar_width_mm, teto + 1e-6)

    def test_nunca_ultrapassa_a_fracao_maxima(self) -> None:
        for escala in (5_000, 50_000, 500_000, 5_000_000):
            with self.subTest(escala=escala):
                spec = scalebar_spec(escala, 180.0)
                self.assertLessEqual(spec.frame_fraction, SCALEBAR_MAX_FRACTION + 1e-9)


class ScaleBarLegibility(unittest.TestCase):
    """CART022 media só a proporção; numa A2 isso reprovava barra legível."""

    def test_barra_longa_em_folha_grande_passa(self) -> None:
        resultado = _check_scalebar_proportion(
            {"scalebar": {"item_id": "b", "frame_fraction": 0.135, "bar_width_mm": 50.0}}
        )
        self.assertEqual(resultado.status, "pass")

    def test_barra_curta_em_termos_absolutos_reprova(self) -> None:
        resultado = _check_scalebar_proportion(
            {"scalebar": {"item_id": "b", "frame_fraction": 0.10, "bar_width_mm": 20.0}}
        )
        self.assertEqual(resultado.status, "fail")
        self.assertIn("20 mm", resultado.detail_pt)

    def test_limite_absoluto_e_o_declarado(self) -> None:
        logo_acima = _check_scalebar_proportion(
            {"scalebar": {"item_id": "b", "frame_fraction": 0.14,
                          "bar_width_mm": SCALEBAR_MIN_LENGTH_MM + 0.1}}
        )
        logo_abaixo = _check_scalebar_proportion(
            {"scalebar": {"item_id": "b", "frame_fraction": 0.14,
                          "bar_width_mm": SCALEBAR_MIN_LENGTH_MM - 0.1}}
        )
        self.assertEqual(logo_acima.status, "pass")
        self.assertEqual(logo_abaixo.status, "fail")

    def test_barra_longa_demais_continua_reprovando(self) -> None:
        resultado = _check_scalebar_proportion(
            {"scalebar": {"item_id": "b", "frame_fraction": 0.60, "bar_width_mm": 160.0}}
        )
        self.assertEqual(resultado.status, "fail")


class ScaleBarUnderMap(unittest.TestCase):
    """Coluna lateral estreita não comporta barra legível; a faixa sob o mapa sim."""

    def test_faixa_sob_o_mapa_e_mais_larga_que_a_coluna(self) -> None:
        na_coluna = solve_layout("A4 landscape", "publicacao")
        sob_o_mapa = solve_layout("A4 landscape", "publicacao", scale_bar_under_map=True)
        self.assertGreater(
            sob_o_mapa.slots["scale_bar"].width,
            na_coluna.slots["scale_bar"].width * 2,
        )

    def test_o_mapa_encolhe_para_abrir_a_faixa(self) -> None:
        na_coluna = solve_layout("A4 landscape", "publicacao")
        sob_o_mapa = solve_layout("A4 landscape", "publicacao", scale_bar_under_map=True)
        self.assertLess(sob_o_mapa.slots["map"].height, na_coluna.slots["map"].height)
        self.assertAlmostEqual(
            sob_o_mapa.slots["map"].width, na_coluna.slots["map"].width, places=6
        )

    def test_nada_sai_da_pagina(self) -> None:
        for page in ("A4 landscape", "A3 landscape", "A2 landscape", "LETTER landscape"):
            with self.subTest(page=page):
                plan = solve_layout(page, "publicacao", scale_bar_under_map=True)
                spec = resolve_page(page)
                for nome, rect in plan.slots.items():
                    self.assertTrue(
                        spec.contains(rect.x, rect.y, rect.width, rect.height),
                        f"{nome} saiu da página em {page}",
                    )

    def test_a_faixa_e_anunciada_nas_notas(self) -> None:
        plan = solve_layout("A4 landscape", "publicacao", scale_bar_under_map=True)
        self.assertTrue(any("faixa sob o mapa" in nota for nota in plan.notes))

    def test_sem_barra_a_opcao_nao_muda_nada(self) -> None:
        sem = solve_layout("A4 landscape", "publicacao", include_scale_bar=False)
        sob = solve_layout(
            "A4 landscape", "publicacao", include_scale_bar=False, scale_bar_under_map=True
        )
        self.assertAlmostEqual(sem.slots["map"].height, sob.slots["map"].height, places=6)


if __name__ == "__main__":
    unittest.main()


class ComparisonLegend(unittest.TestCase):
    """A legenda de uma folha de comparação responde pelos dois quadros."""

    def _observacao(self, listadas: list[str]) -> dict:
        return {
            "map": {"visible_layer_names": ["Municípios", "PE das Carnaúbas"]},
            "map_frames": [
                {"item_id": "main_map", "visible_layer_names": ["Municípios", "PE das Carnaúbas"]},
                {"item_id": "comparison_map", "visible_layer_names": ["Limite estadual", "Municípios"]},
            ],
            "legend": {"item_id": "legend", "layer_names": listadas},
        }

    def test_camada_so_do_segundo_painel_nao_e_fantasma(self) -> None:
        resultado = _check_legend_has_no_phantoms(
            self._observacao(["Municípios", "PE das Carnaúbas", "Limite estadual"])
        )
        self.assertEqual(resultado.status, "pass")

    def test_camada_ausente_do_segundo_painel_e_cobranca(self) -> None:
        resultado = _check_legend_covers_visible_layers(
            self._observacao(["Municípios", "PE das Carnaúbas"])
        )
        self.assertEqual(resultado.status, "fail")
        self.assertIn("Limite estadual", resultado.detail_pt)

    def test_camada_que_nao_esta_em_quadro_nenhum_ainda_e_fantasma(self) -> None:
        resultado = _check_legend_has_no_phantoms(
            self._observacao(["Municípios", "PE das Carnaúbas", "Limite estadual", "Hidrografia"])
        )
        self.assertEqual(resultado.status, "fail")
        self.assertIn("Hidrografia", resultado.detail_pt)

    def test_sem_quadros_extras_o_comportamento_e_o_de_antes(self) -> None:
        observacao = {
            "map": {"visible_layer_names": ["A", "B"]},
            "legend": {"item_id": "legend", "layer_names": ["A", "B", "C"]},
        }
        self.assertEqual(_check_legend_has_no_phantoms(observacao).status, "fail")


class SymbologyPalette(unittest.TestCase):
    """Duas camadas de polígono não podem sair com o mesmo preenchimento."""

    def test_tint_clareia_mantendo_o_matiz(self) -> None:
        for cor in OKABE_ITO:
            with self.subTest(cor=cor):
                claro = _tint(cor, 0.82)
                self.assertTrue(claro.startswith("#") and len(claro) == 7)
                escuros = [int(cor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
                claros = [int(claro.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
                for antes, depois in zip(escuros, claros):
                    self.assertGreaterEqual(depois, antes)

    def test_tints_de_matizes_diferentes_sao_diferentes(self) -> None:
        tints = {_tint(cor, 0.82) for cor in OKABE_ITO[:6]}
        self.assertEqual(len(tints), 6)

    def test_extremos(self) -> None:
        self.assertEqual(_tint("#0072B2", 1.0), "#FFFFFF")
        self.assertEqual(_tint("#0072B2", 0.0), "#0072B2")
        self.assertEqual(_tint("nao-e-cor", 0.5), "nao-e-cor")

    def test_estilo_embutido_de_kml_e_reestilizavel(self) -> None:
        # O KML traz o estilo do Google Earth: traço fino, sem preenchimento e
        # sem amostra na legenda. Preservá-lo entregava uma legenda vazia.
        self.assertIn("QgsEmbeddedSymbolRenderer", RESTYLABLE_RENDERERS)
        self.assertIn("QgsSingleSymbolRenderer", RESTYLABLE_RENDERERS)

    def test_renderizador_tematico_nao_e_reestilizavel(self) -> None:
        for nome in ("QgsCategorizedSymbolRenderer", "QgsGraduatedSymbolRenderer", "QgsRuleBasedRenderer"):
            with self.subTest(nome=nome):
                self.assertNotIn(nome, RESTYLABLE_RENDERERS)


class SourceAndAuthorship(unittest.TestCase):
    """CART007 conferia presença de rodapé, não procedência."""

    def _obs(self, texto: str) -> dict:
        return {"items": [{"id": "source", "role": "source", "type": "label", "text": texto}]}

    def test_so_a_assinatura_da_ferramenta_reprova(self) -> None:
        # É exatamente o que o compositor escreve sozinho quando o assistente
        # não pergunta nada ao usuário.
        resultado = _check_source_credit(
            self._obs("SIRGAS 2000 / UTM 23S (EPSG:31983) · 04/09/2026 · Produzido com SIGMAI/QGIS")
        )
        self.assertEqual(resultado.status, "fail")
        self.assertIn("data_source", resultado.detail_pt)
        self.assertIn("map_author", resultado.detail_pt)

    def test_fonte_sem_autoria_reprova(self) -> None:
        resultado = _check_source_credit(self._obs("Fonte: IBGE 2024 · 04/09/2026"))
        self.assertEqual(resultado.status, "fail")
        self.assertIn("map_author", resultado.detail_pt)
        self.assertNotIn("data_source", resultado.detail_pt)

    def test_autoria_sem_fonte_reprova(self) -> None:
        resultado = _check_source_credit(self._obs("Elaboração: MACIEL, L. S. C. · 04/09/2026"))
        self.assertEqual(resultado.status, "fail")
        self.assertIn("data_source", resultado.detail_pt)

    def test_fonte_e_autoria_aprovam(self) -> None:
        resultado = _check_source_credit(
            self._obs("Fonte: IBGE, Malha Municipal 2024 · Elaboração: MACIEL, L. S. C. · 2026")
        )
        self.assertEqual(resultado.status, "pass")

    def test_rodape_vazio_reprova(self) -> None:
        self.assertEqual(_check_source_credit({"items": []}).status, "fail")

    def test_aceita_os_marcadores_em_ingles(self) -> None:
        resultado = _check_source_credit(self._obs("Source: IBGE 2024 · Author: L. Maciel · 2026"))
        self.assertEqual(resultado.status, "pass")


class ScaleNeverZero(unittest.TestCase):
    """Escala arredondada a zero estourava com um ValueError longe da causa."""

    def test_escala_abaixo_de_um_vira_um(self) -> None:
        # Acontece quando graus são tomados por metros: a extensão da trilha em
        # EPSG:4326 tem 0,05 "unidades" de largura.
        for minimo, alvo in ((0.28, 0.296), (0.001, 0.0011), (0.05, 0.06)):
            with self.subTest(minimo=minimo):
                escala, _ = choose_publication_scale(minimo, alvo)
                self.assertGreaterEqual(escala, 1)

    def test_a_barra_aceita_o_que_a_escala_devolve(self) -> None:
        escala, _ = choose_publication_scale(0.28, 0.296)
        # Não pode levantar: era aqui que o ValueError cru aparecia.
        spec = scalebar_spec(escala, 200.0)
        self.assertGreater(spec.bar_width_mm, 0)

    def test_escalas_normais_seguem_iguais(self) -> None:
        self.assertEqual(choose_publication_scale(24000, 25000), (25000, "serie_cartografica"))


class HelpTabStrings(unittest.TestCase):
    """A aba de Ajuda existia nas strings e nunca tinha sido construída."""

    def test_toda_chave_de_ajuda_existe_nos_dois_idiomas(self) -> None:
        from sigmai.ui.strings import STRINGS

        chaves = [
            "tab_help", "help_title", "help_what_title", "help_what",
            "help_try_title", "help_try", "help_ask_title", "help_ask",
            "help_quality_title", "help_quality", "help_refuse_title", "help_refuse",
            "help_privacy_title", "help_privacy", "help_docs",
        ]
        for idioma in ("pt-BR", "en"):
            for chave in chaves:
                with self.subTest(idioma=idioma, chave=chave):
                    self.assertTrue(STRINGS[idioma].get(chave), f"{chave} vazio em {idioma}")

    def test_os_dois_idiomas_tem_o_mesmo_conjunto_de_chaves(self) -> None:
        from sigmai.ui.strings import STRINGS

        self.assertEqual(set(STRINGS["pt-BR"]), set(STRINGS["en"]))

    def test_as_frases_de_exemplo_sao_pedidos_de_verdade(self) -> None:
        from sigmai.ui.strings import STRINGS

        # Se as frases de exemplo virarem jargão, a aba perde a razão de existir.
        exemplos = STRINGS["pt-BR"]["help_try"]
        self.assertGreaterEqual(exemplos.count("•"), 5)
        for termo in ("EPSG", "CRS", "layer_ids", "compose_map"):
            self.assertNotIn(termo, exemplos)


class EqualisationCost(unittest.TestCase):
    """Igualar as escalas é honesto, mas pode esvaziar um dos painéis."""

    def test_ordens_de_grandeza_distantes_geram_aviso(self) -> None:
        # Parque de 10.000 ha (1:250.000) contra um estado inteiro
        # (1:5.000.000): depois de igualar, o parque ocupa 0,25% do quadro.
        notas = _equalisation_cost_advice((250_000, 5_000_000), 5_000_000)
        self.assertEqual(len(notas), 1)
        self.assertIn("painel 1", notas[0])
        self.assertIn("comparison_same_scale=false", notas[0])
        self.assertIn("include_inset", notas[0])

    def test_escalas_proximas_nao_geram_aviso(self) -> None:
        # 1:200.000 contra 1:250.000: o assunto ainda ocupa 64% do quadro.
        self.assertEqual(_equalisation_cost_advice((200_000, 250_000), 250_000), [])

    def test_o_limiar_e_medido_em_area_e_nao_em_escala(self) -> None:
        # A área cai com o quadrado da razão: 1:100.000 -> 1:1.000.000 deixa 1%.
        self.assertEqual(len(_equalisation_cost_advice((100_000, 1_000_000), 1_000_000)), 1)
        # Já 1:100.000 -> 1:600.000 deixa 2,8%, acima do limiar.
        self.assertEqual(_equalisation_cost_advice((100_000, 600_000), 600_000), [])

    def test_valores_degenerados_nao_estouram(self) -> None:
        for antes in ((0, 100), (100, 0), (-5, 100)):
            with self.subTest(antes=antes):
                _equalisation_cost_advice(antes, 100)
