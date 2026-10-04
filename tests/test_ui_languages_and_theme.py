# -*- coding: utf-8 -*-
"""Idiomas da interface e tema claro/escuro do painel.

Duas queixas de quem usou a 1.0.0 no QGIS: no tema escuro o painel ficava
ilegível, e a interface só existia em português e inglês, trocados por um
botão. Estes testes fixam o que substituiu isso — nove línguas completas
numa lista, e uma folha de estilo que declara fundo e texto de todo widget
nos dois temas — sem precisar de PyQGIS: tudo aqui é Python puro.
"""

from __future__ import annotations

import re
import unittest

from sigmai.consent import ACTION_CATEGORIES, CATEGORY_KEYS
from sigmai.ui.strings import DEFAULT_LANGUAGE, LANGUAGES, STRINGS, language_name, normalize_ui_language, translate
from sigmai.ui.theme import (
    DARK,
    LIGHT,
    PALETTES,
    THEME_AUTO,
    THEME_DARK,
    THEME_LIGHT,
    THEME_PREFERENCES,
    get_sigmai_stylesheet,
    resolve_theme,
)

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class NoveLinguasCompletas(unittest.TestCase):
    def test_a_lista_do_seletor_e_a_tabela_sao_as_mesmas_linguas(self) -> None:
        self.assertEqual([code for code, _ in LANGUAGES], list(STRINGS))
        self.assertEqual(len(LANGUAGES), 9)
        self.assertEqual(LANGUAGES[0][0], DEFAULT_LANGUAGE)

    def test_toda_chave_existe_em_toda_lingua_sem_texto_vazio(self) -> None:
        referencia = set(STRINGS[DEFAULT_LANGUAGE])
        for code, tabela in STRINGS.items():
            with self.subTest(lingua=code):
                self.assertEqual(set(tabela), referencia, f"{code} difere da referência")
                vazias = [k for k, v in tabela.items() if not str(v).strip()]
                self.assertEqual(vazias, [])

    def test_os_marcadores_de_formatacao_batem_com_a_referencia(self) -> None:
        for chave, texto in STRINGS[DEFAULT_LANGUAGE].items():
            esperado = set(_PLACEHOLDER.findall(texto))
            for code, tabela in STRINGS.items():
                with self.subTest(lingua=code, chave=chave):
                    self.assertEqual(set(_PLACEHOLDER.findall(tabela[chave])), esperado)

    def test_o_nome_de_cada_lingua_esta_escrito_nela_mesma(self) -> None:
        nomes = dict(LANGUAGES)
        self.assertEqual(nomes["ja"], "日本語")
        self.assertEqual(nomes["zh-Hans"], "简体中文")
        self.assertEqual(nomes["zh-Hant"], "繁體中文")
        self.assertEqual(nomes["de"], "Deutsch")
        self.assertEqual(language_name("zh_TW"), "繁體中文")

    def test_traducoes_nao_sao_copias_do_portugues(self) -> None:
        # Uma tabela "traduzida" que repete o português em massa é uma tabela
        # que ninguém traduziu. Termos técnicos idênticos (Host, Token, GPS,
        # Raster, Processing, URLs) são esperados; o resto não.
        pt = STRINGS[DEFAULT_LANGUAGE]
        for code, tabela in STRINGS.items():
            if code == DEFAULT_LANGUAGE:
                continue
            iguais = sum(1 for k in pt if tabela[k] == pt[k])
            with self.subTest(lingua=code):
                self.assertLess(iguais / len(pt), 0.12, f"{code}: {iguais} textos iguais ao português")

    def test_dev_prompt_pede_a_palavra_que_o_plugin_aceita(self) -> None:
        # DEV_MODE_CONFIRMATION_WORDS = {"SIM", "YES"}: cada língua tem de
        # pedir uma das duas, senão o usuário digita o certo e é recusado.
        from sigmai.validators import DEV_MODE_CONFIRMATION_WORDS

        for code, tabela in STRINGS.items():
            with self.subTest(lingua=code):
                self.assertTrue(any(palavra in tabela["dev_dialog_prompt"] for palavra in DEV_MODE_CONFIRMATION_WORDS))


class CodigoDeLinguaTolerante(unittest.TestCase):
    def test_grafias(self) -> None:
        for codigo, esperado in (("PT", "pt-BR"), ("pt_BR", "pt-BR"), ("pt-PT", "pt-BR"), ("en-US", "en"), ("EN", "en"),
                                 ("zh-CN", "zh-Hans"), ("zh", "zh-Hans"), ("zh_TW", "zh-Hant"), ("zh-HK", "zh-Hant"),
                                 ("jp", "ja"), ("ja-JP", "ja"), ("es-MX", "es"), ("fr_CA", "fr"), ("de-AT", "de"), ("it", "it")):
            with self.subTest(codigo=codigo):
                self.assertEqual(normalize_ui_language(codigo), esperado)

    def test_desconhecido_e_nulo_caem_no_padrao(self) -> None:
        self.assertEqual(normalize_ui_language("tlh"), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_ui_language(None), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_ui_language(""), DEFAULT_LANGUAGE)

    def test_translate_formata_e_nunca_devolve_a_chave_para_chave_conhecida(self) -> None:
        self.assertEqual(translate("de", "step1_running", host="h", port=1, qgis="4.1"), "Brücke aktiv auf h:1 · QGIS 4.1")
        self.assertEqual(translate("xx", "tab_help"), STRINGS[DEFAULT_LANGUAGE]["tab_help"])
        self.assertEqual(translate("ja", "nao_existe"), "nao_existe")


