# SIGMAI Full QGIS Coverage Roadmap

SIGMAI expands QGIS coverage in safe, testable phases.

| Phase | Area | Goal |
|---|---|---|
| 1 | Cartography | Complete maps with layout items, styles, export and reports. |
| 2 | Vectors, attributes and expressions | Query, select, sample, calculate and join safely. |
| 3 | Symbology and labels | Categorized/graduated styles, labels and layer tree control. |
| 4 | Raster core | Load, inspect, clip, reproject, slope, aspect, hillshade and contours. |
| 5 | Processing profiles | Safe allowlist profiles for vector, raster, cartography and developer use. |
| 6 | Workflows | Plan, dry-run, execute and report multi-step workflows. |
| 7 | Jobs | Use queue/QgsTask patterns for long operations without blocking QGIS. |
| 8 | Atlas and reports | Batch exports, map books and technical reports. |
| 9 | Data sources and OGC | GPX, GPKG, WMS/WFS/XYZ and database inspection with masked secrets. |
| 10 | Plugin super mode | Plugin skeletons, publication checks, smoke tests and releases. |
| 11 | MCP and multi-IA | Formal tool groups for Codex, Claude, Cursor, VS Code and MCP clients. |
| 12 | Future QGIS areas | Point cloud, mesh, 3D and QGIS Server readiness. |

Security rules remain constant: localhost only, bearer token, session discovery, no arbitrary Python execution, dry-run where applicable, confirmation for dangerous actions and auditable logs.

## Maturity Levels

| Level | Capability | Status |
|---:|---|---|
| 5 | Cartographic Map Generation Capable | Confirmed with 30/30 and 200/200 rendered maps. |
| 6 | Vector Analysis and Attribute Capable | Runtime validated after QGIS restart; initial regression passed 19/19. |
| 7 | Professional Cartography Capable | Validated with 50/50 professional maps A/A+ and authorship checks. |
| 8 | Raster Core and Workflow Foundation Capable | Validated with raster and workflow deep regressions. |
| 9 | Job Queue and Long Processing Foundation Capable | Validated as a safe foundation for read-only and dry-run background jobs. |
| 10 | Atlas and Report Foundation Capable | Validated with atlas/report foundation regression and protected blocks. |
| 11 | Data Sources, OGC, GPS and Database Foundation Capable | Validated for local inspection, GPX and protected OGC/database operations. |
| 12 | Plugin Orchestration Foundation Capable | Validated with plugin inventory, adapter report and allowlist blocking. |
| 13 | Multi-IA QGIS Platform | MCP formal foundation validated with manifest, token masking, read-only/dry-run wrappers and dangerous-action blocks. |
| 14 | Broad QGIS Ecosystem Coverage | Coverage roadmap, public release checklist and automatic maturity evidence model implemented. |
