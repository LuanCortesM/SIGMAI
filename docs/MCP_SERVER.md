# The MCP server

`sigmai/mcp/sigmai_mcp.py` is a standalone Python script with no external dependencies. An AI client launches it as a subprocess and talks [Model Context Protocol](https://modelcontextprotocol.io) to it over stdio; the script itself finds the QGIS instance that is actually running the plugin and relays commands to it over `127.0.0.1`. This is the reference for anything not covered by [CONNECT_WITH_CLAUDE.md](CONNECT_WITH_CLAUDE.md), [CONNECT_WITH_CURSOR.md](CONNECT_WITH_CURSOR.md) or [CONNECT_WITH_CODEX.md](CONNECT_WITH_CODEX.md) — a client those guides don't cover, or the schema detail an integration needs.

## Transport

- **Framing**: JSON-Lines over stdio — one JSON-RPC 2.0 message per line, not the `Content-Length`-prefixed framing some other MCP transports use.
- **Protocol version negotiation**: the server accepts `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25` and `2026-07-28`. An unknown version requested by the client is not an error — the server answers with its own supported version instead, because refusing the handshake breaks any client newer than the server.
- **Methods**: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, plus `server/discover` for clients from before the handshake existed. `resources/list` and `prompts/list` return empty lists rather than "method not found", because some clients probe them even without declaring the capability.
- **stdout is reserved for protocol messages.** The moment the transport starts, `sys.stdout` is redirected to `sys.stderr` for the rest of the process, so an accidental `print` — from the plugin, a library, a warning — cannot corrupt the stream. All logging goes to stderr, prefixed `[sigmai-mcp]`.
- **Errors come in two shapes.** A malformed request (bad JSON, unknown method, unknown tool name) is a JSON-RPC `error` object — the model cannot fix that by retrying with different arguments. A tool that ran but failed (the bridge is down, a parameter was rejected, a file already exists) comes back as a normal `result` with `isError: true` and a text payload describing what went wrong — the shape the model is expected to read and act on.

## Session discovery

The server runs as an independent process with no QGIS and no copy of this repository nearby, so it looks for a small JSON session file the plugin writes while the bridge is running. It checks, in order:

1. `SIGMAI_SESSION_FILE`, if set — an explicit path.
2. Per-OS session directories (`%LOCALAPPDATA%\SIGMAI\sessions` and `%TEMP%\SIGMAI\sessions` on Windows; `~/Library/Application Support/SIGMAI/sessions` on macOS; `~/.local/share/sigmai/sessions` and `$TEMP/SIGMAI/sessions` elsewhere), preferring `current_bridge_session.json` and falling back to the most recently modified `SG-*.json` pairing file.

Environment variables override the session file field by field: `SIGMAI_HOST`, `SIGMAI_PORT`, `SIGMAI_TOKEN`, and `SIGMAI_PAIRING_CODE` (matches a specific `SG-XXXX-XXXX.json` session when more than one QGIS profile is running the bridge). The panel's **Advanced** tab shows the exact session file path for the running instance.

If no session is found, every tool call fails with a message telling the user to open the SIGMAI panel and press **Start bridge** — the server never guesses a token or port.

## Calling the bridge

Every tool call becomes one HTTP `POST /command` to the bridge, with the bearer token from the session as `Authorization: Bearer <token>` and a JSON body `{"schema_version": "0.3", "action": ..., "params": ..., "dry_run": ...}`. The server refuses to contact any host other than `127.0.0.1`, `localhost` or `::1`, even if a session file or environment variable claims otherwise.

## Tools

Eleven tools, each with a JSON Schema `inputSchema` and MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) so a client can show the user what a call is about to do before it runs.

| Tool | Reads | Writes | Purpose |
|---|:--:|:--:|---|
| `sigmai_status` | ✓ | | Bridge state, QGIS and plugin version, current access mode, session limits already used |
| `sigmai_project_overview` | ✓ | | Project path, project CRS, and every layer's id, name, geometry type, CRS, feature count, extent and (optionally) fields |
| `sigmai_layer_details` | ✓ | | One layer's fields and types, extent, CRS, current symbology, geometry validity, a feature sample |
| `sigmai_cartographic_rulebook` | ✓ | | The full rulebook as data — id, severity, rationale, reference and fix for every rule, optionally filtered by category |
| `sigmai_plan_map` | ✓ | | Simulates `compose_map` — page, computed slot positions, fitted extent, rounded scale, participating layers — without touching the project or writing a file. Works in every access mode, including read-only |
| `sigmai_compose_map` | | ✓ | Composes, exports and audits a complete map; returns the audit report. Requires write access to be unlocked in the panel |
| `sigmai_audit_layout` | ✓ | | Runs the rulebook against an existing print layout, including one built by hand, and returns grade, score and per-rule findings |
| `sigmai_list_layouts` | ✓ | | Print layouts already in the project, with page size and item list |
| `sigmai_brief_plugin` | ✓ | | Everything needed to drive *another* installed QGIS plugin from one call: identity and load state, Processing provider health, the full parameter contract of every algorithm it registers, which parts of its interface are not programmatically reachable and why, and a safe test order. No source code leaves the machine |
| `sigmai_capabilities` | ✓ | | The full command catalogue `sigmai_run_command` can reach, with group, permission level, dry-run and confirmation support for each |
| `sigmai_run_command` | ✓ | ✓ | Executes any catalogued command by name — vector and raster operations, Processing algorithms, symbology, plugin management, GPX and database tooling, workflows. The dedicated tools above exist because a typed schema produces fewer wrong calls than a free-form escape hatch; this is the escape hatch for everything else |

`sigmai_plan_map` and `sigmai_compose_map` share `compose_map`'s parameters — page and template, `map_crs`/`margin_percent`/`scale`, `subject_layer_id`/`include_inset`/`label_field`, `second_map` for a two-panel comparison layout, and `map_language` for the text the compositor writes on the frame itself. See the parameter descriptions returned by `tools/list`, or [CARTOGRAPHIC_QUALITY_MODEL.md](CARTOGRAPHIC_QUALITY_MODEL.md) for what the engine decides and why.

## Security notes specific to this transport

The MCP server itself holds no secret beyond what it reads from the session file for the duration of one process; it never writes credentials to stdout, and stdio between the AI client and this process is local to the machine. What the token authorises once inside the bridge — and what never becomes reachable through consent alone — is described in [SECURITY_MODEL.md](SECURITY_MODEL.md).
