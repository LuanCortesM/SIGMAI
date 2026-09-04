# -*- coding: utf-8 -*-
"""Correções do lote de validação de parâmetros de compose_map.

Cada teste aqui corresponde a um dos 12 defeitos do relatório dos caçadores.
``params.py`` é Python puro (sem PyQGIS) e é testado diretamente. ``compose.py``
importa PyQGIS só dentro de funções (``_imports()``), nunca no topo do módulo,
então as funções puras que ele expõe — ``_reject_unknown_parameters``,
``_resolve_template``, ``_resolve_grid_style``, ``_resolve_map_crs_text``,
``_credit_line``, ``_reject_if_audit_found_blank_output`` — também são
testáveis aqui sem depender do QGIS estar instalado. O comportamento
end-to-end dentro do QGIS (que elemento aparece no layout, que arquivo é
escrito) foi conferido à parte com ``tools/scenario_runner.py`` sob
``xvfb-run``; os ids de cenário citados nos comentários apontam para essa
verificação.
"""

from __future__ import annotations

import unittest

from sigmai.cartography.compose import (
    KNOWN_PARAMETERS,
    CompositionError,
    _credit_line,
    _reject_if_audit_found_blank_output,
    _reject_unknown_parameters,
    _resolve_grid_style,
    _resolve_map_crs_text,
    _resolve_template,
)
from sigmai.cartography.params import ParameterError, as_flag, as_id_list, as_number, as_text
from sigmai.cartography.symbology import APPLY_STYLE_MODES, apply_default_symbology


# ---------------------------------------------------------------------------
# Item 1 — confirm_overwrite: bool("false") é True e apagava arquivo do usuário
# ---------------------------------------------------------------------------

class ConfirmOverwriteNuncaSilencioso(unittest.TestCase):
    """O defeito mais grave do lote: confirm_overwrite:"false" sobrescrevia.

    Cenário provado sob QGIS: ``safety-confirm-overwrite-string-false`` (bancada
    de erros) e o par ``overwrite-string-false-step1``/``step2`` (bancada
    ocidental) — o passo 2 agora recusa em vez de sobrescrever em silêncio.
    """

    def test_string_false_nao_e_bool_do_python(self) -> None:
        # bool("false") é True em Python porque toda string não vazia é
        # verdadeira — é exatamente esse atalho que apagava o arquivo.
        self.assertTrue(bool("false"))
        valor, nota = as_flag({"confirm_overwrite": "false"}, "confirm_overwrite", False)
        self.assertFalse(valor)
        self.assertIn("confirm_overwrite", nota)

    def test_variantes_de_falso_reconhecidas(self) -> None:
        for texto in ("false", "FALSE", "False", "no", "NO", "não", "nao", "NÃO", "0"):
            with self.subTest(texto=texto):
                valor, _ = as_flag({"x": texto}, "x", True)
                self.assertFalse(valor)

    def test_variantes_de_verdadeiro_reconhecidas(self) -> None:
        for texto in ("true", "TRUE", "yes", "sim", "SIM", "1"):
            with self.subTest(texto=texto):
                valor, _ = as_flag({"x": texto}, "x", False)
                self.assertTrue(valor)

    def test_bool_de_verdade_nao_gera_nota(self) -> None:
        valor, nota = as_flag({"confirm_overwrite": False}, "confirm_overwrite", True)
        self.assertFalse(valor)
        self.assertEqual(nota, "")

    def test_ambiguo_e_recusado_nao_adivinhado(self) -> None:
        with self.assertRaises(ParameterError):
            as_flag({"confirm_overwrite": "maybe"}, "confirm_overwrite", False)
        with self.assertRaises(ParameterError):
            as_flag({"confirm_overwrite": None}, "confirm_overwrite", False)


# ---------------------------------------------------------------------------
# Item 2 — quebras por tipo: dpi/margin_percent/label_font_size/
# inset_zoom_factor/layer_ids/inset_layer_ids/second_map.layer_ids
# ---------------------------------------------------------------------------

