# QGIS Diagnose Project

Use this skill when the user asks Codex to inspect, diagnose, summarize, or troubleshoot the currently open QGIS project through SIGMAI.

## Workflow

1. Ask the user for the SIGMAI token if it is not available in `SIGMAI_TOKEN`.
2. Call `status`.
3. Call `get_capabilities`.
4. Call `get_project_info`.
5. Call `list_layers`.
5. Identify invalid layers, layers without CRS, CRS mismatches, empty projects, and missing layouts.
6. Report findings with concrete layer ids and names from the bridge response.

## Safety

- Do not assume a CRS.
- Do not invent layer names.
- Do not run Processing algorithms during diagnosis unless the user asks.
- Do not modify the project during diagnosis.
