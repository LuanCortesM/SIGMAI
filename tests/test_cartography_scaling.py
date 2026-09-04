"""Testes do núcleo numérico da cartografia. Não exigem QGIS."""

import unittest

from sigmai.cartography.scaling import (
    SCALE_LADDER,
    ExtentError,
    choose_publication_scale,
    fit_extent_to_frame,
    graticule_interval,
    nice_number,
    round_scale,
    scale_from_extent,
    scalebar_spec,
)


class NiceNumberTests(unittest.TestCase):
    def test_snaps_to_the_cartographic_steps(self):
        self.assertEqual(nice_number(1.0), 1.0)
        self.assertEqual(nice_number(2.3), 2.5)
        self.assertEqual(nice_number(4.4), 5.0)
        self.assertEqual(nice_number(9.9), 10.0)
        self.assertEqual(nice_number(2400), 2500)

    def test_direction_is_respected(self):
        self.assertEqual(nice_number(2.3, "up"), 2.5)
        self.assertEqual(nice_number(2.3, "down"), 2.0)

    def test_rejects_non_positive(self):
        with self.assertRaises(ValueError):
            nice_number(0)


class ScaleTests(unittest.TestCase):
    def test_scale_from_extent(self):
        # 100 m de terreno num quadro de 100 mm => 1:1000
        self.assertAlmostEqual(scale_from_extent(100.0, 100.0), 1000.0)

    def test_round_scale_stays_on_the_ladder(self):
        self.assertIn(round_scale(23_500), SCALE_LADDER)
        self.assertEqual(round_scale(23_500, "up"), 25_000)

    def test_publication_scale_prefers_the_ladder_when_the_margin_permits(self):
        scale, basis = choose_publication_scale(233_722, 257_094)
        self.assertEqual(scale, 250_000)
        self.assertEqual(basis, "serie_cartografica")

    def test_publication_scale_abandons_the_ladder_rather_than_wasting_the_page(self):
        # O degrau seguinte da série (500.000) dobraria a extensão: 46% de
        # margem. É a regressão que motivou choose_publication_scale.
        scale, basis = choose_publication_scale(260_000, 286_000)
        self.assertEqual(basis, "dois_algarismos_significativos")
        self.assertGreaterEqual(scale, 260_000)
        self.assertLess((scale / 260_000 - 1) / 2 * 100, 25.0)


