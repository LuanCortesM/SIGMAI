#!/usr/bin/env python3
"""Roda no pacote as mesmas varreduras do repositório de plugins do QGIS.

Desde 2026 o plugins.qgis.org varre toda versão enviada com Bandit,
detect-secrets, Flake8 e uma análise de arquivos. Achado *crítico* do Bandit
ou do detect-secrets bloqueia a versão para download e aprovação, e uma versão
bloqueada não se desbloqueia: é preciso enviar outra. Os demais são avisos.
Documentação: https://plugins.qgis.org/docs/security-scanning

A 1.1.3 teria sido bloqueada por 40 falsos positivos da regra B105 (chaves de
texto da interface como ``advanced_token``, a opção ``persist_token``, o par
``"token_required": True``) e um da B107 (``token=""`` como argumento padrão).
Este script existe para que isso apareça no CI, e não depois do upload.

Uso::

    python tools/qgis_repository_scan.py              # varre sigmai/
    python tools/qgis_repository_scan.py dist/x.zip   # varre o ZIP enviado

Avisos (regras que o site não bloqueia) são listados sem reprovar.

Requer ``bandit``, ``detect-secrets`` e ``flake8`` (``pip install bandit
detect-secrets flake8``). Sai com código 1 se houver achado bloqueante.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "sigmai"

#: Regras que o repositório classifica como Critical (bloqueantes), conforme
#: https://plugins.qgis.org/docs/security-scanning/rules em 2026-10-04: 38 do
#: Bandit, 23 detectores do detect-secrets, 6 do Flake8 e FILE_SUSPICIOUS. A
#: lista do site é viva; se ela mudar, acompanhe aqui.
BANDIT_CRITICAL = frozenset({
    "B102", "B103", "B105", "B106", "B107", "B111", "B201", "B202", "B301",
    "B302", "B304", "B305", "B306", "B307", "B312", "B321", "B323", "B401",
    "B402", "B412", "B413", "B501", "B502", "B503", "B505", "B506", "B507",
    "B601", "B602", "B604", "B605", "B609", "B610", "B611", "B612", "B613",
    "B615", "B701",
})

#: Os únicos detectores do detect-secrets que o site trata como aviso
#: (KeywordDetector, Base64HighEntropyString, HexHighEntropyString); os demais
#: — chaves de AWS, GitHub, OpenAI, chaves privadas etc. — são críticos.
SECRET_WARNING_TYPES = frozenset({"Secret Keyword", "Base64 High Entropy String", "Hex High Entropy String"})

#: Erros do Flake8 que indicam código que nem roda. O site bloqueia E901,
#: E902, E999, F821, F823 e F831; F63, F7 e F822 entram por serem erros reais.
FLAKE8_FATAL = "E9,F63,F7,F821,F822,F823,F831"

#: Extensões que a análise de arquivos do site aponta como suspeitas
#: (FILE_SUSPICIOUS, crítica).
SUSPICIOUS_SUFFIXES = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".ps1", ".sh", ".vbs",
    ".msi", ".com", ".scr", ".jar", ".pyc", ".pyo",
})


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", *args], capture_output=True, text=True, encoding="utf-8")


def _require(module: str, package: str) -> None:
    probe = _run(module, "--version")
    if probe.returncode != 0:
        raise SystemExit(f"{package} não está instalado: pip install bandit detect-secrets flake8")


def bandit_findings(target: Path) -> list[str]:
    _require("bandit", "bandit")
    result = _run("bandit", "-r", str(target), "-f", "json", "-q")
    report = json.loads(result.stdout or "{}")
    findings = []
    for item in report.get("results", []):
        if item["test_id"] in BANDIT_CRITICAL:
            path = Path(item["filename"]).relative_to(target)
            findings.append(f"{item['test_id']} {path}:{item['line_number']} {item['issue_text']}")
    for error in report.get("errors", []):
        findings.append(f"bandit não conseguiu ler {error.get('filename')}: {error.get('reason')}")
    return findings


def secret_findings(target: Path) -> tuple[list[str], list[str]]:
    """(críticos, avisos) do detect-secrets."""
    _require("detect_secrets", "detect-secrets")
    result = _run("detect_secrets", "scan", "--all-files", str(target))
    report = json.loads(result.stdout or "{}")
    critical: list[str] = []
    warnings: list[str] = []
    for filename, entries in report.get("results", {}).items():
        for entry in entries:
            line = f"{entry['type']} {Path(filename)}:{entry['line_number']}"
            (warnings if entry["type"] in SECRET_WARNING_TYPES else critical).append(line)
    return critical, warnings


def flake8_findings(target: Path) -> list[str]:
    _require("flake8", "flake8")
    result = _run("flake8", f"--select={FLAKE8_FATAL}", str(target))
    return [line for line in result.stdout.splitlines() if line.strip()]


def suspicious_files(target: Path) -> list[str]:
    return sorted(
        str(path.relative_to(target))
        for path in target.rglob("*")
        if path.is_file() and path.suffix.lower() in SUSPICIOUS_SUFFIXES
        and "__pycache__" not in path.parts  # o empacotador não leva o cache
    )


def scan(target: Path) -> int:
    secrets_critical, secrets_warning = secret_findings(target)
    blocking = {
        "Bandit (CRITICAL)": bandit_findings(target),
        "detect-secrets (CRITICAL)": secrets_critical,
        "Flake8 (erro fatal)": flake8_findings(target),
        "Arquivos suspeitos (FILE_SUSPICIOUS)": suspicious_files(target),
    }
    advisory = {"detect-secrets": secrets_warning}
    failed = False
    for title, findings in blocking.items():
        print(f"{title}: {len(findings)}")
        for finding in findings:
            print(f"  {finding}")
        failed = failed or bool(findings)
    for title, findings in advisory.items():
        print(f"{title} (aviso): {len(findings)}")
        for finding in findings:
            print(f"  {finding}")
    print("REPROVADO: o repositório do QGIS bloquearia esta versão." if failed else "OK: nada bloqueante.")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv:
        return scan(PACKAGE)
    source = Path(argv[0]).resolve()
    if source.is_dir():
        return scan(source)
    with tempfile.TemporaryDirectory(prefix="sigmai_scan_") as folder:
        with zipfile.ZipFile(source) as archive:
            archive.extractall(folder)
        return scan(Path(folder))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
