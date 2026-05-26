from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "test_outputs" / "sigmai_trusted_plugin_map_test"
REPORT_JSON = OUTPUT_DIR / "SIGMAI_TRUSTED_PLUGIN_MAP_TEST.json"
REPORT_MD = OUTPUT_DIR / "SIGMAI_TRUSTED_PLUGIN_MAP_TEST.md"

TRUSTED_PLUGIN_CANDIDATES = [
    {
        "name": "QuickMapServices",
        "package": "quick_map_services",
        "query": "QuickMapServices",
        "reason": "Popular basemap plugin; useful for map context layers.",
        "expected_use": "Inspect installed plugin and, when available, use basemap/XYZ context through SIGMAI data-source commands.",
    },
    {
        "name": "QuickOSM",
        "package": "QuickOSM",
        "query": "QuickOSM",
        "reason": "Widely used OSM data retrieval plugin; useful for contextual roads/trails/POIs.",
        "expected_use": "Inspect and classify as plugin/provider integration candidate before any network data request.",
    },
    {
        "name": "qgis2web",
        "package": "qgis2web",
        "query": "qgis2web",
        "reason": "Well-known map publication/export plugin; useful for future publication workflows.",
        "expected_use": "Inspect only unless a safe adapter is explicitly created.",
    },
]
DEFAULT_QGIS_REPOSITORY_VERSION = "3.40"


