"""Figuras da 1.5: revista, painéis, localização, hexágonos, linha mínima e EPS.

A primeira parte não precisa do QGIS: são as decisões (letra do painel,
intervalo da grade no papel, fuso UTM, grade de painéis, cores das classes).
A segunda compõe mapas de verdade e confere o que sai no layout.
"""

from __future__ import annotations

import importlib.util
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


class Caixa:
    """Retângulo com a interface de QgsRectangle que as funções puras leem."""

    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def xMinimum(self) -> float:
        return self.x0

    def xMaximum(self) -> float:
        return self.x1

    def yMinimum(self) -> float:
        return self.y0

    def yMaximum(self) -> float:
        return self.y1

    def width(self) -> float:
        return self.x1 - self.x0

    def height(self) -> float:
        return self.y1 - self.y0


class Nome:
    def __init__(self, nome: str) -> None:
        self._nome = nome

    def name(self) -> str:
        return self._nome


class SemQgis(unittest.TestCase):
    def test_letra_do_painel_no_estilo_da_revista(self):
        from sigmai.cartography.journals import panel_label

        self.assertEqual([panel_label(i, "A") for i in range(3)], ["A", "B", "C"])
        self.assertEqual(panel_label(1, "a"), "b")
        self.assertEqual(panel_label(2, "(a)"), "(c)")
        self.assertEqual(panel_label(0, "(A)"), "(A)")
        self.assertEqual(panel_label(3, "a)"), "d)")
        self.assertEqual(panel_label(0, None), "A")

    def test_titulo_comum_da_legenda_de_paineis(self):
        from sigmai.cartography.maptext import common_layer_title

        self.assertEqual(common_layer_title(["Uso da terra 2000", "Uso da terra 2020"]), "Uso da terra")
        self.assertEqual(common_layer_title(["Rios", "Estradas"]), "Rios / Estradas")
        self.assertEqual(common_layer_title(["Geologia", "Geologia"]), "Geologia")

    def test_intervalo_da_grade_abre_ate_os_rotulos_caberem(self):
        from sigmai.cartography.scaling import (GRID_LABEL_GAP_MM, graticule_interval, graticule_interval_on_paper,
                                                grid_label_mm)

        rotulo = grid_label_mm("41°45'W", 6.5)
        intervalo = graticule_interval_on_paper(0.5, 30.0, rotulo, 4, geographic=True)
        self.assertGreaterEqual(30.0 * intervalo / 0.5, rotulo + GRID_LABEL_GAP_MM)
        # Num quadro largo o intervalo continua o de quatro divisões.
        self.assertEqual(graticule_interval_on_paper(0.5, 300.0, rotulo, 4, geographic=True),
                         graticule_interval(0.5, 4, geographic=True))

    def test_dois_paineis_empilhados_e_apoio_na_celula_vazia(self):
        from sigmai.cartography.layoutgrid import solve_layout

        pagina = {"width_mm": 84, "height_mm": 220, "name": "figura"}
        plano = solve_layout(page=pagina, template="publicacao", panels=2, panel_columns=1, include_title=False,
                             include_footer=False)
        self.assertAlmostEqual(plano.slots["map"].x, plano.slots["map_2"].x)
        self.assertGreater(plano.slots["map_2"].y, plano.slots["map"].y)

        plano = solve_layout(page={"width_mm": 180, "height_mm": 180, "name": "figura"}, template="publicacao",
                             panels=3, panel_columns=2, support_in_cell=True, include_title=False,
                             include_footer=False)
        self.assertEqual(plano.arrangement, "celula_vazia")
        self.assertGreater(plano.slots["legend"].x, plano.slots["map_3"].x + plano.slots["map_3"].width)
        self.assertGreater(plano.slots["legend"].y, plano.slots["map"].y + plano.slots["map"].height)

    def test_eps_sem_shell_e_caixa_lida_do_cabecalho(self):
        from sigmai.cartography.epsexport import eps_bounding_box_mm, eps_command, pdf_to_eps

        comando = eps_command("gs", "a.pdf", "b.eps")
        self.assertIn("-sDEVICE=eps2write", comando)
        self.assertIn("-dSAFER", comando)
        self.assertEqual(comando[-1], "a.pdf")
        with tempfile.TemporaryDirectory() as pasta:
            eps = os.path.join(pasta, "f.eps")
            with open(eps, "w", encoding="latin-1") as arquivo:
                arquivo.write("%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 238 323\n%%HiResBoundingBox: 0 0 238.11 323.15\n")
            largura, altura = eps_bounding_box_mm(eps)
            self.assertAlmostEqual(largura, 84.0, delta=0.1)
            self.assertAlmostEqual(altura, 114.0, delta=0.1)
            falha = pdf_to_eps(os.path.join(pasta, "x.pdf"), eps, ghostscript=os.path.join(pasta, "nao_existe.exe"))
            self.assertFalse(falha["ok"])

    def test_rios_pelo_nome_da_camada(self):
        from sigmai.cartography.symbology import _is_water_line

        for nome in ("Drenagem", "Rios", "Hidrografia BC250", "Cursos d'água", "River network"):
            self.assertTrue(_is_water_line(Nome(nome)), nome)
        for nome in ("Territórios quilombolas", "Rodovias", "Trilha"):
            self.assertFalse(_is_water_line(Nome(nome)), nome)

    def test_fuso_utm_julgado_pelo_recorte_impresso(self):
        from sigmai.cartography.compose import _fits_utm_zone

        # Geologia de Sete Cidades: de -42° a -40,7°, impressa até -42,8°; o fuso 24 vai a -42°.
        self.assertFalse(_fits_utm_zone(Caixa(-42.8, -8.0, -40.0, -3.1), 24))
        self.assertTrue(_fits_utm_zone(Caixa(-41.0, -5.0, -40.0, -4.0), 24))

    def test_revista_confere_a_linha_mais_fina(self):
        from sigmai.cartography.journals import check_figure, find_journal

        springer = find_journal("springer")
        problemas = check_figure(springer, 84.0, 120.0, 8.0, "tif", 600, False, 0.08, "camada 'hexágonos'")
        self.assertTrue(any("traço de 0.08 mm" in p and "hexágonos" in p for p in problemas), problemas)
        self.assertFalse(any("traço" in p for p in check_figure(springer, 84.0, 120.0, 8.0, "tif", 600, False, 0.1)))

    def test_hexagonos_contam_cada_ponto_uma_vez(self):
        from sigmai.cartography.pointdensity import HEX_NICE_AREAS_KM2, hex_area_for_scale, hex_bin, hex_side_for_area

        random.seed(5)
        pontos = [(random.uniform(0, 10_000), random.uniform(0, 10_000), random.randint(1, 4)) for _ in range(500)]
        celulas = hex_bin(pontos, hex_side_for_area(1_000_000))
        self.assertEqual(sum(celulas.values()), sum(n for _, _, n in pontos))
        self.assertIn(hex_area_for_scale(250_000), HEX_NICE_AREAS_KM2)

    def test_classes_de_contagem_do_claro_ao_escuro(self):
        from sigmai.cartography.symbology import COUNT_CLASS_MOST, count_class_colours
        from sigmai.cartography.vision import parse_hex, to_lab

        cores = count_class_colours(COUNT_CLASS_MOST)
        claridade = [to_lab(parse_hex(cor))[0] for cor in cores]
        self.assertEqual(len(cores), 6)
        self.assertEqual(claridade, sorted(claridade, reverse=True))

    def test_piso_da_saida_vazia_e_por_pixel(self):
        from sigmai.cartography.rulebook import _check_output_written

        figura = {"output": {"path": "f.png", "exists": True, "size_bytes": 8_800, "format": "png", "pixels": 1_200_000}}
        self.assertEqual(_check_output_written(figura).status, "pass")
        vazia = {"output": {"path": "f.png", "exists": True, "size_bytes": 900, "format": "png", "pixels": 1_200_000}}
        self.assertEqual(_check_output_written(vazia).status, "fail")

    def test_uma_barra_por_painel_basta_para_escalas_diferentes(self):
        from sigmai.cartography.rulebook import _check_comparison_panels

        observacao = {
            "map_frames": [{"item_id": "main_map", "scale": 70_000_000}, {"item_id": "comparison_map", "scale": 15_000_000},
                           {"item_id": "panel_map_3", "scale": 150_000}],
            "scalebar": {"item_id": "scale_bar"},
            "scalebars": [{"item_id": "scale_bar", "linked_map": "main_map"},
                          {"item_id": "scale_bar_b", "linked_map": "comparison_map"},
                          {"item_id": "scale_bar_c", "linked_map": "panel_map_3"}],
            "items": [],
        }
        self.assertEqual(_check_comparison_panels(observacao).status, "pass")
        observacao["scalebars"] = observacao["scalebars"][:1]
        self.assertEqual(_check_comparison_panels(observacao).status, "fail")

    def test_recorte_alto_estreita_para_a_coluna_menor(self):
        from sigmai.cartography.compose import _narrower_figure_width
        from sigmai.cartography.journals import find_journal
        from sigmai.cartography.layoutgrid import solve_layout

        plano = solve_layout(page={"width_mm": 190, "height_mm": 229, "name": "figura"}, template="publicacao",
                             include_title=False, include_footer=False, include_legend=False)
        faixa = Caixa(0, 0, 150_000, 550_000)  # 150 x 550 km, como a geologia de Sete Cidades
        largura = _narrower_figure_width((190.0, None, 240.0, 2.0, faixa), plano, {}, find_journal("elsevier"), 50.0)
        self.assertEqual(largura, 140.0)
        self.assertIsNone(_narrower_figure_width((190.0, None, 240.0, 2.0, faixa), plano, {"figure_width_mm": 190},
                                                 find_journal("elsevier"), 50.0))
        quadrado = Caixa(0, 0, 500_000, 500_000)
        self.assertIsNone(_narrower_figure_width((190.0, None, 240.0, 2.0, quadrado), plano, {}, find_journal("elsevier"),
                                                 50.0))


