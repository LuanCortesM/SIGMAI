# -*- coding: utf-8 -*-
"""Defeitos de reconhecimento de página achados pelos caçadores.

Cada classe aqui corresponde a um dos sete defeitos do relatório: um pedido
de orientação numa língua além de português/inglês, ``orientation`` sozinho
fora da string ``page``, tipos errados que estouravam exceção crua, ``page``
escapando do modo estrito por não ser string, digitação errada sem sugestão,
``margin_mm`` em formatos que a ferramenta não sabia interpretar, e margens
que engolem a página inteira sem que nada avise.
"""

from __future__ import annotations

import unittest

from sigmai.cartography.layoutgrid import solve_layout
from sigmai.cartography.pagespec import (
    MIN_MARGIN_MM,
    PAGE_SIZES,
    _ORIENTATION_VOCAB,
    resolve_page,
)


class OrientationVocabulary(unittest.TestCase):
    """Item 1 — só português e inglês eram reconhecidos; o resto do mundo não."""

    # Um representante de cada língua do briefing, com o pedido exatamente
    # como um usuário real escreveria (maiúsculas variadas, sem sotaque
    # onde a língua permite deixar de acentuar).
    CASOS_LANDSCAPE = {
        "fr": "A4 paysage",
        "es": "A4 apaisado",
        "pt-PT": "A4 apaisado",
        "it": "A4 orizzontale",
        "de": "A4 Querformat",
    }
    CASOS_PORTRAIT = {
        "it": "A4 verticale",
        "de": "A3 Hochformat",
    }

    def test_paisagem_em_varias_linguas(self) -> None:
        for lingua, pedido in self.CASOS_LANDSCAPE.items():
            with self.subTest(lingua=lingua, pedido=pedido):
                spec = resolve_page(pedido, strict=True)
                self.assertEqual(spec.orientation, "landscape")

    def test_retrato_em_varias_linguas(self) -> None:
        for lingua, pedido in self.CASOS_PORTRAIT.items():
            with self.subTest(lingua=lingua, pedido=pedido):
                spec = resolve_page(pedido, strict=True)
                self.assertEqual(spec.orientation, "portrait")

    def test_frase_francesa_de_duas_palavras(self) -> None:
        # "à l'italienne"/"à la française" são termos tipográficos consagrados,
        # não uma única palavra — o reconhecedor precisa comparar a sequência
        # de tokens, não só token a token.
        self.assertEqual(resolve_page("A3 à l'italienne", strict=True).orientation, "landscape")
        self.assertEqual(resolve_page("A3 à la française", strict=True).orientation, "portrait")

    def test_toda_a_vocabulario_resolve_para_a_orientacao_certa(self) -> None:
        # Varredura: cada termo do vocabulário — de qualquer uma das ~20
        # línguas cobertas — tem de bater com a orientação que o dicionário
        # declara, nos dois modos (estrito e tolerante), sozinho como
        # 'orientation' e embutido na string de 'page'.
        for termo, esperado in _ORIENTATION_VOCAB.items():
            for strict in (True, False):
                with self.subTest(termo=termo, strict=strict, via="orientation"):
                    spec = resolve_page(orientation=termo, strict=strict)
                    self.assertEqual(spec.orientation, esperado)
                with self.subTest(termo=termo, strict=strict, via="page"):
                    spec = resolve_page(f"A4 {termo}", strict=strict)
                    self.assertEqual(spec.orientation, esperado)

    def test_comparacao_ignora_caixa_e_acento_latino(self) -> None:
        for pedido in ("A4 PAISAGEM", "a4 Paisagem", "A4 PAYSAGE", "A4 QUERFORMAT"):
            with self.subTest(pedido=pedido):
                self.assertEqual(resolve_page(pedido, strict=True).orientation, "landscape")
        # "retrato" sem qualquer acento (o "á" não existe nessa palavra, mas
        # "français" sem cedilha é o caso real de alguém digitando rápido).
        self.assertEqual(resolve_page("A3 a la francaise", strict=True).orientation, "portrait")


