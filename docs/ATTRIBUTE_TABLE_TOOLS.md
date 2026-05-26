# SIGMAI Attribute Table Tools

Attribute table tools provide bounded, read-only inspection of vector layer attributes. They are designed for AI agents that need to understand data without dumping entire tables.

## Commands

- `list_fields`: returns field names, types and metadata.
- `sample_features`: returns a limited sample of feature attributes and optional geometry summaries.
- `inspect_attribute_table`: combines schema, feature count and sample rows.
- `field_statistics`: calculates basic statistics for one field.
- `unique_values`: returns a limited list of distinct values.

## Limits

- Results are capped with `max_features` or `limit`.
- Geometry is summarized instead of returned in full unless a command explicitly supports geometry output.
- Large layers should be queried incrementally.

## Use Cases

- Find a municipality name field before selection.
- Inspect fields before labels or categorized symbology.
- Get unique categories for legend design.
