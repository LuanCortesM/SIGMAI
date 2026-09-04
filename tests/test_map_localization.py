# -*- coding: utf-8 -*-
"""Os três defeitos de língua/escrita que o caçador achou rodando 66 pedidos
em japonês, chinês, coreano, árabe, hebraico, russo, grego, tailandês e hindi.

Defeito 1 — a moldura do mapa (título padrão, "Fonte:"/"Elaboração:",
"Legenda", "Painel A/B", crédito da ferramenta) saía sempre em português,
mesmo quando título/subtítulo/legenda/fonte/autoria já vinham na língua do
usuário. ``maptext.py`` é a tabela de traduções, testada aqui diretamente
(pura, sem PyQGIS); o fio que liga ``map_language`` a cada texto gerado
(``_credit_line``, ``KNOWN_PARAMETERS``) é testável sem QGIS pelo mesmo motivo
que ``test_parameter_validation.py`` já testa ``_credit_line`` sem QGIS —
``compose.py`` só importa PyQGIS dentro de funções, nunca no topo do módulo.

Defeito 2 — um título largo demais para a caixa reservada era desenhado
inteiro e cortado nas duas bordas da página, em silêncio: ``QgsLayoutItemLabel``
não recusa nem quebra texto que não cabe. ``textfit.py`` é a lógica pura de
encolher/quebrar/recusar, testada aqui com uma medição sintética — a medição
real (que depende de fonte e DPI) só existe dentro do QGIS e foi conferida à
parte com ``tools/scenario_runner.py`` sob ``xvfb-run``, abrindo os PNGs
resultantes (ver o relatório da correção).

Defeito 3 — direção de escrita: o rodapé de um mapa inteiramente em
árabe/hebraico ficava sempre ancorado na margem esquerda. Só a metade
verificável em Python puro (a decisão de alinhamento) é testada aqui; o
comportamento de bidirecionalidade em si é do renderizador de texto do QGIS
e foi conferido por inspeção visual de PNGs — ver o relatório da correção
para como isso foi verificado e por que nenhuma inversão manual de ordem
entrou no código.
"""

from __future__ import annotations

import unicodedata
import unittest

from sigmai.cartography.compose import KNOWN_PARAMETERS, _credit_line
from sigmai.cartography.maptext import (
    MAP_TEXT,
    RTL_LANGUAGES,
    is_rtl,
    maptext,
    normalize_language,
    resolve_language,
)
from sigmai.cartography.rulebook import AUTHOR_MARKERS, SOURCE_MARKERS
from sigmai.cartography.textfit import MIN_FONT_PT, TextTooLongError, fit_text


# ---------------------------------------------------------------------------
# Defeito 1 — maptext.py
# ---------------------------------------------------------------------------

