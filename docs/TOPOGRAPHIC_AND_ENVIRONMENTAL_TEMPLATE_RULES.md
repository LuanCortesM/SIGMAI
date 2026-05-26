# Topographic And Environmental Template Rules

## Environmental Focus Map

Purpose:

Show an environmental spatial question clearly, such as whether trails cross suitable/risky areas in protected/farm landscapes.

Required:

- main focused map;
- semantic legend;
- scale bar;
- north arrow or grid;
- CRS/datum;
- source;
- map author;
- date;
- overview or locator inset;
- direct labels for important boundaries.

Layer hierarchy:

1. primary result;
2. trails/routes;
3. protected/farm boundaries;
4. muted terrain/raster context;
5. administrative context.

Failure conditions:

- RPPN/Fazenda not identifiable;
- routes not readable;
- background raster dominates result;
- legend uses raw layer names;
- map extent too broad for local question.

## Topographic Sheet

Purpose:

Formal technical map with grid, scale, legend, marginalia and metadata.

Required:

- graticule/grid;
- map frame;
- scale bar and numeric scale when print size fixed;
- technical legend;
- CRS/projection/datum;
- index inset;
- source and publication metadata;
- declination/orientation note where relevant.

Failure conditions:

- missing CRS/projection;
- uncontrolled legend;
- no scale;
- informal typography;
- decorative north arrow replacing technical orientation.

## Terrain Presentation Plate

Purpose:

Show relief, raster intensity or morphology as the main visual object.

Required:

- dominant raster/terrain surface;
- minimal supporting layers;
- compact scale;
- restrained labels;
- optional small locator.

Failure conditions:

- too many vector overlays;
- hillshade too weak or too strong for the message;
- legend unrelated to raster meaning.
