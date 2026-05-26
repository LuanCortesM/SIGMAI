# Diagnose Project

```text
python codex_plugin/client/sigmai_client.py status --token TOKEN
python codex_plugin/client/sigmai_client.py project-info --token TOKEN
python codex_plugin/client/sigmai_client.py list-layers --token TOKEN
```

Then inspect:

- `invalid_layers`
- `layers_without_crs`
- layer CRS values versus `project_crs`
