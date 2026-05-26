from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INSTALLED_PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _candidate_roots() -> list[Path]:
    roots = [INSTALLED_PLUGIN_ROOT]
    plugins_dir = INSTALLED_PLUGIN_ROOT.parent
    roots.append(plugins_dir / "sigmai")
    unique: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except Exception:
            resolved = root
        if resolved not in unique:
            unique.append(resolved)
    return unique


ROOTS = _candidate_roots()


LEVELS = [
    {"level": 7, "label": "Professional Cartography Capable", "evidence_files": ["RELATORIO_SIGMAI_LEVEL7_SCALE_FINAL_VALIDATION.md"], "required_commands": ["generate_professional_map", "evaluate_map_quality"]},
    {"level": 8, "label": "Raster Core and Workflow Foundation Capable", "evidence_files": ["RELATORIO_SIGMAI_LEVEL8_VALIDATION.md"], "required_commands": ["raster_info", "raster_hillshade", "plan_workflow", "execute_workflow"]},
    {"level": 9, "label": "Job Queue and Long Processing Foundation Capable", "evidence_files": ["RELATORIO_SIGMAI_JOB_QUEUE_VALIDATION.md"], "required_commands": ["start_job", "get_job_status", "job_logs"]},
    {"level": 10, "label": "Atlas and Report Foundation Capable", "evidence_files": ["RELATORIO_SIGMAI_ATLAS_REPORT_VALIDATION.md"], "required_commands": ["create_atlas", "create_report", "export_report_html"]},
    {"level": 11, "label": "Data Sources, OGC, GPS and Database Foundation Capable", "evidence_files": ["RELATORIO_SIGMAI_DATA_SOURCES_VALIDATION.md"], "required_commands": ["inspect_data_source", "load_gpx", "validate_service_url", "list_database_connections"]},
    {"level": 12, "label": "Plugin Orchestration Foundation Capable", "evidence_files": ["RELATORIO_SIGMAI_PLUGIN_ORCHESTRATION_DEEP_VALIDATION.md"], "required_commands": ["list_qgis_plugins_extended", "inspect_plugin_capabilities", "run_plugin_algorithm_safe"]},
    {"level": 13, "label": "Multi-IA MCP Foundation Capable", "evidence_files": ["RELATORIO_SIGMAI_MCP_FORMAL_VALIDATION.md", "diagnostics/SIGMAI_MCP_TOOL_COVERAGE.json"], "required_commands": ["get_capabilities", "status"]},
    {"level": 14, "label": "Broad QGIS Ecosystem Coverage Roadmap Capable", "evidence_files": ["docs/SIGMAI_BROAD_QGIS_ECOSYSTEM_COVERAGE.md", "docs/PUBLIC_RELEASE_CHECKLIST.md", "diagnostics/SIGMAI_FULL_PLATFORM_REGRESSION.json"], "required_commands": ["evaluate_sigmai_maturity"]},
]


def _resolve_evidence(relative_path: str) -> Path | None:
    for root in ROOTS:
        candidate = root / relative_path
        if candidate.exists():
            return candidate
    return None


def _exists(relative_path: str) -> bool:
    return _resolve_evidence(relative_path) is not None


def _read_json(relative_path: str) -> dict[str, Any]:
    path = _resolve_evidence(relative_path)
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _level_status(level: dict[str, Any], registered: set[str]) -> dict[str, Any]:
    evidence = [path for path in level["evidence_files"] if _exists(path)]
    missing_evidence = [path for path in level["evidence_files"] if path not in evidence]
    commands_present = [action for action in level["required_commands"] if action in registered]
    missing_commands = [action for action in level["required_commands"] if action not in registered]
    return {
        "level": level["level"],
        "label": level["label"],
        "validated": not missing_evidence and not missing_commands,
        "evidence": evidence,
        "missing_evidence": missing_evidence,
        "commands_present": commands_present,
        "missing_commands": missing_commands,
    }


def evaluate_sigmai_maturity(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    registered = set(context.get("registered_actions") or [])
    statuses = [_level_status(level, registered) for level in LEVELS]
    validated_levels = [item for item in statuses if item["validated"]]
    highest = max(validated_levels, key=lambda item: item["level"]) if validated_levels else None
    recommendations = []
    if highest is None or highest["level"] < 14:
        recommendations.append("Complete Level 14 evidence: broad QGIS coverage, public release checklist and full platform regression.")
    return {
        "highest_validated_level": highest["level"] if highest else 0,
        "highest_validated_label": highest["label"] if highest else "No validated maturity evidence found",
        "highest_claimed_level": 14,
        "runtime_command_count": len(registered),
        "evidence_roots": [str(root) for root in ROOTS],
        "levels": statuses,
        "recent_mcp_summary": _read_json("diagnostics/SIGMAI_MCP_TOOL_COVERAGE.json").get("summary", {}),
        "blocked_levels": [item for item in statuses if not item["validated"]],
        "recommendations": recommendations,
        "rules": [
            "A maturity level requires runtime commands and local evidence files.",
            "Commands existing only in code are not enough.",
            "Security, token and local-only rules remain mandatory.",
        ],
    }