class QuebrasPorTipoViramRecusa(unittest.TestCase):
    """TypeError/ValueError crus viram CompositionError com causa nomeada.

    Provado sob QGIS pela bancada de erros: nenhum dos ids
    ``num-dpi-*``/``num-margin-percent-*``/``num-label-font-size-*``/
    ``num-inset-zoom-factor-*``/``num-second-map-margin-texto``/
    ``iter-layer-ids-*``/``iter-inset-layer-ids-inteiro``/
    ``iter-second-map-layer-ids-inteiro`` aparece mais na lista de quebras.
    """

    def test_dpi_string_nao_numerica(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"dpi": "trezentos"}, "dpi", 300, minimum=50, maximum=1200, integer=True)

    def test_dpi_null_e_recusado_nao_e_default_silencioso(self) -> None:
        # Chave presente com valor None é diferente de chave ausente: aqui é
        # um erro do chamador, não "use o padrão".
        with self.assertRaises(ParameterError):
            as_number({"dpi": None}, "dpi", 300)

    def test_margin_percent_texto_nao_numerico(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"margin_percent": "cinco"}, "margin_percent", 5.0, minimum=0.0)

    def test_label_font_size_texto_nao_numerico(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"label_font_size": "grande"}, "label_font_size", 10.0, minimum=3.0, maximum=72.0)

    def test_inset_zoom_factor_texto_nao_numerico(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"inset_zoom_factor": "muito"}, "inset_zoom_factor", 12.0)

    def test_layer_ids_inteiro_nao_e_iteravel(self) -> None:
        # Era aqui que "for layer_id in 42" estourava TypeError cru.
        with self.assertRaises(ParameterError):
            as_id_list({"layer_ids": 42}, "layer_ids")

    def test_layer_ids_bool_e_recusado(self) -> None:
        with self.assertRaises(ParameterError):
            as_id_list({"layer_ids": True}, "layer_ids")

    def test_inset_layer_ids_inteiro_e_recusado(self) -> None:
        with self.assertRaises(ParameterError):
            as_id_list({"inset_layer_ids": 7}, "inset_layer_ids")

    def test_second_map_layer_ids_inteiro_e_recusado(self) -> None:
        # second_map: {"layer_ids": 99} — o mesmo formato usado por
        # _resolve_layer_ids(spec, imports, label) dentro de compose.py.
        with self.assertRaises(ParameterError):
            as_id_list({"layer_ids": 99}, "layer_ids", label="second_map.layer_ids")

    def test_layer_ids_string_solta_vira_lista_de_um(self) -> None:
        # Forma comum de um agente esquecer os colchetes; continua legítima.
        self.assertEqual(as_id_list({"layer_ids": "abc123"}, "layer_ids"), ["abc123"])


# ---------------------------------------------------------------------------
# Item 3 — bandeiras booleanas ignoradas (bool() do Python escondia o pedido)
# ---------------------------------------------------------------------------

class BandeirasBooleanas(unittest.TestCase):
    """As 11 bandeiras de compose_map usam as_flag, nunca bool() cru.

    Provado sob QGIS: ``bool-include-legend-string-false``,
    ``bool-include-north-string-nao``, ``bool-include-grid-string-zero`` e
    ``bool-round-scale-string-false`` — em cada um o item correspondente
    ("legend"/"north_arrow"/"grid") passou a faltar em ``items_created``, e a
    nota da conversão aparece na resposta.
    """

    FLAGS = (
        "include_grid", "include_legend", "include_scale_bar", "include_scale_text",
        "include_north_arrow", "include_logo", "include_inset", "round_scale",
        "auto_projected_crs", "comparison_same_scale", "confirm_overwrite",
    )

    def test_todas_as_bandeiras_aceitam_string_false_como_falso(self) -> None:
        for nome in self.FLAGS:
            with self.subTest(bandeira=nome):
                valor, nota = as_flag({nome: "false"}, nome, True)
                self.assertFalse(valor)
                self.assertTrue(nota)

    def test_ausencia_preserva_o_default_sem_nota(self) -> None:
        for nome in self.FLAGS:
            with self.subTest(bandeira=nome):
                valor, nota = as_flag({}, nome, True)
                self.assertTrue(valor)
                self.assertEqual(nota, "")


