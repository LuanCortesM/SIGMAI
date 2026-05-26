from __future__ import annotations

import json
import subprocess
import sys
import zipfile
import configparser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DIAGNOSTICS = ROOT / "diagnostics"
ZIP_PATH = DIST / "sigmai.zip"
REPORT_JSON = DIAGNOSTICS / "SIGMAI_PUBLIC_RELEASE_AUDIT.json"
REPORT_MD = DIAGNOSTICS / "SIGMAI_PUBLIC_RELEASE_AUDIT.md"

PUBLIC_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "PUBLIC_RELEASE_CHECKLIST.md",
    ROOT / "docs" / "SECURITY_MODEL.md",
    ROOT / "docs" / "MAP_AUTHORSHIP_POLICY.md",
]

FORBIDDEN_REPO_TOKENS = [
    "C:" + "\\Users\\",
    "C:" + "/Users/",
    "T-" + "Gamer",
    "IA " + "Bridge",
    "Geo" + "Bridge",
    "geo" + "bridge",
    "GEO" + "BRIDGE",
    "QGIS 3." + "40.7",
    "Program Files" + "\\QGIS",
    "Shapes pra " + "Teste",
    "external" + "_docs",
    "QGIS-3.44-" + "Documentation",
]

FORBIDDEN_ZIP_PARTS = {
    "__pycache__",
    "logs",
    "diagnostics",
    "test_outputs",
    "external" + "_docs",
    ".git",
    ".pytest_cache",
}

REPOSITORY_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "external" + "_docs",
    "test_outputs",
    "diagnostics",
    "dist",
    "archive",
    "local_archive",
}

REPOSITORY_EXCLUDE_FILES = {
    "obsolete_sigmai_legacy_package.zip",
    "sigmai.zip",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_step(name: str, args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(args, cwd=str(ROOT), text=True, capture_output=True)
    return {
        "name": name,
        "command": args,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def scan_text_file(path: Path, tokens: list[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not path.exists():
        return [{"file": str(path.relative_to(ROOT)), "token": "missing_required_public_file"}]
    text = path.read_text(encoding="utf-8", errors="ignore")
    for token in tokens:
        if token in text:
            findings.append({"file": str(path.relative_to(ROOT)), "token": token})
    return findings


def scan_zip(zip_path: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    files: list[str] = []
    if not zip_path.exists():
        return {"ok": False, "files": [], "findings": [{"file": str(zip_path), "token": "zip_missing"}]}
    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            files.append(name)
            parts = set(Path(name).parts)
            bad_parts = parts & FORBIDDEN_ZIP_PARTS
            for part in sorted(bad_parts):
                findings.append({"file": name, "token": f"forbidden_zip_part:{part}"})
            if not name.lower().endswith((".py", ".txt", ".md", ".json", ".yml", ".yaml", ".html", ".css", ".svg")):
                continue
            text = archive.read(name).decode("utf-8", errors="ignore")
            for token in FORBIDDEN_REPO_TOKENS:
                if token in text:
                    findings.append({"file": name, "token": token})
    required = {"sigmai/metadata.txt", "sigmai/__init__.py", "sigmai/plugin.py", "sigmai/bridge_server.py"}
    missing = sorted(required - set(files))
    for item in missing:
        findings.append({"file": item, "token": "missing_required_zip_file"})
    try:
        metadata = archive_text(zip_path, "sigmai/metadata.txt")
        parser = configparser.ConfigParser()
        parser.read_string(metadata)
        if parser.get("general", "experimental", fallback="").strip().lower() == "true":
            findings.append({"file": "sigmai/metadata.txt", "token": "experimental=True"})
    except Exception:
        findings.append({"file": "sigmai/metadata.txt", "token": "metadata_unreadable"})
    return {"ok": not findings, "files": files, "file_count": len(files), "findings": findings}


def archive_text(zip_path: Path, name: str) -> str:
    with zipfile.ZipFile(zip_path, "r") as archive:
        return archive.read(name).decode("utf-8", errors="ignore")


def scan_public_repository() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        parts = set(rel.parts)
        if parts & REPOSITORY_EXCLUDE_DIRS:
            continue
        if path.name in REPOSITORY_EXCLUDE_FILES:
            findings.append({"file": str(rel), "token": "forbidden_release_artifact"})
            continue
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".py", ".txt", ".md", ".json", ".yml", ".yaml", ".toml", ".html", ".css", ".svg"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN_REPO_TOKENS:
            if token in text:
                findings.append({"file": str(rel), "token": token})
        if path.name == "metadata.txt" and rel.parts[:1] == ("sigmai",):
            parser = configparser.ConfigParser()
            parser.read_string(text)
            if parser.get("general", "experimental", fallback="").strip().lower() == "true":
                findings.append({"file": str(rel), "token": "experimental=True"})
    return findings


def write_reports(report: dict[str, Any]) -> None:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# SIGMAI Public Release Audit",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Overall OK: `{report['ok']}`",
        f"ZIP: `{report['zip_path']}`",
        "",
        "## Steps",
        "",
    ]
    for step in report["steps"]:
        lines.append(f"- `{step['name']}`: `{'OK' if step['ok'] else 'FAILED'}`")
    lines.extend(["", "## Findings", ""])
    findings = report["public_doc_findings"] + report["zip_audit"]["findings"]
    findings += report.get("repository_findings", [])
    if findings:
        lines.extend([f"- `{item['file']}`: `{item['token']}`" for item in findings])
    else:
        lines.append("- None")
    lines.extend(["", "## Release Decision", "", report["release_decision"]])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    steps = [
        run_step("compileall", [sys.executable, "-m", "compileall", "-q", "sigmai", "codex_plugin", "tools", "mcp_server", "tests"]),
        run_step("unit_tests", [sys.executable, "-m", "unittest", "discover", "tests"]),
        run_step("package_plugin_zip", [sys.executable, "tools/package_qgis_plugin_zip.py"]),
    ]
    public_doc_findings: list[dict[str, str]] = []
    for path in PUBLIC_DOCS:
        public_doc_findings.extend(scan_text_file(path, FORBIDDEN_REPO_TOKENS))
    zip_audit = scan_zip(ZIP_PATH)
    repository_findings = scan_public_repository()
    ok = all(step["ok"] for step in steps) and not public_doc_findings and zip_audit["ok"] and not repository_findings
    report = {
        "schema_version": "1.0",
        "generated_at": now(),
        "ok": ok,
        "zip_path": str(ZIP_PATH),
        "steps": steps,
        "public_docs": [str(path.relative_to(ROOT)) for path in PUBLIC_DOCS],
        "public_doc_findings": public_doc_findings,
        "repository_findings": repository_findings,
        "zip_audit": zip_audit,
        "release_decision": "PUBLIC_RELEASE_READY" if ok else "PUBLIC_RELEASE_BLOCKED",
    }
    write_reports(report)
    print(json.dumps({"ok": ok, "report": str(REPORT_JSON), "zip": str(ZIP_PATH), "decision": report["release_decision"]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