class CategoriasDoConsentimentoTraduzidas(unittest.TestCase):
    """O registro guarda o nome canônico (português); a interface traduz só
    na exibição, para que trocar de idioma não esqueça o que foi aprovado."""

    def test_toda_categoria_canonica_tem_chave_em_toda_lingua(self) -> None:
        canonicas = {nome for nome, _ in ACTION_CATEGORIES.values()}
        self.assertEqual(canonicas, set(CATEGORY_KEYS))
        for code, tabela in STRINGS.items():
            for chave in CATEGORY_KEYS.values():
                with self.subTest(lingua=code, chave=chave):
                    self.assertIn(chave, tabela)

    def test_toda_descricao_de_grupo_resolve(self) -> None:
        aliases = {"vector_tools": "vector", "vector_analysis": "vector", "labels": "symbology", "job_queue": "workflows"}
        for grupo in ACTION_CATEGORIES:
            chave = f"category_desc_{aliases.get(grupo, grupo)}"
            with self.subTest(grupo=grupo):
                self.assertIn(chave, STRINGS[DEFAULT_LANGUAGE])


class TemaClaroEEscuro(unittest.TestCase):
    def test_preferencia_forcada_vence_a_paleta(self) -> None:
        self.assertEqual(resolve_theme(THEME_LIGHT, palette=None), THEME_LIGHT)
        self.assertEqual(resolve_theme(THEME_DARK, palette=None), THEME_DARK)
        self.assertEqual(resolve_theme("DARK ", palette=None), THEME_DARK)

    def test_automatico_sem_paleta_e_claro_e_valor_estranho_conta_como_automatico(self) -> None:
        self.assertEqual(resolve_theme(THEME_AUTO), THEME_LIGHT)
        self.assertEqual(resolve_theme("xyz"), THEME_LIGHT)
        self.assertEqual(resolve_theme(None), THEME_LIGHT)
        self.assertEqual(THEME_PREFERENCES, (THEME_AUTO, THEME_LIGHT, THEME_DARK))

    def test_automatico_segue_a_paleta_do_qgis(self) -> None:
        try:
            from qgis.PyQt.QtGui import QColor, QPalette
        except ImportError:
            try:
                from PyQt6.QtGui import QColor, QPalette
            except ImportError:
                try:
                    from PyQt5.QtGui import QColor, QPalette
                except ImportError:  # pragma: no cover
                    self.skipTest("nem PyQGIS, nem PyQt6, nem PyQt5")
        role = getattr(getattr(QPalette, "ColorRole", QPalette), "Window")
        escura, clara = QPalette(), QPalette()
        escura.setColor(role, QColor("#323232"))
        clara.setColor(role, QColor("#EFEFEF"))
        self.assertEqual(resolve_theme(THEME_AUTO, escura), THEME_DARK)
        self.assertEqual(resolve_theme(THEME_AUTO, clara), THEME_LIGHT)
        # A preferência explícita ignora a paleta.
        self.assertEqual(resolve_theme(THEME_LIGHT, escura), THEME_LIGHT)

    def test_a_folha_declara_fundo_e_texto_do_que_o_tema_do_qgis_capturava(self) -> None:
        for dark in (False, True):
            folha = get_sigmai_stylesheet(1.0, dark=dark)
            with self.subTest(dark=dark):
                # Os widgets que ficavam à mercê do tema do aplicativo.
                self.assertRegex(folha, r"QRadioButton, QCheckBox \{[^}]*background: transparent")
                self.assertRegex(folha, r"\n\s*QLabel \{[^}]*color:")
                self.assertRegex(folha, r"QScrollArea > QWidget > QWidget \{[^}]*background-color")
                self.assertIn("QGroupBox::title", folha)
                self.assertIn("QSpinBox::up-button", folha)
                self.assertIn("QComboBox QAbstractItemView", folha)
                self.assertIn("QScrollBar:vertical", folha)
                self.assertIn("QTableWidget::item", folha)
                self.assertIn("QComboBox#languageCombo", folha)

    def test_as_duas_paletas_usam_cores_diferentes_nas_superficies(self) -> None:
        self.assertNotEqual(LIGHT.surface, DARK.surface)
        self.assertNotEqual(LIGHT.ink, DARK.ink)
        self.assertEqual(PALETTES[THEME_DARK], DARK)
        clara, escura = get_sigmai_stylesheet(1.0, False), get_sigmai_stylesheet(1.0, True)
        self.assertIn(LIGHT.surface, clara)
        self.assertNotIn(LIGHT.surface.lower(), escura.lower().replace("#ffffff", ""))  # branco só no logo/pílulas

    def test_contraste_wcag_aa_nos_pares_texto_fundo(self) -> None:
        def luminancia(hex_cor: str) -> float:
            r, g, b = (int(hex_cor[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

            def canal(c: float) -> float:
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

            return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)

        def contraste(a: str, b: str) -> float:
            la, lb = luminancia(a), luminancia(b)
            return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

        for nome, p in (("claro", LIGHT), ("escuro", DARK)):
            pares = {
                "texto/cartão": (p.ink, p.surface), "apoio/cartão": (p.ink_soft, p.surface),
                "texto/página": (p.ink, p.canvas), "marca/cartão": (p.brand, p.surface),
                "perigo": (p.danger, p.danger_soft), "aviso": (p.warn, p.warn_soft),
                "ok/cartão": (p.ok, p.surface), "cabeçalho": (p.header_text, p.brand_deep),
                "pílula desligada": (p.pill_offline_text, p.pill_offline),
            }
            for rotulo, (texto, fundo) in pares.items():
                with self.subTest(tema=nome, par=rotulo):
                    self.assertGreaterEqual(contraste(texto, fundo), 4.5, f"{nome} {rotulo}: {contraste(texto, fundo):.2f}")


if __name__ == "__main__":
    unittest.main()