class OrientationStandalone(unittest.TestCase):
    """Item 2 — 'orientation' fora da string 'page' só entendia inglês literal
    e caía em landscape sem avisar, mesmo quando o pedido era retrato."""

    def test_orientation_sozinho_em_portugues(self) -> None:
        spec = resolve_page(orientation="retrato")
        self.assertEqual(spec.orientation, "portrait")

    def test_orientation_sozinho_em_alemao(self) -> None:
        spec = resolve_page(orientation="Hochformat")
        self.assertEqual(spec.orientation, "portrait")

    def test_orientation_sozinho_como_frase(self) -> None:
        # "portrait haut": a palavra reconhecida (portrait) pode vir
        # acompanhada de outra que não está no vocabulário.
        spec = resolve_page(orientation="portrait haut")
        self.assertEqual(spec.orientation, "portrait")

    def test_estrito_recusa_orientation_nao_reconhecida(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page("A4", orientation="noroeste", strict=True)
        self.assertIn("Orientação", str(ctx.exception))

    def test_tolerante_mantem_o_padrao_quando_nao_reconhece(self) -> None:
        # Sem strict, uma orientação que não bate com nada cai no padrão
        # (landscape) em vez de recusar — mesmo comportamento de sempre para
        # texto desconhecido, só que agora por decisão explícita, não porque
        # o valor nunca foi comparado com o vocabulário.
        spec = resolve_page("A4", orientation="noroeste")
        self.assertEqual(spec.orientation, "landscape")


class OrientationTypeSafety(unittest.TestCase):
    """Item 3 — orientation não-string estourava AttributeError em .lower()."""

    def test_inteiro_vira_recusa_nao_crash(self) -> None:
        for strict in (True, False):
            with self.subTest(strict=strict):
                with self.assertRaises(ValueError) as ctx:
                    resolve_page("A4", orientation=123, strict=strict)
                self.assertIn("texto", str(ctx.exception))

    def test_lista_vira_recusa_nao_crash(self) -> None:
        with self.assertRaises(ValueError):
            resolve_page("A4", orientation=["landscape"], strict=True)

    def test_dict_com_orientation_nao_string_tambem_nao_crash(self) -> None:
        # O mesmo bug existia pelo campo 'orientation' dentro de um 'page'
        # dict, não só pelo argumento solto.
        with self.assertRaises(ValueError):
            resolve_page({"name": "A4", "orientation": 7}, strict=True)


class PageTypeStrictness(unittest.TestCase):
    """Item 4 — 'page' só era validado quando já era string; qualquer outro
    tipo (ou dict malformado) escapava do modo estrito e virava A4 em silêncio."""

    def test_inteiro_e_recusado_em_modo_estrito(self) -> None:
        with self.assertRaises(ValueError):
            resolve_page(150000, strict=True)

    def test_inteiro_cai_no_padrao_em_modo_tolerante(self) -> None:
        # Comportamento tolerante preservado de propósito: só o modo estrito
        # (o usado quando quem pediu foi um assistente) precisa recusar.
        spec = resolve_page(150000)
        self.assertEqual(spec.name, "A4")

    def test_lista_e_recusada_em_modo_estrito(self) -> None:
        with self.assertRaises(ValueError):
            resolve_page(["A4", "landscape"], strict=True)

    def test_dict_com_name_desconhecido_e_recusado(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page({"name": "A9"}, strict=True)
        self.assertIn("A9", str(ctx.exception))

    def test_dict_com_width_sem_height_e_recusado(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page({"width_mm": 500}, strict=True)
        self.assertIn("height_mm", str(ctx.exception))

    def test_dict_com_height_sem_width_e_recusado(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page({"height_mm": 500}, strict=True)
        self.assertIn("width_mm", str(ctx.exception))

    def test_dict_com_dimensao_nao_numerica_e_recusado_com_frase_humana(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page({"width_mm": "300mm", "height_mm": 200}, strict=True)
        mensagem = str(ctx.exception)
        # A regressão específica: a mensagem crua do Python ("could not
        # convert string to float") não pode vazar para quem pediu o mapa.
        self.assertNotIn("could not convert", mensagem)
        self.assertIn("width_mm", mensagem)

    def test_dict_com_dimensao_negativa_e_recusado(self) -> None:
        with self.assertRaises(ValueError):
            resolve_page({"width_mm": -10, "height_mm": 200}, strict=True)

    def test_dict_correto_continua_aceito(self) -> None:
        spec = resolve_page({"width_mm": 300, "height_mm": 200, "name": "personalizado"}, strict=True)
        self.assertEqual((spec.width_mm, spec.height_mm), (300.0, 200.0))


class OrientationTypoSuggestions(unittest.TestCase):
    """Item 5 — erro de digitação na orientação não recebia sugestão nenhuma,
    só a lista de tamanhos de página."""

    def test_sugere_o_termo_de_orientacao_proximo(self) -> None:
        casos = {
            "A4 paisgaem": "paisagem",
            "A4 retratto": "retrato",
            "A4 landscpae": "landscape",
            "A4 orizontal": "horizontal",
        }
        for pedido, esperado in casos.items():
            with self.subTest(pedido=pedido):
                with self.assertRaises(ValueError) as ctx:
                    resolve_page(pedido, strict=True)
                self.assertIn(esperado, str(ctx.exception))

    def test_mensagem_nao_despeja_o_vocabulario_inteiro(self) -> None:
        # A recusa tem de mencionar que orientação aceita várias línguas, com
        # dois ou três exemplos — não as ~50 palavras do vocabulário inteiro.
        with self.assertRaises(ValueError) as ctx:
            resolve_page("A4 paisgaem", strict=True)
        mensagem = str(ctx.exception)
        # A mensagem cita 2-3 exemplos (paisagem/retrato, landscape/portrait,
        # Querformat/Hochformat) — termos de outras línguas do vocabulário,
        # que não fazem parte desses exemplos, não deveriam aparecer.
        for termo_distante in ("orizzontale", "verticale", "panoramico", "quer", "hoch", "tumbado", "paysage"):
            self.assertNotIn(termo_distante, mensagem)


class MarginFormats(unittest.TestCase):
    """Item 6 — margin_mm em formatos que não fossem número/dict escala ou
    número simples estouravam TypeError/ValueError cru do Python."""

    def test_lista_de_quatro_e_aceita_na_ordem_css(self) -> None:
        # Decisão de produto: uma lista de 4 números é aceita, na mesma ordem
        # que CSS usa para 'margin' — topo, direita, baixo, esquerda — por
        # ser a convenção que mais gente já viu.
        spec = resolve_page("A4", margin_mm=[10, 20, 30, 40])
        self.assertEqual(
            (spec.margin_top_mm, spec.margin_right_mm, spec.margin_bottom_mm, spec.margin_left_mm),
            (10.0, 20.0, 30.0, 40.0),
        )

    def test_lista_de_tamanho_errado_e_recusada_com_frase_util(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page("A4", margin_mm=[10, 20, 30])
        self.assertIn("4", str(ctx.exception))

    def test_none_dentro_da_lista_nao_crasha(self) -> None:
        with self.assertRaises(ValueError):
            resolve_page("A4", margin_mm=[10, None, 30, 40])

    def test_string_como_margem_e_recusada_com_frase_humana(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page("A4", margin_mm="dez")
        self.assertNotIn("could not convert", str(ctx.exception))

    def test_dict_com_valor_nao_numerico_e_recusado_com_frase_humana(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_page("A4", margin_mm={"top": "muita"})
        self.assertNotIn("could not convert", str(ctx.exception))

    def test_tipo_nao_reconhecido_e_recusado(self) -> None:
        with self.assertRaises(ValueError):
            resolve_page("A4", margin_mm=object())

    def test_margem_pequena_ainda_respeita_o_piso_de_impressao(self) -> None:
        spec = resolve_page("A4", margin_mm=[0.1, 0.1, 0.1, 0.1])
        for valor in (spec.margin_top_mm, spec.margin_right_mm, spec.margin_bottom_mm, spec.margin_left_mm):
            self.assertGreaterEqual(valor, MIN_MARGIN_MM)


class InsufficientContentArea(unittest.TestCase):
    """Item 7 — um piso de 20 mm em layoutgrid.py mascarava margens absurdas
    com um mapa quase em branco; sem grade, o mesmo pedido estourava mais
    adiante em scaling.py. Agora os dois caminhos recusam do mesmo jeito, na
    hora de resolver a página — antes de qualquer decisão de layout."""

    def test_margem_maior_que_a_pagina_e_recusada(self) -> None:
        # O caso relatado: margin_mm=200 numa A5 (148x210 mm) não deixa área
        # útil nenhuma, em nenhum eixo.
        with self.assertRaises(ValueError) as ctx:
            resolve_page("A5", margin_mm=200)
        mensagem = str(ctx.exception)
        self.assertIn("A5", mensagem)
        self.assertIn("margens", mensagem)

    def test_recusa_independe_de_ser_estrito(self) -> None:
        # Área útil negativa não é uma questão de tolerância — não existe
        # leitura razoável para uma página sem espaço para nada.
        for strict in (True, False):
            with self.subTest(strict=strict):
                with self.assertRaises(ValueError):
                    resolve_page("A5", margin_mm=200, strict=strict)

    def test_recusa_acontece_antes_do_layout_ser_montado(self) -> None:
        # A recusa vem de resolve_page, então nem chega a existir um
        # PageSpec para solve_layout tentar layoutar — o mesmo pedido não
        # pode dar certo com um parâmetro (include_grid) e quebrar feio com
        # outro: aqui ele nunca chega a essa bifurcação.
        with self.assertRaises(ValueError):
            resolve_page("A5", margin_mm=200)

    def test_margem_positiva_mas_insuficiente_para_o_template_e_recusada(self) -> None:
        # Um caso mais sutil: a área útil é positiva (resolve_page aceita),
        # mas pequena demais para título+rodapé+um mapa mínimo no template
        # pedido — é o layoutgrid, não o pagespec, quem sabe disso.
        spec = resolve_page("A5", margin_mm=60)
        self.assertGreater(spec.content_width_mm, 0)
        self.assertGreater(spec.content_height_mm, 0)
        with self.assertRaises(ValueError) as ctx:
            solve_layout(spec)
        self.assertIn("útil", str(ctx.exception))

    def test_pagina_normal_com_margem_padrao_continua_funcionando(self) -> None:
        # Não pode virar recusa geral: toda página razoável continua ok.
        for tamanho in PAGE_SIZES:
            with self.subTest(tamanho=tamanho):
                plan = solve_layout(tamanho)
                self.assertGreater(plan.map_frame().width, 0)
                self.assertGreater(plan.map_frame().height, 0)


if __name__ == "__main__":
    unittest.main()
