"""Os fundamentos das regras têm de ser rastreáveis, e os limiares, declarados.

A revisão do capítulo da dissertação encontrou duas regras citando normas ABNT
que não dizem o que lhes era atribuído (NBR 6027 trata de sumário; NBR 13133,
de levantamento topográfico) e oito citando "convenção" ou "boas práticas" sem
fonte. Estes testes impedem que isso volte: cada referência ou nomeia uma fonte
verificável (decreto, resolução, artigo, livro, instrução a autores) ou diz
explicitamente que é decisão de projeto do SIGMAI; e as funções puras da
análise de sensibilidade continuam a rodar sem QGIS.
"""

from __future__ import annotations

import re
import unittest

from sigmai.cartography.rulebook import RULES, SEVERITY_PENALTY, rulebook_manifest

FONTES_ACEITAS = (
    "Decreto nº 89.817/1984",
    "IBGE (1999)",
    "IBGE, Resolução PR nº 1/2015",
    "Brewer (2016)",
    "Slocum et al. (2009)",
    "Snyder (1987)",
    "Machado, Oliveira & Fernandes (2009)",
    "Okabe & Ito (2008)",
    "Robertson (1977)",
    "PLOS ONE, Figure requirements",
    "Rodriguésia, Normas para autores",
    "Transactions in GIS, Author Guidelines",
    "Decisão de projeto do SIGMAI",
    "decisão de projeto do SIGMAI",
)

VAGAS = ("ABNT", "NBR", "convenção cartográfica", "Convenção de", "Boas práticas", "boas práticas",
         "Instruções a autores de periódicos científicos")


class ReferenciasDasRegras(unittest.TestCase):
    def test_toda_regra_cita_fonte_verificavel_ou_declara_decisao_de_projeto(self):
        for rule in RULES:
            with self.subTest(rule.id):
                self.assertTrue(any(fonte in rule.reference for fonte in FONTES_ACEITAS),
                                f"{rule.id}: referência sem fonte rastreável nem declaração de decisão de projeto: {rule.reference!r}")

    def test_nenhuma_regra_cita_norma_errada_ou_convencao_sem_fonte(self):
        for rule in RULES:
            with self.subTest(rule.id):
                for vaga in VAGAS:
                    self.assertNotIn(vaga, rule.reference, f"{rule.id}: {vaga!r} em {rule.reference!r}")

    def test_documentacao_do_qgis_aparece_como_verificacao_e_nao_como_fundamento(self):
        """A API do QGIS diz COMO a regra é verificada; o fundamento cartográfico vem antes."""
        for rule in RULES:
            if "QGIS" in rule.reference:
                with self.subTest(rule.id):
                    self.assertIn("verificação: QGIS", rule.reference, rule.reference)
                    self.assertLess(rule.reference.index("verificação"), rule.reference.index("QGIS"))

    def test_limiares_citados_na_referencia_batem_com_o_codigo(self):
        from sigmai.cartography import rulebook, vision

        por_id = {rule.id: rule.reference for rule in RULES}
        self.assertIn(f"ΔE*ab < {vision.CONFUSABLE_DELTA_E:g}", por_id["CART070"])
        self.assertIn(f"{int(rulebook.SCALEBAR_MIN_FRACTION * 100)} % a {int(rulebook.SCALEBAR_MAX_FRACTION * 100)} %", por_id["CART022"])
        self.assertIn(f"{rulebook.MIN_PRINT_FONT_PT:g} pt", por_id["CART044"])
        self.assertIn(f"{int(rulebook.FRAME_BAND_EMPTY_MAX * 100)} % de cobertura", por_id["CART069"])
        self.assertIn(f"{rulebook.LEGEND_OVERFLOW_TOLERANCE_MM:g}".replace(".", ","), por_id["CART072"])
        self.assertIn(f"croma ≥ {rulebook.GREYSCALE_CHROMA_MIN}", por_id["CART073"])
        self.assertIn(f"{rulebook.GREYSCALE_MAX_CHROMATIC_FRACTION * 100:g} %".replace(".", ","), por_id["CART073"])
        self.assertEqual(SEVERITY_PENALTY, {"error": 15.0, "warning": 5.0, "advice": 1.5})

    def test_manifesto_expoe_as_referencias(self):
        manifesto = rulebook_manifest()
        regras = [r for grupo in manifesto["categories"].values() for r in grupo]
        self.assertEqual(len(regras), len(RULES))
        self.assertTrue(all(r["reference"] for r in regras))
        self.assertIn("sensibilidade_limiares", manifesto["thresholds_provenance"])
        from sigmai.cartography.vision import CONFUSABLE_DELTA_E
        self.assertEqual(manifesto["thresholds"]["colour_vision_delta_e_min"], CONFUSABLE_DELTA_E)


