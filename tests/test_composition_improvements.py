"""Melhorias de composição vindas do experimento "PyQGIS puro × SIGMAI".

* ``orientation: "auto"`` — a folha gira quando o recorte aproveita melhor;
* ``data_source`` por camada — legenda e crédito com a procedência de cada
  camada, camada desconhecida recusada, metadados da camada como reserva;
* ``add_context_annotations`` — divisa como linha, nomes por polo de
  inacessibilidade, rótulos avulsos, persistência em GeoPackage;
* legenda sem camadas só-de-rótulo.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography.compose import (  # noqa: E402
    AUTO_ORIENTATION_TERMS, JOURNAL_COLUMNS, SUPPORTED_FORMATS, CompositionError, KNOWN_PARAMETERS, _orientation_is_auto,
    _resolve_figure_width, resolve_data_sources,
)
from sigmai.cartography.layoutgrid import map_slot_keys, solve_layout  # noqa: E402


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


class ProcedenciaPorCamada(unittest.TestCase):
    LAYERS = [("id_mun", "Municípios", ""), ("id_uc", "PE das Carnaúbas", "CEUC - CEDIB/COBIO/SEMA")]

    def test_texto_unico_continua_valendo(self):
        self.assertEqual(resolve_data_sources("IBGE 2024", self.LAYERS), ("IBGE 2024", {}, []))
        self.assertEqual(resolve_data_sources(None, self.LAYERS)[0], "")
        self.assertEqual(resolve_data_sources(2024, self.LAYERS)[0], "2024")

    def test_dicionario_por_nome_ou_id_sem_diferenciar_caixa(self):
        credit, per_layer, notes = resolve_data_sources({"municípios": "IBGE, Malha 2024", "id_uc": "CEUC/SEMA-CE"}, self.LAYERS)
        self.assertEqual(per_layer, {"id_mun": "IBGE, Malha 2024", "id_uc": "CEUC/SEMA-CE"})
        self.assertEqual(credit, "IBGE, Malha 2024 (Municípios); CEUC/SEMA-CE (PE das Carnaúbas)")
        self.assertEqual(notes, [])

    def test_lista_de_objetos(self):
        credit, per_layer, _ = resolve_data_sources([{"layer": "Municípios", "source": "IBGE"}, {"layer": "id_uc", "source": "CEUC"}], self.LAYERS)
        self.assertEqual(per_layer, {"id_mun": "IBGE", "id_uc": "CEUC"})
        self.assertIn("IBGE (Municípios)", credit)

    def test_fontes_iguais_agrupam_camadas(self):
        credit, _, _ = resolve_data_sources({"id_mun": "IBGE 2024", "id_uc": "IBGE 2024"}, self.LAYERS)
        self.assertEqual(credit, "IBGE 2024 (Municípios, PE das Carnaúbas)")

    def test_camada_desconhecida_e_recusada_com_a_lista(self):
        with self.assertRaises(CompositionError) as ctx:
            resolve_data_sources({"Rios": "ANA"}, self.LAYERS)
        self.assertIn("'Rios'", str(ctx.exception))
        self.assertIn("Municípios (id_mun)", str(ctx.exception))

    def test_metadados_da_camada_preenchem_o_que_faltou_com_nota(self):
        credit, per_layer, notes = resolve_data_sources({"id_mun": "IBGE 2024"}, self.LAYERS)
        self.assertEqual(per_layer["id_uc"], "CEUC - CEDIB/COBIO/SEMA")
        self.assertTrue(any("metadados" in n for n in notes))
        self.assertIn("CEUC - CEDIB/COBIO/SEMA (PE das Carnaúbas)", credit)

    def test_camada_derivada_herda_a_fonte_da_origem_e_fica_fora_do_credito(self):
        """Divisa e nomes derivados do limite estadual não são 'sem fonte' nem entram no crédito."""
        layers = [("id_uf", "Limite estadual", ""), ("id_div", "Divisa — Limite estadual", "", "id_uf"),
                  ("id_nomes", "Nomes — Limite estadual", "", "id_uf")]
        credit, per_layer, notes = resolve_data_sources({"id_uf": "IBGE, 2024"}, layers)
        self.assertEqual(per_layer, {"id_uf": "IBGE, 2024", "id_div": "IBGE, 2024", "id_nomes": "IBGE, 2024"})
        self.assertEqual(credit, "IBGE, 2024 (Limite estadual)")
        self.assertEqual(notes, [])
        # sem fonte na origem: a derivada também não é cobrada
        _, per_layer, notes = resolve_data_sources({"id_div": "x"}, [("id_uf", "Limite estadual", ""), ("id_div", "Divisa", "", "id_uf")])
        self.assertEqual(per_layer, {"id_div": "x"})
        self.assertTrue(any("'Limite estadual'" in n and "Divisa" not in n for n in notes))

    def test_camada_sem_fonte_nenhuma_gera_nota(self):
        _, per_layer, notes = resolve_data_sources({"id_uc": "CEUC"}, self.LAYERS)
        self.assertNotIn("id_mun", per_layer)
        self.assertTrue(any("Sem fonte declarada" in n and "Municípios" in n for n in notes))

    def test_formato_invalido_e_recusado(self):
        with self.assertRaises(CompositionError):
            resolve_data_sources([{"layer": "x"}], self.LAYERS)
        with self.assertRaises(CompositionError):
            resolve_data_sources(3.5j, self.LAYERS)


class OrientacaoAutomatica(unittest.TestCase):
    def test_grafias_aceitas(self):
        for termo in ("auto", "AUTO", " automática ", "automatic"):
            self.assertTrue(_orientation_is_auto(termo), termo)
        for termo in ("portrait", "paisagem", None, 3):
            self.assertFalse(_orientation_is_auto(termo), termo)
        self.assertIn("auto", AUTO_ORIENTATION_TERMS)

    def test_orientation_continua_parametro_conhecido(self):
        self.assertIn("orientation", KNOWN_PARAMETERS)


class FiguraParaPeriodico(unittest.TestCase):
    def test_largura_por_coluna_ou_em_mm(self):
        self.assertEqual(_resolve_figure_width({"journal_column": "double"}), JOURNAL_COLUMNS["double"])
        self.assertEqual(_resolve_figure_width({"journal_column": "Simples"}), JOURNAL_COLUMNS["single"])
        self.assertEqual(_resolve_figure_width({"journal_column": "1.5"}), JOURNAL_COLUMNS["one_and_half"])
        self.assertEqual(_resolve_figure_width({"figure_width_mm": 90}), 90.0)
        self.assertEqual(_resolve_figure_width({"figure_width_mm": 90, "journal_column": "double"}), 90.0)
        self.assertIsNone(_resolve_figure_width({}))

    def test_coluna_desconhecida_e_recusada_com_a_lista(self):
        with self.assertRaises(CompositionError) as ctx:
            _resolve_figure_width({"journal_column": "tripla"})
        self.assertIn("double (175 mm)", str(ctx.exception))

    def test_formatos_raster_de_revista(self):
        for fmt in ("tif", "tiff", "jpg", "jpeg", "png", "pdf", "svg"):
            self.assertIn(fmt, SUPPORTED_FORMATS)
        for name in ("figure_width_mm", "figure_height_mm", "figure_max_height_mm", "journal_column", "panels"):
            self.assertIn(name, KNOWN_PARAMETERS)


class PaineisEmGrade(unittest.TestCase):
    def test_dois_paineis_continuam_lado_a_lado(self):
        plan = solve_layout(page="A3 landscape", panels=2)
        self.assertEqual(map_slot_keys(plan.slots), ["map", "map_2"])
        self.assertIn("map_2_caption", plan.slots)

    def test_tres_e_seis_paineis_em_grade(self):
        plan = solve_layout(page="A3 landscape", panels=3)
        self.assertEqual(map_slot_keys(plan.slots), ["map", "map_2", "map_3"])
        a, b, c = (plan.slots[k] for k in ("map", "map_2", "map_3"))
        self.assertAlmostEqual(a.width, b.width, places=3)
        # O corpo da A3 paisagem (com coluna lateral) é quase quadrado (1,3):
        # três painéis vão em 2x2 (células 1,33) e não em 3x1 (0,42).
        self.assertGreater(c.y, a.y)
        self.assertTrue(any("3 quadros" in n and "2x2" in n for n in plan.notes))
        plan6 = solve_layout(page="A3 landscape", panels=6)
        self.assertEqual(len(map_slot_keys(plan6.slots)), 6)
        self.assertEqual(len({round(plan6.slots[k].width, 3) for k in map_slot_keys(plan6.slots)}), 1)

    def test_grade_escolhida_pela_celula_mais_proxima_do_quadrado(self):
        from sigmai.cartography.layoutgrid import panel_grid

        # A4 paisagem, corpo ~270x150: três painéis em 3x1 (células 0,59), não 2x2 (1,85 + célula vazia)
        self.assertEqual(panel_grid(3, 270.0, 150.0, 6.0), (3, 1))
        # A4 retrato, corpo ~190x250: três painéis em 2x2 (células 0,76), não 1x3 (faixas de 2,4)
        self.assertEqual(panel_grid(3, 190.0, 250.0, 6.0), (2, 2))
        self.assertEqual(panel_grid(4, 270.0, 150.0, 6.0), (2, 2))
        self.assertEqual(panel_grid(6, 270.0, 150.0, 6.0), (3, 2))
        self.assertEqual(panel_grid(1, 100.0, 100.0, 6.0), (1, 1))
        # Em A4 retrato sem itens de apoio o corpo é alto: 2 colunas, um canto vazio.
        plan = solve_layout(page="A4 portrait", panels=3, include_legend=False, include_scale_bar=False,
                            include_scale_text=False, include_north_arrow=False)
        xs = {round(plan.slots[k].x, 3) for k in map_slot_keys(plan.slots)}
        self.assertEqual(len(xs), 2)


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class ContextoDerivadoNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _estados(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        project = QgsProject.instance()
        project.clear()
        layer = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string", "Estados", "memory")
        feats = []
        for nome, (x0, x1) in (("Piauí", (0, 1000)), ("Ceará", (1000, 2000))):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, 0, x1, 1000)))
            f.setAttribute("nome", nome)
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        project.addMapLayer(layer)
        return layer

    def test_dry_run_descreve_sem_criar(self):
        from sigmai.qgis_actions.context_annotations import add_context_annotations

        layer = self._estados()
        antes = len(layer.project().mapLayers()) if hasattr(layer, "project") else None
        plano = add_context_annotations({"boundary_layer_id": layer.id(), "label_field": "nome"}, {"dry_run": True})
        self.assertTrue(plano["dry_run"])
        self.assertEqual(plano["boundary_layer"], "Divisa — Estados")
        from qgis.core import QgsProject

        self.assertEqual(len(QgsProject.instance().mapLayers()), 1)

    def test_cria_divisa_e_nomes_por_feicao(self):
        from qgis.core import QgsProject

        from sigmai.qgis_actions.context_annotations import add_context_annotations

        layer = self._estados()
        resultado = add_context_annotations(
            {"boundary_layer_id": layer.id(), "label_field": "nome", "dissolve": False,
             "extra_labels": [{"text": "Oceano", "x": 1500, "y": 1200}, {"text": "Atlântico", "lon": -40.0, "lat": -3.0}]},
            {"dry_run": False},
        )
        kinds = {c["kind"]: c for c in resultado["created_layers"]}
        self.assertEqual(set(kinds), {"boundary_line", "label_only_points", "extra_labels"})
        self.assertEqual(kinds["boundary_line"]["features"], 2)
        from sigmai.qgis_actions.context_annotations import derived_from

        self.assertEqual(derived_from(QgsProject.instance().mapLayer(kinds["boundary_line"]["id"])), layer.id())
        self.assertEqual(kinds["label_only_points"]["features"], 2)
        # lon/lat em graus é aceito e reprojetado para o CRS da camada (UTM)
        avulsos = QgsProject.instance().mapLayer(kinds["extra_labels"]["id"])
        self.assertEqual(kinds["extra_labels"]["features"], 2)
        atlantico = [f for f in avulsos.getFeatures() if f["rotulo"] == "Atlântico"][0].geometry().asPoint()
        self.assertGreater(abs(atlantico.x()), 100000)  # metros, não graus
        pontos = QgsProject.instance().mapLayer(kinds["label_only_points"]["id"])
        self.assertEqual(pontos.renderer().type(), "nullSymbol")
        self.assertTrue(pontos.labelsEnabled())
        # o polo de inacessibilidade de um quadrado é o centro
        centros = sorted((round(f.geometry().asPoint().x()), f["rotulo"]) for f in pontos.getFeatures())
        self.assertEqual(centros, [(500, "Piauí"), (1500, "Ceará")])
        self.assertTrue(any("memória" in n for n in resultado["notes"]))

    def test_persiste_em_geopackage(self):
        from qgis.core import QgsProject

        from sigmai.qgis_actions.context_annotations import add_context_annotations

        layer = self._estados()
        with tempfile.TemporaryDirectory() as pasta:
            gpkg = os.path.join(pasta, "contexto.gpkg")
            resultado = add_context_annotations({"boundary_layer_id": layer.id(), "label_text": "Nordeste", "output_gpkg": gpkg}, {"dry_run": False})
            self.assertTrue(os.path.exists(gpkg))
            for created in resultado["created_layers"]:
                camada = QgsProject.instance().mapLayer(created["id"])
                self.assertEqual(camada.providerType(), "ogr")
                self.assertIn("contexto.gpkg", camada.source())
            self.assertFalse(any("memória" in n for n in resultado["notes"]))

    def test_recusas_nomeadas(self):
        from sigmai.qgis_actions.context_annotations import add_context_annotations
        from sigmai.validators import ValidationError

        layer = self._estados()
        with self.assertRaises(ValidationError) as ctx:
            add_context_annotations({"boundary_layer_id": layer.id(), "label_field": "sigla"}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "FIELD_NOT_FOUND")
        with self.assertRaises(ValidationError) as ctx:
            add_context_annotations({"boundary_layer_id": layer.id(), "label_field": "nome", "label_text": "X"}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "BAD_REQUEST")
        with self.assertRaises(ValidationError) as ctx:
            add_context_annotations({"boundary_layer_id": "nao_existe"}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "LAYER_NOT_FOUND")

    def test_compose_com_fonte_por_camada_e_sem_rotulos_na_legenda(self):
        from qgis.core import QgsProject

        from sigmai.cartography.compose import compose_map
        from sigmai.qgis_actions.context_annotations import add_context_annotations

        layer = self._estados()
        criado = add_context_annotations({"boundary_layer_id": layer.id(), "label_field": "nome", "dissolve": False}, {"dry_run": False})
        ids = [c["id"] for c in criado["created_layers"]]
        with tempfile.TemporaryDirectory() as pasta:
            saida = os.path.join(pasta, "m.png")
            r = compose_map({
                "layer_ids": [layer.id()] + ids, "title": "Estados", "map_author": "T",
                "data_source": {"Estados": "IBGE 2024"}, "output_path": saida, "format": "png", "dpi": 72,
                "orientation": "auto", "page": "A5",
            }, {"dry_run": False})
        legend = r["audit"]["observation"]["legend"]["layer_names"]
        self.assertIn("Estados", legend)
        self.assertNotIn("Nomes — Estados", legend)
        self.assertIn("Divisa — Estados", legend)
        fonte = next(i for i in r["audit"]["observation"]["items"] if i["role"] == "source")["text"]
        self.assertIn("IBGE 2024 (Estados)", fonte)
        self.assertTrue(any("Orientação escolhida automaticamente" in n for n in r["notes"]))
        cart020 = next(c for c in r["audit"]["results"] if c["id"] == "CART020")
        self.assertEqual(cart020["status"], "pass", cart020["detail_pt"])

    def test_figura_de_coluna_dupla_e_quatro_paineis(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        from sigmai.cartography.compose import compose_map

        layer = self._estados()
        ponto = QgsVectorLayer("Point?crs=EPSG:31984&field=n:string", "Sede", "memory")
        f = QgsFeature(ponto.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsGeometry.fromRect(QgsRectangle(400, 400, 600, 600)).centroid().asPoint()))
        f.setAttributes(["Sede"])
        ponto.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(ponto)
        with tempfile.TemporaryDirectory() as pasta:
            tif = os.path.join(pasta, "figura.tif")
            r = compose_map({"layer_ids": [layer.id()], "title": "Fig. 1", "map_author": "T", "data_source": "IBGE",
                             "journal_column": "double", "output_path": tif, "format": "tif", "dpi": 300}, {"dry_run": False})
            self.assertEqual(r["page"]["width_mm"], 175.0)
            self.assertEqual(r["template"], "publicacao")
            self.assertTrue(os.path.exists(tif) and os.path.getsize(tif) > 1000)
            self.assertNotIn("CART040", [c["id"] for c in r["audit"]["results"] if c["status"] == "fail"])
            self.assertEqual(next(c for c in r["audit"]["results"] if c["id"] == "CART071")["status"], "pass")
            self.assertTrue(any("Figura para periódico" in n for n in r["notes"]))

            png = os.path.join(pasta, "paineis.png")
            r = compose_map({"layer_ids": [layer.id()], "title": "Painéis", "map_author": "T", "data_source": "IBGE",
                             "panels": [{"layer_ids": [ponto.id()], "panel_title": "Sede"}, {"layer_ids": [layer.id()]},
                                        {"layer_ids": [ponto.id(), layer.id()]}],
                             "page": "A3 landscape", "output_path": png, "format": "png", "dpi": 72}, {"dry_run": False})
            criados = r["items_created"]
            self.assertIn("comparison_map", criados)
            self.assertIn("panel_map_3", criados)
            self.assertIn("panel_map_4", criados)
            captions = [i["text"] for i in r["audit"]["observation"]["items"] if i["id"].startswith("panel_caption")]
            self.assertTrue(any(c.startswith("(a)") for c in captions))
            self.assertTrue(any(c.startswith("(b) Sede") for c in captions))
            self.assertTrue(any(c.startswith("(d)") for c in captions))
            frames = r["audit"]["observation"]["map_frames"]
            self.assertEqual(len(frames), 4)
            # Igualados numa escala comum: os quatro quadros anunciam a mesma.
            self.assertEqual(len({round(float(f["scale"]), -1) for f in frames}), 1)

    def test_panels_e_second_map_juntos_sao_recusados(self):
        from sigmai.cartography.compose import compose_map

        layer = self._estados()
        with self.assertRaises(CompositionError):
            compose_map({"layer_ids": [layer.id()], "title": "x", "second_map": {"layer_ids": [layer.id()]},
                         "panels": [{"layer_ids": [layer.id()]}]}, {"dry_run": True})


if __name__ == "__main__":
    unittest.main()