# ---------------------------------------------------------------------------
# Item 4 — null virando o texto "None"
# ---------------------------------------------------------------------------

class NuloNaoViraTextoNone(unittest.TestCase):
    """str(None) == "None": título, autoria e fonte nulos imprimiam isso.

    Provado sob QGIS: ``null-title-vira-none-literal``,
    ``null-data-source-autor-vira-none`` e ``null-map-crs-mensagem-confusa``
    compõem normalmente agora, sem o texto "None" em lugar nenhum.
    """

    def test_str_de_none_e_a_palavra_none(self) -> None:
        # A causa exata do defeito, para não ficar abstrato.
        self.assertEqual(str(None), "None")

    def test_titulo_nulo_vira_default_nao_a_palavra_none(self) -> None:
        self.assertEqual(as_text({"title": None}, "title", "Mapa"), "Mapa")

    def test_chave_ausente_e_nulo_dao_o_mesmo_resultado(self) -> None:
        self.assertEqual(as_text({}, "title", "Mapa"), as_text({"title": None}, "title", "Mapa"))

    def test_credit_line_nao_imprime_none(self) -> None:
        linha = _credit_line(
            {"data_source": None, "map_author": None, "organization": None}, "", ""
        )
        self.assertNotIn("None", linha)

    def test_credit_line_com_dados_reais(self) -> None:
        linha = _credit_line({"data_source": "IBGE", "map_author": "L. Maciel"}, "EPSG:4674", "04/09/2026")
        self.assertIn("Fonte: IBGE", linha)
        self.assertIn("Elaboração: L. Maciel", linha)
        self.assertNotIn("None", linha)

    def test_numero_e_convertido_texto_e_recusado(self) -> None:
        self.assertEqual(as_text({"production_date": 2026}, "production_date"), "2026")
        with self.assertRaises(ParameterError):
            as_text({"title": ["Meu", "Mapa"]}, "title")  # title-lista-em-vez-de-string
        with self.assertRaises(ParameterError):
            as_text({"title": {"pt": "Mapa"}}, "title")


# ---------------------------------------------------------------------------
# Item 5 — dpi sem piso nem teto
# ---------------------------------------------------------------------------

class DpiComPisoETeto(unittest.TestCase):
    """dpi<=1 gerava pixels de menos; dpi=20000 arrisca a memória do QGIS.

    Provado sob QGIS: ``extremo-dpi-1``, ``extremo-dpi-zero``,
    ``extremo-dpi-negativo`` e ``extremo-dpi-fracionario`` — todos recusados
    hoje nomeando a faixa 50–1200, e nenhum vira "arquivo suspeito de vazio".
    """

    def test_dpi_zero_e_negativo_recusados(self) -> None:
        for valor in (0, -5, 1, 49):
            with self.subTest(dpi=valor):
                with self.assertRaises(ParameterError):
                    as_number({"dpi": valor}, "dpi", 300, minimum=50, maximum=1200, integer=True)

    def test_dpi_absurdamente_alto_recusado(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"dpi": 20000}, "dpi", 300, minimum=50, maximum=1200, integer=True)

    def test_mensagem_nomeia_a_faixa(self) -> None:
        with self.assertRaises(ParameterError) as ctx:
            as_number({"dpi": 20000}, "dpi", 300, minimum=50, maximum=1200, integer=True)
        self.assertIn("50", str(ctx.exception))
        self.assertIn("1200", str(ctx.exception))

    def test_dpi_fracionario_recusado(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"dpi": 150.5}, "dpi", 300, minimum=50, maximum=1200, integer=True)

    def test_dpi_dentro_da_faixa_aceito(self) -> None:
        self.assertEqual(as_number({"dpi": 300}, "dpi", minimum=50, maximum=1200, integer=True), 300)
        self.assertEqual(as_number({"dpi": 96}, "dpi", minimum=50, maximum=1200, integer=True), 96)


# ---------------------------------------------------------------------------
# Item 6 — format e a extensão de output_path divergentes
# ---------------------------------------------------------------------------

