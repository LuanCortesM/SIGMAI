# QGIS Run Processing

Use this skill when the user wants to run a QGIS Processing algorithm through SIGMAI.

## Workflow

1. Call `status`.
2. Call `list_layers`.
3. Confirm the target layer id from the bridge response.
4. Check CRS relevance for the operation.
5. Build a structured `run_processing` command.
6. For file outputs, refuse overwrite unless the user explicitly confirms and set `confirm_overwrite: true`.
7. Run the command and summarize the structured result.

## Example

```json
{
  "action": "run_processing",
  "params": {
    "algorithm": "native:buffer",
    "parameters": {
      "INPUT": "layer-id",
      "DISTANCE": 50,
      "SEGMENTS": 8,
      "OUTPUT": "TEMPORARY_OUTPUT"
    }
  }
}
```

