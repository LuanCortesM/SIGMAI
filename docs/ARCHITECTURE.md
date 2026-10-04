# SIGMAI architecture

SIGMAI puts a validated, consent-gated command layer between an AI assistant and QGIS. The assistant never runs code on the user's machine: it calls typed tools, each tool becomes a catalogued command, and every command that changes the project or writes a file goes through the user's consent before it runs inside QGIS.

```
AI assistant ── MCP client ──stdio──▶ MCP server ──HTTP 127.0.0.1──▶ bridge ──▶ consent ──▶ command registry ──▶ QGIS
                                    sigmai/mcp/             sigmai/bridge_server.py  consent.py   qgis_actions/         │
                                                                                                    cartography/ ◀──────┘
```

## Request path

1. **MCP server** — `sigmai/mcp/sigmai_mcp.py`. A separate process that the AI client launches; JSON-RPC 2.0 over standard input/output, Python standard library only, so it runs on the interpreter that ships with QGIS. It publishes 20 tools with input schemas and behaviour annotations (read-only, destructive, idempotent). It finds the running bridge through the session file (`sigmai/session.py`), reads the bearer token from it on every call, and refuses any host other than the loopback interface. The token never appears in anything the model reads.
2. **Bridge** — `sigmai/bridge_server.py`. An HTTP server inside the QGIS process, bound to `127.0.0.1` with an exclusive port (it moves to the next free port if another QGIS already has 8765), requiring the bearer token on every command. It validates the command envelope (`validators.py`), answers fast read-only queries directly, and queues everything else for the Qt main thread, where a timer executes it: PyQGIS objects are not safe to touch from the HTTP threads.
3. **Consent** — `sigmai/consent.py`. Read-only (default), ask-every-time or allow-for-this-session; output-folder sandboxing; per-session limits; an audit trail. Installing, removing or reloading plugins and executing Python are never covered by consent and require Developer Mode, enabled by hand. Every write can be simulated with `dry_run`, and the bridge checks that a simulation changed nothing.
4. **Command registry** — `sigmai/command_registry.py`, `permissions.py`, `qgis_actions/`. 232 catalogued commands in permission levels (read-only, safe write, plugin write, dangerous plugin write, developer, unsafe developer); 219 are enabled and the rest are refused as if they did not exist, with the reason in the catalogue. The parameters each command reads are extracted from its handler (`parameter_introspection.py`), so an unknown parameter comes back as a warning instead of being ignored. Responses share one envelope (`ok`, `data`, `warnings`, `errors`, `meta`).
5. **Undo** — `sigmai/undo.py`. Before each write the registry snapshots style, name, labels and encoding of the layers involved and the XML of the layouts involved; `undo_last_action` restores them and removes what was created.

## Cartographic engine

`sigmai/cartography/` is split so that its decisions can be verified without QGIS:

| Module | Imports PyQGIS | Role |
|---|:--:|---|
| `pagespec.py` | no | Page sizes (ISO A/B, North American, custom millimetres) and orientation names in several languages |
| `layoutgrid.py` | no | Layout solver: slots for title, map, legend, scale, north arrow, inset, credits; side column or bottom band; panel grids |
| `scaling.py` | no | Extent fitting, scale on the cartographic series, scale bar, grid interval |
| `rulebook.py` | no | 34 rules evaluated against an observation dictionary; grade, failing rules, reasons, references and fixes |
| `vision.py` | no | Colour-vision-deficiency simulation (Machado et al., 2009) and CIELAB distance |
| `recipe.py`, `params.py`, `maptext.py`, `textfit.py` | no | Map recipe and Methods paragraph, parameter validation, map texts in 15 languages, text fitting |
| `compose.py` | yes | Builds the QGIS print layout from a request, styles layers, exports, stores the recipe and calls the audit |
| `inspector.py` | yes | Turns any layout — including hand-made ones — into the observation the rulebook reads, measuring the exported image |
| `symbology.py` | yes | Palette that stays distinguishable under simulated dichromacy; preserves styles the user set |

`tests/` exercises the pure modules on any Python from 3.9; the modules that touch QGIS are tested when PyQGIS is available, and `tools/release_battery.py` composes the full matrix of templates, pages, orientations, formats, data types and map languages inside a real QGIS.

## The panel

`sigmai/plugin.py` is the QGIS plugin entry point and the controller of the dock panel (`sigmai/ui/`), which connects in three steps — start the bridge, copy the client configuration (`client_configs.py`), run the self-test — and holds the Access, Activity, Advanced and Help tabs, in nine interface languages. The self-test launches the MCP server exactly as the AI client will and carries a status call through to the bridge.

## Elsewhere in the repository

- `core/` — protocol schemas, command taxonomy and examples, independent of QGIS.
- `codex_plugin/` — skills and a command-line client for Codex; the MCP server above is the supported route for every client.
- `tools/` — packaging, the release battery, the threshold sensitivity analysis, live-QGIS exercisers and the MCP command-line client (`mcp_call.py`).
- `docs/experiments/` — records of the experiments behind the design decisions.