class FormatoDivergeDaExtensao(unittest.TestCase):
    """output_path "mapa.png" com format "pdf" gerava um PDF chamado .png.

    Provado sob QGIS: ``file-extensao-nao-bate-com-format`` — a mensagem hoje
    diz qual é qual ("termina em '.png' mas format pede 'pdf'") e como
    resolver, em vez de escolher um dos dois em silêncio.
    """

    def test_conflito_e_detectavel_a_partir_dos_dois_valores(self) -> None:
        # A lógica de conflito vive em compose.py (usa Path, que precisa de um
        # caminho real); aqui confirmamos a parte pura — a extração dos dois
        # valores nunca finge que um deles não foi informado.
        explicit_format = as_text({"format": "pdf"}, "format", default="").strip().lower()
        self.assertEqual(explicit_format, "pdf")
        suffix_format = "png"
        self.assertNotEqual(explicit_format, suffix_format)

    def test_format_nulo_equivale_a_omitido(self) -> None:
        # null-format-mensagem-enganosa: format:null não pode virar a string
        # "none" nem ser tratado como um valor realmente pedido.
        self.assertEqual(as_text({"format": None}, "format", default=""), "")


# ---------------------------------------------------------------------------
# Item 7 — grid_style e apply_style com valor inválido
# ---------------------------------------------------------------------------

class EnumsGridEApplyStyle(unittest.TestCase):
    """Valor fora do enum caía num padrão em silêncio — apply_style pior.

    Provado sob QGIS: ``gridstyle-spanish-invalido`` (grid_style="sólido") e
    ``apply-style-invalid-value-fr-invalido`` (apply_style="tout") — os dois
    recusados hoje com a lista do que é aceito e sugestão por proximidade.
    """

    def test_grid_style_desconhecido_e_recusado_com_sugestao(self) -> None:
        with self.assertRaises(CompositionError) as ctx:
            _resolve_grid_style({"grid_style": "sólido"})
        mensagem = str(ctx.exception)
        self.assertIn("solid", mensagem)

    def test_grid_style_valido_e_normalizado(self) -> None:
        self.assertEqual(_resolve_grid_style({"grid_style": "FRAME"}), "frame")
        self.assertEqual(_resolve_grid_style({}), "solid")

    def test_apply_style_desconhecido_nao_forca_estilo_em_tudo(self) -> None:
        # Antes, qualquer valor != "missing"/"none" caía no ramo que reestiliza
        # TODAS as camadas — o comportamento mais destrutivo dos três.
        with self.assertRaises(ParameterError) as ctx:
            apply_default_symbology([], "tout")
        self.assertIn("tout", str(ctx.exception))

    def test_apply_style_aceita_so_o_enum_fechado(self) -> None:
        self.assertEqual(set(APPLY_STYLE_MODES), {"missing", "all", "none"})
        self.assertEqual(apply_default_symbology([], "none"), [])


# ---------------------------------------------------------------------------
# Item 8 — template sensível a caixa
# ---------------------------------------------------------------------------

class TemplateToleranteACaixa(unittest.TestCase):
    """"CIENTIFICO" era recusado enquanto page já aceitava "a4 LANDSCAPE".

    Provado sob QGIS: ``typo-template-maiusculo`` (template="CIENTIFICO")
    passou de recusa de pedido legítimo para "ok".
    """

    def test_maiuscula_e_aceita(self) -> None:
        self.assertEqual(_resolve_template({"template": "CIENTIFICO"}), "cientifico")

    def test_espacos_em_volta_sao_tolerados(self) -> None:
        self.assertEqual(_resolve_template({"template": "  Publicacao  "}), "publicacao")

    def test_nome_inexistente_continua_recusado_com_sugestao(self) -> None:
        with self.assertRaises(CompositionError) as ctx:
            _resolve_template({"template": "cientifico_xyz"})
        self.assertIn("cientifico", str(ctx.exception))

    def test_layout_template_e_sinonimo_de_template(self) -> None:
        self.assertEqual(_resolve_template({"layout_template": "MINIMALISTA"}), "minimalista")

    def test_ausencia_cai_no_padrao(self) -> None:
        self.assertEqual(_resolve_template({}), "cientifico")


