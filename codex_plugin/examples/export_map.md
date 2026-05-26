# Export Map

List layouts:

```text
python codex_plugin/client/sigmai_client.py project-info --token TOKEN
```

Export an existing layout:

```text
python codex_plugin/client/sigmai_client.py command --token TOKEN --json "{\"action\":\"export_layout\",\"params\":{\"layout_name\":\"Mapa_Final\",\"format\":\"pdf\",\"path\":\"C:/saida/mapa_final.pdf\"}}"
```

If the output file already exists, add `confirm_overwrite: true` only after explicit user confirmation.
