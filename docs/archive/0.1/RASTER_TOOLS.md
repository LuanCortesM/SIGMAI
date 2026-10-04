# SIGMAI Raster Tools

SIGMAI exposes raster operations through explicit, auditable commands instead of opening the full Processing toolbox by default.

## Implemented Commands

| Command | Permission | Dry run | Purpose |
|---|---|---:|---|
| `load_raster_layer` | `safe_write` | yes | Load a local raster into the current QGIS project. |
| `raster_info` | `read_only` | no | Summarize CRS, extent, dimensions, pixel size and bands. |
| `raster_band_statistics` | `read_only` | no | Compute band minimum, maximum, mean and standard deviation through QGIS. |
| `raster_metadata_report` | `read_only` | no | Generate a safe technical summary for a raster layer. |
| `raster_reproject` | `safe_write` | yes | Reproject raster through `gdal:warpreproject`. |
| `raster_clip_by_extent` | `safe_write` | yes | Clip raster by a supplied extent through `gdal:cliprasterbyextent`. |
| `raster_clip_by_mask` | `safe_write` | yes | Clip raster by vector mask through `gdal:cliprasterbymasklayer`. |
| `raster_slope` | `safe_write` | yes | Generate slope raster through `gdal:slope`. |
| `raster_aspect` | `safe_write` | yes | Generate aspect raster through `gdal:aspect`. |
| `raster_hillshade` | `safe_write` | yes | Generate relief shading through `gdal:hillshade`. |
| `raster_contours` | `safe_write` | yes | Generate contour lines through `gdal:contour`. |
| `raster_polygonize` | `safe_write` | yes | Polygonize raster classes through `gdal:polygonize`. |

## Safety Model

- Raster commands do not execute arbitrary Python.
- Output paths are checked before writing.
- Existing outputs require `confirm_overwrite=true`.
- Terrain commands warn when the raster CRS is geographic.
- Processing remains allowlisted; unsupported algorithms are blocked by default.

## Typical Workflow

1. Load an elevation raster with `load_raster_layer`.
2. Inspect it with `raster_info` and `raster_band_statistics`.
3. Reproject to a metric CRS when needed with `raster_reproject`.
4. Generate terrain context with `raster_hillshade`, `raster_slope` or `raster_contours`.
5. Use the resulting layers in professional cartographic layouts.

## Planned Additions

- `raster_calculator`
- `raster_reclassify`
- `raster_zonal_statistics`
- batch raster workflows
- background jobs for heavy terrain operations
