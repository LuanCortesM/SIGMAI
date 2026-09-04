"""O regulamento cartográfico precisa reprovar o que era aprovado antes."""

import unittest

from sigmai.cartography.rulebook import (
    RULES,
    RULES_BY_ID,
    SEVERITY_ERROR,
    evaluate,
    rulebook_manifest,
)


def observation_v011() -> dict:
    """A saída real do generate_professional_map 0.1.1, descrita como dados.

    Este era o mapa que o avaliador antigo classificava como
    "A - Professional map" com zero avisos: rosa dos ventos escrita como a
    letra N, barra de escala ocupando 4% do quadro, legenda explicando uma de
    três camadas visíveis e grade habilitada com intervalo zero.
    """
    return {
        "page": {"width_mm": 297, "height_mm": 210,
                 "content_area_mm": {"x": 10, "y": 10, "width": 277, "height": 190}},
        "items": [
            {"id": "main_map", "role": "map", "type": "map", "x": 10, "y": 28, "width": 184, "height": 142},
            {"id": "title", "role": "title", "type": "label", "x": 10, "y": 7, "width": 264, "height": 10,
             "font_size_pt": 17, "text": "Unidades de Conservação"},
            {"id": "subtitle", "role": "subtitle", "type": "label", "x": 10, "y": 18, "width": 264, "height": 7,
             "font_size_pt": 9, "text": "Registros"},
            {"id": "source", "role": "source", "type": "label", "x": 10, "y": 190, "width": 230, "height": 7,
             "font_size_pt": 7, "text": "Fonte: dados de teste"},
            {"id": "north_arrow", "role": "north", "type": "label", "x": 182, "y": 32, "width": 10, "height": 18,
             "font_size_pt": 16, "text": "N ^"},
        ],
        "map": {
            "item_id": "main_map", "crs": "EPSG:31983", "crs_is_geographic": False, "scale": 257090,
            "visible_layer_names": ["Unidades de Conservacao", "Drenagem", "Ocorrencias"],
            "grid": {"enabled": True, "interval_x": 0.0, "interval_y": 0.0, "annotations": True},
            "rendered_ink_fraction": 0.31,
            "extent": {"xmin": 324115, "ymin": 7473874, "xmax": 365119, "ymax": 7508582},
            "data_extent": {"xmin": 325979, "ymin": 7475453, "xmax": 363256, "ymax": 7507005},
        },
        "legend": {"item_id": "legend", "layer_names": ["Unidades de Conservacao"]},
        "scalebar": {"item_id": "scale_bar", "unit": "km", "units_per_segment": 1, "segments": 2,
                     "frame_fraction": 0.041},
        "north": {"item_id": "north_arrow", "kind": "label", "text": "N ^"},
        "output": {"path": "/tmp/x.png", "exists": True, "size_bytes": 516237, "format": "png"},
    }


def observation_good() -> dict:
    observation = observation_v011()
    observation["items"] = [
        item for item in observation["items"] if item["id"] != "north_arrow"
    ] + [
        {"id": "north_arrow", "role": "north", "type": "picture", "x": 248, "y": 32, "width": 12, "height": 18},
        {"id": "scale_text", "role": "scale_text", "type": "label", "x": 220, "y": 152, "width": 60, "height": 7,
         "font_size_pt": 9, "text": "Escala 1:250.000"},
        # A linha de crédito de um mapa publicável diz de ONDE vieram os dados e
        # QUEM fez o mapa: sistema de referência e data, sozinhos, não são
        # procedência.
        {"id": "source", "role": "source", "type": "label", "x": 10, "y": 197, "width": 264, "height": 6,
         "font_size_pt": 7,
         "text": ("Fonte: IBGE, Malha Municipal 2024 · Elaboração: MACIEL, L. S. C. · "
                  "SIRGAS 2000 / UTM 23S (EPSG:31983) · 04/09/2026")},
    ]
    observation["legend"]["layer_names"] = ["Unidades de Conservacao", "Drenagem", "Ocorrencias"]
    observation["scalebar"]["frame_fraction"] = 0.29
    observation["north"] = {"item_id": "north_arrow", "kind": "picture", "path": "NorthArrow_02.svg"}
    observation["map"]["grid"] = {"enabled": True, "interval_x": 10000.0, "interval_y": 10000.0, "annotations": True}
    return observation