@unittest.skipUnless(HAS_QGIS, "PyQGIS indisponível")
class NoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def setUp(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:4674"))

    def _poligono(self, nome, wkt, crs="EPSG:4674"):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        camada = QgsVectorLayer(f"Polygon?crs={crs}&field=nome:string", nome, "memory")
        feicao = QgsFeature(camada.fields())
        feicao.setGeometry(QgsGeometry.fromWkt(wkt))
        feicao.setAttributes([nome])
        camada.dataProvider().addFeatures([feicao])
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        return camada

    def _retangulo(self, nome, x0, y0, x1, y1):
        return self._poligono(nome, f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))")

    def _losango(self, nome, cx, cy, r):
        return self._poligono(nome, f"POLYGON(({cx - r} {cy},{cx} {cy + r},{cx + r} {cy},{cx} {cy - r},{cx - r} {cy}))")

    def _pontos(self, nome, coords):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        camada = QgsVectorLayer("Point?crs=EPSG:4674&field=n:integer", nome, "memory")
        feicoes = []
        for x, y in coords:
            feicao = QgsFeature(camada.fields())
            feicao.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            feicao.setAttributes([1])
            feicoes.append(feicao)
        camada.dataProvider().addFeatures(feicoes)
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        return camada

    def _compor(self, pasta, nome, pedido, formato="pdf"):
        from sigmai.cartography.compose import compose_map

        base = {"title": "Teste", "title_placement": "caption", "data_source": "teste", "map_language": "pt-BR",
                "format": formato, "output_path": os.path.join(pasta, f"{nome}.{formato}"), "confirm_overwrite": True}
        return compose_map({**base, **pedido}, {"dry_run": False})

    @staticmethod
    def _falhas(resultado):
        return [r["id"] for r in resultado["audit"]["results"] if r["status"] == "fail"]

    @staticmethod
    def _itens(resultado):
        return {item["id"]: item for item in resultado["audit"]["observation"]["items"]}

    def test_figura_de_localizacao_tem_escala_e_barra_por_painel(self):
        pais = self._retangulo("País", -74, -34, -34, 5)
        estado = self._retangulo("Estado", -46, -11, -40.5, -2.8)
        parque = self._losango("Parque", -41.7, -4.2, 0.08)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "localizacao", {
                "layer_ids": [pais.id(), estado.id()], "subject_layer_id": pais.id(), "figure_width_mm": 180,
                "panels": [{"layer_ids": [estado.id(), parque.id()], "subject_layer_id": estado.id()},
                           {"layer_ids": [parque.id()], "subject_layer_id": parque.id()}]})
            escalas = [round(float(f["scale"])) for f in r["audit"]["observation"]["map_frames"]]
            self.assertEqual(len(set(escalas)), 3, escalas)
            ligadas = {b["linked_map"] for b in r["audit"]["observation"].get("scalebars", [])}
            self.assertEqual(ligadas, {"main_map", "comparison_map", "panel_map_3"})
            self.assertNotIn("CART066", self._falhas(r))
            self.assertGreaterEqual(self._itens(r)["main_map"].get("overviews", 0), 1)
            self.assertTrue(any("Figura de localização" in nota for nota in r["notes"]))
            self.assertIn("A ", r["audit"]["observation"]["caption"]["scale"])

    def test_paineis_empilham_na_coluna_simples_com_letra_da_revista(self):
        um = self._retangulo("Uso 2000", -42.0, -4.5, -41.5, -4.0)
        dois = self._retangulo("Uso 2020", -42.0, -4.5, -41.5, -4.0)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "paineis", {
                "layer_ids": [um.id()], "journal": "springer", "panel_title": "2000",
                "panels": [{"layer_ids": [dois.id()], "panel_title": "2020"}]}, formato="tif")
            itens = self._itens(r)
            self.assertAlmostEqual(itens["main_map"]["x"], itens["comparison_map"]["x"], delta=0.5)
            self.assertGreater(itens["comparison_map"]["y"], itens["main_map"]["y"])
            self.assertEqual(itens["panel_caption_a"]["text"], "a")  # Springer: a, b, c em minúscula
            self.assertEqual(itens["panel_caption_b"]["text"], "b")
            self.assertEqual(itens["panel_caption_b_name"]["text"], "2020")
            self.assertNotIn("CART001", self._falhas(r))

    def test_assunto_do_painel_fora_das_camadas_e_recusado(self):
        from sigmai.cartography.compose import CompositionError

        um = self._retangulo("A", -42, -5, -41, -4)
        dois = self._retangulo("B", -42, -5, -41, -4)
        with pasta_temporaria() as pasta, self.assertRaises(CompositionError) as recusa:
            self._compor(pasta, "x", {"layer_ids": [um.id()],
                                       "second_map": {"layer_ids": [dois.id()], "subject_layer_id": um.id()}})
        self.assertIn("não está nas layer_ids do painel", str(recusa.exception))

    def test_pontos_dos_paineis_com_o_mesmo_tamanho(self):
        random.seed(3)
        parque = self._losango("Parque", -41.7, -4.2, 0.1)
        muitos = self._pontos("Aves", [(-41.7 + random.gauss(0, 0.01), -4.2 + random.gauss(0, 0.01)) for _ in range(3000)])
        poucos = self._pontos("Plantas", [(-41.75, -4.22), (-41.68, -4.15), (-41.66, -4.25)])
        with pasta_temporaria() as pasta:
            self._compor(pasta, "pontos", {
                "layer_ids": [muitos.id(), parque.id()], "subject_layer_id": parque.id(), "figure_width_mm": 180,
                "panels": [{"layer_ids": [poucos.id(), parque.id()], "subject_layer_id": parque.id()}]})
            tamanhos = {camada.name(): round(float(camada.renderer().symbol().size()), 3) for camada in (muitos, poucos)}
        self.assertEqual(len(set(tamanhos.values())), 1, tamanhos)

    def test_linha_mais_fina_que_a_revista_aceita_e_engrossada(self):
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer

        from sigmai.cartography.symbology import STYLE_ORIGIN_USER, mark_style_origin

        area = self._losango("Área", -41.7, -4.2, 0.3)
        simbolo = QgsFillSymbol.createSimple({"color": "200,220,200", "outline_color": "black", "outline_width": "0.02"})
        area.setRenderer(QgsSingleSymbolRenderer(simbolo))
        mark_style_origin(area, STYLE_ORIGIN_USER)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "linha", {"layer_ids": [area.id()], "journal": "springer"}, formato="tif")
            espessura = area.renderer().symbol().symbolLayer(0).strokeWidth()
        self.assertGreaterEqual(espessura, 0.1 - 1e-6)
        self.assertNotIn("CART083", self._falhas(r))
        self.assertTrue(any("Traços engrossados" in nota for nota in r["notes"]))

    def test_recorte_que_cruza_fusos_vai_para_a_transversa_centrada(self):
        faixa = self._retangulo("Faixa", -43.4, -5.0, -40.6, -4.0)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "fuso", {"layer_ids": [faixa.id()], "figure_width_mm": 180})
        self.assertTrue(any("Transversa de Mercator centrada" in nota for nota in r["notes"]), r["notes"])
        self.assertNotIn("CART064", self._falhas(r))

    def test_recorte_alto_em_coluna_dupla_estreita_a_figura(self):
        alto = self._poligono("Faixa alta", "POLYGON((-41.2 -9,-40.6 -9,-40.4 -3,-41.0 -3,-41.2 -9))")
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "alto", {"layer_ids": [alto.id()], "journal": "elsevier",
                                             "journal_column": "double"})
        self.assertIn(r["page"]["width_mm"], (90.0, 140.0))
        self.assertTrue(any(nota.startswith("Figura com") for nota in r["notes"]), r["notes"])
        self.assertNotIn("CART069", self._falhas(r))

    def test_drenagem_sai_azul(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        area = self._losango("Bacia", -41.7, -4.2, 0.3)
        rios = QgsVectorLayer("LineString?crs=EPSG:4674", "Drenagem", "memory")
        feicao = QgsFeature()
        feicao.setGeometry(QgsGeometry.fromWkt("LINESTRING(-41.9 -4.2,-41.7 -4.25,-41.5 -4.1)"))
        rios.dataProvider().addFeatures([feicao])
        rios.updateExtents()
        QgsProject.instance().addMapLayer(rios)
        with pasta_temporaria() as pasta:
            self._compor(pasta, "rios", {"layer_ids": [rios.id(), area.id()], "subject_layer_id": area.id()})
            cor = rios.renderer().symbol().color().name().lower()
        self.assertEqual(cor, "#0072b2")

    def test_contorno_da_paleta_volta_a_ser_preenchido_quando_o_papel_muda(self):
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer

        from sigmai.cartography.symbology import STYLE_ORIGIN_PALETTE, _is_filled, apply_default_symbology, mark_style_origin

        estado = self._retangulo("Estado", -46, -11, -40.5, -2.8)
        contorno = QgsFillSymbol.createSimple({"color": "255,255,255,0", "style": "no", "outline_color": "black",
                                               "outline_width": "0.45"})
        estado.setRenderer(QgsSingleSymbolRenderer(contorno))
        mark_style_origin(estado, STYLE_ORIGIN_PALETTE)
        self.assertFalse(_is_filled(estado))
        apply_default_symbology([estado], "missing", outline_ids=set())
        self.assertTrue(_is_filled(estado))

    def test_hexagonos_com_classes_de_contagem(self):
        random.seed(9)
        parque = self._losango("Parque", -44.6, -22.4, 0.15)
        registros = self._pontos("Registros", [(-44.6 + random.gauss(0, 0.05), -22.4 + random.gauss(0, 0.05))
                                               for _ in range(4000)])
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "hex", {"layer_ids": [registros.id(), parque.id()], "subject_layer_id": parque.id(),
                                            "dense_points": "grid", "figure_width_mm": 88})
        self.assertNotIn("CART070", self._falhas(r))
        self.assertNotIn("CART076", self._falhas(r))
        nomes = r["audit"]["observation"]["legend"]["layer_names"] if r["audit"]["observation"].get("legend") else []
        self.assertTrue(any("célula" in str(n) or "km²" in str(n) for n in nomes) or
                        any("célula" in nota for nota in r["notes"]), (nomes, r["notes"]))

    def test_figura_de_revista_poe_legenda_barra_e_norte_dentro_do_quadro(self):
        # Uma área pequena no meio de uma região: os cantos do quadro ficam sem dado do assunto.
        regiao = self._retangulo("Região", -43.0, -5.5, -40.4, -2.9)
        area = self._losango("Área", -41.7, -4.2, 0.25)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "dentro", {"layer_ids": [area.id(), regiao.id()], "subject_layer_id": area.id(),
                                               "margin_percent": 60, "journal": "biodiversity_informatics"})
        self.assertEqual(r["legend"]["placement"], "inside")
        self.assertIn("scale", r["audit"]["observation"]["caption"])
        self.assertEqual(self._falhas(r), [])

    def test_camada_vermelha_vai_para_o_cinza_no_inserto(self):
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer

        from sigmai.cartography.compose import _competes_with_marker, _inset_style_overrides

        estados = self._retangulo("Estados", -50, -25, -40, -15)
        estados.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "255,255,255,0", "style": "no", "outline_color": "#B2182B", "outline_width": "0.45"})))
        self.assertTrue(_competes_with_marker(estados))
        override = _inset_style_overrides([estados], [estados])[estados.id()]
        self.assertNotIn("178,24,43", override)  # o vermelho da divisa não vai para o inserto
        # No cinza, a divisa continua afinada como as outras camadas do mapa no inserto.
        import xml.etree.ElementTree as ET

        from sigmai.cartography.compose import INSET_OUTLINE_MAX_MM

        raiz = ET.fromstring(override.split("\n", 1)[1])
        larguras = [float(o.get("value")) for o in raiz.iter("Option") if o.get("name") == "outline_width"]
        larguras += [float(p.get("v")) for p in raiz.iter("prop") if p.get("k") == "outline_width"]
        self.assertTrue(larguras)
        self.assertLessEqual(max(larguras), INSET_OUTLINE_MAX_MM)
        parque = self._losango("Parque", -44.6, -22.4, 0.2)
        parque.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "255,255,255,0", "style": "no", "outline_color": "#1A1A1A", "outline_width": "0.45"})))
        self.assertFalse(_competes_with_marker(parque))

    def test_receita_refaz_o_estilo_da_camada_restilizada_no_mesmo_projeto(self):
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer

        from sigmai.cartography.symbology import STYLE_ORIGIN_USER, _is_filled, mark_style_origin
        from sigmai.qgis_actions.cartography_engine import recompose_from_recipe

        parque = self._losango("Parque", -44.6, -22.4, 0.2)
        parque.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "#E69F00", "outline_color": "#8C5A00", "outline_width": "0.4"})))
        mark_style_origin(parque, STYLE_ORIGIN_USER)
        with pasta_temporaria() as pasta:
            self._compor(pasta, "fig2", {"layer_ids": [parque.id()], "figure_width_mm": 88,
                                         "recipe_path": os.path.join(pasta, "fig2.json")})
            # Para a figura seguinte, o parque vira contorno.
            parque.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
                {"color": "255,255,255,0", "style": "no", "outline_color": "black", "outline_width": "0.45"})))
            self.assertFalse(_is_filled(parque))
            recompose_from_recipe({"recipe_path": os.path.join(pasta, "fig2.json"),
                                   "overrides": {"output_path": os.path.join(pasta, "fig2_de_novo.pdf")}},
                                  {"dry_run": False})
            self.assertTrue(_is_filled(parque))

    def test_eps_vetorial_na_largura_da_revista(self):
        from sigmai.cartography.epsexport import eps_bounding_box_mm, find_ghostscript

        if find_ghostscript() is None:
            self.skipTest("Ghostscript indisponível neste computador")
        area = self._losango("Área", -41.7, -4.2, 0.4)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "figura", {"layer_ids": [area.id()], "journal": "springer"}, formato="eps")
            caminho = os.path.join(pasta, "figura.eps")
            with open(caminho, "rb") as arquivo:
                cabecalho = arquivo.read(32)
            largura, _altura = eps_bounding_box_mm(caminho)
        self.assertTrue(cabecalho.startswith(b"%!PS-Adobe"))
        self.assertAlmostEqual(largura, 84.0, delta=0.5)
        self.assertNotIn("CART083", self._falhas(r))

    def test_eps_sem_ghostscript_e_recusado_antes_de_compor(self):
        from sigmai.cartography import compose

        area = self._losango("Área", -41.7, -4.2, 0.4)
        original = compose.find_ghostscript
        compose.find_ghostscript = lambda *args, **kwargs: None
        try:
            with self.assertRaises(compose.CompositionError) as recusa:
                compose.compose_map({"layer_ids": [area.id()], "journal": "springer", "format": "eps",
                                     "title_placement": "caption", "data_source": "teste"}, {"dry_run": True})
        finally:
            compose.find_ghostscript = original
        self.assertIn("Ghostscript", str(recusa.exception))
        self.assertIn("TIFF", str(recusa.exception))

    def _varios(self, nome, wkts, tipo="Polygon"):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        camada = QgsVectorLayer(f"{tipo}?crs=EPSG:4674&field=n:integer", nome, "memory")
        feicoes = []
        for numero, wkt in enumerate(wkts):
            feicao = QgsFeature(camada.fields())
            feicao.setGeometry(QgsGeometry.fromWkt(wkt))
            feicao.setAttributes([numero])
            feicoes.append(feicao)
        camada.dataProvider().addFeatures(feicoes)
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        return camada

    def test_inserto_na_faixa_continua_alto(self):
        # Mapa de localização para laudo (A4): com a legenda numa linha própria,
        # o inserto ia para uma tira de 9 mm embaixo, e o estado saía minúsculo.
        estado = self._retangulo("Estado", -46, -11, -40.5, -2.8)
        outras = self._retangulo("Outras unidades de conservação (CNUC/MMA via IBGE (2022))", -41.9, -4.4, -41.5, -4.0)
        parque = self._losango("Parque Nacional de Sete Cidades (CNUC/MMA via IBGE (2022))", -41.7, -4.2, 0.08)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "laudo", {
                "layer_ids": [parque.id(), outras.id()], "subject_layer_id": parque.id(), "page": "A4",
                "title_placement": "map", "include_inset": True, "inset_layer_ids": [estado.id()]})
        inserto = self._itens(r)["inset_map"]
        self.assertGreaterEqual(min(inserto["width"], inserto["height"]), 25.0, inserto)

    def test_poligono_sob_pontos_vira_contorno_e_agua_continua_preenchida(self):
        from sigmai.cartography.symbology import _is_filled

        random.seed(5)
        parque = self._losango("Parque", -41.7, -4.2, 0.1)
        lagoa = self._retangulo("Lagoa", -41.55, -4.35, -41.5, -4.3)
        registros = self._pontos("Registros", [(-41.7 + random.gauss(0, 0.08), -4.2 + random.gauss(0, 0.08))
                                               for _ in range(60)])
        with pasta_temporaria() as pasta:
            self._compor(pasta, "pontos", {"layer_ids": [registros.id(), parque.id(), lagoa.id()],
                                           "subject_layer_id": registros.id()})
            self.assertFalse(_is_filled(parque))
            self.assertTrue(_is_filled(lagoa))

    def test_estado_sob_a_malha_de_linhas_vira_contorno(self):
        from sigmai.cartography.symbology import _is_filled

        random.seed(6)
        # Cobre uns 57 % do retângulo das rodovias, que passam também pelos vizinhos.
        estado = self._poligono("Estado", "POLYGON((-45.5 -10.5,-40.5 -10.5,-40.5 -6,-42.5 -3.5,-45.5 -3.5,-45.5 -10.5))")
        trechos = []
        for _ in range(80):
            x, y = random.uniform(-46, -40), random.uniform(-11, -3)
            trechos.append(f"LINESTRING({x} {y},{x + random.uniform(-0.6, 0.6)} {y + random.uniform(-0.6, 0.6)})")
        rodovias = self._varios("Rodovias", trechos, "LineString")
        with pasta_temporaria() as pasta:
            self._compor(pasta, "rodovias", {"layer_ids": [rodovias.id(), estado.id()],
                                             "subject_layer_id": rodovias.id()})
            self.assertFalse(_is_filled(estado))

    def test_manchas_espalhadas_sob_a_drenagem_continuam_preenchidas(self):
        from sigmai.cartography.symbology import _is_filled

        # A extensão das manchas cobre a drenagem inteira; a área delas, quase nada.
        manchas = self._varios("Área edificada", [
            f"POLYGON(({x} {y},{x + 0.02} {y},{x + 0.02} {y + 0.02},{x} {y + 0.02},{x} {y}))"
            for x, y in ((-42.0, -4.5), (-41.4, -4.5), (-42.0, -3.9), (-41.4, -3.9), (-41.7, -4.2))])
        rios = self._varios("Drenagem", ["LINESTRING(-42 -4.5,-41.7 -4.2,-41.38 -3.88)",
                                         "LINESTRING(-42 -3.88,-41.7 -4.2,-41.38 -4.5)"], "LineString")
        with pasta_temporaria() as pasta:
            self._compor(pasta, "drenagem", {"layer_ids": [rios.id(), manchas.id()], "subject_layer_id": rios.id()})
            self.assertTrue(_is_filled(manchas))

    def test_parque_como_assunto_sob_os_pontos_vira_contorno(self):
        from sigmai.cartography.symbology import _is_filled

        # O parque, preenchido na figura de localização, é o assunto do mapa
        # dos registros e não pode continuar preenchido sob os pontos.
        random.seed(7)
        parque = self._losango("Parque", -41.7, -4.2, 0.1)
        municipios = self._retangulo("Municípios", -42.2, -4.7, -41.2, -3.7)
        registros = self._pontos("Registros", [(-41.7 + random.uniform(-0.04, 0.04), -4.2 + random.uniform(-0.04, 0.04))
                                               for _ in range(300)])
        with pasta_temporaria() as pasta:
            self._compor(pasta, "localizacao", {"layer_ids": [parque.id(), municipios.id()],
                                                "subject_layer_id": parque.id()})
            self.assertTrue(_is_filled(parque))
            self._compor(pasta, "registros", {"layer_ids": [registros.id(), parque.id()],
                                              "subject_layer_id": parque.id()})
            self.assertFalse(_is_filled(parque))

    def test_parque_como_assunto_com_pontos_fora_continua_preenchido(self):
        from sigmai.cartography.symbology import _is_filled

        # As sedes dos municípios em volta do parque não fazem dele um contorno.
        parque = self._losango("Parque", -41.7, -4.2, 0.1)
        sedes = self._pontos("Sedes", [(-41.95, -4.0), (-41.45, -4.0), (-41.95, -4.4), (-41.45, -4.4), (-41.7, -4.2)])
        with pasta_temporaria() as pasta:
            self._compor(pasta, "sedes", {"layer_ids": [sedes.id(), parque.id()], "subject_layer_id": parque.id()})
            self.assertTrue(_is_filled(parque))

    def test_figura_regional_sem_rotulos_na_grade_em_graus_reprova(self):
        from qgis.core import QgsLayoutItemMapGrid, QgsLayoutItemPicture, QgsProject

        from sigmai.cartography.compose import audit_layout

        # A figura de revista leva grade em graus sobre a UTM. A dispensa do
        # mapa-múndi (grade sem rótulos, sem rosa) não vale para ela.
        parque = self._losango("Parque", -41.7, -4.2, 0.1)
        with pasta_temporaria() as pasta:
            r = self._compor(pasta, "coluna", {"layer_ids": [parque.id()], "journal_column": "single",
                                               "figure_width_mm": 88})
            layout = QgsProject.instance().layoutManager().layoutByName(r["layout_name"])
            mapa = layout.itemById("main_map")
            grade = mapa.grids().grid(0)
            self.assertTrue(grade.crs().isGeographic(), "a figura de revista devia ter grade em graus")
            grade.setAnnotationEnabled(False)
            sem_rotulos = audit_layout(layout, collect_labels=False)
            for item in [i for i in layout.items() if isinstance(i, QgsLayoutItemPicture)]:
                layout.removeLayoutItem(item)
            sem_norte = audit_layout(layout, collect_labels=False)
        estado = {r["id"]: r["status"] for r in sem_rotulos["results"]}
        self.assertEqual(estado["CART027"], "fail")
        self.assertEqual({r["id"]: r["status"] for r in sem_norte["results"]}["CART006"], "fail")
        self.assertIsInstance(grade, QgsLayoutItemMapGrid)

    def test_escala_fixada_leva_margem_e_notas_junto(self):
        # Com a escala fixada, a resposta repetia "margem efetiva de 13,2 % para
        # fechar na escala 1:400.000", a escala que o ajuste tinha escolhido.
        parque = self._losango("Parque", -41.7, -4.2, 0.1)
        with pasta_temporaria() as pasta:
            auto = self._compor(pasta, "auto", {"layer_ids": [parque.id()]})["extent"]
            pedida = int(auto["scale_denominator"]) * 2
            fixa = self._compor(pasta, "fixa", {"layer_ids": [parque.id()], "scale": pedida})["extent"]
        self.assertEqual(int(fixa["scale_denominator"]), pedida)
        minima = float(auto["raw_scale_denominator"]) / 1.1
        self.assertAlmostEqual(float(fixa["effective_margin_percent"]), (pedida / minima - 1.0) * 50.0, delta=0.5)
        self.assertFalse([nota for nota in fixa["notes"] if "escala" in nota.lower()], fixa["notes"])

    def test_subdivisao_em_contorno_cinza(self):
        from sigmai.cartography.symbology import OUTLINE_COLOURS, SUBDIVISION_OUTLINE_COLOUR, apply_default_symbology

        estado = self._retangulo("Estado", -46, -11, -40.5, -2.8)
        municipios = self._varios("Municípios", [
            f"POLYGON(({x} {y},{x + 1} {y},{x + 1} {y + 1},{x} {y + 1},{x} {y}))"
            for x in range(-46, -41) for y in range(-11, -5)])
        apply_default_symbology([estado, municipios], "missing", outline_ids={estado.id(), municipios.id()},
                                outline_parent_ids={estado.id()})
        cor = municipios.renderer().symbol().symbolLayer(0).strokeColor().name().upper()
        self.assertEqual(cor, SUBDIVISION_OUTLINE_COLOUR.upper())
        self.assertIn(estado.renderer().symbol().symbolLayer(0).strokeColor().name().upper(),
                      {c.upper() for c in OUTLINE_COLOURS})


if __name__ == "__main__":
    unittest.main()
