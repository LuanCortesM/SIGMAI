# SIGMAI Vector Analysis Tools

Vector analysis tools wrap safe QGIS Processing algorithms behind explicit high-level commands. They are preferred over unrestricted `run_processing`.

## Existing GIS Core

- `validate_geometries`
- `fix_geometries`
- `buffer`
- `clip`
- `dissolve`
- `reproject_layer`
- `export_layer`

## Level 6 Additions

- `intersection`
- `union`
- `difference`
- `centroids`
- `multipart_to_singleparts`
- `count_points_in_polygon`

## Safety

- Commands support `dry_run`.
- Outputs are new layers/files; source data is not edited.
- Algorithms remain allowlisted.
- Overwrite protection remains active for file outputs.
