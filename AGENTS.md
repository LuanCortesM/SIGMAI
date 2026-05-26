# SIGMAI Agent Instructions

SIGMAI separates responsibilities:

- QGIS plugin: executes GIS actions inside QGIS.
- Codex plugin: guides the agent and calls the bridge.
- Core protocol: defines commands, responses, errors, schemas, and examples.

Agent rules:

- Check `status` before any workflow.
- List layers before referencing a layer.
- Verify CRS before spatial analysis.
- Use structured JSON commands only.
- Never invent layer ids, layout names, or CRS values.
- Never overwrite outputs without explicit user confirmation.
- Do not add or use arbitrary Python execution in the MVP.
- Inspect bridge logs when a command fails.
