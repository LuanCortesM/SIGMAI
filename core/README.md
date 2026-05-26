# SIGMAI Core Protocol

The core protocol is the stable contract shared by all SIGMAI clients and runtimes.
It is intentionally independent from QGIS, Codex, VS Code, or any other host.

## Principles

- Commands are JSON objects with a required `action`.
- Responses are JSON objects with `ok`, `action`, `data`, `warnings`, `errors`, and `meta`.
- Destructive or overwriting operations require explicit confirmation.
- Normal commands are structured actions, not free-form Python code.
- Implementations should log every accepted command and every failure.

## Core Actions

- `status`
- `list_layers`
- `get_project_info`
- `get_layer_info`
- `run_processing`
- `export_layout`
- `get_logs`

See `schemas/`, `protocol/`, and `examples/` for the full contract.
