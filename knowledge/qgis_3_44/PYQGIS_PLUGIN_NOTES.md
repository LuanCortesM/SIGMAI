# PyQGIS Plugin Notes for SIGMAI

Primary sources: `pyqgis_developer_cookbook/plugins/*`, `pyqgis_developer_cookbook/processing`.

## Relevant APIs/classes/files

- `metadata.txt`
- `__init__.py`
- plugin class with `initGui()` and `unload()`
- `QgsApplication.processingRegistry()`
- `QgsProcessingProvider`
- `QgsSettings`
- `qgis.utils.plugins`
- `qgis.utils.active_plugins`

## Correct patterns

- A plugin must expose a `classFactory(iface)` in `__init__.py`.
- `metadata.txt` is central for display name, version, author, icon, category and optional `hasProcessingProvider=yes`.
- If a plugin provides Processing algorithms:
  - add `hasProcessingProvider=yes` to metadata;
  - create a provider class subclassing `QgsProcessingProvider`;
  - register it with `QgsApplication.processingRegistry().addProvider(provider)`;
  - remove it in `unload()`.

## Care points

- Do not import or execute arbitrary plugin code for static validation; use AST/static checks where possible.
- Runtime checks can use `qgis.utils.plugins` and `active_plugins`, but these are only meaningful inside QGIS.
- Self-management must avoid hot-reloading the running bridge aggressively.
- Package output must exclude `__pycache__`, `.pyc`, diagnostics, sessions, logs, tokens and Git metadata.

## SIGMAI command relation

- `inspect_plugin`
- `validate_metadata_txt`
- `check_plugin_imports`
- `check_plugin_structure`
- `check_plugin_resources`
- `check_plugin_icon`
- `check_processing_provider_registration`
- `check_plugin_algorithm_registration`
- `package_plugin_zip`
- `self_health_check`

## Tests needed in QGIS real

- Validate plugin `sigmai`.
- Confirm plugin is active/loaded.
- Confirm toolbar/menu actions exist.
- Confirm provider checks do not fail when plugin has no Processing provider.
- Confirm packaging excludes tokens/session files.

