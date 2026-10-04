# Cartographic Template Metrics

Approximate template metrics extracted from reference maps.

| Template | Main Map | Legend | Inset | Metadata | White Space | Best Use |
|---|---:|---:|---:|---:|---:|---|
| `scientific_two_panel` | 65-80% | 5-10% | 0-5% | 3-6% | 10-20% | A/B comparisons, bias, density |
| `environmental_focus_map` | 58-78% | 8-18% | 5-15% | 4-8% | 8-18% | RPPN, trails, suitability, environmental planning |
| `topographic_sheet` | 55-75% | 10-22% | 5-12% | 8-18% | 5-12% | official-style technical products |
| `terrain_presentation_plate` | 75-95% | 0-8% | 0-8% | 2-6% | 3-10% | terrain, REM, hillshade, risk surfaces |
| `tourism_environmental_map` | 55-75% | 8-16% | 5-15% | 8-20% | 5-12% | protected areas, roads, attractions |
| `multi_detail_density_map` | 55-75% | 3-8% | 15-35% | 2-5% | 5-10% | traffic, hotspots, repeated detail panels |
| `municipal_locator_map` | 45-65% | 0-5% | 15-30% | 0-5% | 20-40% | context only |
| `biodiversity_records_map` | 65-80% | 5-10% | 0-10% | 4-8% | 10-20% | records, effort, sampling bias |
| `risk_suitability_map` | 60-80% | 8-15% | 5-15% | 4-8% | 8-15% | risk/adequability interpretation |
| `black_white_publication_map` | 70-88% | 2-8% | 0-8% | 3-8% | 8-18% | article figures |

## Failure Conditions

- Main map below 50% for analytical map: maximum grade C.
- Legend above 25% without grouping: maximum grade B.
- Metadata missing source/CRS/date: maximum grade B for scientific maps.
- Inset present but unrelated to spatial question: maximum grade B.
- White space above 35% without design purpose: maximum grade B.
