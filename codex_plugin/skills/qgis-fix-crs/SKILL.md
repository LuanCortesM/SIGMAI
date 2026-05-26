# QGIS Fix CRS

Use this skill when the user asks to find or fix CRS problems.

## Workflow

1. Call `status`.
2. Call `get_project_info`.
3. Call `list_layers`.
4. Identify layers without CRS and layers whose CRS differs from the project CRS.
5. Explain the issue and ask for user confirmation before any transformation.
6. For reprojection, use `run_processing` with an appropriate QGIS Processing algorithm and a confirmed output path.

## Safety

- Do not assign or transform CRS silently.
- Do not assume the correct CRS for a layer.
- Prefer creating a new output layer over modifying source data.
