<div align="center">

<img src="sigmai/icons/sigmai_logo_full.png" alt="SIGMAI" height="72">

**Secure GIS-AI Interface** — a local, auditable bridge that lets AI assistants operate QGIS.

[![QGIS plugin](https://img.shields.io/badge/QGIS-3.28%20→%204.x-589632)](https://plugins.qgis.org/plugins/sigmai/)
[![MCP](https://img.shields.io/badge/MCP-JSON--RPC%202.0%20stdio-6E56CF)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Tests](https://github.com/LuanCortesM/SIGMAI/actions/workflows/tests.yml/badge.svg)](https://github.com/LuanCortesM/SIGMAI/actions/workflows/tests.yml)

[Português](docs/pt-BR/LEIAME.md) · [Install](#install) · [Connect an AI client](#connect-an-ai-client) · [Cartographic rulebook](#the-cartographic-rulebook) · [Security](#security-model)

</div>

---

## What this is

Ask an AI assistant to make you a map today and it will either write PyQGIS for you to paste, or drive your screen with a mouse robot. The first makes you the runtime; the second is unauditable and breaks on the next UI change.

SIGMAI takes a third path. It runs inside QGIS as a plugin and exposes a **local, token-protected command interface** with a fixed vocabulary of validated JSON commands. An AI assistant connects to it through the **Model Context Protocol**, asks what the project contains, and issues commands that the plugin validates, authorises against rules you set, executes, logs, and then **audits**.

That last step is the part that matters. Producing a map is easy; producing a map that is *cartographically correct* is not, and an assistant that receives no useful feedback cannot tell the difference. SIGMAI ships an explicit rulebook — legend covers every visible layer, scale bar spans a legible fraction of the frame, coordinate grid actually renders, datum declared, north arrow is a symbol and not the letter N — and returns a report saying which rules failed, why the rule exists, and which command fixes it.

## Install

**From the QGIS Plugin Repository** — `Plugins ▸ Manage and Install Plugins ▸ All`, search for *SIGMAI*.

**From a ZIP** — download `sigmai-<version>.zip` from the [latest release](https://github.com/LuanCortesM/SIGMAI/releases/latest), then `Plugins ▸ Manage and Install Plugins ▸ Install from ZIP`.

Then open the SIGMAI panel from the toolbar. No external Python packages are required: SIGMAI runs on the interpreter that ships with QGIS/OSGeo4W.

The panel speaks nine languages — Português (Brasil), English, Español, Français, Deutsch, Italiano, 日本語, 简体中文, 繁體中文 — chosen from the list in its header, each named in itself. It follows the QGIS theme (light or dark, including *Night Mapping*) with a palette of its own for each, and *Advanced ▸ Appearance* forces one if you prefer. The maps the assistant composes carry their own frame texts in fifteen languages (`map_language`), independent of the panel language.

## Connect an AI client

The panel does this for you — pick your program in step 2 and it produces the exact configuration block with the correct absolute paths. For reference, the shape is the same everywhere:

```json
{
  "mcpServers": {
    "sigmai": {
      "command": "C:\\OSGeo4W\\apps\\Python312\\python.exe",
      "args": ["C:\\Users\\you\\AppData\\Roaming\\QGIS\\QGIS3\\profiles\\default\\python\\plugins\\sigmai\\mcp\\sigmai_mcp.py"],
      "env": { "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1" }
    }
  }
}
```

| Client | Where the configuration lives | Guide |
|---|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` | [docs/CONNECT_WITH_CLAUDE.md](docs/CONNECT_WITH_CLAUDE.md) |
| Claude Code | `.mcp.json` in the project, or `~/.claude.json` | [docs/CONNECT_WITH_CLAUDE.md](docs/CONNECT_WITH_CLAUDE.md) |
| Cursor | `~/.cursor/mcp.json` | [docs/CONNECT_WITH_CURSOR.md](docs/CONNECT_WITH_CURSOR.md) |
| Codex CLI | `~/.codex/config.toml` | [docs/CONNECT_WITH_CODEX.md](docs/CONNECT_WITH_CODEX.md) |
| Anything else | any MCP stdio client works | [docs/MCP_SERVER.md](docs/MCP_SERVER.md) |

Step 3 of the panel runs a self-test across the whole path — bridge, authentication, session file, MCP server, project, access mode — and names the step that failed instead of leaving you to guess.

## What the assistant can do

Twenty MCP tools, each with a validated input schema. `sigmai_briefing` is where an assistant should start: it replaces the usual five opening calls with one.

| Tool | Reads | Writes | Purpose |
|---|:--:|:--:|---|
| `sigmai_briefing` | ✓ | | One call: versions, project, every layer (id, geometry, count, CRS, probable name field with examples, labels, encoding problems), layouts, access mode, rulebook summary, templates, recommended paths |
| `sigmai_status` | ✓ | | Bridge state, QGIS version, current access mode and session limits |
| `sigmai_project_overview` | ✓ | | Project, CRS, every layer with id, geometry, extent, fields, draw order |
| `sigmai_layer_details` | ✓ | | Fields, symbology, geometry validity, feature sample |
| `sigmai_cartographic_rulebook` | ✓ | | The rules a map must satisfy, with rationale and fixes |
| `sigmai_plan_map` | ✓ | | Simulate a composition: page, slots, extent, scale — changes nothing |
| `sigmai_compose_map` | | ✓ | Compose, export and audit a complete map |
| `sigmai_audit_layout` | ✓ | | Audit any layout in the project, including hand-made ones |
| `sigmai_spatial_relationship` | ✓ | | Where is what: containment fraction, intersecting features, nearest feature with geodesic distance |
| `sigmai_add_context_annotations` | | ✓ | Boundary line and name labels of a context layer, as label-only layers, so the map says which state or municipality it shows |
| `sigmai_campaign_map` | | ✓ | Field-campaign map: sites + track + area + context + inset, with a coordinate table (CSV); a sites spreadsheet loads through `load_vector_layer` (lon/lat, delimiter and decimal mark detected) |
| `sigmai_export_coordinate_table` | | ✓ | Coordinates of a point layer in the CRS you name, plus lon/lat |
| `sigmai_map_recipe` | ✓ | | The exact recipe of a composed map (parameters, layers with SHA-256, versions), from the layout or from the PNG/JSON |
| `sigmai_recompose_from_recipe` | | ✓ | Reproduce a map from its recipe, with overrides; reports which data changed since |
| `sigmai_methods_paragraph` | ✓ | | A Methods paragraph (pt-BR, en, es) describing how the map was made, plus the software reference |
| `sigmai_undo` | | ✓ | Undo the last write in the project: styles, names, labels, layouts, created layers (files on disk stay) |
| `sigmai_list_layouts` | ✓ | | Print layouts in the project |
| `sigmai_capabilities` | ✓ | | Command catalogue, filterable, with the parameters each command reads |
| `sigmai_brief_plugin` | ✓ | | Everything needed to drive another QGIS plugin in one call: state, Processing algorithms with their full contracts, and what is not scriptable |
| `sigmai_run_command` | ✓ | ✓ | Any catalogued command: vector, raster, Processing, symbology, workflows |

Behind them sit 232 catalogued commands, 219 of them enabled. `sigmai_run_command` reaches all of the enabled ones; the dedicated tools exist because a typed schema produces fewer wrong calls than a free-form escape hatch. The 13 disabled commands (the atlas family, the PostGIS family and `create_map_hierarchy`) are refused by the bridge as if they did not exist and listed in `get_capabilities` with the reason — the catalogue describes what the plugin does, not what it might do one day.

## Access control

Read commands and dry runs always work. Everything that changes the project or writes a file goes through a consent layer you control from the **Access** tab:

- **Read only** (default) — the assistant inspects and simulates. A refused write returns a message telling it to show the plan and ask you to unlock, so it stops instead of retrying.
- **Ask every time** — each changing action opens a dialog naming the action, the category and the files it would write.
- **Allow for this session** — no prompts, inside the folders and limits you set.

Independently of the mode: **output folders** restrict where files may be written; **per-session limits** cap project changes, exports and Processing runs; the **Activity** tab records every decision. Installing, removing or reloading plugins and executing Python are never covered by consent — they require Developer Mode, enabled by hand.

## The cartographic engine

`compose_map` is not a template filler. For a given page and set of layers it:

- resolves the page (A5–A0, portrait or landscape, or custom millimetres) and solves a layout whose slots are guaranteed to sit inside the margins — a wide page gets a side column, a tall page a bottom band;
- expands the extent to the map frame's aspect ratio **before** applying the margin, so the margin you asked for is the margin you get on both axes;
- closes the scale on the cartographic series (1:250 000, not 1:257 090), and says so, including the margin that resulted;
- sizes the scale bar to span 15–45% of the frame, ending on a round number in a sensible unit;
- computes a coordinate grid interval from the extent and places the annotations outside the frame, vertical on the sides;
- builds the legend from **every layer in the map frame**, not just the primary one;
- places a real north arrow symbol linked to grid north;
- declares datum, projection, source, authorship and date;
- reprojects to the appropriate UTM zone when the project is in geographic coordinates, because a metric scale bar over degrees is wrong across most of the sheet;
- picks the page orientation — and where the legend and scale bar go, side column or bottom band — from the shape of the data when you ask for `orientation: "auto"` (either choice switches only for a 12 % gain in scale; `arrangement` forces one), and lets you ask for a journal figure by column width (`journal_column`, `figure_width_mm`) instead of by paper size;
- composes two, three or more panels — `second_map` or `panels` — lettered (a), (b), (c) with a shared scale when you ask for one;
- takes `data_source` per layer and prints each layer's source in the legend, next to the layer it belongs to;
- knows the field-campaign case (`compose_campaign_map`): sites over a track over an area over its context, with a locator inset and a coordinate table.

Then it audits what it produced, stores the **recipe** of the map in the layout and in the exported PNG (parameters, layers with their SHA-256, QGIS and SIGMAI versions), and returns the report. The recipe can be read back (`sigmai_map_recipe`), re-run with changes (`sigmai_recompose_from_recipe`) and turned into a Methods paragraph with the software reference (`sigmai_methods_paragraph`). Every write to the project goes through an undo stack (`sigmai_undo`).

## The cartographic rulebook

34 rules across ten categories — elements, scale, orientation, provenance, grid, geometry, typography, projection, data, symbology. Each carries its severity, the reason it exists, its reference, and the command that satisfies it. `sigmai_cartographic_rulebook` returns the whole thing as data, so an assistant can read the rules before composing rather than discovering them by failing.

Five rules came out of the 1.0.3 experiment in which the same request was given to an agent writing raw PyQGIS and to an agent driving SIGMAI, the audit was run on both maps, and the new version was then driven end to end by an emulated assistant: labels the labelling engine could not place (`CART068`), an empty band of the frame that the page shape left unused (`CART069`), colour pairs that a reader with a colour-vision deficiency cannot tell apart, simulated with the Machado, Oliveira & Fernandes (2009) matrices (`CART070`), fonts that fall below the readable size once the figure is printed at column width (`CART071`), and a legend whose content is larger than its box, which QGIS silently clips (`CART072`). The audit also learned to read hand-made layouts — items without an id, headings such as "Data sources", label-only layers — instead of failing them for what it could not see.

Every rule says what it rests on — Brazil's national cartography regulations (Decreto nº 89.817/1984, arts. 12–21), IBGE's SIRGAS2000 resolution, the cartography textbooks of Brewer and Slocum, Snyder's projection manual, the colour-vision model of Machado et al., the figure requirements of journals — or says plainly that a number is a SIGMAI design decision. None of the thresholds was measured with readers, so `tools/threshold_sensitivity.py` re-scores 138 test maps while varying each one and reports which thresholds decide anything and which do not; the tables and a reading of them are in [docs/experiments/2026-09-19_sensibilidade_limiares/](docs/experiments/2026-09-19_sensibilidade_limiares/).

A worked example of why this matters is in [docs/CARTOGRAPHIC_QUALITY_MODEL.md](docs/CARTOGRAPHIC_QUALITY_MODEL.md): the same map that the 0.1.1 evaluator graded *"A — Professional map"* with zero warnings scores **E — invalid** under the rulebook, with three blocking errors that a reader would have spotted immediately.

## Architecture

```mermaid
flowchart LR
    A["AI assistant<br/>Claude · Cursor · Codex"]
    B["MCP server<br/>JSON-RPC 2.0 over stdio<br/>sigmai/mcp/"]
    C["Local bridge<br/>127.0.0.1 · bearer token<br/>sigmai/bridge_server.py"]
    D["Consent<br/>mode · folders · limits · audit<br/>sigmai/consent.py"]
    E["Command registry<br/>219 validated actions<br/>sigmai/qgis_actions/"]
    F["Cartographic engine<br/>page · scale · rulebook<br/>sigmai/cartography/"]
    G[("QGIS<br/>project, layers, layouts")]

    A <-->|"tools/list · tools/call"| B
    B <-->|"HTTP POST /command"| C
    C --> D
    D -->|"authorised"| E
    E --> F
    E --> G
    F --> G
    F -.->|"audit report"| A
```

The split between `cartography` and the rest is deliberate: `pagespec`, `scaling`, `layoutgrid` and `rulebook` never import PyQGIS, so the cartographic decisions can be tested in CI where no QGIS exists. Only `compose` and `inspector` touch the QGIS layout API.

## Development

```bash
git clone https://github.com/LuanCortesM/SIGMAI.git
cd SIGMAI
python -m pytest tests -q          # 686 tests; those that need PyQGIS, a given PyQt or a POSIX system skip themselves without it
python tools/package_qgis_plugin_zip.py
```

Tests that need a live QGIS live in `tools/` and run against a real instance: `exercise_commands.py`, `exercise_plugins_and_basemaps.py`, `exercise_third_party_plugin.py`, `scenario_runner.py` (243 multilingual scenarios in `tests/cenarios/`) and `release_battery.py`, the gate a version has to pass before it ships — 683 checks across every template, page, orientation, format, data type and map language. Everything in `tests/` runs on plain Python.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to propose changes, report a problem or ask for help, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the internals.

## Security model

- The bridge binds to **127.0.0.1 only** and rejects any non-local client.
- Every command requires a **bearer token**; a request without one is refused with 401. `/health` is the single unauthenticated endpoint and returns nothing beyond existence and version.
- The command surface is an **allowlist** of typed handlers. There is no generic evaluator; normal operation cannot execute arbitrary Python.
- **Developer Mode** is off by default, must be enabled in the QGIS interface with a typed confirmation, and is the only route to Python execution.
- Existing files are never overwritten without `confirm_overwrite`.
- Logs and audit records never contain tokens, passwords or credentials.

Full model: [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) · what the MCP layer adds: [docs/MCP_SECURITY_MODEL.md](docs/MCP_SECURITY_MODEL.md).

## Authorship

Plugin author: **MACIEL, L. S. C.** — herpetomantiqueira@gmail.com
Developed by Luan da Silva Cortes Maciel as a research product associated with Herpeto Mantiqueira.

**The plugin author is not the author of the maps you make with it.** Generated maps credit the map author you supply, your SIGMAI user profile, or a neutral `Produzido com SIGMAI/QGIS` line. See [docs/MAP_AUTHORSHIP_POLICY.md](docs/MAP_AUTHORSHIP_POLICY.md).

## Citation

```bibtex
@software{maciel_sigmai,
  author  = {Maciel, Luan da Silva Cortes},
  title   = {{SIGMAI}: Secure {GIS}-{AI} Interface},
  version = {1.1.5},
  doi     = {10.5281/zenodo.20389286},
  url     = {https://github.com/LuanCortesM/SIGMAI},
  license = {MIT}
}
```

Every release is archived on Zenodo. To cite SIGMAI in general, use the DOI that always resolves to the latest version, [10.5281/zenodo.20389286](https://doi.org/10.5281/zenodo.20389286); to cite the exact version you used, use its own DOI, listed under *Versions* on that record — 1.1.4, for example, is [10.5281/zenodo.23146393](https://doi.org/10.5281/zenodo.23146393), and the first public version, V0.1.0, is [10.5281/zenodo.20389287](https://doi.org/10.5281/zenodo.20389287).

Machine-readable metadata: [CITATION.cff](CITATION.cff).

## License

MIT License. See [LICENSE](LICENSE).
