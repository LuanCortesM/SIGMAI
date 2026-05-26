# SIGMAI Client

This client talks to the QGIS plugin through the local HTTP bridge.

## Examples

```text
python sigmai_client.py status --token TOKEN
python sigmai_client.py capabilities --token TOKEN
python sigmai_client.py environment --token TOKEN
python sigmai_client.py list-layers --token TOKEN
python sigmai_client.py project-info --token TOKEN
python sigmai_client.py layer-info --layer-id LAYER_ID --token TOKEN
python sigmai_client.py list-layouts --token TOKEN
python sigmai_client.py list-plugins --token TOKEN
python sigmai_client.py inspect-plugin --plugin-name sigmai --token TOKEN
python sigmai_client.py validate-metadata --plugin-name sigmai --token TOKEN
python sigmai_client.py recent-errors --token TOKEN
python sigmai_client.py get-logs --tail 200 --token TOKEN
python sigmai_client.py command --json "{\"action\":\"status\"}" --token TOKEN
```

You can also set:

```text
SIGMAI_TOKEN=TOKEN
```