def _run(args: list[str], timeout: int = 180) -> dict[str, Any]:
    cmd = [sys.executable, str(ROOT / "tools" / "sigmai.py"), *args]
    started = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        stdout = proc.stdout.strip()
        parsed: Any = None
        if stdout:
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                parsed = stdout
        return {
            "command": " ".join(args),
            "started_at": started,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0 and (not isinstance(parsed, dict) or parsed.get("ok", True)),
            "stdout": parsed,
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {
            "command": " ".join(args),
            "started_at": started,
            "returncode": -1,
            "ok": False,
            "stdout": None,
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def _extract_error(result: dict[str, Any]) -> str:
    stdout = result.get("stdout")
    if isinstance(stdout, dict):
        errors = stdout.get("errors") or []
        if errors:
            first = errors[0]
            return f"{first.get('code', 'ERROR')}: {first.get('message', '')}"
    return result.get("stderr") or "unknown"


def _write_reports(report: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# SIGMAI Trusted Plugin Map Test",
        "",
        f"Generated at: {report['generated_at']}",
        f"Overall status: {report['summary']['status']}",
        f"Bridge available: {report['summary']['bridge_available']}",
        f"Commands attempted: {report['summary']['commands_attempted']}",
        f"Commands OK: {report['summary']['commands_ok']}",
        "",
        "## Key Findings",
        "",
    ]
    for finding in report["summary"].get("findings", []):
        lines.append(f"- {finding}")
    lines.extend(["", "## Plugin Candidates", ""])
    for item in report["plugins"]:
        lines.append(f"### {item['name']}")
        lines.append(f"- Reason: {item['reason']}")
        lines.append(f"- Repository search: {item.get('repository_status', 'not_run')}")
        lines.append(f"- Installed inspection: {item.get('installed_status', 'not_run')}")
        if item.get("notes"):
            lines.append(f"- Notes: {'; '.join(item['notes'])}")
        lines.append("")
    lines.extend(["## Command Results", ""])
    for result in report["command_results"]:
        status = "OK" if result["ok"] else "FAIL"
        lines.append(f"- `{result['command']}`: {status}")
        if not result["ok"]:
            lines.append(f"  - {_extract_error(result)}")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_name": "SIGMAI trusted plugin download/use/map test",
        "plugins": [],
        "command_results": [],
        "summary": {
            "status": "started",
            "bridge_available": False,
            "commands_attempted": 0,
            "commands_ok": 0,
            "findings": [],
        },
    }

    def run(args: list[str], timeout: int = 180) -> dict[str, Any]:
        result = _run(args, timeout=timeout)
        report["command_results"].append(result)
        return result

    status = run(["status"], timeout=30)
    if not status["ok"]:
        report["summary"].update(
            {
                "status": "blocked_bridge_offline",
                "bridge_available": False,
                "commands_attempted": len(report["command_results"]),
                "commands_ok": sum(1 for item in report["command_results"] if item["ok"]),
            }
        )
        report["summary"]["findings"].append(
            "SIGMAI Bridge is offline or refusing connections; plugin download/use tests cannot run through SIGMAI yet."
        )
        _write_reports(report)
        return 1

    report["summary"]["bridge_available"] = True
    capabilities = run(["capabilities"], timeout=60)
    if not capabilities["ok"]:
        report["summary"]["findings"].append("Capabilities failed; continuing with conservative probes.")

    inventory = run(["plugins-extended"], timeout=120)

    for candidate in TRUSTED_PLUGIN_CANDIDATES:
        item = {**candidate, "repository_status": "not_run", "installed_status": "not_run", "notes": []}
        search = run(
            [
                "plugin-repo-search",
                candidate["query"],
                "--qgis-version",
                DEFAULT_QGIS_REPOSITORY_VERSION,
                "--confirm-network",
                "--limit",
                "5",
            ],
            timeout=120,
        )
        item["repository_status"] = "ok" if search["ok"] else "failed"
        if not search["ok"]:
            item["notes"].append(f"Repository search failed: {_extract_error(search)}")

        inspect = run(["inspect-plugin", candidate.get("package") or candidate["name"]], timeout=60)
        item["installed_status"] = "ok" if inspect["ok"] else "not_installed_or_unavailable"
        if not inspect["ok"]:
            item["notes"].append(f"Installed inspection failed: {_extract_error(inspect)}")

        install_dry_run = run(
            [
                "install-plugin-repository",
                candidate["name"],
                "--qgis-version",
                DEFAULT_QGIS_REPOSITORY_VERSION,
                "--confirm-network",
                "--dry-run",
            ],
            timeout=180,
        )
        item["install_dry_run_status"] = "ok" if install_dry_run["ok"] else "failed"
        if not install_dry_run["ok"]:
            item["notes"].append(f"Repository install dry-run failed: {_extract_error(install_dry_run)}")
        report["plugins"].append(item)

    # Use existing safe QGIS capabilities to create a map only after plugin probes complete.
    layers = run(["layers"], timeout=60)
    if layers["ok"] and isinstance(layers.get("stdout"), dict):
        layer_items = ((layers["stdout"].get("data") or {}).get("layers") or [])
        first_vector = next((layer for layer in layer_items if layer.get("type") == "vector"), None)
        if first_vector:
            output = OUTPUT_DIR / "SIGMAI_TRUSTED_PLUGIN_CONTEXT_MAP.png"
            map_result = run(
                [
                    "professional-map",
                    "--layer-id",
                    first_vector["id"],
                    "--title",
                    "SIGMAI plugin orchestration context map",
                    "--output",
                    str(output),
                    "--format",
                    "png",
                    "--layout-template",
                    "scientific_publication",
                    "--style-profile",
                    "scientific_soft",
                    "--map-author",
                    "Luan da Silva Cortes Maciel",
                    "--data-source",
                    "QGIS project layers and trusted plugin orchestration test",
                    "--confirm-overwrite",
                ],
                timeout=240,
            )
            report["summary"]["findings"].append(
                "Professional map generation after plugin probes: " + ("OK" if map_result["ok"] else _extract_error(map_result))
            )
        else:
            report["summary"]["findings"].append("No vector layer available for professional map generation.")
    else:
        report["summary"]["findings"].append("Layer inventory unavailable; skipped map generation.")

    report["summary"].update(
        {
            "status": "completed",
            "commands_attempted": len(report["command_results"]),
            "commands_ok": sum(1 for item in report["command_results"] if item["ok"]),
        }
    )
    _write_reports(report)
    return 0 if report["summary"]["commands_ok"] == report["summary"]["commands_attempted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
