from __future__ import annotations

import fnmatch
import configparser
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "qgis_plugin"
OUTPUT_DIR = ROOT / "dist"
ZIP_PATH = OUTPUT_DIR / "sigmai.zip"
DIAGNOSTICS = ROOT / "diagnostics"
REPORT = DIAGNOSTICS / "qgis_plugin_zip_report.json"

PLUGIN_FOLDER_NAME = "sigmai"
EXCLUDES = {"__pycache__", "*.pyc", "*.pyo", "logs", "diagnostics", "test_outputs", ".git", "*.tmp"}
FORBIDDEN_RELEASE_TOKENS = [
    "C:" + "\\Users\\",
    "C:" + "/Users/",
    "T-" + "Gamer",
    "IA " + "Bridge",
    "Geo" + "Bridge",
    "geo" + "bridge",
    "GEO" + "BRIDGE",
    "Shapes pra " + "Teste",
    "external" + "_docs",
    "QGIS-3.44-" + "Documentation",
]


def excluded(path: Path) -> bool:
    if set(path.parts) & {"__pycache__", "logs", "diagnostics", "test_outputs", ".git"}:
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDES)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def release_findings(files: list[str], zip_path: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            lowered = name.lower()
            if any(part in lowered for part in ["/logs/", "/diagnostics/", "/test_outputs/", "__pycache__"]):
                findings.append({"file": name, "token": "packaging_excluded_path"})
                continue
            if not name.lower().endswith((".py", ".txt", ".md", ".json", ".yml", ".yaml", ".html", ".css", ".svg")):
                continue
            try:
                text = archive.read(name).decode("utf-8", errors="ignore")
            except Exception:
                continue
            for token in FORBIDDEN_RELEASE_TOKENS:
                if token in text:
                    findings.append({"file": name, "token": token})
    for file in files:
        if file.startswith(f"{PLUGIN_FOLDER_NAME}/logs/") or file.startswith(f"{PLUGIN_FOLDER_NAME}/diagnostics/") or file.startswith(f"{PLUGIN_FOLDER_NAME}/test_outputs/"):
            findings.append({"file": file, "token": "runtime_artifact"})
    metadata_text = (SOURCE / "metadata.txt").read_text(encoding="utf-8", errors="ignore")
    parser = configparser.ConfigParser()
    parser.read_string(metadata_text)
    if parser.get("general", "experimental", fallback="").strip().lower() == "true":
        findings.append({"file": f"{PLUGIN_FOLDER_NAME}/metadata.txt", "token": "experimental=True"})
    return findings


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path in SOURCE.rglob("*"):
            relative = source_path.relative_to(SOURCE)
            if excluded(relative) or source_path.is_dir():
                continue
            arcname = Path(PLUGIN_FOLDER_NAME) / relative
            archive.write(source_path, arcname.as_posix())
            written.append(arcname.as_posix())

    required = [
        f"{PLUGIN_FOLDER_NAME}/metadata.txt",
        f"{PLUGIN_FOLDER_NAME}/__init__.py",
        f"{PLUGIN_FOLDER_NAME}/plugin.py",
        f"{PLUGIN_FOLDER_NAME}/bridge_server.py",
    ]
    missing = [item for item in required if item not in written]
    findings = release_findings(written, ZIP_PATH)
    report = {
        "generated_at": now(),
        "zip_path": str(ZIP_PATH),
        "plugin_folder_name": PLUGIN_FOLDER_NAME,
        "ok": not missing and not findings,
        "missing_required": missing,
        "release_findings": findings,
        "file_count": len(written),
        "files": written,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"QGIS plugin ZIP: {ZIP_PATH}")
    if missing:
        print(f"Missing required files: {missing}")
        return 1
    if findings:
        print(f"Release audit failed: {findings}")
        return 1
    print("Install this ZIP in QGIS with Plugins > Manage and Install Plugins > Install from ZIP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
