"""Receita reproduzível, recomposição e parágrafo de Métodos.

Um script de 353 linhas reproduz um mapa só para quem o escreveu; a
receita do SIGMAI reproduz para qualquer um — e diz, na seção de Métodos,
o que foi feito, com quê e em que versão.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography.recipe import (  # noqa: E402
    RECIPE_SCHEMA, build_recipe, data_changes, file_fingerprint, local_file_of_source, methods_paragraph,
    recipe_from_json, recipe_to_json,
)
from sigmai.permissions import COMMAND_PERMISSIONS  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


def _receita_exemplo(**extra):
    params = {"layer_ids": ["m", "u"], "title": "Parque", "map_author": "Maria Silva",
              "data_source": {"m": "IBGE 2024", "u": "CEUC/SEMA-CE"}, "output_path": "/x/mapa.png", "format": "png", "dpi": 300}
    result = {"layout_name": "Parque", "template": "cientifico", "page": {"name": "A4", "orientation": "landscape"},
              "map_crs": "EPSG:31984", "map_crs_description": "SIRGAS 2000 / UTM zona 24S", "scale_denominator": 150000,
              "extent": {}, "output_path": "/x/mapa.png", "format": "png", "export": {"dpi": 300},
              "audit": {"grade": "A", "score": 100.0, "results": [{"id": "CART001", "status": "pass"}] * 33}}
    layers = [{"id": "m", "name": "Municípios", "source_text": "IBGE 2024"}, {"id": "u", "name": "PE das Carnaúbas", "source_text": "CEUC/SEMA-CE"}]
    recipe = build_recipe(params, layers, result, sigmai_version="1.1.0", qgis_version="3.34.4-Prizren")
    recipe.update(extra)
    return recipe


class ReceitaPura(unittest.TestCase):
    def test_build_e_roundtrip_json(self):
        recipe = _receita_exemplo()
        self.assertEqual(recipe["schema"], RECIPE_SCHEMA)
        self.assertEqual(recipe["audit"], {"grade": "A", "score": 100.0, "rule_count": 33, "failed": []})
        self.assertEqual(recipe_from_json(recipe_to_json(recipe))["scale_denominator"], 150000)
        with self.assertRaises(ValueError):
            recipe_from_json(json.dumps({"schema": "outra-coisa"}))

    def test_fingerprint_e_mudancas(self):
        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "dados.geojson")
            Path(caminho).write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            fp = file_fingerprint(caminho)
            self.assertTrue(fp["exists"])
            self.assertEqual(len(fp["sha256"]), 64)
            recipe = _receita_exemplo(layers=[{"id": "m", "name": "Municípios", "file": fp}])
            self.assertEqual(data_changes(recipe), [])
            Path(caminho).write_text('{"type":"FeatureCollection","features":[{}]}', encoding="utf-8")
            self.assertEqual(len(data_changes(recipe)), 1)
            self.assertIn("SHA-256", data_changes(recipe)[0])
            os.remove(caminho)
            self.assertIn("não existe mais", data_changes(recipe)[0])
        self.assertFalse(file_fingerprint("/nao/existe.shp")["exists"])

    def test_fonte_local_de_uma_string_de_origem(self):
        with pasta_temporaria() as pasta:
            shp = os.path.join(pasta, "a.gpkg")
            Path(shp).write_bytes(b"x")
            self.assertEqual(local_file_of_source(f"{shp}|layername=divisa"), shp)
            self.assertIsNone(local_file_of_source("dbname='x' host=localhost user=u password=p table=t"))
            self.assertIsNone(local_file_of_source("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"))
            self.assertIsNone(local_file_of_source("/nao/existe.shp"))

    def test_paragrafo_de_metodos_em_tres_linguas(self):
        recipe = _receita_exemplo()
        pt = methods_paragraph(recipe, "pt-BR")
        self.assertIn("QGIS 3.34.4", pt["paragraph"])
        self.assertIn("SIGMAI 1.1.0", pt["paragraph"])
        self.assertIn("IBGE 2024 (Municípios)", pt["paragraph"])
        self.assertIn("1:150.000", pt["paragraph"])
        self.assertIn("nota A (100.0/100)", pt["paragraph"])
        self.assertIn("Elaboração: Maria Silva", pt["paragraph"])
        self.assertIn("MACIEL, L. S. C.", pt["software_reference"])
        self.assertEqual(pt["note"], "")
        en = methods_paragraph(recipe, "en")
        self.assertIn("1:150,000", en["paragraph"])
        self.assertIn("graded A", en["paragraph"])
        es = methods_paragraph(recipe, "es")
        self.assertIn("nota A", es["paragraph"])
        ja = methods_paragraph(recipe, "ja")
        self.assertEqual(ja["language"], "en")
        self.assertIn("'ja'", ja["note"])
        self.assertIn("em página A4 paisagem", pt["paragraph"])
        self.assertIn("on an A4 landscape page", en["paragraph"])

    def test_paragrafo_descreve_figura_de_revista_e_camadas_derivadas(self):
        """A emulação da 1.1.0 devolveu 'on a figura landscape page' e listou as
        camadas de anotação (divisa, nomes) como se fossem dados."""
        recipe = _receita_exemplo(
            page={"name": "figura", "orientation": "landscape", "width_mm": 175.0, "height_mm": 127.5},
            layers=[{"id": "u", "name": "PE das Carnaúbas", "source_text": "CEUC/SEMA-CE"},
                    {"id": "d", "name": "Divisa — Piauí", "derived_from": "uf"}],
        )
        recipe["params"]["journal_column"] = "double"
        en = methods_paragraph(recipe, "en")["paragraph"]
        self.assertIn("as a journal figure at its final printed width (175 × 127.5 mm, double column)", en)
        self.assertNotIn("figura landscape", en)
        self.assertIn("Layers used: PE das Carnaúbas;", en)
        self.assertIn("annotation layers derived from them in QGIS (boundaries and names): Divisa — Piauí", en)
        pt = methods_paragraph(recipe, "pt-BR")["paragraph"]
        self.assertIn("como figura para periódico na largura final impressa (175 × 127.5 mm, coluna dupla)", pt)
        self.assertIn("camadas de anotação derivadas delas no QGIS (divisas e nomes): Divisa — Piauí", pt)

    def test_acoes_catalogadas(self):
        self.assertEqual(COMMAND_PERMISSIONS["get_map_recipe"].permission_level, "safe_write")
        self.assertEqual(COMMAND_PERMISSIONS["recompose_from_recipe"].permission_level, "safe_write")
        self.assertEqual(COMMAND_PERMISSIONS["describe_map_for_methods"].permission_level, "read_only")


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class ReceitaNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _camada(self, pasta):
        from qgis.core import (
            QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorFileWriter,
            QgsVectorLayer,
        )

        project = QgsProject.instance()
        project.clear()
        # O CRS do projeto é fixado de propósito: um teste anterior pode deixar
        # o projeto sem CRS e a composição precisa de um (do projeto ou da camada).
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        memoria = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string", "Quadrado", "memory")
        f = QgsFeature(memoria.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1000, 1000)))
        f.setAttributes(["Q"])
        memoria.dataProvider().addFeatures([f])
        caminho = os.path.join(pasta, "quadrado.gpkg")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        erro, _mensagem, *_resto = QgsVectorFileWriter.writeAsVectorFormatV3(memoria, caminho, project.transformContext(), options)
        self.assertEqual(int(erro), 0, _mensagem)
        layer = QgsVectorLayer(caminho, "Quadrado", "ogr")
        self.assertTrue(layer.isValid())
        if not layer.crs().isValid():
            # Na suíte inteira (nunca isolado), ~1 corrida em 10 devolve o GPKG
            # recém-gravado com CRS inválido: nesse estado do processo,
            # QgsCoordinateReferenceSystem.fromWkt recusa QUALQUER WKT (até o
            # de EPSG:4326) enquanto EPSG, fromProj e o OSR continuam a
            # funcionar. Não é o arquivo: o OSR lê o CRS gravado e confirma o
            # EPSG:31984. Só então o CRS é atribuído pela autoridade — se o
            # arquivo estiver errado de verdade, a asserção abaixo reprova.
            from osgeo import ogr

            dataset = ogr.Open(caminho)  # a referência ao dataset tem de viver enquanto a camada é lida
            self.assertIsNotNone(dataset, "GPKG não abre pelo OGR")
            gravado = dataset.GetLayer(0).GetSpatialRef()
            self.assertIsNotNone(gravado, "GPKG gravado sem CRS")
            self.assertEqual(gravado.GetAuthorityCode(None), "31984", gravado.ExportToWkt()[:120])
            layer.setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        self.assertTrue(layer.crs().isValid())
        project.addMapLayer(layer)
        return layer

    def test_compor_guardar_descrever_e_recompor(self):
        from qgis.PyQt.QtGui import QImage

        from sigmai.cartography.recipe import RECIPE_PNG_KEY, RECIPE_PROPERTY
        from sigmai.qgis_actions.cartography_engine import (
            compose_map, describe_map_for_methods, get_map_recipe, recompose_from_recipe,
        )
        from sigmai.validators import ValidationError

        with pasta_temporaria() as pasta:
            layer = self._camada(pasta)
            saida = os.path.join(pasta, "mapa.png")
            r = compose_map({"layer_ids": [layer.id()], "title": "Quadrado", "map_author": "T", "data_source": "teste",
                             "output_path": saida, "format": "png", "dpi": 72, "layout_name": "Q",
                             "recipe_path": os.path.join(pasta, "mapa.json")}, {"dry_run": False})
            self.assertTrue(r["recipe"]["stored_in_layout"])
            self.assertTrue(r["recipe"]["embedded_in_output"])
            self.assertTrue(os.path.exists(os.path.join(pasta, "mapa.json")))
            self.assertIn(RECIPE_PNG_KEY, QImage(saida).textKeys())
            from qgis.core import QgsProject

            layout = QgsProject.instance().layoutManager().layoutByName("Q")
            self.assertTrue(layout.customProperty(RECIPE_PROPERTY, ""))

            g = get_map_recipe({"layout_name": "Q"}, {})
            self.assertEqual(g["recipe"]["layers"][0]["name"], "Quadrado")
            self.assertEqual(len(g["recipe"]["layers"][0]["file"]["sha256"]), 64)
            self.assertEqual(g["data_changes"], [])
            self.assertEqual(get_map_recipe({"recipe_path": saida}, {})["recipe"]["layout_name"], "Q")

            m = describe_map_for_methods({"layout_name": "Q", "language": "pt-BR"}, {})
            self.assertIn("UTM zona 24S", m["paragraph"])
            self.assertIn("SIGMAI", m["paragraph"])

            rr = recompose_from_recipe({"layout_name": "Q", "overrides": {"output_path": os.path.join(pasta, "mapa2.png")}}, {"dry_run": False})
            self.assertTrue(os.path.exists(os.path.join(pasta, "mapa2.png")))
            self.assertEqual(rr["recomposed_from"], "layout:Q")
            self.assertTrue(any("substituído" in n for n in rr["notes"]))

            # Camada recarregada com outro id: a receita a encontra pelo nome.
            QgsProject.instance().removeMapLayer(layer.id())
            from qgis.core import QgsVectorLayer

            novo = QgsVectorLayer(os.path.join(pasta, "quadrado.gpkg"), "Quadrado", "ogr")
            QgsProject.instance().addMapLayer(novo)
            rr = recompose_from_recipe({"recipe_path": os.path.join(pasta, "mapa.json"),
                                        "overrides": {"output_path": os.path.join(pasta, "mapa3.png")}}, {"dry_run": False})
            self.assertTrue(any("localizadas pelo nome" in n for n in rr["notes"]))

            # Sem a camada, recusa nomeada.
            QgsProject.instance().removeMapLayer(novo.id())
            with self.assertRaises(ValidationError) as ctx:
                recompose_from_recipe({"recipe_path": os.path.join(pasta, "mapa.json")}, {"dry_run": True})
            self.assertEqual(ctx.exception.code, "LAYER_NOT_FOUND")

    def test_receita_de_mapa_com_raster(self):
        """Raster não tem featureCount: a receita descreve a camada mesmo assim (regressão da bateria 1.1.0)."""
        from osgeo import gdal, osr
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer

        from sigmai.qgis_actions.cartography_engine import compose_map, get_map_recipe

        project = QgsProject.instance()
        project.clear()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "r.tif")
            ds = gdal.GetDriverByName("GTiff").Create(caminho, 20, 20, 1, gdal.GDT_Byte)
            ds.SetGeoTransform((0, 50, 0, 1000, 0, -50))
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(31984)
            ds.SetProjection(srs.ExportToWkt())
            ds.GetRasterBand(1).WriteArray(__import__("numpy").arange(400, dtype="uint8").reshape(20, 20))
            ds = None
            raster = QgsRasterLayer(caminho, "Relevo")
            self.assertTrue(raster.isValid())
            project.addMapLayer(raster)
            r = compose_map({"layer_ids": [raster.id()], "title": "Relevo", "map_author": "T", "data_source": "teste",
                             "output_path": os.path.join(pasta, "r.png"), "format": "png", "dpi": 72, "layout_name": "R"},
                            {"dry_run": False})
            self.assertTrue(r["recipe"]["stored_in_layout"])
            g = get_map_recipe({"layout_name": "R"}, {})
            self.assertEqual(g["recipe"]["layers"][0]["name"], "Relevo")
            self.assertIsNone(g["recipe"]["layers"][0].get("feature_count"))
            self.assertEqual(len(g["recipe"]["layers"][0]["file"]["sha256"]), 64)

    def test_auditoria_de_figura_usa_margens_e_largura_da_receita(self):
        """Na emulação da 1.1.0 a figura de revista (margens de 5 mm por desenho) era
        auditada com os 10 mm padrão e reprovava em CART041 pelo que a própria
        composição decidiu; e CART071 não rodava porque a largura impressa se perdia."""
        from sigmai.qgis_actions.cartography_engine import audit_map_layout, compose_map

        with pasta_temporaria() as pasta:
            layer = self._camada(pasta)
            r = compose_map({"layer_ids": [layer.id()], "title": "Figura", "map_author": "T", "data_source": "teste",
                             "journal_column": "double", "output_path": os.path.join(pasta, "f.png"), "format": "png",
                             "dpi": 72, "layout_name": "F"}, {"dry_run": False})
            self.assertEqual(r["print_width_mm"], 175.0)
            self.assertNotIn("CART041", [c["id"] for c in r["audit"]["results"] if c["status"] == "fail"])
            laudo = audit_map_layout({"layout_name": "F"}, {})
            falhas = [c["id"] for c in laudo["results"] if c["status"] == "fail"]
            self.assertNotIn("CART041", falhas, laudo.get("next_actions"))
            self.assertEqual(laudo["observation"].get("print_width_mm"), 175.0)
            self.assertTrue(any("receita" in n for n in laudo.get("notes", [])))
            self.assertEqual(laudo["grade"], r["audit"]["grade"])

    def test_layout_sem_receita_e_recusado(self):
        from qgis.core import QgsPrintLayout, QgsProject

        from sigmai.qgis_actions.cartography_engine import get_map_recipe
        from sigmai.validators import ValidationError

        project = QgsProject.instance()
        project.clear()
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("manual")
        project.layoutManager().addLayout(layout)
        with self.assertRaises(ValidationError) as ctx:
            get_map_recipe({"layout_name": "manual"}, {})
        self.assertEqual(ctx.exception.code, "RECIPE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
