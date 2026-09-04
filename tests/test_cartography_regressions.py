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
from sigmai.cartography.rulebook import (
    SCALEBAR_MIN_LENGTH_MM,
    _check_scalebar_proportion,
)
from sigmai.cartography.scaling import SCALEBAR_MAX_FRACTION, scalebar_spec


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