class LinguaAceitaDeFormaTolerante(unittest.TestCase):
    """resolve_language precisa da mesma tolerância de grafia que o resto do
    pacote já aplica a entrada de agente de IA (ver params.py, pagespec.py)."""

    def test_grafias_equivalentes_de_portugues(self) -> None:
        for codigo in ("pt", "pt-BR", "pt_BR", "PT-br", "pt-PT", "PT", ""):
            with self.subTest(codigo=codigo):
                chave, reconhecida = resolve_language(codigo)
                self.assertEqual(chave, "pt-BR")
                self.assertTrue(reconhecida)

    def test_grafias_equivalentes_de_chines(self) -> None:
        # "zh" sozinho é ambíguo entre simplificado e tradicional; o padrão
        # razoável é simplificado (mais falado). Regiões específicas resolvem
        # para o script que de fato usam.
        for codigo, esperado in (
            ("zh", "zh-Hans"), ("ZH", "zh-Hans"), ("zh-CN", "zh-Hans"), ("zh_cn", "zh-Hans"),
            ("zh-Hans", "zh-Hans"), ("zh-hans", "zh-Hans"),
            ("zh-TW", "zh-Hant"), ("zh-Hant", "zh-Hant"), ("zh-HK", "zh-Hant"),
        ):
            with self.subTest(codigo=codigo):
                self.assertEqual(normalize_language(codigo), esperado)

    def test_grafias_regionais_diversas(self) -> None:
        casos = {
            "en-US": "en", "en-GB": "en", "EN": "en",
            "es-ES": "es", "es-MX": "es",
            "ja-JP": "ja", "JP": "ja",
            "ko-KR": "ko", "kr": "ko",
            "he-IL": "he", "iw": "he",
        }
        for codigo, esperado in casos.items():
            with self.subTest(codigo=codigo):
                self.assertEqual(normalize_language(codigo), esperado)

    def test_lingua_desconhecida_cai_em_pt_br_e_marca_nao_reconhecida(self) -> None:
        # Uma língua que a tabela não cobre não pode estourar, mas também não
        # pode evaporar em silêncio: compose.py usa o segundo valor da tupla
        # para registrar uma nota avisando que o pedido de língua não "pegou".
        for codigo in ("klingon", "xx-YY", "esperanto"):
            with self.subTest(codigo=codigo):
                chave, reconhecida = resolve_language(codigo)
                self.assertEqual(chave, "pt-BR")
                self.assertFalse(reconhecida)

    def test_ausencia_de_lingua_e_diferente_de_lingua_nao_reconhecida(self) -> None:
        # Nulo/vazio é "ninguém pediu língua nenhuma" — o mesmo padrão que
        # as_text já usa em compose.py para default (ver params.py). Um tipo
        # que nem é texto (compose.py nunca chama resolve_language com um
        # destes: as_text já teria recusado antes) também não pode estourar.
        for codigo in (None, "", "  ", 123, ["ja"]):
            with self.subTest(codigo=codigo):
                chave, _reconhecida = resolve_language(codigo)  # type: ignore[arg-type]
                self.assertEqual(chave, "pt-BR")


class VarreduraDeTodasAsChavesEmTodasAsLinguas(unittest.TestCase):
    """"É melhor uma língua a menos do que uma tradução errada": a tabela por
    língua é parcial de propósito. maptext() tem de completar toda chave
    ausente com o valor de pt-BR, para NENHUMA combinação (língua, chave)
    nunca devolver vazio, None, ou estourar."""

    def test_toda_chave_de_referencia_existe_em_toda_lingua_declarada(self) -> None:
        chaves_referencia = set(MAP_TEXT["pt-BR"])
        self.assertTrue(chaves_referencia, "a tabela de referência não pode estar vazia")
        for lingua in MAP_TEXT:
            for chave in chaves_referencia:
                with self.subTest(lingua=lingua, chave=chave):
                    texto = maptext(lingua, chave)
                    self.assertIsInstance(texto, str)
                    self.assertTrue(texto.strip(), f"{lingua}/{chave} devolveu vazio")

    def test_nenhuma_lingua_declara_chave_que_pt_br_nao_tem(self) -> None:
        # Uma chave órfã (só numa língua, ausente do fallback) quebraria a
        # garantia de queda: maptext() cairia para _PT_BR.get(key, key) e
        # devolveria a CHAVE crua em vez de um texto, só para essa língua.
        chaves_referencia = set(MAP_TEXT["pt-BR"])
        for lingua, tabela in MAP_TEXT.items():
            with self.subTest(lingua=lingua):
                self.assertTrue(set(tabela) <= chaves_referencia)

    def test_lingua_desconhecida_como_chave_de_maptext_tambem_cai_em_pt_br(self) -> None:
        self.assertEqual(maptext("klingon", "titulo_padrao"), MAP_TEXT["pt-BR"]["titulo_padrao"])
        self.assertEqual(maptext("klingon", "legenda_padrao"), MAP_TEXT["pt-BR"]["legenda_padrao"])

    def test_chave_que_nem_pt_br_tem_no_pior_caso_devolve_a_propria_chave(self) -> None:
        # Não é um caso esperado (toda chave usada em compose.py existe em
        # pt-BR), mas maptext() não pode estourar mesmo aqui — um typo na
        # chamada não pode virar exceção no meio da composição de um mapa.
        self.assertEqual(maptext("en", "chave_que_nao_existe_em_lugar_nenhum"), "chave_que_nao_existe_em_lugar_nenhum")

    def test_minimo_de_linguas_pedido_no_briefing_esta_coberto(self) -> None:
        exigidas = {
            "pt-BR", "en", "es", "fr", "de", "it", "ja",
            "zh-Hans", "zh-Hant", "ko", "ru", "ar", "he",
        }
        self.assertTrue(exigidas <= set(MAP_TEXT))


