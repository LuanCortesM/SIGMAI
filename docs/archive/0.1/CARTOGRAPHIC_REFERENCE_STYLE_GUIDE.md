# Cartographic Reference Style Guide

This guide summarizes reusable design patterns extracted from the `Exemplos de Bons Mapas` folder. It is a guide for SIGMAI map generation, not a license to copy visual designs.

## Reading Order

A professional SIGMAI map should establish this order:

1. Title or theme.
2. Main spatial question.
3. Dominant visual layer.
4. Supporting context.
5. Legend and technical metadata.

If the reader cannot identify the main message in a thumbnail, the map should not receive grade A.

## Visual Hierarchy

Assign each layer a role before styling:

- `primary_result`: strongest thematic layer.
- `primary_boundary`: key study area boundary.
- `route_or_trail`: line feature that must remain readable.
- `terrain_context`: hillshade, DEM, slope, risk background.
- `administrative_context`: municipality, state, locator.
- `supporting_data`: secondary features.

Only one or two roles should dominate visually.

## Layout Families

Use:

- `environmental_focus_map` for RPPN, trail, suitability and risk interpretation.
- `scientific_two_panel` for comparisons.
- `topographic_sheet` for formal technical products.
- `terrain_presentation_plate` for relief/raster visual products.
- `density_hotspot_map` for intensity.
- `municipal_locator_map` for context only.

## Color

Use muted background and strong but controlled primary symbols.

Do not use saturated colors for every class. Saturation should mean importance.

## Boundaries

Important boundaries must be identifiable without guessing. Use:

- distinct hue;
- sufficient line width;
- optional casing/halo;
- direct label or callout when multiple boundaries overlap.

## Trails and Routes

Routes should be drawn above suitability/raster layers with:

- high contrast;
- line width adequate for export scale;
- halo or casing over complex backgrounds;
- consistent legend name.

## Terrain and Raster

Hillshade and terrain rasters support interpretation. They should not overpower the primary analytical layer unless the map is specifically a terrain presentation.

## Text

Use at most three type hierarchy levels:

- title;
- section/subtitle;
- technical note/labels.

Labels should name real features, not layer categories.

## Authorship

Keep plugin authorship separate from map authorship. Generated maps should show the user/map author, data sources, CRS and date. The plugin author is not automatically the map author.
