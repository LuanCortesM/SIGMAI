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

from codex_plugin.client.sigmai_client import SigmaiClient


OUT_DIR = ROOT / "test_outputs" / "sigmai_professional_map_regression"
TEST_DATA_ROOT = Path(os.environ.get("SIGMAI_TEST_DATA_DIR", ROOT.parent / ("Shapes pra " + "Teste")))
TEST_SHAPE_CANDIDATES = [
    TEST_DATA_ROOT / "Municipios" / "SP_Municipios_2025.shp",
    TEST_DATA_ROOT / "Estados" / "BR_UF_2025.shp",
    TEST_DATA_ROOT / "Pais" / "BR_Pais_2025.shp",
]
TEMPLATES = ["scientific_basic", "scientific_publication", "environmental_report", "minimal_clean", "technical_dark", "atlas_page"]
PROFILES = ["scientific_soft", "environmental_green", "technical_blue", "monochrome_publication", "biodiversity_report"]
PLUGIN_AUTHOR_MARKERS = ["MACIEL, L. S. C.", "MACIEL, L. S. C."]


def command(client: SigmaiClient, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    return client.command({"schema_version": "0.3", "request_id": f"professional-regression-{action}", "action": action, "params": params or {}, "dry_run": dry_run})


def pick_layers(client: SigmaiClient) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for shape in TEST_SHAPE_CANDIDATES:
        if shape.exists():
            response = command(client, "load_vector_layer", {"path": str(shape), "name": f"profreg_{shape.stem}"})
            data = response.get("data", {}) if isinstance(response.get("data"), dict) else {}
            layer_id = data.get("layer_id") or data.get("id")
            if layer_id:
                loaded.append({"id": layer_id, "name": data.get("name", shape.stem)})
    response = command(client, "list_layers")
    layers = response.get("data", {}).get("layers", []) if isinstance(response.get("data"), dict) else []
    candidates = loaded + [layer for layer in layers if str(layer.get("type", "")).lower() == "vector"]
    valid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for layer in candidates:
        layer_id = str(layer.get("id", ""))
        if not layer_id or layer_id in seen:
            continue
        seen.add(layer_id)
        info = command(client, "get_layer_info", {"layer_id": layer_id})
        info_data = info.get("data", {}) if isinstance(info.get("data"), dict) else {}
        extent = info_data.get("extent", {}) if isinstance(info_data.get("extent"), dict) else {}
        try:
            valid_extent = float(extent.get("xmax", 0)) > float(extent.get("xmin", 0)) and float(extent.get("ymax", 0)) > float(extent.get("ymin", 0))
        except Exception:
            valid_extent = False
        if info.get("ok") and valid_extent:
            layer = dict(layer)
            layer["name"] = layer.get("name") or info_data.get("name")
            valid.append(layer)
    return valid[:5]


def run(limit: int, out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    client = SigmaiClient(timeout=240)
    records = []
    status = command(client, "status")
    capabilities = command(client, "get_capabilities")
    templates = command(client, "list_layout_templates")
    layers = pick_layers(client)
    if not layers:
        raise RuntimeError("No vector layers available for professional map regression.")
    for index in range(limit):
        layer = layers[index % len(layers)]
        template = TEMPLATES[index % len(TEMPLATES)]
        profile = PROFILES[index % len(PROFILES)]
        output = out_dir / f"professional_{index:03d}_{template}_{profile}.png"
        response = command(
            client,
            "generate_professional_map",
            {
                "layer_id": layer["id"],
                "title": f"SIGMAI Professional Map {index:03d}",
                "subtitle": f"{template} | {profile}",
                "output_path": str(output),
                "format": "png",
                "layout_template": template,
                "style_profile": profile,
                "legend_layers": [layer["id"]],
                "public_mode": True,
                "map_author": "" if index % 2 == 0 else f"Regression User {index:03d}",
                "data_source": "SIGMAI test data",
                "confirm_overwrite": True,
            },
        )
        data = response.get("data", {}) if isinstance(response.get("data"), dict) else {}
        quality = data.get("map_quality", {}) if isinstance(data, dict) else {}
        credits = data.get("credits", {}) if isinstance(data, dict) else {}
        grade = quality.get("grade", "")
        credit_line = str(credits.get("credit_line", ""))
        map_author = str(credits.get("map_author", ""))
        public_author_ok = True
        if index % 2 == 0:
            public_author_ok = not map_author and not any(marker in credit_line for marker in PLUGIN_AUTHOR_MARKERS)
        else:
            public_author_ok = map_author == f"Regression User {index:03d}"
        records.append(
            {
                "index": index,
                "layer_name": layer.get("name"),
                "layer_id": layer.get("id"),
                "template": template,
                "style_profile": profile,
                "ok": bool(response.get("ok")),
                "grade": grade,
                "visual_success": bool(quality.get("visual_success", False)),
                "export_success": bool(quality.get("export_success", False)),
                "missing_elements": quality.get("base_assessment", {}).get("missing_elements", []),
                "quality_warnings": quality.get("warnings", []),
                "public_author_ok": public_author_ok,
                "map_author": map_author,
                "credit_line": credit_line,
                "output": str(output),
                "output_exists": output.exists(),
                "output_size": output.stat().st_size if output.exists() else 0,
                "errors": response.get("errors", []),
                "warnings": response.get("warnings", []),
            }
        )
    rendered = sum(1 for item in records if item["ok"] and item["output_exists"] and item["output_size"] > 10000)
    high_grade = sum(1 for item in records if item["grade"] in {"A+", "A"})
    nonblank = sum(1 for item in records if item["visual_success"])
    author_ok = sum(1 for item in records if item["public_author_ok"])
    summary = {
        "run_time": datetime.now(timezone.utc).isoformat(),
        "status_ok": bool(status.get("ok")),
        "capabilities_ok": bool(capabilities.get("ok")),
        "templates_ok": bool(templates.get("ok")),
        "total": len(records),
        "rendered": rendered,
        "nonblank": nonblank,
        "a_or_better": high_grade,
        "author_policy_ok": author_ok,
        "criteria": {
            "commands_ok": f"{len([r for r in records if r['ok']])}/{len(records)}",
            "outputs_existing": f"{len([r for r in records if r['output_exists']])}/{len(records)}",
            "nonblank": f"{nonblank}/{len(records)}",
            "a_or_better_minimum": "45/50 for default limit",
            "author_policy": f"{author_ok}/{len(records)}",
        },
        "records": records,
    }
    (out_dir / "SIGMAI_PROFESSIONAL_MAP_REGRESSION.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# SIGMAI Professional Map Regression",
        "",
        f"- Total: `{len(records)}`",
        f"- Rendered: `{rendered}`",
        f"- Nonblank visual pass: `{nonblank}`",
        f"- A/A+: `{high_grade}`",
        f"- Authorship policy OK: `{author_ok}`",
        "",
        "| # | Layer | Template | Profile | Grade | Visual | Author OK | OK |",
        "|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for item in records:
        lines.append(f"| {item['index']} | `{item['layer_name']}` | `{item['template']}` | `{item['style_profile']}` | `{item['grade']}` | {item['visual_success']} | {item['public_author_ok']} | {item['ok']} |")
    (out_dir / "SIGMAI_PROFESSIONAL_MAP_REGRESSION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SIGMAI professional map regression.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()
    summary = run(args.limit, Path(args.out_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    minimum_a = min(summary["total"], 45 if summary["total"] >= 50 else summary["total"])
    return 0 if summary["rendered"] == summary["total"] and summary["nonblank"] == summary["total"] and summary["a_or_better"] >= minimum_a and summary["author_policy_ok"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