class DirecaoDeEscrita(unittest.TestCase):
    """RTL_LANGUAGES/is_rtl — usado por compose.py para decidir alinhamento
    do rodapé (defeito 3). Só árabe e hebraico correm da direita para a
    esquerda entre as línguas cobertas."""

    def test_arabe_e_hebraico_sao_rtl(self) -> None:
        self.assertTrue(is_rtl("ar"))
        self.assertTrue(is_rtl("he"))
        self.assertEqual(RTL_LANGUAGES, frozenset({"ar", "he"}))

    def test_demais_linguas_cobertas_nao_sao_rtl(self) -> None:
        for lingua in MAP_TEXT:
            if lingua in RTL_LANGUAGES:
                continue
            with self.subTest(lingua=lingua):
                self.assertFalse(is_rtl(lingua))

    def test_grafia_tolerante_tambem_vale_para_is_rtl(self) -> None:
        self.assertTrue(is_rtl("AR"))
        self.assertTrue(is_rtl("he-IL"))
        self.assertTrue(is_rtl("ara"))  # apelido ISO 639-2


class CreditLineFalaALinguaDoMapa(unittest.TestCase):
    """_credit_line (compose.py) é o ponto que gravava "Fonte:"/"Elaboração:"/
    "Produzido com SIGMAI/QGIS" cravados em português. Testável sem PyQGIS
    pelo mesmo motivo que test_parameter_validation.py já testa esta função:
    compose.py só importa PyQGIS dentro de _imports(), nunca no topo."""

    def test_padrao_sem_map_language_continua_em_portugues(self) -> None:
        # Ninguém que já usa o plugin pode ver o texto mudar por causa desta
        # correção: map_language tem de ser 100% opt-in.
        linha = _credit_line({"data_source": "IBGE", "map_author": "L. Maciel"}, "EPSG:4674", "04/09/2026")
        self.assertIn("Fonte: IBGE", linha)
        self.assertIn("Elaboração: L. Maciel", linha)
        self.assertIn("Produzido com SIGMAI/QGIS", linha)

    def test_map_language_traduz_os_rotulos_gerados(self) -> None:
        linha = _credit_line(
            {"data_source": "IBGE", "map_author": "L. Maciel"}, "EPSG:4674", "04/09/2026", "ja",
        )
        self.assertIn("出典: IBGE", linha)
        self.assertIn("作成: L. Maciel", linha)
        self.assertIn("SIGMAI/QGISで作成", linha)
        # E não pode sobrar nenhuma palavra do rótulo em português.
        self.assertNotIn("Fonte:", linha)
        self.assertNotIn("Elaboração:", linha)
        self.assertNotIn("Produzido", linha)

    def test_map_language_desconhecido_tambem_nao_quebra_credit_line(self) -> None:
        linha = _credit_line({"data_source": "IBGE"}, "EPSG:4674", "04/09/2026", "klingon")
        self.assertIn("Fonte: IBGE", linha)  # cai em pt-BR, não estoura

    def test_valores_nulos_continuam_sem_imprimir_none_em_qualquer_lingua(self) -> None:
        # Regressão que test_parameter_validation.py já cobre para pt-BR;
        # aqui é a mesma garantia com map_language setado.
        for lingua in ("pt-BR", "en", "ja", "ar"):
            with self.subTest(lingua=lingua):
                linha = _credit_line(
                    {"data_source": None, "map_author": None, "organization": None}, "", "", lingua,
                )
                self.assertNotIn("None", linha)


