# Map Visual Scoring Rules

These rules should guide `evaluate_map_quality`.

| Rule ID | Severity | Max Grade If Violated | Detection |
|---|---|---:|---|
| `NO_DEBUG_TEXT_ON_FINAL_MAP` | critical | C | text pattern |
| `HUMANIZED_LEGEND_LABELS` | high | B | text pattern |
| `MAP_HAS_DOMINANT_LAYER` | high | B | layer roles/output image |
| `LEGEND_NOT_LAYER_DUMP` | critical | C | layout items |
| `SPATIAL_MESSAGE_CLEAR` | high | B | map intent/manual |
| `SCALE_NOT_DEGREES_UNLESS_ALLOWED` | critical | C | CRS/scale metadata |
| `NORTH_ARROW_NOT_DOMINANT` | medium | B | layout item size |
| `FOOTER_HAS_SOURCE_AUTHOR_CRS_DATE` | high | B | text pattern |
| `LOGO_NOT_DOMINANT` | medium | B | layout item size |
| `MAP_BODY_LARGE_ENOUGH` | high | C | layout item area |
| `WHITE_SPACE_NOT_EXCESSIVE` | medium | B | output image |
| `INSET_HAS_CONTEXT_PURPOSE` | medium | B | layout item + params |
| `BACKGROUND_DOES_NOT_COMPETE` | high | B | layer roles/style |
| `ROUTES_READABLE_OVER_BACKGROUND` | high | C | style/output image |
| `IMPORTANT_BOUNDARIES_IDENTIFIABLE` | high | C | layer roles/labels |
| `THUMBNAIL_READABILITY_OK` | medium | B | downsampled PNG |

## Grade Logic

`A+`: professional/publication-ready, clear message, clean legend, correct scale/CRS, strong hierarchy.

`A`: professional map with minor limitations.

`B`: usable technical map with minor clarity or polish issues.

`C`: technically valid but visually or semantically weak.

`D`: likely misleading, blank-ish, confusing or missing key map elements.

`E`: failed/blank/no usable output.

## Required Evidence For A/A+

- clear map intent;
- dominant primary layer;
- semantic legend;
- readable routes/boundaries;
- CRS and scale valid;
- footer complete;
- no raw/debug labels;
- map readable as thumbnail.
