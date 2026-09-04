"""Página e solucionador de layout: nada pode cair fora da folha."""

import unittest

from sigmai.cartography.layoutgrid import DEFAULT_TEMPLATE, TEMPLATES, solve_layout
from sigmai.cartography.pagespec import MIN_MARGIN_MM, PAGE_SIZES, resolve_page


class PageSpecTests(unittest.TestCase):
    def test_named_sizes_resolve_in_landscape_by_default(self):
        page = resolve_page("A4")
        self.assertEqual((round(page.width_mm), round(page.height_mm)), (297, 210))
        self.assertEqual(page.orientation, "landscape")

    def test_orientation_can_be_given_in_portuguese(self):
        page = resolve_page("A3 retrato")
        self.assertEqual(page.orientation, "portrait")
        self.assertLess(page.width_mm, page.height_mm)

    def test_custom_size(self):
        page = resolve_page({"width_mm": 300, "height_mm": 200, "name": "custom"})
        self.assertEqual((page.width_mm, page.height_mm), (300.0, 200.0))

    def test_unknown_name_falls_back_to_a4(self):
        page = resolve_page("papel-inventado")
        self.assertEqual((round(page.width_mm), round(page.height_mm)), (297, 210))

    def test_margins_never_go_below_the_print_floor(self):
        page = resolve_page("A5", margin_mm=0.5)
        self.assertGreaterEqual(page.margin_left_mm, MIN_MARGIN_MM)

    def test_content_area_is_the_page_minus_margins(self):
        page = resolve_page("A4", margin_mm=12)
        self.assertAlmostEqual(page.content_width_mm, 297 - 24)
        self.assertAlmostEqual(page.content_height_mm, 210 - 24)


class LayoutSolverTests(unittest.TestCase):
    def test_every_slot_stays_inside_the_margins_for_every_combination(self):
        pages = list(PAGE_SIZES) + ["A4 portrait", "A3 retrato"]
        for page_name in pages:
            for template in TEMPLATES:
                with self.subTest(page=page_name, template=template):
                    plan = solve_layout(page_name, template, include_logo=True)
                    for name, rect in plan.slots.items():
                        self.assertTrue(
                            plan.page.within_margins(rect.x, rect.y, rect.width, rect.height),
                            f"{name} fora das margens em {page_name}/{template}: {rect.to_dict()}",
                        )

    def test_wide_pages_get_a_side_column_and_tall_pages_a_bottom_band(self):
        self.assertEqual(solve_layout("A4 landscape").arrangement, "coluna_lateral")
        self.assertEqual(solve_layout("A4 portrait").arrangement, "faixa_inferior")

    def test_map_dominates_the_content_area(self):
        for page_name in ("A5 portrait", "A4", "A3", "A0"):
            with self.subTest(page=page_name):
                plan = solve_layout(page_name)
                frame = plan.map_frame()
                content = plan.page.content_width_mm * plan.page.content_height_mm
                self.assertGreater(frame.width * frame.height / content, 0.35)

    def test_no_two_slots_overlap(self):
        plan = solve_layout("A4", include_logo=True)
        rects = list(plan.slots.items())
        for index, (name_a, a) in enumerate(rects):
            for name_b, b in rects[index + 1:]:
                overlap_w = min(a.right, b.right) - max(a.x, b.x)
                overlap_h = min(a.bottom, b.bottom) - max(a.y, b.y)
                self.assertFalse(
                    overlap_w > 0.5 and overlap_h > 0.5,
                    f"{name_a} sobrepõe {name_b}",
                )

    def test_grid_gutter_shrinks_the_map_frame(self):
        without = solve_layout("A4").map_frame()
        with_gutter = solve_layout("A4", grid_annotation_gutter_mm=6.0).map_frame()
        self.assertLess(with_gutter.width, without.width)
        self.assertAlmostEqual(with_gutter.x - without.x, 6.0, places=3)

    def test_fonts_scale_with_the_page_but_never_below_the_legibility_floor(self):
        small = solve_layout("A5 portrait").fonts
        large = solve_layout("A0").fonts
        self.assertGreater(large["title"], small["title"])
        for fonts in (small, large):
            for value in fonts.values():
                self.assertGreaterEqual(value, 6.0)

    def test_unknown_template_falls_back_and_says_so(self):
        plan = solve_layout("A4", "template-inexistente")
        self.assertEqual(plan.template, DEFAULT_TEMPLATE)
        self.assertTrue(any("desconhecido" in note for note in plan.notes))


if __name__ == "__main__":
    unittest.main()
