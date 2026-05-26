from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "diagnostics"
JSON_REPORT = DIAGNOSTICS / "processing_algorithms_report.json"
MD_REPORT = DIAGNOSTICS / "processing_algorithms_report.md"

CANDIDATE_IDS = {
    "native:buffer",
    "native:clip",
    "native:dissolve",
    "native:intersection",
    "native:union",
    "native:difference",
    "native:fixgeometries",
    "native:reprojectlayer",
    "native:centroids",
    "native:multiparttosingleparts",
    "native:extractbyattribute",
    "native:extractbylocation",
    "gdal:warpreproject",
    "gdal:cliprasterbyextent",
    "gdal:cliprasterbymasklayer",
    "gdal:slope",
    "gdal:aspect",
    "gdal:hillshade",
    "gdal:contour",
    "gdal:polygonize",
    "gdal:rastercalculator",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parameter_to_dict(parameter) -> dict[str, Any]:
    return {
        "name": parameter.name(),
        "description": parameter.description(),
        "type": parameter.type(),
        "optional": bool(parameter.flags() & parameter.FlagOptional),
        "default": str(parameter.defaultValue()) if parameter.defaultValue() is not None else None,
    }


def output_to_dict(output) -> dict[str, Any]:
    return {
        "name": output.name(),
        "description": output.description(),
        "type": output.type(),
    }


def collect() -> dict[str, Any]:
    try:
        from qgis.core import QgsApplication  # type: ignore
    except Exception as exc:
        return {"generated_at": now(), "available": False, "error": f"{type(exc).__name__}: {exc}"}

    registry = QgsApplication.processingRegistry()
    providers = []
    candidates = []
    algorithm_count = 0

    for provider in registry.providers():
        provider_algorithms = []
        for algorithm in provider.algorithms():
            algorithm_count += 1
            item = {
                "id": algorithm.id(),
                "name": algorithm.name(),
                "display_name": algorithm.displayName(),
                "group": algorithm.group(),
                "group_id": algorithm.groupId(),
                "provider_id": provider.id(),
                "flags": int(algorithm.flags()),
                "parameters": [parameter_to_dict(p) for p in algorithm.parameterDefinitions()],
                "outputs": [output_to_dict(o) for o in algorithm.outputDefinitions()],
                "allowlist_candidate": algorithm.id() in CANDIDATE_IDS,
            }
            if item["allowlist_candidate"]:
                candidates.append(item)
            provider_algorithms.append(item)
        providers.append(
            {
                "id": provider.id(),
                "name": provider.name(),
                "active": bool(provider.isActive()),
                "algorithm_count": len(provider_algorithms),
                "algorithms": provider_algorithms,
            }
        )

    return {
        "generated_at": now(),
        "available": True,
        "algorithm_count": algorithm_count,
        "providers": providers,
        "allowlist_candidates_found": candidates,
        "proposed_allowlist": {
            "vector": [
                "native:buffer",
                "native:clip",
                "native:dissolve",
                "native:intersection",
                "native:union",
                "native:difference",
                "native:fixgeometries",
                "native:reprojectlayer",
                "native:centroids",
                "native:multiparttosingleparts",
                "native:extractbyattribute",
                "native:extractbylocation",
            ],
            "raster": [
                "gdal:warpreproject",
                "gdal:cliprasterbyextent",
                "gdal:cliprasterbymasklayer",
                "gdal:slope",
                "gdal:aspect",
                "gdal:hillshade",
                "gdal:contour",
                "gdal:polygonize",
                "gdal:rastercalculator",
            ],
        },
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Processing Algorithms Report",
        "",
        f"Generated at: `{report.get('generated_at')}`",
        f"Available: `{report.get('available')}`",
        f"Algorithm count: `{report.get('algorithm_count', 0)}`",
        "",
        "## Providers",
        "",
        "| Provider | Name | Active | Algorithms |",
        "|---|---|---:|---:|",
    ]
    for provider in report.get("providers", []):
        lines.append(
            f"| `{provider.get('id')}` | {provider.get('name')} | {provider.get('active')} | {provider.get('algorithm_count')} |"
        )
    lines.extend(["", "## Allowlist Candidates Found", ""])
    for item in report.get("allowlist_candidates_found", []):
        lines.append(f"- `{item['id']}` - {item['display_name']} ({item['provider_id']})")
    lines.extend(
        [
            "",
            "## Proposed Initial Allowlist",
            "",
            "### Vector",
        ]
    )
    for item in report.get("proposed_allowlist", {}).get("vector", []):
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("### Raster")
    for item in report.get("proposed_allowlist", {}).get("raster", []):
        lines.append(f"- `{item}`")
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    report = collect()
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_markdown(report)
    print(str(JSON_REPORT))
    print(str(MD_REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
