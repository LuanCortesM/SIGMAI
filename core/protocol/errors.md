# Errors

Errors are structured objects:

```json
{
  "code": "TOKEN_INVALID",
  "message": "Invalid or missing bearer token.",
  "details": {}
}
```

## Common Codes

- `BAD_REQUEST`: malformed JSON or invalid command shape.
- `TOKEN_INVALID`: missing or invalid bearer token.
- `FORBIDDEN_REMOTE_HOST`: request did not come from localhost.
- `ACTION_NOT_ALLOWED`: action is not part of the protocol whitelist.
- `DANGEROUS_COMMAND`: command contains blocked keys or values.
- `DRY_RUN_NOT_SUPPORTED`: dry-run was requested for an action that does not support it.
- `LAYER_NOT_FOUND`: requested layer id does not exist.
- `PLUGIN_NOT_FOUND`: requested plugin folder was not found.
- `LAYOUT_ALREADY_EXISTS`: requested layout name already exists.
- `PROCESSING_NOT_AVAILABLE`: QGIS Processing could not be imported or initialized.
- `PROCESSING_ALGORITHM_NOT_FOUND`: algorithm id was not found.
- `OVERWRITE_BLOCKED`: output path already exists and overwrite was not confirmed.
- `LAYOUT_NOT_FOUND`: requested layout does not exist.
- `EXPORT_FAILED`: layout export failed.
- `INTERNAL_ERROR`: unexpected runtime error.
