# TopoTrail RPPN Map Design Guide

## Correct Map Type

The TopoTrail/RPPN map should be an:

`environmental_focus_map`

It should not be a generic professional map.

## Spatial Question

Do existing trails cross, approach or avoid TopoTrail suitability/risk zones inside or near the RPPN, Reserva Chico Nunes and Fazenda Batedor?

## Required Structure

- Main panel: zoomed RPPN/Fazenda/trail sector.
- Inset 1: Cruzeiro/SP locator.
- Inset 2: full TopoTrail model overview.
- Legend: grouped by meaning.
- Footer: sources, map author, CRS/datum, date.
- Note: limitations and invalid layers.

## Layer Roles

| Role | Layer Type | Visual Treatment |
|---|---|---|
| Primary result | TopoTrail overlap/suitability | warm highlight or clear green/yellow result |
| Route | existing trail | dark wine/black line with halo |
| Primary boundary | RPPN/Reserva | green or earth boundary, direct label |
| Secondary boundary | Fazenda Batedor | blue/gray boundary, direct label |
| Terrain context | hillshade/risk | muted grayscale/soft opacity |
| Administrative context | Cruzeiro/SP | thin neutral line, inset only if possible |

## Legend Groups

1. Resultado da analise.
2. Limites ambientais e fundiarios.
3. Trilhas.
4. Contexto fisico/topografico.
5. Dados de apoio.

## Avoid

- all layers with equal visual weight;
- raw QGIS filenames in legend;
- large municipal extent when local RPPN decision is the focus;
- very strong raster background;
- unlabelled RPPN/Fazenda boundaries;
- using Travessia Marins-Itaguare while it has no valid CRS/features;
- fake context panels.

## Quality Criteria

The map should be rejected or capped below A if:

- RPPN/Fazenda cannot be identified immediately;
- trail is not readable;
- overlap areas are not visually obvious;
- legend does not explain the analysis result;
- scale/CRS are absent or inconsistent;
- map looks like a screenshot of loaded layers rather than a designed product.
