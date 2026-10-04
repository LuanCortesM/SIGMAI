#!/usr/bin/env python3
"""Roda no pacote a mesma "Qt6 Check" do repositório de plugins do QGIS.

O plugins.qgis.org passa cada versão enviada pelo ``pyqt5_to_pyqt6.py`` do
próprio QGIS e mostra o resultado na aba "Qt6 Check"; é ela que decide o selo
"QGIS 4 Ready". A 1.1.4 funcionava no QGIS 4 e mesmo assim saiu com dois
apontamentos — ``box.exec_()`` num ramo de compatibilidade e um
``from PyQt5`` de reserva fora do QGIS —, porque o script lê o texto, não o
comportamento. Este utilitário baixa o script numa versão fixa e o roda em
modo de simulação; sai com código 1 se houver apontamento.

Uso::

    python tools/qgis_qt6_check.py              # verifica sigmai/
    python tools/qgis_qt6_check.py dist/x.zip   # verifica o ZIP enviado

Requer PyQt6, PyQt6-QScintilla e tokenize-rt (``pip install PyQt6
PyQt6-QScintilla tokenize-rt``); o Python do QGIS 4 já traz os dois primeiros.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "sigmai"

#: Versão fixa do script, para que um commit novo no QGIS não mude o
#: resultado sem aviso. Atualize quando o repositório de plugins atualizar.
CHECKER_COMMIT = "42c6d1d4d840a08e8b0006af4b3f622c52a8329d"
CHECKER_URL = (
    f"https://raw.githubusercontent.com/qgis/QGIS/{CHECKER_COMMIT}"
    "/scripts/pyqt5_to_pyqt6/pyqt5_to_pyqt6.py"
)

#: Configura o log *antes* de carregar o script: fora do QGIS ele avisa no
#: import que não há classes do QGIS para inspecionar, esse aviso configura o
#: logging do Python, e o ``--logfile`` dele passa a ser ignorado.
RUNNER = """
import logging, runpy, sys
script, target, log = sys.argv[1:4]
logging.basicConfig(level=logging.DEBUG, format="%(message)s", filename=log, filemode="w", encoding="utf-8")
sys.argv = [script, "--dry_run", target]
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit:
    pass
"""


def run_checker(target: Path, workdir: Path) -> list[str]:
    script = workdir / "pyqt5_to_pyqt6.py"
    with urllib.request.urlopen(CHECKER_URL, timeout=60) as response:  # noqa: S310 (URL fixa, https)
        script.write_bytes(response.read())
    log = workdir / "qt6_check.log"
    result = subprocess.run(
        [sys.executable, "-c", RUNNER, str(script), str(target), str(log)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0 or not log.exists():
        raise SystemExit(f"o verificador não rodou:\n{result.stderr[-2000:]}")
    # Todo apontamento começa pelo caminho do arquivo: "arq.py:linha:col - msg"
    # ou, nos avisos de import, "arq.py: msg".
    prefix = str(target)
    return [
        line[len(prefix):].lstrip("\\/")
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith(prefix)
    ]


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory(prefix="sigmai_qt6_") as folder:
        workdir = Path(folder)
        target = PACKAGE
        if argv:
            source = Path(argv[0]).resolve()
            target = source
            if not source.is_dir():
                with zipfile.ZipFile(source) as archive:
                    archive.extractall(workdir / "pkg")
                target = workdir / "pkg" / "sigmai"
        findings = run_checker(target, workdir)
    print(f"Qt6 Check (pyqt5_to_pyqt6.py @ {CHECKER_COMMIT[:7]}): {len(findings)} apontamento(s)")
    for finding in findings:
        print(f"  {finding}")
    print("REPROVADO: o selo QGIS 4 Ready não viria." if findings else "OK: nenhum apontamento.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
