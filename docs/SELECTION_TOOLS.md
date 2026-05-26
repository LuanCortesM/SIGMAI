# SIGMAI Selection Tools

Selection commands let an AI agent mark or extract features safely. Selection changes project state, while extraction creates a new output and does not alter the source layer.

## Commands

- `select_by_expression`
- `select_by_attribute`
- `select_by_location`
- `extract_by_expression`
- `extract_by_attribute`
- `extract_by_location`

## Safety

- Commands support `dry_run`.
- Source layers are not edited.
- Extraction uses `TEMPORARY_OUTPUT` or explicit output paths.
- In-place destructive edits are not part of this command family.

## Notes

Spatial selection depends on QGIS Processing behavior and should be validated with real project layers before publication workflows.