class FitExtentTests(unittest.TestCase):
    def setUp(self):
        self.extent = (325_979.0, 7_475_453.0, 363_256.0, 7_507_005.0)

    def test_matches_the_frame_aspect_ratio(self):
        fitted = fit_extent_to_frame(*self.extent, 176.0, 135.0, margin_percent=5)
        self.assertAlmostEqual(fitted.width / fitted.height, 176.0 / 135.0, places=6)

    def test_never_clips_the_data(self):
        fitted = fit_extent_to_frame(*self.extent, 176.0, 135.0, margin_percent=0)
        self.assertLessEqual(fitted.xmin, self.extent[0])
        self.assertLessEqual(fitted.ymin, self.extent[1])
        self.assertGreaterEqual(fitted.xmax, self.extent[2])
        self.assertGreaterEqual(fitted.ymax, self.extent[3])

    def test_keeps_the_centre(self):
        fitted = fit_extent_to_frame(*self.extent, 176.0, 135.0, margin_percent=8)
        self.assertAlmostEqual((fitted.xmin + fitted.xmax) / 2, (self.extent[0] + self.extent[2]) / 2, places=3)
        self.assertAlmostEqual((fitted.ymin + fitted.ymax) / 2, (self.extent[1] + self.extent[3]) / 2, places=3)

    def test_reports_the_margin_it_actually_delivered(self):
        fitted = fit_extent_to_frame(*self.extent, 176.0, 135.0, margin_percent=5)
        self.assertEqual(fitted.scale_denominator, 250_000)
        # Não basta arredondar a escala: a margem resultante precisa ser
        # declarada, senão o usuário pede 5% e recebe outra coisa em silêncio.
        self.assertLess(fitted.effective_margin_percent, 25.0)
        self.assertTrue(fitted.notes)

    def test_geographic_extent_needs_map_units_per_metre(self):
        """Graus tratados como metros produzem uma escala sem sentido.

        Regressão de dado real: o Piauí em SIRGAS 2000 geográfico (EPSG:4674)
        mede ~5,6 x 8,2 graus. Sem converter para metros, a extensão parece ter
        8 unidades de largura e a escala saía como 1:65 — três ordens de
        grandeza fora, com o quadro do mapa cortando todos os dados.
        """
        piaui = (-45.99, -10.93, -40.37, -2.74)
        as_if_metres = fit_extent_to_frame(*piaui, 190.0, 140.0, margin_percent=5)
        self.assertLess(as_if_metres.scale_denominator, 1000)

        # Um grau de longitude a ~7°S mede cerca de 110,5 km.
        metres_per_degree = 110_500.0
        corrected = fit_extent_to_frame(
            *piaui, 190.0, 140.0, margin_percent=5,
            map_units_per_metre=1.0 / metres_per_degree,
        )
        self.assertGreater(corrected.scale_denominator, 3_000_000)
        self.assertLess(corrected.scale_denominator, 12_000_000)

    def test_scale_bar_for_a_state_sized_map_is_in_kilometres(self):
        spec = scalebar_spec(7_200_000, 190.0)
        self.assertEqual(spec.unit, "km")
        self.assertGreaterEqual(spec.units_per_segment, 10)
        self.assertEqual(spec.units_per_segment, int(spec.units_per_segment))

    def test_rejects_degenerate_extent(self):
        with self.assertRaises(ExtentError):
            fit_extent_to_frame(10, 10, 10, 20, 100, 100)


class ScaleBarTests(unittest.TestCase):
    def test_bar_occupies_a_legible_fraction_across_five_orders_of_magnitude(self):
        for denominator in (500, 1_000, 5_000, 25_000, 100_000, 250_000, 1_000_000, 10_000_000):
            with self.subTest(scale=denominator):
                spec = scalebar_spec(denominator, 176.0)
                self.assertGreaterEqual(spec.frame_fraction, 0.15)
                self.assertLessEqual(spec.frame_fraction, 0.45)

    def test_segment_length_is_a_round_number(self):
        spec = scalebar_spec(250_000, 176.0)
        self.assertIn(spec.units_per_segment / (10 ** len(str(int(spec.units_per_segment))[1:])), (1.0, 2.0, 2.5, 5.0))

    def test_uses_metres_below_a_kilometre(self):
        self.assertEqual(scalebar_spec(2_000, 176.0).unit, "m")

    def test_honours_the_slot_width(self):
        # A barra não pode estourar a faixa reservada: era o que sobrepunha a
        # legenda nos layouts em retrato.
        spec = scalebar_spec(250_000, 176.0, max_width_mm=30.0)
        self.assertLessEqual(spec.bar_width_mm, 30.0)

    def test_rejects_invalid_scale(self):
        with self.assertRaises(ValueError):
            scalebar_spec(0, 100)


class GraticuleTests(unittest.TestCase):
    def test_projected_interval_is_round(self):
        self.assertEqual(graticule_interval(41_000, 4), 10_000)

    def test_geographic_interval_lands_on_a_sexagesimal_fraction(self):
        interval = graticule_interval(0.42, 4, geographic=True)
        self.assertAlmostEqual(interval * 60, 5.0, places=6)

    def test_never_returns_zero(self):
        # O intervalo zero é o padrão do QGIS e o motivo de a grade do
        # SIGMAI 0.1.1 nunca aparecer no papel.
        for span in (0.0001, 1, 1000, 5_000_000):
            self.assertGreater(graticule_interval(span, 4), 0)


if __name__ == "__main__":
    unittest.main()
