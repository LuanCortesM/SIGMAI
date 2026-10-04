"""Uma licença só, declarada igual em todo lugar.

O GitHub passou a dizer MIT (editado pela web em 2026-05-26) enquanto o
plugin, o pyproject, o CITATION.cff e o README continuavam declarando
GPL-3.0-or-later. Quem baixasse pelo repositório do QGIS e quem clonasse
pelo GitHub leria licenças diferentes para o mesmo código. A 1.1.2 adota a
MIT em todos os pontos; este teste impede que eles voltem a divergir.
"""

from __future__ import annotations

import configparser
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _metadata_license() -> str:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(ROOT / "sigmai" / "metadata.txt", encoding="utf-8")
    return parser.get("general", "license", fallback="")


class LicencaUnica(unittest.TestCase):
    def test_metadata_declara_mit(self):
        self.assertEqual(_metadata_license(), "MIT")

    def test_textos_integrais_iguais_na_raiz_e_no_pacote(self):
        raiz = (ROOT / "LICENSE").read_text(encoding="utf-8")
        pacote = (ROOT / "sigmai" / "LICENSE").read_text(encoding="utf-8")
        self.assertEqual(raiz, pacote)
        self.assertTrue(raiz.startswith("MIT License"))
        self.assertIn("Permission is hereby granted", raiz)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', raiz)
        self.assertIn("MACIEL, L. S. C.", raiz)

    def test_pyproject_citation_readme_concordam(self):
        self.assertIn('license = { text = "MIT" }', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertRegex((ROOT / "CITATION.cff").read_text(encoding="utf-8"), r"(?m)^license: MIT$")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("license-MIT", readme)
        self.assertIn("license = {MIT}", readme)

    def test_nenhum_texto_publico_fala_em_gpl(self):
        # O changelog do metadata.txt registra a troca e por isso cita a GPL;
        # o campo license= é conferido em test_metadata_declara_mit.
        alvos = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "docs" / "pt-BR" / "LEIAME.md",
                 *sorted((ROOT / "sigmai" / "ui" / "strings").glob("*.py"))]
        for alvo in alvos:
            with self.subTest(alvo.name):
                self.assertNotRegex(alvo.read_text(encoding="utf-8"), re.compile(r"\bGPL\b|General Public License"))


if __name__ == "__main__":
    unittest.main()
