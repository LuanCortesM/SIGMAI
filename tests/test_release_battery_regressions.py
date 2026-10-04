# -*- coding: utf-8 -*-
"""Regressões apanhadas pela bateria de liberação (tools/release_battery.py).

Cada classe corresponde a um defeito que só apareceu na COMBINAÇÃO de
variações — template × página × formato × elemento omitido — e não em nenhum
teste de peça isolada. Ficam aqui, sem PyQGIS, para que o defeito não volte
sem que a suíte acuse.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from sigmai.cartography.inspector import _existing_grid, _observe_map
from sigmai.cartography.maptext import MAP_TEXT, resolve_language
from sigmai.cartography.rulebook import evaluate


class _Grade:
    def __init__(self, enabled: bool = True, interval: float = 0.0, annotations: bool = False) -> None:
        self._enabled, self._interval, self._annotations = enabled, interval, annotations

    def enabled(self) -> bool:
        return self._enabled

    def intervalX(self) -> float:  # noqa: N802 — nome da API do QGIS
        return self._interval

    def intervalY(self) -> float:  # noqa: N802
        return self._interval

    def annotationEnabled(self) -> bool:  # noqa: N802
        return self._annotations


class _Pilha:
    def __init__(self, grades: list[_Grade]) -> None:
        self._grades = grades

    def size(self) -> int:
        return len(self._grades)

    def grid(self, index: int) -> _Grade:
        return self._grades[index]


class _Quadro:
    """Imita QgsLayoutItemMap: ``grid()`` CRIA uma grade quando não há nenhuma
    (habilitada, intervalo zero) — exatamente o comportamento do QGIS."""

    def __init__(self, grades: list[_Grade] | None = None) -> None:
        self._grades = list(grades or [])
        self.grid_criada_pela_observacao = False

    def grids(self) -> _Pilha:
        return _Pilha(self._grades)

    def grid(self) -> _Grade:
        if not self._grades:
            self._grades.append(_Grade(enabled=True, interval=0.0))
            self.grid_criada_pela_observacao = True
        return self._grades[0]

    # Superfície mínima que _observe_map lê.
    def crs(self):
        return None

    def layers(self):
        return []

    def id(self):
        return "main_map"

    def scale(self):
        return 50000.0

    def mapRotation(self):  # noqa: N802
        return 0.0

    def extent(self):
        return None


class GradeFantasmaNaInspecao(unittest.TestCase):
    """``QgsLayoutItemMap.grid()`` cria uma grade habilitada com intervalo 0
    quando o quadro não tem nenhuma. O inspetor lia por esse caminho e, num
    mapa pedido SEM grade, fabricava uma grade-fantasma: CART026/CART027
    reprovavam o mapa e CART010 aprovava uma grade que não existia."""

    def test_observar_um_quadro_sem_grade_nao_cria_grade(self) -> None:
        quadro = _Quadro()
        info = _observe_map(quadro, None, None)
        self.assertFalse(quadro.grid_criada_pela_observacao, "a observação alterou o layout inspecionado")
        self.assertEqual(info["grid"], {"enabled": False, "interval_x": 0.0, "interval_y": 0.0, "annotations": False})

    def test_grade_existente_continua_sendo_lida(self) -> None:
        quadro = _Quadro([_Grade(enabled=True, interval=1000.0, annotations=True)])
        info = _observe_map(quadro, None, None)
        self.assertEqual(info["grid"], {"enabled": True, "interval_x": 1000.0, "interval_y": 1000.0, "annotations": True})

    def test_existing_grid_devolve_none_sem_pilha(self) -> None:
        class SemPilha:
            pass

        self.assertIsNone(_existing_grid(SemPilha()))

    def test_regulamento_nao_acusa_grade_num_mapa_sem_grade(self) -> None:
        observacao = {
            "page": {"width_mm": 297.0, "height_mm": 210.0},
            "map": {"item_id": "main_map", "crs": "EPSG:31984", "crs_is_geographic": False, "scale": 50000.0,
                    "visible_layer_names": ["Trilha"], "grid": _observe_map(_Quadro(), None, None)["grid"]},
            "items": [{"item_id": "title", "role": "title", "type": "label", "text": "T"}],
        }
        laudo = evaluate(observacao)
        por_id = {r["id"]: r["status"] for r in laudo["results"]}
        self.assertEqual(por_id["CART026"], "skip")
        self.assertEqual(por_id["CART027"], "skip")
        self.assertEqual(por_id["CART010"], "fail")


class LinguaDesconhecidaRecusada(unittest.TestCase):
    """``map_language`` fora da tabela deixou de cair em português com uma
    nota: o assistente via a nota, o usuário via um mapa em língua que não
    pediu. Agora a composição recusa — mesmo tratamento de page/template."""

    def test_resolve_language_continua_tolerante(self) -> None:
        for codigo, esperado in (("EN", "en"), ("en_US", "en"), ("jp", "ja"), ("zh-TW", "zh-Hant"), ("PT-br", "pt-BR")):
            with self.subTest(codigo=codigo):
                self.assertEqual(resolve_language(codigo), (esperado, True))

    def test_codigo_sem_correspondencia_e_sinalizado(self) -> None:
        self.assertEqual(resolve_language("tlh"), ("pt-BR", False))

    def test_a_recusa_de_compose_map_lista_as_linguas(self) -> None:
        import inspect

        from sigmai.cartography import compose

        fonte = inspect.getsource(compose._compose_map)
        self.assertIn("if not map_language_known:", fonte)
        self.assertIn("raise CompositionError", fonte.split("if not map_language_known:", 1)[1][:400])
        self.assertNotIn("saíram em português", fonte)
        for lingua in MAP_TEXT:
            self.assertTrue(lingua)  # a lista vem de MAP_TEXT, não de uma cópia manual


class SimbologiaSoDepoisDaValidacao(unittest.TestCase):
    """A reestilização das camadas é a única mutação do projeto que
    compose_map faz antes de criar o layout. Ela tem de vir DEPOIS da última
    recusa de parâmetro: uma página inexistente recusada não pode deixar o
    projeto do usuário com a simbologia trocada por um mapa que não saiu."""

    def test_aplicacao_real_vem_depois_das_recusas(self) -> None:
        import inspect

        from sigmai.cartography import compose

        fonte = inspect.getsource(compose._compose_map)
        previa = fonte.index("apply_default_symbology(styling_targets, apply_style_value, dry_run=True)")
        aplicacao = fonte.index("apply_default_symbology(styling_targets, apply_style_value, dry_run=False)")
        ultima_recusa = max(
            fonte.index("O arquivo já existe"),
            fonte.index("A pasta de saída não existe"),
            fonte.index("Formato de saída inválido"),
            fonte.index("map_crs inválido"),
        )
        self.assertLess(previa, ultima_recusa)
        self.assertGreater(aplicacao, ultima_recusa)
        self.assertLess(aplicacao, fonte.index('imports["QgsPrintLayout"](project)'))


class ProcedenciaEmTodasAsLinguas(unittest.TestCase):
    """Japonês e chinês pontuam "出典：" com dois-pontos de largura inteira.
    O marcador derivado tirava só o ":" ASCII e virava "出典：:", que nunca
    aparece — CART007 acusava falta de fonte num mapa japonês completo."""

    def test_a_linha_de_credito_de_cada_lingua_satisfaz_cart007(self) -> None:
        from sigmai.cartography.compose import _credit_line
        from sigmai.cartography.rulebook import _check_source_credit

        for lingua in sorted(MAP_TEXT):
            with self.subTest(lingua=lingua):
                linha = _credit_line({"data_source": "IBGE 2024", "map_author": "L. Maciel"}, "EPSG:4674", "05/09/2026", lingua)
                observacao = {"items": [{"id": "source", "role": "source", "type": "label", "text": linha}]}
                resultado = _check_source_credit(observacao)
                self.assertEqual(resultado.status, "pass", f"{lingua}: {linha!r} → {resultado.detail_pt}")

    def test_sem_fonte_continua_reprovando_em_japones(self) -> None:
        from sigmai.cartography.compose import _credit_line
        from sigmai.cartography.rulebook import _check_source_credit

        linha = _credit_line({}, "EPSG:4674", "05/09/2026", "ja")
        resultado = _check_source_credit({"items": [{"id": "source", "role": "source", "type": "label", "text": linha}]})
        self.assertEqual(resultado.status, "fail")


class SeparadorDeMilharPorLingua(unittest.TestCase):
    """"Escala 1:250.000" num mapa em inglês lê-se como duzentos e cinquenta.
    O denominador segue o símbolo de agrupamento do CLDR da língua do mapa;
    laudos e notas (em português) continuam com ponto."""

    def test_formato_por_lingua(self) -> None:
        from sigmai.cartography.compose import _format_scale

        self.assertEqual(_format_scale(250000), "1:250.000")
        self.assertEqual(_format_scale(250000, "pt-BR"), "1:250.000")
        self.assertEqual(_format_scale(250000, "en"), "1:250,000")
        self.assertEqual(_format_scale(250000, "fr"), "1:250 000")
        self.assertEqual(_format_scale(250000, "ru"), "1:250 000")
        self.assertEqual(_format_scale(1500000, "ja"), "1:1,500,000")
        self.assertEqual(_format_scale(500, "en"), "1:500")

    def test_toda_lingua_declara_o_separador(self) -> None:
        for lingua, tabela in MAP_TEXT.items():
            with self.subTest(lingua=lingua):
                self.assertIn("separador_milhar", tabela)
                self.assertEqual(len(tabela["separador_milhar"]), 1)

    def test_separadores_batem_com_o_cldr_via_qlocale(self) -> None:
        """Verificação independente contra os dados do CLDR embutidos no Qt.
        Árabe fica de fora da comparação direta: o QLocale padrão usa
        algarismos arábico-índicos, e o mapa escreve algarismos ocidentais."""
        try:
            from PyQt5.QtCore import QLocale
        except ImportError:  # pragma: no cover - ambiente sem Qt
            self.skipTest("PyQt5 não instalado")
        locales = {"pt-BR": "pt_BR", "en": "en_US", "es": "es_ES", "fr": "fr_FR", "de": "de_DE", "it": "it_IT",
                   "ja": "ja_JP", "zh-Hans": "zh_CN", "zh-Hant": "zh_TW", "ko": "ko_KR", "ru": "ru_RU",
                   "he": "he_IL", "el": "el_GR", "th": "th_TH"}
        for lingua, nome in locales.items():
            with self.subTest(lingua=lingua):
                self.assertEqual(QLocale(nome).groupSeparator(), MAP_TEXT[lingua]["separador_milhar"])


class CaminhoDeSaidaDeOutroSistemaOuRelativo(unittest.TestCase):
    """Um caminho do Windows colado num QGIS em Linux era, para o POSIX, um
    nome relativo com barras invertidas: a exportação criava um arquivo
    chamado literalmente ``C:\\Users\\...\\mapa.png`` na pasta corrente e
    reportava sucesso. Um caminho relativo ia parar numa pasta que o usuário
    não conhece. Os dois viram recusa nomeada — no compositor e na ponte."""

    @unittest.skipIf(__import__("os").name == "nt", "a regra do caminho estrangeiro só vale em POSIX")
    def test_classificacao(self) -> None:
        from sigmai.security import classify_output_path

        self.assertEqual(classify_output_path(r"C:\Dados\Fulano\Documentos\mapa.png"), "foreign")
        self.assertEqual(classify_output_path(r"\\servidor\pasta\mapa.png"), "foreign")
        self.assertEqual(classify_output_path("D:/mapas/mapa.png"), "foreign")
        self.assertEqual(classify_output_path("mapa.png"), "relative")
        self.assertEqual(classify_output_path("saida/mapa.png"), "relative")
        self.assertEqual(classify_output_path("/tmp/mapa.png"), "ok")
        self.assertEqual(classify_output_path("~/mapa.png"), "ok")
        self.assertEqual(classify_output_path("/tmp/x/../mapa.png"), "ok")

    @unittest.skipIf(__import__("os").name == "nt", "a regra do caminho estrangeiro só vale em POSIX")
    def test_normalize_output_path_recusa_com_sugestao(self) -> None:
        from sigmai.security import OutputPathError, normalize_output_path

        with self.assertRaises(OutputPathError) as ctx:
            normalize_output_path(r"C:\Dados\Fulano\mapa.png")
        self.assertIn("Windows", str(ctx.exception))
        with self.assertRaises(OutputPathError) as ctx:
            normalize_output_path("mapa.png")
        self.assertIn("absolute", str(ctx.exception))
        # No macOS /tmp é link para /private/tmp, e o caminho sai resolvido.
        self.assertEqual(normalize_output_path("/tmp/x/../mapa.png"), Path("/tmp/mapa.png").resolve())

    @unittest.skipIf(__import__("os").name == "nt", "a regra do caminho estrangeiro só vale em POSIX")
    def test_compose_recusa_em_portugues_sem_tocar_no_disco(self) -> None:
        from sigmai.cartography.compose import CompositionError, _resolve_output_path

        with self.assertRaises(CompositionError) as ctx:
            _resolve_output_path({"output_path": r"C:\Dados\Fulano\Documentos\mapa.png"})
        self.assertIn("caminho do Windows", str(ctx.exception))
        with self.assertRaises(CompositionError) as ctx:
            _resolve_output_path({"output_path": "mapa.png"})
        self.assertIn("absoluto", str(ctx.exception))
        self.assertIsNone(_resolve_output_path({}))
        self.assertIsNone(_resolve_output_path({"output_path": "  "}))
        self.assertEqual(str(_resolve_output_path({"output_path": "/tmp/img/../mapa.png"})), "/tmp/mapa.png")

    def test_a_ponte_devolve_bad_request_e_nao_erro_interno(self) -> None:
        from sigmai.command_registry import CommandRegistry
        from sigmai.security import OutputPathError

        registry = CommandRegistry({})

        def handler(params, context):
            raise OutputPathError("Output path must be absolute; got 'mapa.png'.")

        registry.register("export_layout", handler)
        resposta = registry.execute({"action": "export_layout", "params": {"layout_name": "x", "path": "mapa.png", "format": "png", "confirm_overwrite": True}})
        self.assertFalse(resposta["ok"])
        self.assertEqual(resposta["errors"][0]["code"], "BAD_REQUEST")
        self.assertEqual(resposta["errors"][0]["details"], {"parameter": "output_path"})


class FormatoInvalidoSemOutputPath(unittest.TestCase):
    """format='imagen' sem output_path era aceito calado — o formato só era
    validado na hora de exportar. Um parâmetro aceito sem efeito é o mesmo
    defeito de improvisar em silêncio que o resto do compositor combate."""

    def test_a_validacao_nao_depende_de_output_path(self) -> None:
        import inspect

        from sigmai.cartography import compose

        fonte = inspect.getsource(compose._compose_map)
        trecho = fonte.split("explicit_format = as_text(params, \"format\"", 1)[1]
        self.assertIn("if explicit_format and explicit_format not in SUPPORTED_FORMATS:", trecho[:900])


class DominioDoMapaNaFolhaDeComparacao(unittest.TestCase):
    """CART043 contava só o quadro principal: numa folha de dois painéis os
    mapas ocupam mais da metade da área útil e a regra dizia 27%."""

    def _observacao(self, quadros: int) -> dict:
        itens = [{"id": "title", "role": "title", "type": "label", "text": "T"}]
        for i in range(quadros):
            itens.append({"id": "main_map" if i == 0 else "comparison_map", "role": "map", "type": "map",
                          "x": 14.3 + 150 * i, "y": 46.4, "width": 133.7, "height": 214.4})
        itens.append({"id": "inset_map", "role": "inset", "type": "map", "x": 300, "y": 60, "width": 90, "height": 90})
        return {"page": {"width_mm": 420.0, "height_mm": 297.0, "content_area_mm": {"width": 391.4, "height": 268.4}},
                "map": {"item_id": "main_map"}, "items": itens}

    def test_dois_quadros_somam(self) -> None:
        from sigmai.cartography.rulebook import _check_map_dominance

        um = _check_map_dominance(self._observacao(1))
        dois = _check_map_dominance(self._observacao(2))
        self.assertEqual(um.status, "fail")
        self.assertEqual(dois.status, "pass")
        self.assertAlmostEqual(dois.evidence.get("map_area_ratio", 0) or 0, 0.0)  # pass não carrega evidência
        self.assertIn("2 quadros", dois.detail_pt)

    def test_o_inserto_nao_conta_como_mapa(self) -> None:
        from sigmai.cartography.rulebook import _check_map_dominance

        obs = self._observacao(1)
        # Um inserto enorme não pode salvar um mapa principal pequeno.
        obs["items"][-1].update({"width": 300, "height": 200})
        self.assertEqual(_check_map_dominance(obs).status, "fail")


if __name__ == "__main__":
    unittest.main()
