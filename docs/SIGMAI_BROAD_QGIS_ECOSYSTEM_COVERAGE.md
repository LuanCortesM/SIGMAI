# SIGMAI Broad QGIS Ecosystem Coverage

SIGMAI is now a validated local AI-QGIS bridge through Level 13. Level 14 is a coverage and maturity layer: it maps the remaining QGIS ecosystem, tracks evidence and prevents unsupported maturity claims.

| Area | Current status | Risk | Commands needed | Test data needed | Priority |
|---|---|---|---|---|---|
| Vector editing | Planned | High | edit session, add/update/delete feature with confirmation, rollback report | disposable vector layer | Medium |
| Advanced geometry | Partial | Medium | simplify, smooth, densify, check validity profiles | polygon/line datasets | High |
| Topology | Planned | Medium | topology rules, gap/overlap checks, topology report | polygon fabric | Medium |
| Network analysis | Planned | Medium | shortest path, service area, graph validation | routable line network | Medium |
| Raster advanced | Partial | Medium | raster calculator, reclassify, zonal statistics, resample, align | DEM and categorical raster | High |
| Point cloud | Planned | High | pointcloud_info, clip, export | LAS/LAZ sample | Low |
| Mesh | Planned | High | mesh_info, export vertices/faces | mesh sample | Low |
| 3D | Planned | High | 3D scene report, elevation profile, layout 3D map | DEM + vector | Low |
| Temporal controller | Planned | Medium | temporal layer report, time filter | temporal vector/raster | Low |
| Annotation | Planned | Low | list/create/update annotations | project sample | Low |
| Forms and relations | Planned | Medium | inspect forms, relations, constraints | relational project | Medium |
| Layout advanced | Partial | Medium | advanced grids, map themes, overview maps, templates | project layouts | High |
| Atlas advanced | Foundation | Medium | full QgsLayoutAtlas export, dynamic titles, batch image export | coverage layer | High |
| Reports | Foundation | Medium | PDF report renderer, analysis report templates | project with outputs | High |
| Model designer | Planned | Medium | inspect models, run safe models, model report | processing model | Medium |
| Processing history | Planned | Low | list history, summarize recent algorithms | QGIS processing history | Medium |
| QGIS Server | Planned | Medium | WMS/WFS readiness, OGC metadata report | server-ready project | Medium |
| Database manager | Foundation | High | read-only connection inspection, PostGIS layer loading | test database | Medium |
| Field calculator | Partial | Medium | calculate_field with dry-run/confirmation | vector table | High |
| Geometry generator | Planned | Medium | inspect/apply geometry generator styles | vector layer | Medium |
| Style manager | Planned | Low | list symbols, import/export style library | style DB | Medium |
| Authentication manager | Planned | High | masked auth config inventory only | configured auth profiles | Low |
| Plugin manager | Working foundation | High | adapter tests, allowlist management, plugin release checks | installed plugins | High |

Security notes:

- Network and database actions stay read-only by default.
- Credentials are always masked.
- Editing commands require dry-run, confirmation and disposable test data before public release.
- No arbitrary Python execution is allowed.

