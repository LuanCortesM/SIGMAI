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

## Where the pieces run — and what a phone can and cannot do

Three things take part in a conversation, and only one of them is remote:

| Piece | Where it runs | Talks to |
|---|---|---|
| The language model (Claude, GPT, …) | the vendor's servers | the MCP client, through the vendor's app |
| The MCP client (Claude Desktop, Cursor, Codex CLI, Claude Code) | **the computer with QGIS** | launches `sigmai_mcp.py` as a subprocess over stdio |
| The bridge (the plugin) | inside QGIS, on `127.0.0.1` only | the MCP server, with a bearer token |

The model never touches the computer: everything it knows about the project comes back from tool calls, and everything it does goes through the bridge's validation, consent and audit trail. `tools/remote_ai_lab.py` + `tools/mcp_call.py` reproduce exactly this situation — a headless QGIS with the bridge up, and an "assistant" that may only issue MCP calls — and were used to test the plugin from the model's point of view.

What this means for a person chatting **on their phone** while QGIS runs on their desk: the app on the phone does not contain the MCP client, and the bridge is deliberately unreachable from anything but the computer's own loopback interface (a request from any other address is refused before it reaches a socket; there is no relay, no tunnel and no cloud endpoint). So the phone alone cannot drive QGIS. What does work is keeping the chat *client* on the computer — Claude Desktop, Cursor, Claude Code or Codex open next to QGIS. If you want to type from the phone, the route that certainly works is a remote-desktop app controlling that computer; whether a vendor's mobile app can hand a tool call to an MCP server hosted by its desktop app is up to that vendor, changes over time, and has not been verified here. Exposing the bridge to the network on purpose (a tunnel, a public MCP endpoint) would turn a local, consent-gated interface into a remotely operable one, and is not something SIGMAI will do quietly on the user's behalf.

## What SIGMAI adds over an agent that writes PyQGIS directly

A fair question is why any of this is needed when a coding agent with shell access to the computer can simply write PyQGIS. It was put to the test: the same informal request ("an A4 map of the Parque Estadual das Carnaúbas with the surrounding municipalities and a locator inset, IBGE 2024 and CEUC/SEMA data, author Maria Silva"), the same data, the same model, two agents. One could only issue MCP calls to SIGMAI, with no access to the computer at all (`tools/remote_ai_lab.py`). The other had a full shell on the computer and was forbidden to use the plugin.

| | Through SIGMAI (no computer access) | Raw PyQGIS (full shell access) |
|---|---|---|
| Steps | 17–18 MCP calls | 15 tool runs, 5 iterations of a 353-line script |
| Wall time | 5.5 min | 19 min |
| Tokens generated by the model | 5–7 thousand | 32 thousand |
| QGIS API pitfalls hit | none visible to the model | 12, solved by trial and error (`QFont` integer sizes, scale bar labelled "0,005 km", legend renaming project layers, `setExtent` resizing the frame, a segfault at exit…) |
| Rulebook grade | A (100/100) | B (90/100) |
| Where it ran | inside the user's live QGIS session, every write in the consent log, output only in the allowed folder | in a separate process on the user's files, unrestricted, no record beyond the script itself |
| Reproducible by | one JSON call (`sigmai_compose_map`) | re-running that script |

The raw map is visually richer — it draws the state boundary, names both states, cites the decree and CNUC code. SIGMAI's value is not that its map is prettier; it is that the cartographic decisions and the QGIS gotchas are encoded once and audited, that a model without code execution (a chat client, a non-programmer's assistant) can still get a correct map, and that the user can see and bound what happened. The experiment also found that `sigmai_audit_layout` did not work on the hand-made layout at all until 1.0.3 — the inspector dropped items without an `id`, which is every item created through the QGIS interface. That defect is fixed and covered by `tests/test_foreign_layout_audit.py`.

The exercise was repeated for 1.1.0 with the new tools — briefing, spatial relationship, context annotations, journal figure, recipe, Methods paragraph, CSV sites, campaign map, undo — driven end to end by an assistant with nothing but the MCP client; `docs/experiments/2026-09-19_emulacao_1.1.0/` records the calls, the figures, the consent trail and the seven defects the run exposed (SIGMAI's own palette failing its own colour-vision rule, legend text clipped without warning, the audit of a composed figure disagreeing with the composer), all fixed in the same version.

## Calling the bridge

Every tool call becomes one HTTP `POST /command` to the bridge, with the bearer token from the session as `Authorization: Bearer <token>` and a JSON body `{"schema_version": "0.3", "action": ..., "params": ..., "dry_run": ...}`. The server refuses to contact any host other than `127.0.0.1`, `localhost` or `::1`, even if a session file or environment variable claims otherwise.

## Tools

Twenty tools, each with a JSON Schema `inputSchema` and MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) so a client can show the user what a call is about to do before it runs.

