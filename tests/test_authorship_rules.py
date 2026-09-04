import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sigmai.qgis_actions.cartography import PLUGIN_AUTHOR, build_product_credit  # noqa: E402


class AuthorshipRulesTests(unittest.TestCase):
    def test_metadata_keeps_plugin_author(self):
        metadata = (ROOT / "sigmai" / "metadata.txt").read_text(encoding="utf-8")
        self.assertIn("author=MACIEL, L. S. C.", metadata)
        self.assertIn("email=herpetomantiqueira@gmail.com", metadata)

    def test_readme_keeps_plugin_author(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("MACIEL, L. S. C.", readme)
        self.assertIn("herpetomantiqueira@gmail.com", readme)

    def test_ui_keeps_plugin_author(self):
        # A autoria do plugin saiu do cabeçalho do painel e passou para a
        # seção "Sobre", em Avançado: o cabeçalho responde "como conecto?",
        # não "quem escreveu isto?". A informação continua visível e é o
        # arquivo de textos da interface que a carrega, nos dois idiomas.
        strings = (ROOT / "sigmai" / "ui" / "strings.py").read_text(encoding="utf-8")
        self.assertEqual(strings.count("Plugin author: MACIEL, L. S. C."), 2)
        self.assertIn("herpetomantiqueira@gmail.com", strings)

    def test_ui_separates_plugin_authorship_from_map_authorship(self):
        strings = (ROOT / "sigmai" / "ui" / "strings.py").read_text(encoding="utf-8")
        self.assertIn("about_map_authorship", strings)
        self.assertIn("map_author", strings)

    def test_public_map_credit_does_not_default_to_plugin_author(self):
        context = {"user_profile": {"default_map_author": "", "default_map_author_email": "", "default_organization": "", "default_credit_line": "", "use_plugin_author_as_map_author_in_dev": True}}
        credits = build_product_credit({}, context)
        self.assertEqual(credits["plugin_author"], PLUGIN_AUTHOR)
        self.assertEqual(credits["map_author"], "")
        self.assertNotIn(PLUGIN_AUTHOR, credits["credit_line"])
        self.assertIn("Elaborado com SIGMAI", credits["credit_line"])
        self.assertIn("QGIS", credits["credit_line"])

    def test_map_author_is_used_when_explicit(self):
        credits = build_product_credit({"map_author": "Nome do Usuario", "data_source": "IBGE, 2025"}, {})
        self.assertEqual(credits["map_author"], "Nome do Usuario")
        self.assertIn("Elaboracao: Nome do Usuario.", credits["credit_line"])
        self.assertIn("Fonte: IBGE, 2025.", credits["credit_line"])

    def test_user_profile_map_author_is_used(self):
        context = {"user_profile": {"default_map_author": "Autora Configurada", "default_map_author_email": "", "default_organization": "Laboratorio SIG", "default_credit_line": "", "use_plugin_author_as_map_author_in_dev": True}}
        credits = build_product_credit({}, context)
        self.assertEqual(credits["map_author"], "Autora Configurada")
        self.assertIn("Elaboracao: Autora Configurada.", credits["credit_line"])
        self.assertIn("Organizacao: Laboratorio SIG.", credits["credit_line"])

    def test_plugin_author_can_be_dev_fallback_only_with_flag(self):
        credits = build_product_credit({"dev_mode": True, "use_plugin_author_as_map_author_in_dev": True}, {})
        self.assertEqual(credits["map_author"], PLUGIN_AUTHOR)
        self.assertIn(PLUGIN_AUTHOR, credits["credit_line"])


if __name__ == "__main__":
    unittest.main()