class ParametroMapLanguage(unittest.TestCase):
    """map_language precisa ser um parâmetro aceito por compose_map — fora de
    KNOWN_PARAMETERS ele cairia na recusa de "parâmetro desconhecido"."""

    def test_map_language_esta_em_known_parameters(self) -> None:
        self.assertIn("map_language", KNOWN_PARAMETERS)


# ---------------------------------------------------------------------------
# Defeito 2 — textfit.py
# ---------------------------------------------------------------------------

def _medida_sintetica(texto: str, pt: float) -> float:
    """(texto, pt) -> largura em mm: cada caractere pesa o mesmo, linear em
    pt. Não precisa ser realista — só monotônica em comprimento e tamanho de
    fonte — para exercitar a lógica de quebra/encolhimento/recusa sem
    depender de QFontMetricsF/QGIS. A medição real é conferida à parte com
    tools/scenario_runner.py (ver o relatório da correção)."""
    return len(texto) * pt * 0.35


class TextoQueJaCabeFicaIntocado(unittest.TestCase):
    """Ninguém que já compõe mapas com título curto pode ver mudança nenhuma
    — nem quebra, nem fonte menor — por causa desta correção."""

    def test_texto_curto_nao_e_alterado(self) -> None:
        resultado = fit_text("Mapa do Parque", 200.0, 15.0, _medida_sintetica)
        self.assertEqual(resultado.lines, ("Mapa do Parque",))
        self.assertEqual(resultado.font_pt, 15.0)
        self.assertFalse(resultado.shrunk)
        self.assertFalse(resultado.wrapped)

    def test_texto_vazio_nao_estoura(self) -> None:
        resultado = fit_text("   ", 200.0, 15.0, _medida_sintetica)
        self.assertEqual(resultado.text, "")


class QuebraEmEscritaSemEspaco(unittest.TestCase):
    """Defeito 2, causa raiz: CJK e tailandês não têm espaço entre palavras,
    então não há onde o QGIS quebrar linha sozinho. fit_text tem de inserir
    pontos de quebra entre ideogramas — sem precisar reduzir a fonte, se
    quebrar já for suficiente."""

    def test_cjk_longo_quebra_em_vez_de_so_encolher(self) -> None:
        texto_sem_espaco = "伊" * 60  # nenhum espaço em lugar nenhum
        resultado = fit_text(texto_sem_espaco, 50.0, 15.0, _medida_sintetica)
        self.assertGreater(len(resultado.lines), 1)
        self.assertTrue(resultado.wrapped)
        self.assertFalse(resultado.shrunk)  # quebrar bastou; não precisou encolher
        for linha in resultado.lines:
            self.assertLessEqual(_medida_sintetica(linha, resultado.font_pt), 50.0 * 0.99 + 1e-6)

    def test_controle_espaco_evita_o_encolhimento_que_a_falta_de_espaco_forca(self) -> None:
        # A prova central do defeito 2, replicada em miniatura: o cenário
        # "stress-pt-nospace" do caçador mostrou um título em PORTUGUÊS sem
        # espaço nenhum sofrendo o mesmo corte que os títulos em CJK/tailandês
        # — ou seja, a causa é a ausência de ponto de quebra, não a escrita.
        # Aqui: a MESMA palavra latina repetida, sem e com espaço entre as
        # repetições, na mesma largura/fonte. Sem espaço não há onde quebrar
        # e fit_text só pode encolher; com espaço, QGIS teria como quebrar
        # sozinho e o tamanho original é preservado.
        palavra = "Carnaubas"
        sem_espaco = palavra * 2  # 18 caracteres: largo demais a 15pt, cabe encolhido no piso
        com_espaco = (palavra + " ") * 2
        r_sem = fit_text(sem_espaco, 60.0, 15.0, _medida_sintetica)
        r_com = fit_text(com_espaco, 60.0, 15.0, _medida_sintetica)
        self.assertTrue(r_sem.shrunk)
        self.assertFalse(r_sem.wrapped)  # uma só "palavra": nada para quebrar
        self.assertFalse(r_com.shrunk)  # havia espaço: quebrar bastou
        self.assertTrue(r_com.wrapped)

    def test_latim_sem_espaco_nao_tem_onde_quebrar_so_encolhe(self) -> None:
        # É o cenário de controle stress-pt-nospace: uma palavra latina sem
        # espaço nenhum não pode ganhar quebra inventada — quebrar uma
        # palavra ao meio não é a mesma coisa que quebrar entre ideogramas.
        texto = "A" * 20
        resultado = fit_text(texto, 50.0, 15.0, _medida_sintetica)
        self.assertFalse(resultado.wrapped)
        self.assertTrue(resultado.shrunk)
        self.assertEqual(resultado.lines, (texto,))


