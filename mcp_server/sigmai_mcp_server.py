from __future__ import annotations

"""Local JSON-lines tool server for SIGMAI.

This is a dependency-free fallback. It reads JSON lines from stdin:
{"tool": "sigmai_status", "arguments": {}}
and writes one JSON response per line.
"""

import json
import sys

try:
    from .tools import TOOLS, sigmai_tool_manifest
except ImportError:
    from tools import TOOLS, sigmai_tool_manifest


def main() -> int:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            tool_name = request.get("tool")
            arguments = request.get("arguments") or {}
            if tool_name in {"list_tools", "tools/list"}:
                response = sigmai_tool_manifest(arguments)
            elif tool_name not in TOOLS:
                response = {"ok": False, "error": f"Unknown tool: {tool_name}"}
            else:
                response = TOOLS[tool_name](arguments)
        except Exception as exc:
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