class RulebookShapeTests(unittest.TestCase):
    def test_every_rule_carries_reason_fix_and_reference(self):
        for rule in RULES:
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.rationale_pt.strip(), "a regra precisa dizer por que existe")
                self.assertTrue(rule.fix_pt.strip(), "a regra precisa dizer como corrigir")
                self.assertTrue(rule.reference.strip(), "a regra precisa citar a origem")
                self.assertTrue(callable(rule.check))

    def test_rule_ids_are_unique(self):
        self.assertEqual(len(RULES), len(RULES_BY_ID))

    def test_manifest_is_serialisable_and_grouped(self):
        manifest = rulebook_manifest()
        self.assertEqual(manifest["rule_count"], len(RULES))
        self.assertIn("elementos", manifest["categories"])


class RegressionAgainstTheOldEvaluatorTests(unittest.TestCase):
    def test_the_map_the_old_evaluator_called_professional_is_rejected(self):
        report = evaluate(observation_v011())
        self.assertGreater(report["counts"]["errors"], 0)
        self.assertIn(report["grade"], {"D", "E"})

    def test_it_names_the_three_defects_that_mattered(self):
        report = evaluate(observation_v011())
        failed = {entry["id"] for entry in report["results"] if entry["status"] == "fail"}
        self.assertIn("CART020", failed)  # legenda não cobre as camadas visíveis
        self.assertIn("CART026", failed)  # grade com intervalo zero
        self.assertIn("CART025", failed)  # rosa dos ventos como texto
        self.assertIn("CART022", failed)  # barra de escala desproporcional

    def test_each_failure_explains_itself_and_offers_a_fix(self):
        report = evaluate(observation_v011())
        for entry in report["results"]:
            if entry["status"] == "fail":
                with self.subTest(rule=entry["id"]):
                    self.assertTrue(entry["detail_pt"])
                    self.assertTrue(entry["fix_pt"])
                    self.assertTrue(entry["rationale_pt"])

    def test_next_actions_lead_with_the_blocking_errors(self):
        report = evaluate(observation_v011())
        self.assertTrue(report["next_actions"])
        self.assertEqual(report["next_actions"][0]["severity"], SEVERITY_ERROR)
        self.assertTrue(report["blocking_issues"])


class GoodMapTests(unittest.TestCase):
    def test_a_corrected_map_passes(self):
        report = evaluate(observation_good())
        self.assertEqual(report["counts"]["errors"], 0)
        self.assertEqual(report["grade"], "A")

    def test_blank_map_frame_is_an_error_even_when_the_file_exists(self):
        observation = observation_good()
        observation["map"]["rendered_ink_fraction"] = 0.0001
        report = evaluate(observation)
        failed = {entry["id"] for entry in report["results"] if entry["status"] == "fail"}
        self.assertIn("CART062", failed)

    def test_metric_scale_bar_on_a_geographic_crs_is_an_error(self):
        observation = observation_good()
        observation["map"]["crs"] = "EPSG:4674"
        observation["map"]["crs_is_geographic"] = True
        report = evaluate(observation)
        failed = {entry["id"] for entry in report["results"] if entry["status"] == "fail"}
        self.assertIn("CART024", failed)

    def test_item_outside_the_page_is_caught(self):
        observation = observation_good()
        observation["items"].append(
            {"id": "perdido", "role": "label", "type": "label", "x": 320, "y": 10, "width": 40, "height": 8,
             "font_size_pt": 8, "text": "fora"}
        )
        report = evaluate(observation)
        failed = {entry["id"] for entry in report["results"] if entry["status"] == "fail"}
        self.assertIn("CART040", failed)

    def test_a_broken_rule_never_takes_down_the_report(self):
        # Uma observação vazia não pode gerar exceção: o laudo é o canal pelo
        # qual o agente descobre o que fazer, e precisa sempre chegar.
        report = evaluate({})
        self.assertIn("grade", report)
        self.assertIn("results", report)


if __name__ == "__main__":
    unittest.main()
