"""Normas de figura das revistas (sigmai/cartography/journals.py): puro, sem QGIS."""

import unittest

from sigmai.cartography.journals import (
    JOURNAL_PROFILES, check_figure, column_width, find_journal, profile_from_dict, resolve_journal,
)
from sigmai.cartography.params import ParameterError


class Perfis(unittest.TestCase):
    def test_todo_perfil_tem_fonte_e_data(self):
        # Nenhum valor de norma sem o endereço de onde veio e o dia em que foi lido.
        for key, perfil in JOURNAL_PROFILES.items():
            with self.subTest(revista=key):
                self.assertEqual(perfil.key, key)
                self.assertTrue(perfil.sources)
                self.assertRegex(perfil.checked, r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(perfil.widths_mm or perfil.max_width_mm or perfil.notes)

    def test_acha_pelo_nome_e_pelo_apelido(self):
        self.assertEqual(find_journal("Biodiversity Informatics").key, "biodiversity_informatics")
        self.assertEqual(find_journal("PLOS ONE").key, "plos_one")
        self.assertEqual(find_journal("zjls").key, "zoological_journal_linnean_society")
        self.assertIsNone(find_journal("Revista Que Não Existe"))

    def test_coluna_da_revista(self):
        bi = find_journal("bi")
        self.assertEqual(column_width(bi, None), ("single", 88.0))
        self.assertEqual(column_width(bi, "dupla"), ("double", 180.0))
        with self.assertRaises(ParameterError):
            column_width(bi, "one_and_half")

    def test_area_maxima_sem_coluna(self):
        zootaxa = find_journal("zootaxa")
        self.assertEqual(column_width(zootaxa, None), ("max", 170.0))
        self.assertTrue(zootaxa.accepts_width(88.0))
        self.assertFalse(zootaxa.accepts_width(175.0))

    def test_sem_largura_declarada_pede_figure_width(self):
        with self.assertRaises(ParameterError):
            column_width(find_journal("biota neotropica"), None)

    def test_confere_largura_fonte_formato_e_resolucao(self):
        plos = find_journal("plos")
        problemas = check_figure(plos, 88.0, 120.0, 7.0, "pdf", None)
        self.assertEqual(len(problemas), 2)  # 7 pt < 8 pt; PDF não aceito
        self.assertEqual(check_figure(plos, 132.0, 160.0, 8.0, "tif", 299.99), [])  # arredondamento de pixel
        self.assertTrue(check_figure(find_journal("springer"), 100.0, 100.0, 8.0, "tif", 300, has_halftone=False))

    def test_resolucao_de_combinacao_com_relevo(self):
        elsevier = find_journal("elsevier")
        self.assertEqual(elsevier.raster_dpi(has_halftone=True), 500)
        self.assertEqual(elsevier.raster_dpi(has_halftone=False), 1000)


class PerfilInformado(unittest.TestCase):
    def test_revista_fora_da_tabela(self):
        perfil = profile_from_dict({"name": "Revista X", "widths_mm": {"single": 80, "double": 170},
                                    "max_height_mm": 220, "min_font_pt": 7, "formats": ["tiff", "pdf"]})
        self.assertEqual(perfil.widths_mm, {"single": 80.0, "double": 170.0})
        self.assertEqual(resolve_journal({"journal_profile": {"widths_mm": {"single": 80}}}).widths_mm, {"single": 80.0})

    def test_campo_errado_e_recusado(self):
        with self.assertRaises(ParameterError):
            profile_from_dict({"widths_mm": {"single": 80}, "min_font": 7})
        with self.assertRaises(ParameterError):
            profile_from_dict({"max_height_mm": 220})

    def test_revista_desconhecida_manda_ler_a_norma(self):
        with self.assertRaises(ParameterError) as erro:
            resolve_journal({"journal": "Revista Que Não Existe"})
        self.assertIn("journal_profile", str(erro.exception))


if __name__ == "__main__":
    unittest.main()
