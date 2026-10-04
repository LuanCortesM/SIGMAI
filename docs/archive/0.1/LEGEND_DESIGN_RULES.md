# Legend Design Rules

## Core Rule

A legend is an interpretation guide, not a dump of QGIS layer names.

## Required Practices

- Use human-readable names.
- Group entries by meaning.
- Order entries by visual importance.
- Show units for numeric raster/classes.
- Keep legend shorter than the map body can support.
- Rename temporary outputs before export.

## Recommended Groups

For environmental/trail maps:

1. Result of analysis.
2. Environmental/farm limits.
3. Trails/routes.
4. Terrain/risk context.
5. Administrative context.

For raster maps:

1. Main raster ramp with units.
2. Contours or derived classes.
3. Boundaries.
4. Context.

For topographic sheets:

1. Roads/routes.
2. Hydrography.
3. Land cover.
4. Relief/elevation.
5. Points of interest.
6. Administrative/index information.

## Penalize

- raw filenames;
- UUIDs;
- `clip_output`, `temp`, `final_final`;
- duplicate layers;
- empty legend entries;
- legend listing layers outside the map frame;
- legend larger than needed.
