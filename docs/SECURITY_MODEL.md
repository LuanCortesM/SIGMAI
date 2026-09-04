# Security model

This is the complete model — both the local HTTP bridge and the MCP transport on top of it. The short version in the main [README](../README.md#security-model) is the summary; this is the reference a reviewer or a security-conscious user actually wants.

## Network exposure

The bridge (`sigmai/bridge_server.py`) binds to `127.0.0.1` and only `127.0.0.1`; starting it with any other host raises `ValueError` before a socket ever opens. Every request handler checks the connecting client's address a second time and answers `403 Only localhost requests are accepted` to anything that isn't `127.0.0.1` / `localhost` / `::1` — belt and suspenders, since a misconfigured `host` argument should not be the only thing standing between the bridge and the network. `/health` is the one endpoint that answers without a token, and even it is local-only; it returns whether the bridge is running, the plugin and QGIS versions, the auth scheme, and the current consent mode — enough for a client to distinguish "not running" from "wrong token" without learning anything about the project.

If the default port (8765) is taken, the bridge scans forward up to 20 ports and fails with a clear message rather than silently binding somewhere unexpected.

## Authentication

Every `/command` request needs `Authorization: Bearer <token>`, checked with `secrets.compare_digest` (constant-time, so response timing can't leak the token). The token is generated with `secrets.token_urlsafe(32)` when the bridge starts, written to a local session file the MCP server reads, and — unless the user opts into **Keep the same token between QGIS sessions** in the panel's Advanced tab — regenerated on every start, so a client holding a stale token from a previous session is locked out rather than silently still working. It is a local session credential, not a cloud credential: it authorises one running QGIS process, never leaves the machine as part of normal operation, and is excluded by name from the packaged plugin zip and from application logs.

## The consent layer

`sigmai/consent.py` decides whether a write action runs, in one of three modes the user sets in the panel's **Access** tab:

| Mode | Behaviour |
|---|---|
| `read_only` (default) | Reads and simulations (`dry_run`) always work. A write is refused with a message telling the assistant to show the plan and ask the user to unlock — so it stops instead of retrying. |
| `ask` | Each write opens a decision dialog naming the action, its category (see below) and the files it would touch. The user approves once, denies, or approves the whole category for the rest of the session. |
| `allow_session` | Writes proceed without a prompt, still bounded by the output folders and per-session limits below. |

Actions are grouped into categories (cartography, symbology, layers, raster, vector operations, Processing, workflows, data sources, databases, GPS/GPX, user profile, …) so that approving one, e.g. "compose and export maps", does not implicitly approve an unrelated one, e.g. "reorganise the layer tree".

Two controls apply in every mode:

- **Output folders** — an allowlist of directories a write may target. A path outside it is refused before the action runs, independent of consent mode.
- **Per-session limits** — default caps of 200 project-changing writes, 60 exports and 120 Processing runs per session, so a runaway loop stops instead of consuming the whole session's budget silently.

The **Activity** tab in the panel is the audit trail: every decision — allowed, denied, denied for a limit, denied for an output-folder violation — is recorded with a timestamp, and it is exportable. Logs and audit records are built to exclude tokens, passwords and other credentials by construction, never by redaction after the fact.

### What consent never covers

A fixed set of actions is excluded from every consent mode, not just the strict ones — `install_plugin_from_folder`, `install_plugin_from_zip`, `install_qgis_plugin_from_repository`, `update_plugin_from_folder`, `uninstall_plugin`, `enable_plugin`, `disable_plugin`, `reload_plugin`, `download_qgis_plugin_zip`, `self_apply_update`, `self_stage_update`, `self_rollback`, and `dev_execute_qgis_python`. These change the environment SIGMAI itself runs in, or execute arbitrary Python. Consent — even "allow for this session" — cannot approve them; they require the user's own click in the QGIS interface, and the Python one additionally requires Developer Mode.

## The command surface

`sigmai/permissions.py` is an allowlist, not an evaluator: every one of the catalogued commands is a specific, typed Python handler with a declared permission level (`read_only`, `safe_write`, `project_write`, `plugin_write`, `dangerous_plugin_write`, `developer`, `unsafe_developer`), whether it requires explicit confirmation, and whether it supports `dry_run`. There is no code path from an MCP tool call to an arbitrary Python `eval`/`exec` in normal operation — the only handler at the `unsafe_developer` level is the one Developer Mode itself gates.

## Developer Mode

Off by default. Turning it on (`plugin.py`'s `toggle_dev_mode`) shows a warning dialog in QGIS and then requires typing `SIM` into a confirmation box — a deliberate typed action, not a checkbox a script could tick unattended. It is the only route to `dev_execute_qgis_python`, and it can be turned off from the same control at any time.

## File safety

An existing output file is never overwritten unless the call explicitly sets `confirm_overwrite: true` — this applies uniformly across export, raster and vector-write commands, independent of consent mode.

## Network egress for basemaps and OGC services

Loading a remote XYZ, WMS, WFS or ArcGIS REST layer (`sigmai/qgis_actions/data_sources.py`) is a `safe_write`-level action like any other, but a request whose URL is not local additionally requires `confirm_network: true` — the model has to say, in the same call, that it means to make the QGIS process fetch data from an external server. A licensed source (OpenStreetMap and similar) also requires an `attribution` string before the layer loads, so a generated map cannot silently drop the credit its source's licence requires.

## What this model does not claim

In the same spirit as the rest of this project: a few limits worth stating plainly rather than leaving implicit.

- Consent governs SIGMAI's own command surface. It does not sandbox what a Processing algorithm or a third-party QGIS plugin does once SIGMAI is authorised to run it — `sigmai_brief_plugin`'s risk classification for another plugin's algorithms is advisory information for the assistant, not an enforcement boundary.
- `allow_session` is a broad grant on purpose — it exists for a user actively driving the assistant, not as a background always-on mode. Nothing in SIGMAI decides when a session should end; that is the user closing QGIS or switching back to `read_only`.
- The bridge and the MCP server both trust the local machine: stdio between the AI client and the MCP process, and loopback HTTP between the MCP process and QGIS, are not encrypted, because both ends are the same machine and the same user. This model assumes the machine itself is not compromised; it does not defend against another local process reading the session file or the token.
