# Responses

Every response follows the same envelope:

```json
{
  "schema_version": "0.2",
  "request_id": "req-1",
  "ok": true,
  "action": "status",
  "data": {},
  "warnings": [],
  "errors": [],
  "meta": {
    "timestamp": "2026-05-17T16:00:00Z",
    "duration_ms": 12,
    "permission_level": "read_only",
    "qgis_version": "3.x"
  }
}
```

Failed responses keep the same shape:

```json
{
  "schema_version": "0.2",
  "request_id": "req-2",
  "ok": false,
  "action": "get_layer_info",
  "data": null,
  "warnings": [],
  "errors": [
    {
      "code": "LAYER_NOT_FOUND",
      "message": "Layer not found.",
      "details": { "layer_id": "abc" }
    }
  ],
  "meta": {
    "timestamp": "2026-05-17T16:00:00Z",
    "duration_ms": 3,
    "permission_level": "read_only"
  }
}
```
