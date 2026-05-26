# QGIS Run Analysis

Use this skill for GIS analysis workflows such as buffer, clip, dissolve, spatial join, raster slope, or reprojection.

## Workflow

1. Call `status`.
2. Call `get_capabilities`.
3. Call `list_layers`.
4. Inspect involved layers with `get_layer_info`.
5. Check CRS before spatial operations.
6. Prefer high-level commands when available.
7. If using `run_processing`, verify the algorithm id and parameters.
8. Use temporary outputs unless the user confirms a file path.
9. Use `dry_run: true` before modifying state when supported.
10. Summarize results and limitations.

## Safety

- Never overwrite outputs without explicit confirmation.
- Never assume projected units are meters unless CRS confirms it.
- Never run arbitrary Python for normal analysis.