# ---------------------------------------------------------------------------
# Item 9 — map_crs com espaço em volta dos dois-pontos
# ---------------------------------------------------------------------------

class MapCrsComEspaco(unittest.TestCase):
    """"EPSG: 4674" era recusado sem nenhuma dica de formato.

    Provado sob QGIS: ``crs-epsg-with-space-de`` (map_crs="EPSG: 4674")
    passou de recusa de pedido legítimo para "ok", reprojetando para SIRGAS
    2000 normalmente.
    """

    def test_espaco_depois_dos_dois_pontos_e_normalizado(self) -> None:
        self.assertEqual(_resolve_map_crs_text({"map_crs": "EPSG: 4674"}), "EPSG:4674")

    def test_espaco_antes_e_depois_e_normalizado(self) -> None:
        self.assertEqual(_resolve_map_crs_text({"map_crs": "EPSG : 4674"}), "EPSG:4674")

    def test_sem_espaco_fica_igual(self) -> None:
        self.assertEqual(_resolve_map_crs_text({"map_crs": "EPSG:31983"}), "EPSG:31983")

    def test_nulo_e_ausente_viram_string_vazia_nao_a_palavra_none(self) -> None:
        self.assertEqual(_resolve_map_crs_text({"map_crs": None}), "")
        self.assertEqual(_resolve_map_crs_text({}), "")


# ---------------------------------------------------------------------------
# Item 10 — parâmetros mortos: scale e style_profile
# ---------------------------------------------------------------------------

class ParametrosMortos(unittest.TestCase):
    """scale e style_profile estavam em KNOWN_PARAMETERS e não faziam nada.

    Um parâmetro aceito e ignorado é o mesmo defeito de "improvisar em
    silêncio" que a ferramenta combate. Os dois foram resolvidos de formas
    diferentes, e a diferença é deliberada:

    * ``scale`` foi **implementado**. "Faça em 1:25.000" é o pedido
      cartográfico mais comum que existe — numa dissertação a escala costuma
      ser imposta pela norma, não escolhida — e recusá-lo deixaria a
      ferramenta sem responder a um pedido legítimo e corriqueiro.
    * ``style_profile`` foi **removido**: não havia semântica definida para
      ele, e inventar uma seria o risco que a ferramenta existe para evitar.
      Cai na recusa de parâmetro desconhecido, apontando ``apply_style``.

    Provado sob QGIS: ``dead-scale-ignorado``, ``conceito-escala-impossivel``
    (bancada de erros) e ``scale-noop-param-en`` (bancada ocidental).
    """

    def test_scale_voltou_a_ser_um_parametro_valido(self) -> None:
        self.assertIn("scale", KNOWN_PARAMETERS)

    def test_style_profile_nao_esta_mais_em_known_parameters(self) -> None:
        self.assertNotIn("style_profile", KNOWN_PARAMETERS)

    def test_scale_nao_e_mais_recusado_como_desconhecido(self) -> None:
        # Não pode levantar: o parâmetro existe e é honrado.
        _reject_unknown_parameters({"layer_ids": ["x"], "scale": 150000})

    def test_scale_precisa_ser_inteiro_positivo(self) -> None:
        for valor in (0, -1, 1.5, "grande", None):
            with self.subTest(valor=valor):
                with self.assertRaises(ParameterError):
                    as_number({"scale": valor}, "scale", minimum=1.0, integer=True, label="scale")

    def test_style_profile_e_recusado_com_dica_especifica(self) -> None:
        with self.assertRaises(CompositionError) as ctx:
            _reject_unknown_parameters({"layer_ids": ["x"], "style_profile": "daltonico_estrito"})
        self.assertIn("apply_style", str(ctx.exception))

    def test_parametros_normais_continuam_aceitos(self) -> None:
        # Não pode ter sobrado nenhum efeito colateral na lista principal.
        _reject_unknown_parameters({"layer_ids": ["x"], "title": "Mapa", "dpi": 300})


