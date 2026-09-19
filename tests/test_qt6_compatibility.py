"""Impede a volta do defeito que travou o SIGMAI 0.2.0 no QGIS 4.1.

O plugin declara ``qgisMaximumVersion=4.99``, e o QGIS 4 roda sobre Qt6, onde
os enums só existem no escopo qualificado. Um único ``QSizePolicy.Fixed`` no
construtor do painel bastou para o painel não abrir — e nenhum teste pegou,
porque a suíte roda sem Qt e o ambiente de desenvolvimento tinha Qt5.

Estes testes fecham as duas frestas: o verificador estático roda sobre o pacote
inteiro, e o painel é construído de verdade contra PyQt6 quando ele está
disponível.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_qt6_compat.py"


def _pyqt6_available() -> bool:
    """Há PyQt6 instalado? Sem importá-lo.

    Importar PyQt6.QtWidgets aqui carregava o Qt6 no MESMO processo em que a
    suíte roda o QGIS com PyQt5 — dois Qt num processo é comportamento
    indefinido, e era a origem de falhas intermitentes noutros arquivos
    (EPSG:4326 resolvendo como CRS inválido, segfault em QgsProject.clear).
    Os testes que usam o Qt6 rodam em subprocesso; aqui basta saber que ele
    existe.
    """
    import importlib.util

    try:
        return importlib.util.find_spec("PyQt6.QtWidgets") is not None
    except (ImportError, ValueError):
        return False


class StaticCheckerTests(unittest.TestCase):
    def test_checker_exists(self):
        self.assertTrue(CHECKER.exists(), "tools/check_qt6_compat.py sumiu")

    @unittest.skipUnless(_pyqt6_available(), "PyQt6 não instalado")
    def test_package_has_no_qt5_only_enum_access(self):
        result = subprocess.run(
            [sys.executable, str(CHECKER), "sigmai", "--mode", "qt"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"acessos incompatíveis com Qt6:\n{result.stdout}")

    def test_checker_flags_a_known_bad_pattern(self):
        """O verificador precisa reprovar o padrão exato que causou a falha."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "amostra.py"
            sample.write_text(
                "from qgis.PyQt.QtWidgets import QSizePolicy\n"
                "def build(widget):\n"
                "    widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(CHECKER), str(sample), "--mode", "qt"],
                cwd=ROOT, capture_output=True, text=True,
            )
        if not _pyqt6_available():
            self.skipTest("PyQt6 não instalado")
        self.assertEqual(result.returncode, 1, "o verificador deixou passar QSizePolicy.Fixed")
        self.assertIn("QSizePolicy.Policy.Fixed", result.stdout)


@unittest.skipUnless(_pyqt6_available(), "PyQt6 não instalado")
class PanelUnderQt6Tests(unittest.TestCase):
    """Constrói o painel com o binding do Qt6, como o QGIS 4 faria."""

    @classmethod
    def setUpClass(cls):
        cls.script = ROOT / "tools" / "qt6_panel_check.py"
        if not cls.script.exists():
            raise unittest.SkipTest("tools/qt6_panel_check.py ausente")

    def test_panel_builds_and_reacts(self):
        result = subprocess.run(
            [sys.executable, str(self.script)],
            cwd=ROOT, capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(ROOT)},
        )
        self.assertEqual(result.returncode, 0, f"o painel falhou sob Qt6:\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
