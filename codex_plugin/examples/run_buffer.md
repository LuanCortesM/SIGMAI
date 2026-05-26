# Run Buffer

First list layers and choose the exact layer id:

```text
python codex_plugin/client/sigmai_client.py list-layers --token TOKEN
```

Then send a structured command:

```text
python codex_plugin/client/sigmai_client.py command --token TOKEN --json "{\"action\":\"run_processing\",\"params\":{\"algorithm\":\"native:buffer\",\"parameters\":{\"INPUT\":\"LAYER_ID\",\"DISTANCE\":50,\"SEGMENTS\":8,\"OUTPUT\":\"TEMPORARY_OUTPUT\"}}}"
```