class MarcaCombinanteNuncaSeparadaDoBase(unittest.TestCase):
    """O defeito documentado explicitamente no regulamento: quebrar no meio
    de um agrupamento (dakuten japonês em forma NFD, sinal de tom/vogal
    tailandês) corrompe a leitura. Nenhuma linha resultante pode começar com
    uma marca combinante."""

    def test_dakuten_japones_em_forma_nfd_nunca_comeca_uma_linha(self) -> None:
        # "が" (ga) em NFD é "か" (ka) + marca de sonorização combinante —
        # exatamente o cenário ja-05-nfd do caçador.
        base_nfd = unicodedata.normalize("NFD", "が")
        self.assertEqual(len(base_nfd), 2)  # confirma que a normalização separou a marca
        texto = base_nfd * 40
        resultado = fit_text(texto, 30.0, 15.0, _medida_sintetica)
        for linha in resultado.lines:
            if linha:
                self.assertEqual(unicodedata.combining(linha[0]), 0, f"linha começa com marca combinante: {linha!r}")

    def test_sinal_de_tom_tailandes_nunca_comeca_uma_linha(self) -> None:
        # Consoante base + sinal de tom (mai ek, combinante) repetidos sem
        # nenhum espaço — o padrão do cenário stress-th-a5.
        texto = ("ก" + "่") * 40  # ก (consoante) + ่ (mai ek, Mn)
        resultado = fit_text(texto, 30.0, 15.0, _medida_sintetica)
        for linha in resultado.lines:
            if linha:
                self.assertEqual(unicodedata.category(linha[0]), "Lo", f"linha começa com marca combinante: {linha!r}")


class DevanagariNaoGanhaQuebraInventada(unittest.TestCase):
    """O regulamento pede, explicitamente, para NÃO quebrar devanágari sem
    uma regra segura de agrupamento (consoantes conjuntas ligadas por
    virama). fit_text trata devanágari como qualquer escrita sem regra de
    quebra conhecida: só encolhe ou recusa, nunca insere quebra própria."""

    def test_texto_devanagari_sem_espaco_so_encolhe_ou_recusa(self) -> None:
        texto = "क" * 20  # sem espaço, sem marca combinante
        resultado = fit_text(texto, 50.0, 15.0, _medida_sintetica)
        self.assertFalse(resultado.wrapped)


class PisoDeFonteRespeitaCart044(unittest.TestCase):
    """CART044 do regulamento: fonte impressa abaixo de 6pt já reprova em
    qualquer revisão editorial. fit_text nunca pode devolver menos que isso."""

    def test_nunca_encolhe_abaixo_do_piso(self) -> None:
        resultado = fit_text("A" * 15, 40.0, 15.0, _medida_sintetica)
        self.assertGreaterEqual(resultado.font_pt, MIN_FONT_PT)

    def test_piso_e_seis_pontos_como_o_regulamento_exige(self) -> None:
        self.assertEqual(MIN_FONT_PT, 6.0)

    def test_recusa_respeita_o_piso_pedido_por_quem_chama(self) -> None:
        piso_customizado = 8.0
        with self.assertRaises(TextTooLongError):
            fit_text("B" * 500, 10.0, 15.0, _medida_sintetica, min_font_pt=piso_customizado)


