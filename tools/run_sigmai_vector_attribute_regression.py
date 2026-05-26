from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_plugin.client.sigmai_client import SigmaiClient, SigmaiClientError


OUT_DIR = ROOT / "test_outputs" / "sigmai_vector_attribute_regression"
TEST_DATA_ROOT = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", ROOT.parent / ("Shapes pra " + "Teste")))
TEST_SHAPE_CANDIDATES = [
    TEST_DATA_ROOT / "Municipios" / "SP_Municipios_2025.shp",
    TEST_DATA_ROOT / "Estados" / "BR_UF_2025.shp",
    TEST_DATA_ROOT / "Pais" / "BR_Pais_2025.shp",
    ROOT / ("Shapes pra " + "Teste") / "Municipios" / "SP_Municipios_2025.shp",
]


def command(client: SigmaiClient, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    return client.command(
        {
            "schema_version": "0.3",
            "request_id": f"vector-regression-{action}",
            "action": action,
            "params": params or {},
            "dry_run": dry_run,
        }
    )


def pick_vector_layer(layers: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred = [
        "SP_Municipios_2025",
        "Cruzeiro limite municipal",
        "TopoTrail potencial clip Cruzeiro",
        "BR_UF_2025",
        "BR_Pais_2025",
    ]
    for name in preferred:
        for layer in layers:
            if layer.get("name") == name or name in str(layer.get("name", "")):
                return layer
    for layer in layers:
        if str(layer.get("type", "")).lower() == "vector":
            return layer
    return None


def find_test_shape() -> Path | None:
    for path in TEST_SHAPE_CANDIDATES:
        if path.exists():
            return path
    return None


def first_field(fields: list[dict[str, Any]]) -> str | None:
    for field in fields:
        name = field.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def record(records: list[dict[str, Any]], name: str, response: dict[str, Any], required: bool = True) -> None:
    ok = bool(response.get("ok"))
    records.append(
        {
            "test": name,
            "ok": ok,
            "required": required,
            "status": "PASS" if ok else ("FAIL" if required else "WARN"),
            "errors": response.get("errors", []),
            "warnings": response.get("warnings", []),
        }
    )


def write_reports(summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "SIGMAI_VECTOR_ATTRIBUTE_REGRESSION.json"
    md_path = out_dir / "SIGMAI_VECTOR_ATTRIBUTE_REGRESSION.md"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# SIGMAI Vector, Attribute and Expression Regression",
        "",
        f"- Run time: `{summary['run_time']}`",
        f"- Bridge status: `{summary['bridge_status']}`",
        f"- Layer: `{summary.get('layer_name', '')}`",
        f"- Field used: `{summary.get('field_name', '')}`",
        f"- Passed: `{summary['passed']}/{summary['total']}`",
        f"- Required failures: `{summary['required_failures']}`",
        "",
        "## Results",
        "",
        "| Test | Status | Required | Notes |",
        "|---|---:|---:|---|",
    ]
    for item in summary["records"]:
        notes = []
        if item.get("warnings"):
            notes.append("warnings")
        if item.get("errors"):
            notes.append("errors")
        lines.append(f"| `{item['test']}` | {item['status']} | {item['required']} | {', '.join(notes)} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This regression checks that SIGMAI can inspect layer tree state, read bounded attribute data, validate QGIS expressions, query features, perform dry-run selections/extractions and generate a map with a filtered legend.",
            "",
            "If commands return UNKNOWN_COMMAND, restart QGIS or disable/enable the SIGMAI plugin so the newly installed files are loaded in memory.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["report_md"] = str(md_path)
    summary["report_json"] = str(json_path)


def run(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    client = SigmaiClient(timeout=180)
    records: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "run_time": datetime.now(timezone.utc).isoformat(),
        "bridge_status": "UNKNOWN",
        "records": records,
    }
    status = command(client, "status")
    summary["bridge_status"] = "OK" if status.get("ok") else "FAILED"
    record(records, "status", status)

    capabilities = command(client, "get_capabilities")
    record(records, "get_capabilities", capabilities)

    layers_resp = command(client, "list_layers")
    record(records, "list_layers", layers_resp)
    layers = layers_resp.get("data", {}).get("layers", []) if isinstance(layers_resp.get("data"), dict) else []
    layer = pick_vector_layer(layers)
    if not layer:
        shape = find_test_shape()
        if shape:
            load_resp = command(client, "load_vector_layer", {"path": str(shape), "name": shape.stem})
            record(records, "load_test_vector_layer", load_resp)
            layers_resp = command(client, "list_layers")
            record(records, "list_layers_after_load", layers_resp)
            layers = layers_resp.get("data", {}).get("layers", []) if isinstance(layers_resp.get("data"), dict) else []
            layer = pick_vector_layer(layers)
    if not layer:
        records.append({"test": "pick_vector_layer", "ok": False, "required": True, "status": "FAIL", "errors": [{"message": "No vector layer available."}], "warnings": []})
        summary.update({"total": len(records), "passed": sum(1 for r in records if r["ok"]), "required_failures": 1})
        write_reports(summary, out_dir)
        return summary

    layer_id = str(layer["id"])
    summary["layer_id"] = layer_id
    summary["layer_name"] = layer.get("name", "")

    record(records, "list_layer_tree", command(client, "list_layer_tree"))
    record(records, "set_layer_visibility_dry_run", command(client, "set_layer_visibility", {"layer_id": layer_id, "visible": True}, dry_run=True))
    record(records, "move_layer_order_dry_run", command(client, "move_layer_order", {"layer_id": layer_id, "index": 0}, dry_run=True))

    fields_resp = command(client, "list_fields", {"layer_id": layer_id})
    record(records, "list_fields", fields_resp)
    fields = fields_resp.get("data", {}).get("fields", []) if isinstance(fields_resp.get("data"), dict) else []
    field_name = first_field(fields)
    summary["field_name"] = field_name or ""

    record(records, "sample_features", command(client, "sample_features", {"layer_id": layer_id, "max_features": 5}))
    record(records, "inspect_attribute_table", command(client, "inspect_attribute_table", {"layer_id": layer_id, "max_features": 5}))
    if field_name:
        record(records, "field_statistics", command(client, "field_statistics", {"layer_id": layer_id, "field_name": field_name}))
        record(records, "unique_values", command(client, "unique_values", {"layer_id": layer_id, "field_name": field_name, "limit": 10}))
    else:
        records.append({"test": "field_dependent_tests", "ok": False, "required": True, "status": "FAIL", "errors": [{"message": "No field found."}], "warnings": []})

    expression = "1=1"
    record(records, "validate_expression", command(client, "validate_expression", {"layer_id": layer_id, "expression": expression}))
    record(records, "evaluate_expression", command(client, "evaluate_expression", {"layer_id": layer_id, "expression": expression, "max_features": 5}))
    record(records, "query_features", command(client, "query_features", {"layer_id": layer_id, "expression": expression, "max_features": 5}))
    record(records, "select_by_expression_dry_run", command(client, "select_by_expression", {"layer_id": layer_id, "expression": expression}, dry_run=True))
    record(records, "extract_by_expression_dry_run", command(client, "extract_by_expression", {"layer_id": layer_id, "expression": expression, "output": "TEMPORARY_OUTPUT"}, dry_run=True))

    map_output = out_dir / "SIGMAI_VECTOR_ATTRIBUTE_FILTERED_LEGEND.png"
    record(
        records,
        "generate_basic_map_filtered_legend",
        command(
            client,
            "generate_basic_map",
            {
                "layer_id": layer_id,
                "title": "SIGMAI vector attribute regression",
                "output_path": str(map_output),
                "format": "png",
                "legend_layers": [layer_id],
                "layout_template": "scientific_basic",
                "confirm_overwrite": True,
            },
        ),
    )

    summary.update(
        {
            "total": len(records),
            "passed": sum(1 for item in records if item["ok"]),
            "required_failures": sum(1 for item in records if item["required"] and not item["ok"]),
            "map_output": str(map_output),
        }
    )
    write_reports(summary, out_dir)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SIGMAI vector/attribute/expression regression tests.")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()
    try:
        summary = run(Path(args.out_dir))
    except SigmaiClientError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary.get("required_failures", 1) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