# ---------------------------------------------------------------------------
# Item 11 — a ferramenta contradizia o próprio laudo
# ---------------------------------------------------------------------------

class AuditoriaContraditoriaFalha(unittest.TestCase):
    """CART063 "provável exportação vazia" com severidade error e sucesso mesmo assim.

    Provado sob QGIS: ``frame-margin-mm-excessiva-a5`` (margin_mm=200 numa
    A5) — o cenário já é interceptado mais cedo hoje (validação de margem em
    pagespec.py), mas o laço de segurança em compose.py é testado
    diretamente aqui, sem depender de reproduzir a causa raiz específica.
    """

    def test_cart063_bloqueia_o_retorno_de_sucesso(self) -> None:
        audit = {
            "blocking_issues": [
                {"id": "CART063", "detail_pt": "A saída tem apenas 200 bytes; provável exportação vazia."}
            ]
        }
        with self.assertRaises(CompositionError) as ctx:
            _reject_if_audit_found_blank_output(audit)
        self.assertIn("CART063", str(ctx.exception))

    def test_cart062_quadro_em_branco_tambem_bloqueia(self) -> None:
        audit = {
            "blocking_issues": [
                {"id": "CART062", "detail_pt": "O quadro do mapa está praticamente em branco."}
            ]
        }
        with self.assertRaises(CompositionError):
            _reject_if_audit_found_blank_output(audit)

    def test_outros_erros_do_regulamento_nao_bloqueiam_o_retorno(self) -> None:
        # CART001 (sem título) é um erro editorial, não uma exportação vazia;
        # o mapa existe e foi entregue — não é o caso que este laço cobre.
        audit = {"blocking_issues": [{"id": "CART001", "detail_pt": "Sem título."}]}
        _reject_if_audit_found_blank_output(audit)  # não deve levantar

    def test_laudo_sem_falhas_bloqueantes_nao_levanta(self) -> None:
        _reject_if_audit_found_blank_output({"blocking_issues": []})
        _reject_if_audit_found_blank_output({})


# ---------------------------------------------------------------------------
# Item 12 — label_font_size sem faixa sensata
# ---------------------------------------------------------------------------

class LabelFontSizeComFaixa(unittest.TestCase):
    """label_font_size:900 descartava todos os rótulos e a resposta mentia.

    Provado sob QGIS: ``extremo-label-font-size-900`` e
    ``extremo-label-font-size-negativo`` — recusados hoje nomeando a faixa
    3–72 pt, em vez de compor um mapa "rotulado" sem nenhum rótulo visível.
    """

    def test_valor_gigante_e_recusado(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"label_font_size": 900}, "label_font_size", 10.0, minimum=3.0, maximum=72.0)

    def test_valor_negativo_e_recusado(self) -> None:
        with self.assertRaises(ParameterError):
            as_number({"label_font_size": -5}, "label_font_size", 10.0, minimum=3.0, maximum=72.0)

    def test_valor_fracionario_dentro_da_faixa_e_aceito(self) -> None:
        # label_font_size não exige integer=True: 8,5pt é uma escolha
        # tipográfica normal, ao contrário de dpi.
        self.assertEqual(
            as_number({"label_font_size": 8.5}, "label_font_size", minimum=3.0, maximum=72.0), 8.5
        )

    def test_virgula_decimal_inequivoca_e_aceita(self) -> None:
        # num-comma-fontsize-it: "12,5" é como se escreve doze e meio em
        # italiano, francês, alemão, espanhol e português. Só há uma leitura
        # possível, então recusar seria punir o usuário pela língua dele.
        self.assertEqual(
            as_number({"label_font_size": "12,5"}, "label_font_size", minimum=3.0, maximum=72.0), 12.5
        )

    def test_virgula_ambigua_continua_recusada(self) -> None:
        # "1,500" vale mil e quinhentos em inglês e um e meio em francês.
        # Escolher entre as duas seria adivinhar.
        with self.assertRaises(ParameterError) as ctx:
            as_number({"dpi": "1,500"}, "dpi", minimum=50.0, maximum=1200.0)
        self.assertIn("duas formas", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