class RecusaQuandoNadaCabe(unittest.TestCase):
    """No limite — nem reduzindo a fonte até o piso, nem quebrando — fit_text
    tem de recusar dizendo quantos caracteres cabem, nunca cortar em silêncio."""

    def test_texto_absurdamente_longo_e_recusado_com_a_contagem_de_caracteres(self) -> None:
        with self.assertRaises(TextTooLongError) as ctx:
            fit_text("B" * 5000, 50.0, 15.0, _medida_sintetica)
        self.assertGreater(ctx.exception.max_chars, 0)
        self.assertLess(ctx.exception.max_chars, 5000)

    def test_mensagem_de_recusa_e_acionavel(self) -> None:
        with self.assertRaises(TextTooLongError) as ctx:
            fit_text("C" * 5000, 50.0, 15.0, _medida_sintetica)
        mensagem = str(ctx.exception)
        self.assertIn("CART044", mensagem)
        self.assertIn(str(ctx.exception.max_chars), mensagem)

    def test_cenario_legitimo_pequeno_nunca_e_recusado(self) -> None:
        # Guarda contra o risco oposto ao defeito: a correção não pode virar
        # tão conservadora a ponto de recusar um título perfeitamente comum.
        try:
            resultado = fit_text("Parque Estadual das Carnaúbas", 180.0, 15.0, _medida_sintetica)
        except TextTooLongError:
            self.fail("um título comum, que cabe, não pode ser recusado")
        self.assertEqual(resultado.lines, ("Parque Estadual das Carnaúbas",))


# ---------------------------------------------------------------------------
# Defeito 3 — direção de escrita (RTL)
# ---------------------------------------------------------------------------

class RodapeAlinhaConformeALingua(unittest.TestCase):
    """A única parte de defeito 3 decidível em Python puro: compose.py decide
    align="right" para o rodapé quando map_language é RTL, e "left" quando
    não é — a bidirecionalidade do texto em si é responsabilidade do
    renderizador do QGIS (ver o relatório da correção para como isso foi
    verificado por inspeção visual, e por que nenhuma heurística extra de
    reordenação de texto entrou no código)."""

    def test_decisao_de_alinhamento_e_rtl_para_arabe_e_hebraico(self) -> None:
        for lingua in ("ar", "he", "AR", "he-IL"):
            with self.subTest(lingua=lingua):
                self.assertTrue(is_rtl(lingua))

    def test_decisao_de_alinhamento_e_ltr_para_as_demais_linguas_cobertas(self) -> None:
        for lingua in MAP_TEXT:
            if lingua in RTL_LANGUAGES:
                continue
            with self.subTest(lingua=lingua):
                self.assertFalse(is_rtl(lingua))


# ---------------------------------------------------------------------------
# Regressão do regulamento: CART007 precisa reconhecer "Fonte:"/"Elaboração:"
# traduzidos, senão a tradução do defeito 1 criaria um defeito novo na
# auditoria — um mapa japonês com data_source/map_author preenchidos seria
# acusado de "sem procedência" só porque o detector só conhecia pt/en.
# ---------------------------------------------------------------------------

class MarcadoresDeProcedenciaAcompanhamMapLanguage(unittest.TestCase):
    def test_marcadores_originais_em_pt_e_en_continuam_presentes(self) -> None:
        for original in ("fonte:", "source:", "elabora", "author"):
            with self.subTest(original=original):
                self.assertIn(original, SOURCE_MARKERS + AUTHOR_MARKERS)

    def test_fonte_traduzida_e_reconhecida_como_marcador_de_procedencia(self) -> None:
        for lingua in MAP_TEXT:
            marcador_fonte = maptext(lingua, "fonte").strip().rstrip(":").strip().lower() + ":"
            with self.subTest(lingua=lingua):
                self.assertIn(marcador_fonte, SOURCE_MARKERS)

    def test_elaboracao_traduzida_e_reconhecida_como_marcador_de_autoria(self) -> None:
        for lingua in MAP_TEXT:
            marcador_autor = maptext(lingua, "elaboracao").strip().rstrip(":").strip().lower() + ":"
            with self.subTest(lingua=lingua):
                self.assertIn(marcador_autor, AUTHOR_MARKERS)


if __name__ == "__main__":
    unittest.main()
