# PyQGIS Processing Notes for SIGMAI

Primary sources: `user_manual/processing/console`, `pyqgis_developer_cookbook/processing`, `processing_algs/*`.

## Relevant APIs

- `from qgis import processing`
- `processing.run(algorithm_id, parameters)`
- `processing.runAndLoadResults(algorithm_id, parameters)`
- `QgsApplication.processingRegistry().algorithms()`
- `QgsApplication.processingRegistry().algorithmById(id)`
- `processing.algorithmHelp(id)`
- `QgsProcessingProvider`

## Correct patterns

- Use algorithm IDs, e.g. `native:buffer`, not display names.
- Discover algorithms through the Processing registry.
- Use `algorithmHelp()` / algorithm metadata to understand parameters.
- `processing.run()` returns a dict of outputs but does not automatically add outputs to the project.
- `processing.runAndLoadResults()` loads outputs, but SIGMAI should prefer explicit output handling for auditability.

## Parameter notes

- Vector/raster inputs can be layer IDs, layer names, source paths or layer objects.
- Enum parameters use integer values.
- Boolean parameters use booleans.
- CRS parameters accept EPSG-like strings.
- Extents must be provided in expected QGIS extent syntax for generic Processing.
- Outputs can be file paths, `memory:` or temporary outputs depending on algorithm.

## SIGMAI implications

- Keep `run_processing` behind an allowlist.
- Prefer high-level commands (`buffer`, `clip`, `fix_geometries`, `reproject_layer`) for real writes.
- Use `dry_run` for generic Processing parameter validation.
- Avoid long Processing calls on the QGIS main thread; future work should use jobs/tasks.

## Relevant algorithms

Vector:

- `native:buffer`
- `native:clip`
- `native:dissolve`
- `native:fixgeometries`
- `native:reprojectlayer`
- `native:multiparttosingleparts`
- `native:centroids`
- `native:intersection`
- `native:union`
- `native:difference`
- `native:extractbyattribute`
- `native:extractbylocation`

Raster candidates:

- GDAL warp/reproject
- GDAL clip raster by extent/mask
- QGIS/GDAL slope, aspect, hillshade
- contour
- polygonize

## Risks

- Long operations block QGIS if not routed to task/job infrastructure.
- Generic parameter dictionaries can be ambiguous for AI agents.
- Output overwrite must remain blocked without confirmation.
- Processing provider availability differs by installation.

## Tests needed in QGIS real

- Check allowlist algorithms exist.
- Run high-level commands with small test layers.
- Keep generic `run_processing` real execution conservative.
- Verify outputs are created and reloadable.

