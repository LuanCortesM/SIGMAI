from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MCP = ROOT / "mcp_server"
if str(MCP) not in sys.path:
    sys.path.insert(0, str(MCP))

from mcp_server import tools  # noqa: E402

OUT_DIR = ROOT / "diagnostics"
OUT_JSON = OUT_DIR / "SIGMAI_MCP_TOOL_COVERAGE.json"
OUT_MD = OUT_DIR / "SIGMAI_MCP_TOOL_COVERAGE.md"


def _record(name: str, result: dict[str, Any], expected_ok: bool = True) -> dict[str, Any]:
    ok = bool(result.get("ok"))
    return {
        "tool": name,
        "ok": ok,
        "expected_ok": expected_ok,
        "validated": ok == expected_ok,
        "error": result.get("error") or result.get("errors"),
        "keys": sorted(result.keys())[:20],
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    calls = [
        ("sigmai_tool_manifest", tools.sigmai_tool_manifest, {}, True),
        ("sigmai_health", tools.sigmai_health, {}, True),
        ("sigmai_status", tools.TOOLS["sigmai_status"], {}, True),
        ("sigmai_get_capabilities", tools.TOOLS["sigmai_get_capabilities"], {}, True),
        ("sigmai_list_layers", tools.TOOLS["sigmai_list_layers"], {}, True),
        ("sigmai_processing_providers", tools.TOOLS["sigmai_processing_providers"], {}, True),
        ("sigmai_plugin_inventory", tools.TOOLS["sigmai_plugin_inventory"], {}, True),
        ("sigmai_command_status", tools.sigmai_command, {"action": "status"}, True),
        ("sigmai_command_basic_map_dry_run", tools.sigmai_command, {"action": "generate_basic_map", "params": {}, "dry_run": True}, False),
        ("sigmai_command_blocked_self_apply", tools.sigmai_command, {"action": "self_apply_update", "params": {}, "dry_run": True}, False),
    ]

    records: list[dict[str, Any]] = []
    for name, func, args, expected_ok in calls:
        try:
            result = func(args)
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        records.append(_record(name, result, expected_ok=expected_ok))

    manifest = tools.sigmai_tool_manifest({})
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    tool_names = [item["name"] for item in manifest.get("tools", [])]
    summary = {
        "records_total": len(records),
        "validated": sum(1 for item in records if item["validated"]),
        "failed": sum(1 for item in records if not item["validated"]),
        "tool_count": len(tool_names),
        "dangerous_actions_blocked": sorted(tools.BLOCKED_MCP_ACTIONS),
        "token_exposed": "Bearer " in manifest_text,
    }
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_name": "SIGMAI MCP Tool Coverage",
        "summary": summary,
        "tools": tool_names,
        "records": records,
        "decision": "LEVEL 13 - MCP Formal Foundation Capable" if summary["failed"] == 0 and not summary["token_exposed"] else "MCP validation failed",
        "limitations": [
            "Dependency-free JSON-lines MCP-compatible wrapper; full SDK transport is still planned.",
            "Dangerous plugin/self-management actions remain blocked from MCP and require explicit SIGMAI UI/CLI confirmation.",
        ],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# SIGMAI MCP Tool Coverage",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Decision: {report['decision']}",
        f"- Tools exposed: {summary['tool_count']}",
        f"- Records: {summary['validated']}/{summary['records_total']} validated",
        f"- Token exposed: {summary['token_exposed']}",
        "",
        "## Tools",
        "",
    ]
    lines.extend(f"- `{name}`" for name in tool_names)
    lines.extend(["", "## Regression Records", ""])
    for item in records:
        lines.append(f"- `{item['tool']}`: validated={item['validated']} ok={item['ok']} expected_ok={item['expected_ok']} error={item['error']}")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {line}" for line in report["limitations"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["failed"] == 0 and not summary["token_exposed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
