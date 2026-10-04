# SIGMAI Expression Tools

SIGMAI uses QGIS expressions as a safe alternative to arbitrary Python execution. Expressions can filter, query and evaluate layer data through QGIS' own expression engine.

## Commands

- `validate_expression`: parser validation and referenced column reporting.
- `evaluate_expression`: evaluates an expression over a bounded sample of features.
- `query_features`: returns sampled features matching an expression.

## Safety

- No Python `eval` or `exec`.
- No mutation of source data.
- Results are limited by `max_features`.
- Parser/evaluation errors are returned as structured JSON.

## Example

```json
{
  "action": "query_features",
  "params": {
    "layer_id": "...",
    "expression": "\"NM_MUN\" = 'Cruzeiro'",
    "max_features": 10
  }
}
```
