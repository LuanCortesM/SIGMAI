from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "test_outputs" / "sigmai_generic_plugin_engine_regression"


def _try_init_qgis() -> tuple[bool, str]:
    try:
        from qgis.core import QgsApplication  # type: ignore

        QgsApplication.setPrefixPath(r"C:/PROGRA~1/QGIS34~1.7/apps/qgis-ltr", True)
        app = QgsApplication([], False)
        app.initQgis()
        try:
            import processing  # noqa: F401  # type: ignore
            from processing.core.Processing import Processing  # type: ignore

            Processing.initialize()
        except Exception as exc:
            return True, f"QGIS initialized; Processing Python plugin unavailable: {type(exc).__name__}: {exc}"
        return True, "QGIS and Processing initialized."
    except Exception as exc:
        return False, f"QGIS unavailable: {type(exc).__name__}: {exc}"


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# SIGMAI Generic Plugin Engine Regression",
        "",
        f"Generated at: `{payload['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Plugins inspected: `{summary['plugins_inspected']}`",
        f"- Processing algorithms discovered: `{summary['processing_algorithms_discovered']}`",
        f"- Generic dry-run plans tested: `{summary['generic_dry_run_plans_tested']}`",
        f"- Acceptance: 10 plugins inspected: `{summary['acceptance_minimum_10_plugins']}`",
        f"- Acceptance: no static inspection failures: `{summary['acceptance_no_static_failures']}`",
        "",
        "## Plugins",
        "",
        "| Plugin | Version | Static risk | Algorithms | Inspectable |",
        "|---|---:|---|---:|---|",
    ]
    for item in payload["plugins"]:
        lines.append(
            f"| {item.get('plugin_name')} | {item.get('version', '')} | "
            f"{item.get('static_risk', {}).get('risk_level', 'unknown')} | "
            f"{item.get('algorithm_count', 0)} | {item.get('inspectable')} |"
        )
    lines.extend(["", "## Failures", ""])
    if payload["failures"]:
        for failure in payload["failures"]:
            lines.append(f"- `{failure.get('plugin_name', failure.get('algorithm_id', 'unknown'))}`: {failure.get('reason')}")
    else:
        lines.append("No static inspection failures.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    qgis_ok, qgis_note = _try_init_qgis()
    from qgis_plugin.qgis_actions.plugin_tools import build_plugin_capability_manifest, dry_run_plugin_algorithm_generic

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = build_plugin_capability_manifest({"include_inactive": True, "max_algorithms": 50}, {"dry_run": True})
    plugins = manifest.get("plugins", [])
    failures: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []

    for plugin in plugins:
        if "error" in plugin:
            failures.append({"plugin_name": plugin.get("plugin_name"), "reason": plugin.get("error")})
        plugin["inspectable"] = "error" not in plugin and bool(plugin.get("safe_usage_policy", {}).get("inspectable", True))
        for algorithm in plugin.get("algorithms", [])[:5]:
            algorithm_id = algorithm.get("id")
            if not algorithm_id or not algorithm.get("found"):
                continue
            try:
                plan = dry_run_plugin_algorithm_generic({"algorithm_id": algorithm_id, "parameters": {}}, {"dry_run": True})
                plans.append(
                    {
                        "algorithm_id": algorithm_id,
                        "missing_required_parameters": plan.get("missing_required_parameters", []),
                        "execution_policy": plan.get("execution_policy", {}),
                    }
                )
            except Exception as exc:
                failures.append({"algorithm_id": algorithm_id, "reason": f"{type(exc).__name__}: {exc}"})

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "qgis_initialized": qgis_ok,
        "qgis_note": qgis_note,
        "summary": {
            "plugins_inspected": len(plugins),
            "processing_algorithms_discovered": manifest.get("algorithm_count", 0),
            "generic_dry_run_plans_tested": len(plans),
            "failures": len(failures),
            "acceptance_minimum_10_plugins": len(plugins) >= 10,
            "acceptance_no_static_failures": not failures,
            "functional_verdict": "PASS" if len(plugins) >= 10 and not failures else "NOT_YET_FUNCTIONAL",
        },
        "plugins": plugins,
        "generic_algorithm_plans": plans,
        "failures": failures,
        "recommendations": [
            "Install or enable at least 10 trusted QGIS plugins before declaring the generic plugin engine fully functional.",
            "Prefer Processing providers for generic execution; UI-only plugins should remain inspect-only until a dedicated adapter is generated.",
            "Keep network, credential and data-mutation plugins behind explicit confirmations and risk review.",
        ],
    }
    json_path = OUT_DIR / "SIGMAI_GENERIC_PLUGIN_ENGINE_REGRESSION.json"
    md_path = OUT_DIR / "SIGMAI_GENERIC_PLUGIN_ENGINE_REGRESSION.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    _write_markdown(md_path, payload)
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    return 0 if payload["summary"]["acceptance_no_static_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