class ParametrosDeclaradosDoCompositor(unittest.TestCase):
    """Os limiares editoriais do compositor são constantes nomeadas — o que a
    análise de sensibilidade varia e o capítulo declara."""

    def test_constantes_existem_com_os_valores_declarados(self):
        from sigmai.cartography import compose, layoutgrid, scaling

        self.assertEqual(compose.LAYOUT_SWITCH_GAIN, 1.12)
        self.assertEqual(scaling.MAX_EFFECTIVE_MARGIN_PERCENT, 25.0)
        self.assertEqual(layoutgrid.FONT_SCALE_EXPONENT, 0.62)
        self.assertEqual((layoutgrid.FONT_SCALE_MIN, layoutgrid.FONT_SCALE_MAX), (0.72, 2.6))
        self.assertEqual(layoutgrid.EMPTY_CELL_PENALTY, 0.35)

    def test_ganho_de_troca_e_lido_da_constante(self):
        import inspect

        from sigmai.cartography import compose

        fonte = inspect.getsource(compose)
        self.assertNotIn(">= 1.12", fonte)
        self.assertEqual(fonte.count("LAYOUT_SWITCH_GAIN"), 4)  # definição + três usos


class AnaliseDeSensibilidadeSemQgis(unittest.TestCase):
    def test_paleta_janela_do_limiar(self):
        from tools.threshold_sensitivity import analyse_palette

        paleta = analyse_palette()
        classicos = paleta["pares clássicos"]["marcados_por_limiar"]
        okabe = paleta["Okabe & Ito (2008) pura"]["marcados_por_limiar"]
        # Em 15 os três pares de calibração são acusados e a paleta de Okabe & Ito não.
        self.assertGreaterEqual(classicos["15"], 3)
        self.assertEqual(okabe["15"], 0)
        self.assertGreater(okabe["18"], 0)
        atuais = paleta["preenchimentos atuais (POLYGON_FILLS)"]["pares"]
        primeiros = [p for p in atuais if all(int(n) <= 4 for n in re.findall(r"cor (\d)", p["par"]))]
        self.assertTrue(all(p["dE_min_simulado"] >= 15 for p in primeiros), "os quatro primeiros preenchimentos devem ser mutuamente distinguíveis")

    def test_compositor_com_extensoes_sinteticas(self):
        from tools.threshold_sensitivity import analyse_composer

        extensoes = {"alto": {"width": 300_000.0, "height": 500_000.0, "crs": "EPSG:5880"},
                     "largo": {"width": 500_000.0, "height": 250_000.0, "crs": "EPSG:5880"}}
        mapas = [{"rotulo": "x", "extent": {"raw_scale_denominator": 2_310_000.0}, "scale_denominator": 2_500_000}]
        saida = analyse_composer(extensoes, mapas)
        decisoes = {d["limiar"]: d for d in saida["ganho_de_troca"]["decisoes"]}
        self.assertGreaterEqual(decisoes[1.0]["trocas_de_orientacao"], decisoes[1.12]["trocas_de_orientacao"])
        self.assertEqual(decisoes[1.3]["trocas_de_orientacao"], 0)
        grades = saida["custo_por_celula_vazia"]["varredura"]
        atual = next(l for l in grades if l["atual"])
        self.assertEqual(atual["grades"]["3 painéis / A3 paisagem"], "3x1")
        self.assertEqual(atual["grades"]["4 painéis / A4 paisagem"], "2x2")
        margem = next(l for l in saida["margem_efetiva_maxima"]["varredura"] if l["atual"])
        self.assertEqual(margem["escalas_diferentes_da_atual"], 0)


if __name__ == "__main__":
    unittest.main()
