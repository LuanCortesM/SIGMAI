"""Título e créditos no mapa, na legenda do texto ou fora do mapa (title_placement).

As revistas pedem título e legenda da figura no texto, e não no arquivo da
imagem (Evolution, que a Biodiversity Informatics adota). O SIGMAI escrevia
sempre título e rodapé na imagem, e a auditoria reprovava quem não os tinha.
Com ``title_placement="caption"`` os dois saem da imagem e voltam como texto
pronto para a legenda; a auditoria passa a conferir a fonte nessa legenda.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography import rulebook  # noqa: E402
from sigmai.cartography.compose import (  # noqa: E402
    CompositionError, _caption_text, _resolve_title_placement,
)
from sigmai.cartography.layoutgrid import solve_layout  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def _regra(rule_id):
    return next(rule for rule in rulebook.RULES if rule.id == rule_id)


class PaginaSemTituloNemRodape(unittest.TestCase):
    def test_sem_as_faixas_o_mapa_fica_com_a_altura(self):
        com = solve_layout(page="A4 landscape")
        sem = solve_layout(page="A4 landscape", include_title=False, include_footer=False)
        self.assertNotIn("title", sem.slots)
        self.assertNotIn("subtitle", sem.slots)
        self.assertNotIn("footer", sem.slots)
        self.assertGreater(sem.map_frame().height, com.map_frame().height + 10)

    def test_sem_titulo_o_rodape_continua(self):
        plano = solve_layout(page="A4 landscape", include_title=False, include_subtitle=True)
        self.assertNotIn("title", plano.slots)
        self.assertNotIn("subtitle", plano.slots)
        self.assertIn("footer", plano.slots)


class OpcaoELegenda(unittest.TestCase):
    def test_valores_e_apelidos(self):
        self.assertEqual(_resolve_title_placement({}), "map")
        self.assertEqual(_resolve_title_placement({"title_placement": "Caption"}), "caption")
        self.assertEqual(_resolve_title_placement({"title_placement": "legenda"}), "caption")
        self.assertEqual(_resolve_title_placement({"title_placement": "sem_titulo"}), "none")
        with self.assertRaises(CompositionError):
            _resolve_title_placement({"title_placement": "rodape"})

    def test_legenda_do_texto(self):
        texto = _caption_text({}, "GBIF occurrence records per site", "", "SIRGAS 2000 / UTM zone 23S (EPSG:31983)",
                              "en", source_text="GBIF.org (2026) https://doi.org/10.15468/dl.kee8xx")
        self.assertEqual(texto, "GBIF occurrence records per site. Source: GBIF.org (2026) "
                                "https://doi.org/10.15468/dl.kee8xx. SIRGAS 2000 / UTM zone 23S (EPSG:31983). "
                                "Produced with SIGMAI/QGIS.")

    def test_autoria_entra_quando_pedida(self):
        texto = _caption_text({"map_author": "A. Autor"}, "Mapa", "", "", "pt-BR", source_text="IBGE (2024)")
        self.assertIn("Elaboração: A. Autor.", texto)


class RegrasComALegenda(unittest.TestCase):
    @staticmethod
    def _obs(caption=None, rodape=""):
        itens = [{"type": "label", "role": "source", "id": "source", "text": rodape}] if rodape else []
        return {"items": itens, "caption": caption}

    def test_titulo_na_legenda_passa(self):
        resultado = _regra("CART001").check(self._obs({"title_placement": "caption", "title": "Mapa B"}))
        self.assertEqual(resultado.status, rulebook.STATUS_PASSED)
        self.assertIn("legenda do texto", resultado.detail_pt)

    def test_sem_titulo_por_escolha_nao_reprova(self):
        for placement in ("caption", "none"):
            with self.subTest(placement=placement):
                resultado = _regra("CART001").check(self._obs({"title_placement": placement}))
                self.assertEqual(resultado.status, rulebook.STATUS_SKIP)

    def test_sem_titulo_e_sem_escolha_continua_reprovando(self):
        self.assertEqual(_regra("CART001").check(self._obs()).status, rulebook.STATUS_FAIL)

    def test_fonte_na_legenda_dispensa_a_autoria(self):
        legenda = {"title_placement": "caption", "text": "Mapa. Source: GBIF.org (2026). Produced with SIGMAI/QGIS."}
        self.assertEqual(_regra("CART007").check(self._obs(legenda)).status, rulebook.STATUS_PASSED)

    def test_legenda_sem_fonte_reprova(self):
        legenda = {"title_placement": "caption", "text": "Mapa. SIRGAS 2000. Produced with SIGMAI/QGIS."}
        self.assertEqual(_regra("CART007").check(self._obs(legenda)).status, rulebook.STATUS_FAIL)

    def test_sistema_de_referencia_lido_na_legenda(self):
        obs = self._obs({"title_placement": "caption", "text": "Mapa. SIRGAS 2000 / UTM zone 23S (EPSG:31983)."})
        obs["map"] = {"crs": "EPSG:31983"}
        self.assertEqual(_regra("CART008").check(obs).status, rulebook.STATUS_PASSED)


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
        from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))
        self.parque = QgsVectorLayer("Polygon?crs=EPSG:31983", "Park", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((520000 7515000,545000 7515000,545000 7535000,520000 7535000,"
                                          "520000 7515000))"))
        self.parque.dataProvider().addFeatures([f])
        self.parque.updateExtents()
        self.pontos = QgsVectorLayer("Point?crs=EPSG:31983", "Records", "memory")
        sorteio = random.Random(3)
        feats = []
        for _ in range(40):
            g = QgsFeature()
            g.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(sorteio.uniform(521000, 544000), sorteio.uniform(7516000, 7534000))))
            feats.append(g)
        self.pontos.dataProvider().addFeatures(feats)
        self.pontos.updateExtents()
        QgsProject.instance().addMapLayers([self.parque, self.pontos])

    def _compor(self, pasta, **extra):
        from sigmai.cartography.compose import compose_map

        params = {"layer_ids": [self.pontos.id(), self.parque.id()], "subject_layer_id": self.parque.id(),
                  "title": "Records in the park", "map_language": "en", "figure_width_mm": 180,
                  "data_source": {self.pontos.id(): "GBIF.org (2026) https://doi.org/10.15468/dl.kee8xx",
                                  self.parque.id(): "CNUC/MMA (2025)"},
                  "output_path": os.path.join(pasta, "f.png"), "format": "png", "dpi": 72, "confirm_overwrite": True}
        params.update(extra)
        return compose_map(params, {"dry_run": False})

    @staticmethod
    def _status(resultado, rule_id):
        return next(r for r in resultado["audit"]["results"] if r["id"] == rule_id)["status"]

    def test_figura_de_revista_sem_titulo_nem_rodape_na_imagem(self):
        from qgis.core import QgsLayoutItemLabel, QgsLayoutItemLegend, QgsProject

        from sigmai.cartography.compose import CAPTION_PROPERTY, audit_layout

        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, title_placement="caption")
            layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
            textos = [i.text() for i in layout.items() if isinstance(i, QgsLayoutItemLabel)]
            legenda = next(i for i in layout.items() if isinstance(i, QgsLayoutItemLegend))
            rotulos = [n.name() for n in legenda.model().rootGroup().findLayers()]
            guardada = json.loads(layout.customProperty(CAPTION_PROPERTY))
            de_novo = audit_layout(layout)
        self.assertNotIn("title", resultado["items_created"])
        self.assertNotIn("source", resultado["items_created"])
        self.assertFalse(any("Source" in t or "Records in the park" in t for t in textos), textos)
        self.assertFalse(any("GBIF.org" in r for r in rotulos), rotulos)
        self.assertTrue(resultado["caption"].startswith("Records in the park. Source: "))
        self.assertIn("https://doi.org/10.15468/dl.kee8xx", resultado["caption"])
        self.assertEqual(guardada["title_placement"], "caption")
        self.assertEqual(resultado["audit"]["grade"], "A", resultado["audit"].get("failing"))
        for regra in ("CART001", "CART007", "CART008"):
            self.assertEqual(self._status(resultado, regra), rulebook.STATUS_PASSED, regra)
            self.assertEqual(next(r for r in de_novo["results"] if r["id"] == regra)["status"], rulebook.STATUS_PASSED)

    def test_sem_titulo_com_creditos_no_mapa(self):
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, title_placement="none")
        self.assertNotIn("title", resultado["items_created"])
        self.assertIn("source", resultado["items_created"])
        self.assertNotIn("caption", resultado)
        self.assertEqual(self._status(resultado, "CART001"), rulebook.STATUS_SKIP)

    def test_padrao_continua_no_mapa_e_sugere_a_legenda_na_figura(self):
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, map_author="A. Autor")
        self.assertIn("title", resultado["items_created"])
        self.assertIn("source", resultado["items_created"])
        self.assertTrue(any("title_placement='caption'" in nota for nota in resultado["notes"]))


if __name__ == "__main__":
    unittest.main()
