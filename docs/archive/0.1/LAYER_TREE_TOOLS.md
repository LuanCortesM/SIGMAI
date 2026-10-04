# SIGMAI Layer Tree Tools

SIGMAI exposes layer tree controls as safe, auditable commands. These commands change QGIS project state only, never source data.

## Commands

- `list_layer_tree`: read-only snapshot of layer order, groups, visibility and layer ids.
- `set_layer_visibility`: toggles one layer on/off in the project layer tree.
- `move_layer_order`: moves a layer to a target top-level index.
- `create_layer_group`: creates a layer tree group.
- `move_layer_to_group`: moves a layer node into an existing or newly created group.

## Safety

- Write commands support `dry_run`.
- No command removes layers or deletes data.
- Responses include before/after order where practical.
- These commands are useful before cartographic export because map visibility and legend content depend on layer tree state.
