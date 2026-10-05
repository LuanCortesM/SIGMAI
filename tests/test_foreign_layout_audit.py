"""A auditoria precisa enxergar layouts que o SIGMAI não compôs.

Origem: um experimento de comparação. Um agente com acesso total ao
computador fez, em PyQGIS puro, um mapa A4 retrato completo — título,
subtítulo, grade anotada, legenda, barra e escala numérica, rosa dos ventos,
inserto com quadro-guia, bloco "FONTES DOS DADOS", autoria e data. O
``audit_map_layout`` do SIGMAI deu a esse mapa nota **D (50/100)**: "nenhum
item com papel de título", "falta a linha de fonte". Os itens não tinham
``id`` — o QGIS deixa o id vazio em tudo que se cria pela interface, e
scripts raramente o preenchem — e o inspetor descartava itens sem id. Com o
primeiro remendo a nota caiu para **E**: a página 210x297 era lida como
paisagem (tudo abaixo de 210 mm "fora da página") e a tinta era medida no
inserto, não no quadro principal. Depois **C**: a legenda observada tinha
``item_id`` vazio, o cabeçalho "FONTES DOS DADOS" sem dois-pontos não
contava como fonte, e camadas só-de-rótulo (``QgsNullSymbolRenderer``) eram
cobradas na legenda.

Cada classe abaixo fixa um desses degraus. As que precisam de PyQGIS são
puladas — não reprovadas — numa máquina sem QGIS.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography import inspector  # noqa: E402
from sigmai.cartography.pagespec import resolve_page  # noqa: E402
from sigmai.cartography.rulebook import SOURCE_MARKERS, evaluate  # noqa: E402


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


def _entry(item_id, type_name, **extra):
    entry = {"id": item_id, "type": type_name, "role": type_name, "x": 0.0, "y": 0.0, "width": 10.0, "height": 5.0}
    entry.update(extra)
    return entry


class PapeisInferidosSemId(unittest.TestCase):
    """``_infer_roles`` preenche o que o id não diz — e só isso."""

    def test_titulo_e_o_maior_corpo_e_subtitulo_o_rotulo_logo_abaixo(self):
        titulo = _entry("label#1", "label", text="Parque", font_size_pt=15.0, y=6.0, height=10.0, id_inferred=True)
        sub = _entry("label#2", "label", text="Municípios", font_size_pt=9.5, y=15.0, height=6.0, id_inferred=True)
        nota = _entry("label#3", "label", text="malha indisponível", font_size_pt=6.5, y=169.0, id_inferred=True)
        inspector._infer_roles([(None, titulo), (None, sub), (None, nota)])
        self.assertEqual(titulo["role"], "title")
        self.assertTrue(titulo["role_inferred"])
        self.assertEqual(sub["role"], "subtitle")
        self.assertEqual(nota["role"], "label")

    def test_bloco_de_fontes_vence_a_assinatura_do_software(self):
        assinatura = _entry("label#1", "label", text="Mapa elaborado em QGIS 3.34", font_size_pt=6.0, id_inferred=True)
        fontes = _entry("label#2", "label", text="FONTES DOS DADOS\n• IBGE 2024", font_size_pt=6.8, id_inferred=True)
        autoria = _entry("label#3", "label", text="Elaboração: Maria Silva", font_size_pt=7.5, id_inferred=True)
        inspector._infer_roles([(None, assinatura), (None, fontes), (None, autoria)])
        self.assertEqual(fontes["role"], "source")
        self.assertEqual(assinatura["role"], "label")

    def test_quadro_menor_com_quadro_guia_vira_inserto(self):
        principal = _entry("map#2", "map", width=175.0, height=161.0, overviews=0, id_inferred=True)
        inserto = _entry("map#1", "map", width=58.0, height=83.0, overviews=1, id_inferred=True)
        inspector._infer_roles([(None, inserto), (None, principal)])
        self.assertEqual(principal["role"], "map")
        self.assertEqual(inserto["role"], "inset")

    def test_layout_do_sigmai_com_ids_explicitos_sai_intocado(self):
        itens = [
            _entry("title", "label", role="title", text="T", font_size_pt=15.0),
            _entry("subtitle", "label", role="subtitle", text="S", font_size_pt=9.0, y=12.0),
            _entry("footer", "label", role="source", text="Fonte: IBGE · Elaboração: X", font_size_pt=7.0),
            _entry("main_map", "map", role="map", width=200.0, height=150.0, overviews=0),
            _entry("comparison_map", "map", role="map", width=200.0, height=150.0, overviews=0),
        ]
        antes = [dict(i) for i in itens]
        inspector._infer_roles([(None, i) for i in itens])
        self.assertEqual(itens, antes)

    def test_imagem_de_rosa_dos_ventos_reconhecida_pelo_caminho(self):
        self.assertEqual(
            inspector._role_for("picture#1", "picture", "", "/usr/share/qgis/svg/arrows/NorthArrow_04.svg"),
            "north",
        )
        self.assertEqual(inspector._role_for("picture#1", "picture", "", "/tmp/logo_ufpi.png"), "picture")


class PaginaComDimensoesExplicitas(unittest.TestCase):
    def test_210x297_sem_orientacao_e_retrato(self):
        spec = resolve_page({"width_mm": 210.0, "height_mm": 297.0, "name": "detectada"})
        self.assertEqual((spec.width_mm, spec.height_mm, spec.orientation), (210.0, 297.0, "portrait"))

    def test_300x200_sem_orientacao_continua_paisagem(self):
        spec = resolve_page({"width_mm": 300, "height_mm": 200, "name": "custom"})
        self.assertEqual((spec.width_mm, spec.height_mm, spec.orientation), (300.0, 200.0, "landscape"))

    def test_nome_de_formato_sem_orientacao_continua_paisagem(self):
        spec = resolve_page("A4")
        self.assertEqual((spec.width_mm, spec.height_mm), (297.0, 210.0))

    def test_orientacao_explicita_ainda_vence(self):
        spec = resolve_page({"width_mm": 210.0, "height_mm": 297.0}, orientation="landscape")
        self.assertEqual((spec.width_mm, spec.height_mm), (297.0, 210.0))


class CabecalhoDeFontesSemDoisPontos(unittest.TestCase):
    def test_marcadores_de_cabecalho(self):
        for marcador in ("fontes dos dados", "fonte de dados", "data sources", "fuentes de datos"):
            self.assertIn(marcador, SOURCE_MARKERS)

    def test_bloco_de_fontes_em_cabecalho_passa_cart007(self):
        observation = {
            "page": {"width_mm": 210, "height_mm": 297, "content_area_mm": {"x": 10, "y": 10, "width": 190, "height": 277}},
            "items": [
                {"id": "label#2", "type": "label", "role": "source",
                 "text": "FONTES DOS DADOS\n• Malha municipal: IBGE 2024\nElaboração: Maria Silva", "font_size_pt": 6.8},
            ],
            "map": {}, "legend": None, "scalebar": None, "north": None, "map_frames": [], "inset": None, "output": {},
        }
        laudo = evaluate(observation)
        cart007 = next(c for c in laudo["results"] if c["id"] == "CART007")
        self.assertEqual(cart007["status"], "pass", cart007["detail_pt"])


class CamadasSoDeRotuloNaLegenda(unittest.TestCase):
    def _obs(self, listed):
        return {
            "page": {"width_mm": 210, "height_mm": 297, "content_area_mm": {"x": 10, "y": 10, "width": 190, "height": 277}},
            "items": [{"id": "legend#1", "type": "legend", "role": "legend"}],
            "map": {"item_id": "map#2", "visible_layer_names": ["UC", "Municipios", "rotulos"],
                    "label_only_layer_names": ["rotulos"]},
            "legend": {"item_id": "legend#1", "layer_names": listed},
            "scalebar": None, "north": None, "map_frames": [], "inset": None, "output": {},
        }

    def test_legenda_sem_a_camada_de_rotulos_passa_cart020(self):
        laudo = evaluate(self._obs(["UC", "Municipios"]))
        cart020 = next(c for c in laudo["results"] if c["id"] == "CART020")
        self.assertEqual(cart020["status"], "pass", cart020["detail_pt"])

    def test_legenda_que_lista_a_camada_de_rotulos_nao_e_fantasma(self):
        laudo = evaluate(self._obs(["UC", "Municipios", "rotulos"]))
        cart021 = next(c for c in laudo["results"] if c["id"] == "CART021")
        self.assertEqual(cart021["status"], "pass", cart021["detail_pt"])

    def test_camada_com_simbolo_de_verdade_continua_sendo_cobrada(self):
        laudo = evaluate(self._obs(["UC"]))
        cart020 = next(c for c in laudo["results"] if c["id"] == "CART020")
        self.assertEqual(cart020["status"], "fail")
        self.assertEqual(cart020["evidence"]["missing_layers"], ["Municipios"])


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class LayoutFeitoAMaoNoQgis(unittest.TestCase):
    """Um layout construído em PyQGIS puro, sem nenhum ``setId``."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _layout(self):
        from qgis.core import (
            QgsCoordinateReferenceSystem,
            QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemPicture,
            QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsNullSymbolRenderer, QgsPrintLayout,
            QgsProject, QgsRectangle, QgsUnitTypes, QgsVectorLayer,
        )
        from qgis.PyQt.QtGui import QFont

        project = QgsProject.instance()
        project.clear()
        poly = QgsVectorLayer("Polygon?crs=EPSG:31984&field=id:integer", "Municipios", "memory")
        pts = QgsVectorLayer("Point?crs=EPSG:31984&field=id:integer", "rotulos", "memory")
        pts.setRenderer(QgsNullSymbolRenderer())
        # Uma feição no quadro: com as camadas vazias o quadro sai em branco, e
        # desde que CART062 renderiza as camadas (E1, paper/tgis) isso é
        # acusado — com razão, mas não é o que este layout quer testar.
        from qgis.core import QgsFeature, QgsGeometry

        feicao = QgsFeature(poly.fields())
        feicao.setGeometry(QgsGeometry.fromRect(QgsRectangle(100, 100, 900, 900)))
        feicao.setAttribute("id", 1)
        poly.dataProvider().addFeatures([feicao])
        poly.updateExtents()
        project.addMapLayers([poly, pts])
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("manual")
        layout.pageCollection().page(0).setPageSize(QgsLayoutSize(210, 297, QgsUnitTypes.LayoutMillimeters))
        mm = QgsUnitTypes.LayoutMillimeters

        def label(text, x, y, w, h, pt):
            item = QgsLayoutItemLabel(layout)
            item.setText(text)
            font = QFont()
            font.setPointSizeF(pt)
            fmt = item.textFormat()
            fmt.setFont(font)
            fmt.setSize(pt)
            item.setTextFormat(fmt)
            item.attemptMove(QgsLayoutPoint(x, y, mm))
            item.attemptResize(QgsLayoutSize(w, h, mm))
            layout.addLayoutItem(item)
            return item

        label("Parque Estadual das Carnaúbas e municípios do entorno", 10, 6, 190, 10, 15)
        label("Municípios de Granja e Viçosa do Ceará", 10, 16, 190, 6, 9.5)
        main = QgsLayoutItemMap(layout)
        main.attemptMove(QgsLayoutPoint(20, 29, mm))
        main.attemptResize(QgsLayoutSize(175, 161, mm))
        main.setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        main.setExtent(QgsRectangle(0, 0, 1000, 1000))
        main.setLayers([poly, pts])
        layout.addLayoutItem(main)
        inset = QgsLayoutItemMap(layout)
        inset.attemptMove(QgsLayoutPoint(10, 203, mm))
        inset.attemptResize(QgsLayoutSize(58, 83, mm))
        inset.setExtent(QgsRectangle(-5000, -5000, 5000, 5000))
        inset.setLayers([poly])
        layout.addLayoutItem(inset)
        overview = inset.overview()
        overview.setLinkedMap(main)
        overview.setEnabled(True)
        legend = QgsLayoutItemLegend(layout)
        legend.setLinkedMap(main)
        legend.attemptMove(QgsLayoutPoint(72, 198, mm))
        layout.addLayoutItem(legend)
        bar = QgsLayoutItemScaleBar(layout)
        bar.setLinkedMap(main)
        bar.attemptMove(QgsLayoutPoint(73, 233, mm))
        layout.addLayoutItem(bar)
        north = QgsLayoutItemPicture(layout)
        north.setPicturePath("/usr/share/qgis/svg/arrows/NorthArrow_04.svg")
        north.attemptMove(QgsLayoutPoint(178, 32, mm))
        north.attemptResize(QgsLayoutSize(13, 16, mm))
        layout.addLayoutItem(north)
        label("FONTES DOS DADOS\n• IBGE 2024\nElaboração: Maria Silva\n06/09/2026\nSIRGAS 2000 / UTM 24S (EPSG:31984)",
              134, 198, 66, 88, 6.8)
        label("Escala 1:450.000", 72, 243, 58, 5, 7.5)
        project.layoutManager().addLayout(layout)
        return layout

    def test_observacao_reconhece_todos_os_papeis(self):
        layout = self._layout()
        obs = inspector.observe_layout(layout)
        papeis = {item["role"] for item in obs["items"]}
        self.assertTrue({"title", "subtitle", "source", "map", "inset", "legend", "scalebar", "north", "scale_text"} <= papeis, papeis)
        self.assertEqual(obs["legend"]["item_id"], "legend#1")
        self.assertEqual(obs["north"]["item_id"], "picture#1")
        self.assertEqual(obs["inset"]["overviews"], 1)
        self.assertEqual(obs["map"]["label_only_layer_names"], ["rotulos"])
        self.assertEqual(obs["page"]["orientation"], "portrait")

    def test_regras_de_presenca_passam_e_a_pagina_e_retrato(self):
        layout = self._layout()
        from sigmai.qgis_actions.cartography_engine import audit_map_layout

        laudo = audit_map_layout({"layout_name": "manual"}, {})
        por_id = {c["id"]: c for c in laudo["results"]}
        for regra in ("CART001", "CART002", "CART005", "CART006", "CART007", "CART008", "CART009", "CART020", "CART021", "CART040"):
            self.assertEqual(por_id[regra]["status"], "pass", f"{regra}: {por_id[regra]['detail_pt']}")
        self.assertEqual(laudo["observation"]["page"]["width_mm"], 210.0)
        self.assertNotIn(laudo["grade"], ("D", "E"))

    def test_list_layouts_descreve_itens_sem_id(self):
        layout = self._layout()
        from sigmai.qgis_actions.layouts import _describe_layout

        descricao = _describe_layout(layout)
        self.assertEqual(len(descricao["items"]), 9)
        self.assertTrue(all(item.get("id_missing") for item in descricao["items"]))
        self.assertEqual(len(descricao["map_frames"]), 2)


if __name__ == "__main__":
    unittest.main()
