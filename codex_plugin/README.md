# SIGMAI for Codex
### Secure GIS-AI Interface

This kit teaches Codex how to work with QGIS through SIGMAI, the Secure GIS-AI Interface.

Public name and plugin identity: SIGMAI.

Author: MACIEL, L. S. C.  
Email: herpetomantiqueira@gmail.com

## Rules for Agents

- Always call `status` before other commands.
- Prefer SIGMAI MCP tools when available.
- If MCP is unavailable, use `python tools/sigmai.py`.
- If CLI is unavailable, use `client/sigmai_client.py`.
- If discovery fails, ask for the pairing code shown in QGIS.
- Always call `get_capabilities` after `status`.
- Always call `list_layers` before operating on layers.
- Always inspect CRS before spatial analysis.
- Prefer high-level SIGMAI commands such as `diagnose_crs`, `validate_geometries`, `buffer`, `clip`, `dissolve`, `reproject_layer`, and `export_layer` before using generic `run_processing`.
- Never invent layer ids or layer names.
- Never overwrite output files unless the user explicitly confirms that overwrite is acceptable.
- Prefer structured SIGMAI commands over free-form instructions.
- Explain complex workflows before running them.
- Do not use Developer Mode Python execution for normal GIS workflows.
- Use `dry_run` before modifying project state when the command supports it.
- Produce a workflow report for multi-step work.

## Client

The Python client is in `client/sigmai_client.py`.

```text
python codex_plugin/client/sigmai_client.py status --token TOKEN
python codex_plugin/client/sigmai_client.py list-layers --token TOKEN
```

## Skills

The skills in `skills/` describe common safe GIS workflows:

- Diagnose a project.
- Create a map from user intent.
- Run Processing algorithms.
- Create map layouts.
- Fix CRS issues.
- Export maps.
- Develop QGIS plugins with bridge-assisted diagnostics.
- Test plugins inside a real QGIS environment.
- Collect debugging evidence.
- Generate workflow reports.
