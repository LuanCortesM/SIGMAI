# SIGMAI Cartographic Quality Model

SIGMAI evaluates generated maps through both structural and visual checks.

## Authorship Quality Rule

Publication maps must separate:

- plugin author;
- map author;
- data source;
- organization;
- software credit;
- processing method.

The plugin author must not be injected as the map author by default.

## Required Credit Fields

Cartographic commands can receive:

```json
{
  "map_author": "",
  "map_author_email": "",
  "organization": "",
  "data_source": "",
  "created_with": "SIGMAI - Secure GIS-AI Interface",
  "plugin_author": "MACIEL, L. S. C."
}
```

Only map-facing fields should be rendered in the map footer. Plugin author metadata remains available for SIGMAI technical provenance.