| Tool | Reads | Writes | Purpose |
|---|:--:|:--:|---|
| `sigmai_briefing` | ✓ | | Start here. One call returns the plugin and QGIS versions, the project (path, CRS), every layer with id, geometry, feature count, CRS, the probable name field with example values, whether labels are on and whether the encoding is broken, the layouts (and which were composed by SIGMAI), the access mode and allowed folders, the rulebook summary, the templates and a recommended path for the common requests. In the two emulations run before 1.1.0 the assistant spent its first five calls collecting exactly this |
| `sigmai_status` | ✓ | | Bridge state, QGIS and plugin version, current access mode, session limits already used |
| `sigmai_project_overview` | ✓ | | Project path, project CRS, and every layer's id, name, geometry type, CRS, feature count, extent and (optionally) fields |
| `sigmai_layer_details` | ✓ | | One layer's fields and types, extent, CRS, current symbology, geometry validity, a feature sample |
| `sigmai_cartographic_rulebook` | ✓ | | The full rulebook as data — id, severity, rationale, reference and fix for every rule, optionally filtered by category |
| `sigmai_plan_map` | ✓ | | Simulates `compose_map` — page, computed slot positions, fitted extent, rounded scale, participating layers — without touching the project or writing a file. Works in every access mode, including read-only |
| `sigmai_compose_map` | | ✓ | Composes, exports and audits a complete map; returns the audit report. Requires write access to be unlocked in the panel |
| `sigmai_audit_layout` | ✓ | | Runs the rulebook against an existing print layout, including one built by hand, and returns grade, score and per-rule findings |
| `sigmai_spatial_relationship` | ✓ | | The relation between two layers, as numbers and text: the fraction of each feature of A inside B, the features of B that intersect A, and the nearest feature of B with its geodesic distance in metres (`radius_m` bounds the search). Use it before assuming which state or municipality something is in |
| `sigmai_add_context_annotations` | | ✓ | Adds, as label-only layers, the boundary line and the name labels of a context layer (a state, the municipalities) at each polygon's pole of inaccessibility, plus any `extra_labels` you pass; optionally persisted to a GeoPackage. The composed map then says where it is |
| `sigmai_campaign_map` | | ✓ | The field-campaign template: `points_layer_id` over `track_layer_id` over `area_layer_ids` over `context_layer_ids`, with `inset_layer_ids` for the locator, the subject extent taken from points *and* track, sites labelled by the name field (auto-detected, up to 60 points), and a coordinate table written to `coordinate_table_path`. Sites that arrive as a spreadsheet load through `sigmai_run_command` → `load_vector_layer` with the `.csv` path: delimiter, decimal mark and encoding are detected in the file, the coordinate columns are recognised by name (lon/lat assumes EPSG:4326; E/N needs `crs`) or given as `x_field`/`y_field` |
| `sigmai_export_coordinate_table` | | ✓ | CSV of a point layer's coordinates in the CRS you name (E/N) plus lon/lat in EPSG:4326, with the fields you choose; polygons and lines are reduced to a representative point and the note says so |
| `sigmai_map_recipe` | ✓ | | The recipe stored in a composed layout (or embedded in its PNG / written as JSON): the parameters, the layers with provider, source, CRS, feature count and SHA-256 of the local file, the QGIS and SIGMAI versions, the project path and the audit result; with `data_changes` listing files whose fingerprint no longer matches |
| `sigmai_recompose_from_recipe` | | ✓ | Runs the recipe again, with `overrides`; layers are found by id and, failing that, by name; the response says what was substituted and which data changed since the original |
| `sigmai_methods_paragraph` | ✓ | | A paragraph for the Methods section (`language`: pt-BR, en or es; other languages fall back to English with a note) — software and versions, layers and their sources, CRS, scale, page, export, audit grade — plus the bibliographic reference of SIGMAI |
| `sigmai_undo` | | ✓ | Undoes the last write in the project in this QGIS session: restores style, name, labels and encoding of the layers touched, restores layouts replaced and removes layouts and layers created. Files written to disk are kept and listed. `list: true` shows the history instead |
| `sigmai_list_layouts` | ✓ | | Print layouts already in the project: pages, items and every map frame's CRS, scale, layers and overviews |
| `sigmai_brief_plugin` | ✓ | | Everything needed to drive *another* installed QGIS plugin from one call: identity and load state, Processing provider health, the full parameter contract of every algorithm it registers, which parts of its interface are not programmatically reachable and why, and a safe test order. No source code leaves the machine |
| `sigmai_capabilities` | ✓ | | The command catalogue `sigmai_run_command` can reach — filter with `group`, `search` or `names_only`; each command lists the parameters it reads (`parameters`, `parameters_complete`) |
| `sigmai_run_command` | ✓ | ✓ | Executes any catalogued command by name — vector and raster operations, Processing algorithms, symbology, plugin management, GPX and database tooling, workflows. The dedicated tools above exist because a typed schema produces fewer wrong calls than a free-form escape hatch; this is the escape hatch for everything else |

`sigmai_plan_map` and `sigmai_compose_map` share `compose_map`'s parameters — page and template, `orientation` (`portrait`, `landscape` or `auto`, chosen from the data's shape), `arrangement` (`auto`, `coluna_lateral` or `faixa_inferior` — where the title, legend and scale bar go; `auto` picks the one that gives the map frame the larger scale, switching only for a gain of 12 % or more), `map_crs`/`margin_percent`/`scale`, `subject_layer_id` (one id or a list)/`include_inset`/`label_field`, `data_source` as one credit line or as a `{layer id or name: source}` object printed per layer in the legend, `second_map` for a two-panel comparison layout or `panels` for three or more lettered (a), (b), (c), `journal_column` (`single` 85 mm, `one_and_half` 120 mm, `double` 175 mm) or `figure_width_mm` for a journal figure sized in millimetres instead of paper, `format` including `tif` and `jpg` for submission systems, `recipe_path` to also write the recipe as JSON, and `map_language` for the text the compositor writes on the frame itself. See the parameter descriptions returned by `tools/list`, or [CARTOGRAPHIC_QUALITY_MODEL.md](CARTOGRAPHIC_QUALITY_MODEL.md) for what the engine decides and why.

## Security notes specific to this transport

The MCP server itself holds no secret beyond what it reads from the session file for the duration of one process; it never writes credentials to stdout, and stdio between the AI client and this process is local to the machine. What the token authorises once inside the bridge — and what never becomes reachable through consent alone — is described in [SECURITY_MODEL.md](SECURITY_MODEL.md).
