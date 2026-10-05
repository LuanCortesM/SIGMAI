"""Figura em tons de cinza: colour_mode='greyscale' e a regra CART073.

Periódicos imprimem em cinza e cobram a cor impressa (a *Transactions in GIS*
pede gráficos de linha em preto e branco). Um mapa colorido convertido depois
perde a distinção entre cores de mesma luminosidade; composto em cinza, não —
e a auditoria confere, no raster exportado, que a figura saiu sem cor.
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

from sigmai.cartography import rulebook  # noqa: E402
from sigmai.cartography.inspector import chromatic_fraction  # noqa: E402
from sigmai.cartography.params import ParameterError  # noqa: E402
from sigmai.cartography.symbology import (  # noqa: E402
    COLOUR_MODES, GREY_POLYGON_FILLS, _tint, normalize_colour_mode,
)
from sigmai.cartography.vision import confusable_pairs  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def _argb(red: int, green: int, blue: int, alpha: int = 255) -> int:
    return (alpha << 24) | (red << 16) | (green << 8) | blue


class ModoDeCor(unittest.TestCase):
    def test_valores_e_sinonimos(self):
        self.assertEqual(COLOUR_MODES, ("colour", "greyscale"))
        for valor in (None, "", "colour", "color", "Cor"):
            self.assertEqual(normalize_colour_mode(valor), "colour", valor)
        for valor in ("greyscale", "Grayscale", "grey", "cinza", "black-and-white", "preto e branco"):
            self.assertEqual(normalize_colour_mode(valor), "greyscale", valor)

    def test_valor_desconhecido_e_recusado_com_a_lista(self):
        with self.assertRaises(ParameterError) as ctx:
            normalize_colour_mode("sepia")
        self.assertIn("colour, greyscale", str(ctx.exception))

    def test_os_quatro_cinzas_solidos_nao_se_confundem(self):
        solidos = [cinza for cinza, padrao in GREY_POLYGON_FILLS if padrao == "solid"]
        self.assertEqual(len(solidos), 4)
        self.assertEqual(confusable_pairs([(f"c{i}", cinza) for i, cinza in enumerate(solidos)]), [])
        for cinza in solidos:  # sem matiz: os três canais iguais
            self.assertEqual(len({cinza[1:3], cinza[3:5], cinza[5:7]}), 1, cinza)

    def test_o_azul_quase_branco_da_paleta_colorida_conta_como_cor(self):
        """O contexto colorido (#0072B2 clareado 85 %) é o caso que a regra tem de pegar."""
        azul = _tint("#0072B2", 0.85)
        canais = [int(azul[i:i + 2], 16) for i in (1, 3, 5)]
        self.assertGreaterEqual(max(canais) - min(canais), rulebook.GREYSCALE_CHROMA_MIN)


class FracaoCromatica(unittest.TestCase):
    def test_cinzas_e_branco_nao_tem_cor(self):
        pixels = [_argb(255, 255, 255)] * 50 + [_argb(v, v, v) for v in range(0, 240, 10)]
        self.assertEqual(chromatic_fraction(pixels, rulebook.GREYSCALE_CHROMA_MIN), 0.0)

    def test_transparente_e_branco_nao_sao_tinta(self):
        self.assertIsNone(chromatic_fraction([_argb(255, 0, 0, 0), _argb(255, 255, 255)], 20))

    def test_conta_so_sobre_a_tinta(self):
        pixels = [_argb(255, 255, 255)] * 100 + [_argb(0, 0, 0)] * 3 + [_argb(192, 57, 43)]
        self.assertAlmostEqual(chromatic_fraction(pixels, 20), 0.25)

    def test_ruido_de_compressao_abaixo_do_limiar_nao_conta(self):
        self.assertEqual(chromatic_fraction([_argb(120, 128, 125), _argb(60, 52, 58)], 20), 0.0)


class RegraCART073(unittest.TestCase):
    def _regra(self):
        return next(rule for rule in rulebook.RULES if rule.id == "CART073")

    def test_so_se_aplica_a_figura_pedida_em_cinza(self):
        self.assertEqual(self._regra().check({"output": {"chromatic_fraction": 0.4}}).status, rulebook.STATUS_SKIP)
        self.assertEqual(self._regra().check({"colour_mode": "colour", "output": {"chromatic_fraction": 0.4}}).status,
                         rulebook.STATUS_SKIP)

    def test_sem_raster_nao_ha_o_que_medir(self):
        self.assertEqual(self._regra().check({"colour_mode": "greyscale", "output": {}}).status, rulebook.STATUS_SKIP)

    def test_passa_e_reprova_no_limiar(self):
        limite = rulebook.GREYSCALE_MAX_CHROMATIC_FRACTION
        passa = self._regra().check({"colour_mode": "greyscale", "output": {"chromatic_fraction": limite}})
        reprova = self._regra().check({"colour_mode": "greyscale", "output": {"chromatic_fraction": limite * 4}})
        self.assertEqual(passa.status, rulebook.STATUS_PASSED)
        self.assertEqual(reprova.status, rulebook.STATUS_FAIL)
        self.assertIn("colour_mode='greyscale'", reprova.detail_pt)

    def test_e_erro_porque_viola_um_pedido_explicito(self):
        self.assertEqual(self._regra().severity, rulebook.SEVERITY_ERROR)


@unittest.skipUnless(HAS_QGIS, "PyQGIS indisponível")
class FiguraEmCinzaNoQgis(unittest.TestCase):
    """Composição de verdade: paleta, inserto e grade em cinza, e o laudo confere."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _poligono(self, nome, x0, y0, lado):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        layer = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string", nome, "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, y0, x0 + lado, y0 + lado)))
        feature.setAttribute("nome", nome)
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _compor(self, pasta, **extra):
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        from sigmai.cartography.compose import compose_map

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        estado = self._poligono("Estado", 300000, 8800000, 400000)
        parque = self._poligono("Parque", 480000, 9000000, 20000)
        params = {
            "layer_ids": [estado.id(), parque.id()], "subject_layer_id": parque.id(), "title": "Parque",
            "map_author": "T", "data_source": "teste", "include_inset": True, "inset_layer_ids": [estado.id()],
            "include_grid": True, "output_path": os.path.join(pasta, "m.png"), "format": "png", "dpi": 96,
        }
        params.update(extra)
        return parque, compose_map(params, {"dry_run": False})

    def _cart073(self, resultado):
        regras = resultado["audit"]["rules"] if "rules" in resultado["audit"] else resultado["audit"]["results"]
        return next(entry for entry in regras if entry["id"] == "CART073")

    def test_figura_em_cinza_sai_sem_cor_e_o_laudo_confirma(self):
        with pasta_temporaria() as pasta:
            parque, resultado = self._compor(pasta, colour_mode="greyscale")
            self.assertEqual(parque.renderer().symbol().color().name().upper(), GREY_POLYGON_FILLS[0][0])
            regra = self._cart073(resultado)
            self.assertEqual(regra["status"], rulebook.STATUS_PASSED, regra)
            fracao = resultado["audit"]["observation"]["output"]["chromatic_fraction"]
            self.assertLessEqual(fracao, rulebook.GREYSCALE_MAX_CHROMATIC_FRACTION)

    def test_figura_colorida_nao_e_cobrada(self):
        with pasta_temporaria() as pasta:
            _, resultado = self._compor(pasta)
            self.assertEqual(self._cart073(resultado)["status"], rulebook.STATUS_SKIP)
            self.assertGreater(resultado["audit"]["observation"]["output"]["chromatic_fraction"],
                               rulebook.GREYSCALE_MAX_CHROMATIC_FRACTION)


if __name__ == "__main__":
    unittest.main()
