# Examples

## Capabilities

```json
{
  "schema_version": "0.2",
  "request_id": "cap-1",
  "action": "get_capabilities"
}
```

## Environment

```json
{
  "schema_version": "0.2",
  "request_id": "env-1",
  "action": "get_qgis_environment"
}
```

## Inspect Plugin

```json
{
  "schema_version": "0.2",
  "request_id": "plugin-1",
  "action": "inspect_plugin",
  "params": {
    "plugin_name": "TopoTrail"
  }
}
```

## Dry-Run Layout Creation

```json
{
  "schema_version": "0.2",
  "request_id": "layout-1",
  "action": "create_layout",
  "dry_run": true,
  "params": {
    "layout_name": "Mapa_Final"
  }
}
```
