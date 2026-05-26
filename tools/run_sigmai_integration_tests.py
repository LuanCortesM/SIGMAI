from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_discovery import resolve_connection


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "diagnostics"
JSON_REPORT = DIAGNOSTICS / "integration_test_results.json"
MD_REPORT = DIAGNOSTICS / "integration_test_results.md"
SHAPES_ROOT = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", ROOT.parent / ("Shapes pra " + "Teste")))

PASSED = "PASSED"
FAILED = "FAILED"
SKIPPED_NOT_IMPLEMENTED = "SKIPPED_NOT_IMPLEMENTED"
SKIPPED_NO_DATA = "SKIPPED_NO_DATA"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class BridgeClient:
    def __init__(self, host: str, port: int, token: str):
        self.host = host
        self.port = port
        self.token = token

    def command(self, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> tuple[int, dict[str, Any]]:
        payload = {
            "schema_version": "0.2",
            "request_id": f"itest-{int(time.time() * 1000)}",
            "action": action,
            "params": params or {},
            "dry_run": dry_run,
        }
        request = urllib.request.Request(
            f"http://{self.host}:{self.port}/command",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, {"ok": False, "errors": [{"code": "HTTP_ERROR", "message": body, "details": {}}]}
        except Exception as exc:
            return 0, {"ok": False, "errors": [{"code": type(exc).__name__, "message": str(exc), "details": {}}]}


def classify_response(action: str, status_code: int, response: dict[str, Any], optional: bool = False) -> str:
    if response.get("ok"):
        return PASSED
    codes = [error.get("code") for error in response.get("errors", [])]
    if "ACTION_NOT_ALLOWED" in codes and optional:
        return SKIPPED_NOT_IMPLEMENTED
    return FAILED


def run_case(client: BridgeClient, action: str, params: dict[str, Any] | None = None, dry_run: bool = False, optional: bool = False) -> dict[str, Any]:
    status_code, response = client.command(action, params=params, dry_run=dry_run)
    return {
        "name": action + (" dry_run" if dry_run else ""),
        "action": action,
        "status": classify_response(action, status_code, response, optional=optional),
        "http_status": status_code,
        "response": response,
    }


def find_shape_paths() -> list[Path]:
    if not SHAPES_ROOT.exists():
        return []
    return sorted(SHAPES_ROOT.rglob("*.shp"))


def run_tests(client: BridgeClient) -> dict[str, Any]:
    results = []
    capabilities_result = run_case(client, "get_capabilities")
    results.extend(
        [
            run_case(client, "status"),
            capabilities_result,
            run_case(client, "get_qgis_environment"),
            run_case(client, "get_bridge_config"),
            run_case(client, "get_recent_errors"),
            run_case(client, "diagnose_crs"),
            run_case(client, "list_layers"),
            run_case(client, "get_project_info"),
            run_case(client, "list_layouts"),
            run_case(client, "list_installed_plugins"),
            run_case(client, "inspect_plugin", {"plugin_name": "sigmai"}),
            run_case(client, "validate_metadata_txt", {"plugin_name": "sigmai"}),
            run_case(client, "collect_plugin_logs", {"plugin_name": "sigmai"}),
            run_case(client, "get_logs"),
        ]
    )

    implemented = set()
    if capabilities_result["response"].get("ok"):
        for actions in capabilities_result["response"].get("data", {}).get("groups", {}).values():
            implemented.update(actions)

    loaded_layer_ids = []
    shapes = find_shape_paths()
    if not shapes:
        results.append({"name": "load test shapes", "action": "load_vector_layer", "status": SKIPPED_NO_DATA, "response": {}})
    else:
        for shape in shapes:
            if "load_vector_layer" not in implemented:
                results.append({"name": f"load_vector_layer {shape.name}", "action": "load_vector_layer", "status": SKIPPED_NOT_IMPLEMENTED, "response": {}})
                continue
            result = run_case(client, "load_vector_layer", {"path": str(shape), "name": shape.stem, "provider": "ogr"})
            results.append(result)
            layer_id = result["response"].get("data", {}).get("layer_id")
            if result["status"] == PASSED and layer_id:
                loaded_layer_ids.append(layer_id)

    results.append(run_case(client, "list_layers"))
    for layer_id in loaded_layer_ids:
        results.append(run_case(client, "get_layer_info", {"layer_id": layer_id}))
        results.append(run_case(client, "validate_geometries", {"layer_id": layer_id, "max_features": 5000}))
        results.append(run_case(client, "fix_geometries", {"layer_id": layer_id, "output": "TEMPORARY_OUTPUT"}, dry_run=True))
        results.append(run_case(client, "buffer", {"layer_id": layer_id, "distance": 50, "segments": 8, "output": "TEMPORARY_OUTPUT"}, dry_run=True))
        results.append(run_case(client, "dissolve", {"layer_id": layer_id, "fields": [], "output": "TEMPORARY_OUTPUT"}, dry_run=True))
        results.append(run_case(client, "reproject_layer", {"layer_id": layer_id, "target_crs": "EPSG:31983", "output": "TEMPORARY_OUTPUT"}, dry_run=True))
        results.append(run_case(client, "export_layer", {"layer_id": layer_id, "output_path": str(ROOT / "test_outputs" / f"export_{layer_id}.gpkg"), "format": "GPKG"}, dry_run=True))
    if len(loaded_layer_ids) >= 2:
        results.append(run_case(client, "clip", {"input_layer_id": loaded_layer_ids[0], "overlay_layer_id": loaded_layer_ids[1], "output": "TEMPORARY_OUTPUT"}, dry_run=True))

    plugin_diagnostics = [
        ("check_plugin_structure", {"plugin_name": "sigmai"}, False),
        ("check_plugin_imports", {"plugin_name": "sigmai"}, False),
        ("check_plugin_resources", {"plugin_name": "sigmai"}, False),
        ("check_plugin_icon", {"plugin_name": "sigmai"}, False),
        ("check_plugin_runtime_status", {"plugin_name": "sigmai"}, False),
        ("generate_plugin_report", {"plugin_name": "sigmai", "output_path": str(ROOT / "test_outputs" / "plugin_report_sigmai.md")}, True),
        ("package_plugin_zip", {"plugin_name": "sigmai", "output_path": str(ROOT / "test_outputs" / "sigmai_package.zip")}, True),
        ("self_inspect", {}, False),
        ("self_health_check", {}, False),
        ("self_backup", {}, True),
    ]
    for action, params, dry_run in plugin_diagnostics:
        if action in implemented:
            results.append(run_case(client, action, params, dry_run=dry_run))
        else:
            results.append({"name": action, "action": action, "status": SKIPPED_NOT_IMPLEMENTED, "response": {}})

    for action in ["generate_basic_map", "generate_workflow_report"]:
        if action in implemented:
            params = {}
            dry_run = action in {"buffer", "clip", "generate_basic_map"}
            results.append(run_case(client, action, params, dry_run=dry_run))
        else:
            results.append({"name": action, "action": action, "status": SKIPPED_NOT_IMPLEMENTED, "response": {}})

    results.append(run_case(client, "create_layout", {"layout_name": f"SIGMAI_DryRun_{int(time.time())}"}, dry_run=True))
    results.append(run_case(client, "export_layout", {"layout_name": "SIGMAI_DryRun_Missing", "format": "pdf", "path": str(ROOT / "test_outputs" / f"dryrun_{int(time.time())}.pdf")}, dry_run=True))

    summary = {
        PASSED: sum(1 for item in results if item["status"] == PASSED),
        FAILED: sum(1 for item in results if item["status"] == FAILED),
        SKIPPED_NOT_IMPLEMENTED: sum(1 for item in results if item["status"] == SKIPPED_NOT_IMPLEMENTED),
        SKIPPED_NO_DATA: sum(1 for item in results if item["status"] == SKIPPED_NO_DATA),
    }
    return {"generated_at": now(), "shapes_root": str(SHAPES_ROOT), "results": results, "summary": summary}


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# SIGMAI Integration Test Results",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Shapes root: `{report['shapes_root']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Results", "", "| Test | Status | Error |", "|---|---|---|"])
    for item in report["results"]:
        errors = item.get("response", {}).get("errors", [])
        error_text = "; ".join(f"{err.get('code')}: {err.get('message')}" for err in errors)
        lines.append(f"| `{item['name']}` | `{item['status']}` | {error_text} |")
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--pairing-code", default=None)
    parser.add_argument("--session-file", default=None)
    args = parser.parse_args()
    connection = resolve_connection(args.host, args.port, args.token, args.pairing_code, args.session_file)
    if connection.get("session_path"):
        print(f"Using session file: {connection['session_path']}")
    if not connection["token"]:
        print("Missing token. Use --token, SIGMAI_TOKEN, SIGMAI_SESSION_FILE, or enable QGIS session file writing.")
        return 2
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    report = run_tests(BridgeClient(connection["host"], connection["port"], connection["token"]))
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report)
    print(f"Integration tests written to {JSON_REPORT}")
    return 1 if report["summary"].get(FAILED, 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
