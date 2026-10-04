"""``spatial_relationship`` e ``set_layer_encoding``.

O primeiro responde o que descobrir "por sorte" nos atributos não deveria
exigir: quanto de A está dentro de B, o que toca, o que está mais perto e
a quantos metros. O segundo corrige o "Piau�" que apareceu nas respostas
do experimento — um shapefile ISO-8859-1 sem ``.cpg``.
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

from sigmai.qgis_actions.encoding import has_mojibake  # noqa: E402
from sigmai.permissions import COMMAND_PERMISSIONS  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


class Catalogo(unittest.TestCase):
    def test_acoes_catalogadas(self):
        self.assertEqual(COMMAND_PERMISSIONS["spatial_relationship"].permission_level, "read_only")
        self.assertEqual(COMMAND_PERMISSIONS["set_layer_encoding"].permission_level, "safe_write")
        self.assertEqual(COMMAND_PERMISSIONS["add_context_annotations"].permission_level, "safe_write")

    def test_mojibake(self):
        self.assertTrue(has_mojibake("Piau�"))
        self.assertFalse(has_mojibake("Piauí"))
        self.assertFalse(has_mojibake(None))


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class RelacoesNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _cenario(self):
        """Dois estados lado a lado (UTM) e uma UC que cai 25% em A e 75% em B."""
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        project = QgsProject.instance()
        project.clear()
        estados = QgsVectorLayer("Polygon?crs=EPSG:31984&field=CD_UF:string&field=NM_UF:string", "Estados", "memory")
        feats = []
        for cd, nome, (x0, x1) in (("22", "Piauí", (0, 10000)), ("23", "Ceará", (10000, 20000)), ("21", "Maranhão", (-30000, -20000))):
            f = QgsFeature(estados.fields())
            f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, 0, x1, 10000)))
            f.setAttributes([cd, nome])
            feats.append(f)
        estados.dataProvider().addFeatures(feats)
        estados.updateExtents()
        uc = QgsVectorLayer("Polygon?crs=EPSG:31984&field=Nome_UC:string", "UC", "memory")
        f = QgsFeature(uc.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(9000, 2000, 13000, 3000)))
        f.setAttributes(["Parque"])
        uc.dataProvider().addFeatures([f])
        uc.updateExtents()
        project.addMapLayers([estados, uc])
        return estados, uc

    def test_contencao_intersecao_e_vizinho(self):
        from sigmai.qgis_actions.spatial import spatial_relationship

        estados, uc = self._cenario()
        r = spatial_relationship({"layer_id": uc.id(), "other_layer_id": estados.id()}, {})
        feature = r["features"][0]
        self.assertEqual(feature["subject"]["name"], "Parque")
        self.assertEqual(feature["inside_fraction"], 1.0)
        nomes = {e["name"]: e["fraction_of_subject"] for e in feature["intersecting"]}
        self.assertAlmostEqual(nomes["Ceará"], 0.75, places=3)
        self.assertAlmostEqual(nomes["Piauí"], 0.25, places=3)
        # Maranhão não toca: é o vizinho mais próximo, a 29 km da borda oeste da UC (x=9000 → x=-20000)
        self.assertEqual(feature["nearest"][0]["name"], "Maranhão")
        # A distância é GEODÉSICA: 29 000 m de grade (x=9000 → x=-20000), medidos a ~500 km
        # do meridiano central da zona UTM (fator de escala ~1,003), valem ~28 920 m no terreno.
        self.assertAlmostEqual(feature["nearest"][0]["distance_m"], 28920.0, delta=40.0)
        self.assertEqual(r["display_field"], "NM_UF")
        self.assertIn("100% de 'Parque' está dentro de 'Estados'", feature["summary"])

    def test_raio_em_metros_limita_a_busca(self):
        from sigmai.qgis_actions.spatial import spatial_relationship

        estados, uc = self._cenario()
        r = spatial_relationship({"layer_id": uc.id(), "other_layer_id": estados.id(), "radius_m": 5000}, {})
        self.assertEqual(r["features"][0]["nearest"], [])

    def test_fora_de_tudo(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        from sigmai.qgis_actions.spatial import spatial_relationship

        estados, _ = self._cenario()
        ilha = QgsVectorLayer("Polygon?crs=EPSG:31984&field=n:string", "Ilha", "memory")
        f = QgsFeature(ilha.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(50000, 50000, 51000, 51000)))
        f.setAttributes(["Ilha"])
        ilha.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(ilha)
        r = spatial_relationship({"layer_id": ilha.id(), "other_layer_id": estados.id()}, {})
        feature = r["features"][0]
        self.assertEqual(feature["inside_fraction"], 0.0)
        self.assertEqual(feature["intersecting"], [])
        self.assertEqual(feature["nearest"][0]["name"], "Ceará")

    def test_recusas(self):
        from sigmai.qgis_actions.spatial import spatial_relationship
        from sigmai.validators import ValidationError

        estados, uc = self._cenario()
        with self.assertRaises(ValidationError) as ctx:
            spatial_relationship({"layer_id": uc.id(), "other_layer_id": "nada"}, {})
        self.assertEqual(ctx.exception.code, "LAYER_NOT_FOUND")
        with self.assertRaises(ValidationError) as ctx:
            spatial_relationship({"layer_id": uc.id(), "other_layer_id": estados.id(), "display_field": "SIGLA"}, {})
        self.assertEqual(ctx.exception.code, "FIELD_NOT_FOUND")
        with self.assertRaises(ValidationError) as ctx:
            spatial_relationship({"layer_id": uc.id(), "other_layer_id": estados.id(), "feature_id": 99}, {})
        self.assertEqual(ctx.exception.code, "FEATURE_NOT_FOUND")

    def test_codificacao_detectada_e_corrigida(self):
        import tempfile

        from qgis.core import QgsFeature, QgsProject, QgsVectorFileWriter, QgsVectorLayer, QgsGeometry, QgsPointXY

        from sigmai.qgis_actions.encoding import detect_encoding_problem, set_layer_encoding
        from sigmai.qgis_actions.get_layer_info import handle as layer_info

        project = QgsProject.instance()
        project.clear()
        memoria = QgsVectorLayer("Point?crs=EPSG:4674&field=NM_UF:string", "m", "memory")
        f = QgsFeature(memoria.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(-42, -7)))
        f.setAttributes(["Piauí"])
        memoria.dataProvider().addFeatures([f])
        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "uf.shp")
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "ESRI Shapefile"
            options.fileEncoding = "ISO-8859-1"
            QgsVectorFileWriter.writeAsVectorFormatV3(memoria, caminho, project.transformContext(), options)
            cpg = os.path.join(pasta, "uf.cpg")
            if os.path.exists(cpg):
                os.remove(cpg)  # sem .cpg o QGIS lê como UTF-8 e o acento quebra
            layer = QgsVectorLayer(caminho, "UF", "ogr")
            layer.setProviderEncoding("UTF-8")
            project.addMapLayer(layer)
            problema = detect_encoding_problem(layer)
            self.assertIsNotNone(problema)
            self.assertTrue(has_mojibake(problema["examples"][0]))
            self.assertIsNotNone(layer_info({"layer_id": layer.id()}, {})["encoding_problem"])
            resultado = set_layer_encoding({"layer_id": layer.id(), "encoding": "ISO-8859-1"}, {})
            self.assertIsNone(resultado["problem_after"])
            self.assertIn("Piauí", resultado["sample_texts"])


if __name__ == "__main__":
    unittest.main()
