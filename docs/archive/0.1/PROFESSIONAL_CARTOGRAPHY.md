# SIGMAI Professional Cartography

This document describes the first professional cartography layer in SIGMAI.

## Commands

- `list_layout_templates`
- `generate_professional_map`
- `evaluate_map_quality`
- `choose_style_profile`
- `apply_cartographic_palette`
- `validate_map_readability`
- `detect_visual_collisions`
- `suggest_layout_improvements`

## Templates

- `scientific_basic`
- `scientific_publication`
- `environmental_report`
- `minimal_clean`
- `technical_dark`
- `atlas_page`

## Style Profiles

- `scientific_soft`
- `environmental_green`
- `technical_blue`
- `monochrome_publication`
- `contrast_highlight`
- `terrain_context`
- `biodiversity_report`
- `protected_area_map`

## Safety

Professional map generation remains a `safe_write` command. It creates layouts and exported files, but does not edit original data.

The command keeps localhost-only access, token authentication, output overwrite protection, dry-run support, filtered legends, CRS-safe layout extents and visual map quality assessment.

## Validation

```powershell
python tools\run_sigmai_professional_map_regression.py --limit 50
```
