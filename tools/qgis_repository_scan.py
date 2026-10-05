#!/usr/bin/env python3
"""Roda no pacote as mesmas varreduras do repositório de plugins do QGIS.

Desde 2026 o plugins.qgis.org varre toda versão enviada com Bandit,
detect-secrets, Flake8 e uma análise de arquivos, e uma versão bloqueada não se
desbloqueia: é preciso enviar outra. Documentação:
https://plugins.qgis.org/docs/security-scanning

O critério que de fato bloqueia não é o da tabela de regras do site, e sim o do
código dele (``qgis-app/plugins/security_scanner.py`` e
``tasks/run_security_scan.py`` do QGIS-Plugins-Website): a verificação do
Bandit e a do detect-secrets têm gravidade crítica *inteiras* e só passam com
zero achados entre as regras ativas. A gravidade de cada regra só muda a
exibição. Flake8, permissões e arquivos suspeitos apenas informam e baixam a
"Pass Rate" mostrada na página da versão; este script reprova também esses,
para que a versão saia com 100%.

Por isso a 1.1.4 foi bloqueada com 159 achados de regras que a tabela chama de
"aviso" (try/except/pass, urlopen, random...), depois de este script — que
então só olhava as regras "críticas" — aprová-la. As regras de aviso podem ser
desligadas no formulário de envio; as que o SIGMAI desliga, e por quê, estão em
``UPLOAD_SKIPPED_RULES``. Tudo o mais tem de dar zero.

Uso::

    python tools/qgis_repository_scan.py              # varre sigmai/
    python tools/qgis_repository_scan.py dist/x.zip   # varre o ZIP enviado

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

#: Regras do Bandit ativas no site em 2026-10-04 (74): as 38 que não se pode
#: pular (https://plugins.qgis.org/docs/security-scanning/rules) e as 36 que o
#: formulário de envio deixa desligar. A lista do site é viva; se mudar,
#: acompanhe aqui.
BANDIT_MANDATORY = frozenset({
    "B102", "B103", "B105", "B106", "B107", "B111", "B201", "B202", "B301",
    "B302", "B304", "B305", "B306", "B307", "B312", "B321", "B323", "B401",
    "B402", "B412", "B413", "B501", "B502", "B503", "B505", "B506", "B507",
    "B601", "B602", "B604", "B605", "B609", "B610", "B611", "B612", "B613",
    "B615", "B701",
})
BANDIT_SKIPPABLE = frozenset({
    "B101", "B104", "B108", "B110", "B112", "B113", "B303", "B308", "B310",
    "B311", "B313", "B314", "B315", "B316", "B317", "B318", "B319", "B320",
    "B324", "B403", "B405", "B406", "B407", "B408", "B409", "B504", "B508",
    "B509", "B603", "B606", "B607", "B608", "B614", "B702", "B703", "B704",
})

#: Regras que o SIGMAI desliga no formulário de envio, com o motivo. Cada uma
#: tem de estar em BANDIT_SKIPPABLE; ao enviar, desligue exatamente estas.
UPLOAD_SKIPPED_RULES = {
    "B110": "try/except/pass: ~130 pontos de compatibilidade entre as APIs do QGIS 3.28 a 4.x, "
            "em que um recurso ausente na versão instalada deve ser ignorado, não derrubar o mapa",
    "B112": "try/except/continue: o mesmo, dentro de laços sobre camadas e itens de layout",
}

#: As 26 regras do Flake8 ativas no site em 2026-10-04 (6 "críticas" e 20 de
#: aviso), mais F63/F7, erros reais. No site o Flake8 só informa — não bloqueia
#: —, mas cada achado tira 20 pontos da "Pass Rate" da versão: a 1.1.6 saiu com
#: 80% por seis variáveis chamadas ``l`` (E741). Aqui reprova.
FLAKE8_RULES = (
    "E901,E902,E999,F821,F823,F831,"
    "C901,E101,E711,E712,E713,E714,E721,E722,E731,E741,E742,E743,"
    "F402,F403,F404,F405,F811,F822,F901,W605,F63,F7"
)

#: Extensões que a análise de arquivos do site aponta como suspeitas. No site
#: é aviso; aqui reprova, porque o pacote não deve levar nenhuma.
SUSPICIOUS_SUFFIXES = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".ps1", ".sh", ".vbs",
    ".msi", ".com", ".scr", ".jar", ".pyc", ".pyo",
})


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args], capture_output=True, text=True, encoding="utf-8",
        cwd=str(cwd) if cwd else None,
    )


def _require(module: str, package: str) -> None:
    probe = _run(module, "--version")
    if probe.returncode != 0:
        raise SystemExit(f"{package} não está instalado: pip install bandit detect-secrets flake8")


def bandit_findings(target: Path) -> list[str]:
    """Achados das regras ativas que o envio não desliga (como o site roda)."""
    _require("bandit", "bandit")
    tests = sorted((BANDIT_MANDATORY | BANDIT_SKIPPABLE) - set(UPLOAD_SKIPPED_RULES))
    result = _run("bandit", "-r", str(target), "-f", "json", "--quiet", "-t", ",".join(tests))
    report = json.loads(result.stdout or "{}")
    findings = []
    for item in report.get("results", []):
        path = Path(item["filename"]).relative_to(target)
        findings.append(f"{item['test_id']} {path}:{item['line_number']} {item['issue_text']}")
    for error in report.get("errors", []):
        findings.append(f"bandit não conseguiu ler {error.get('filename')}: {error.get('reason')}")
    return findings


def secret_findings(target: Path) -> list[str]:
    """Achados do detect-secrets, com os mesmos argumentos do site."""
    _require("detect_secrets", "detect-secrets")
    result = _run(
        "detect_secrets", "scan", "--all-files",
        "--exclude-files", r"metadata\.txt", "--exclude-files", r"\.secrets\.baseline", ".",
        cwd=target,
    )
    report = json.loads(result.stdout or "{}")
    return [
        f"{entry['type']} {Path(filename)}:{entry['line_number']}"
        for filename, entries in report.get("results", {}).items()
        for entry in entries
    ]


def flake8_findings(target: Path) -> list[str]:
    _require("flake8", "flake8")
    result = _run("flake8", f"--select={FLAKE8_RULES}", str(target))
    return [line for line in result.stdout.splitlines() if line.strip()]


def suspicious_files(target: Path) -> list[str]:
    return sorted(
        str(path.relative_to(target))
        for path in target.rglob("*")
        if path.is_file() and path.suffix.lower() in SUSPICIOUS_SUFFIXES
        and "__pycache__" not in path.parts  # o empacotador não leva o cache
    )


def scan(target: Path) -> int:
    invalid = sorted(set(UPLOAD_SKIPPED_RULES) - BANDIT_SKIPPABLE)
    if invalid:
        raise SystemExit(f"o site não deixa pular {', '.join(invalid)}: corrija o código em vez de pular")
    blocking = {
        "Bandit (regras ativas, menos as desligadas no envio)": bandit_findings(target),
        "detect-secrets": secret_findings(target),
        "Flake8 (regras ativas no site)": flake8_findings(target),
        "Arquivos suspeitos": suspicious_files(target),
    }
    failed = False
    for title, findings in blocking.items():
        print(f"{title}: {len(findings)}")
        for finding in findings:
            print(f"  {finding}")
        failed = failed or bool(findings)
    print("Ao enviar, desligue no formulário: " + ", ".join(sorted(UPLOAD_SKIPPED_RULES)))
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
