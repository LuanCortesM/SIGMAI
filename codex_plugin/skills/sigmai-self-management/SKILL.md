# SIGMAI Self Management

Use this skill when the user asks to inspect, backup, validate, stage, update, or roll back the SIGMAI plugin itself.

## Workflow

1. Call `status`.
2. Call `self_inspect`.
3. Call `self_health_check`.
4. For an update folder, call `self_validate_update`.
5. Call `self_stage_update` with `dry_run=true`.
6. Create `self_backup`.
7. Apply only with `self_apply_update` and explicit confirmation.
8. Tell the user when QGIS/plugin restart is required.
9. For rollback, use `self_rollback` with an explicit backup path and confirmation.

## Rules

- Never modify the running Bridge directly.
- Always preserve backup and rollback.
- Do not attempt aggressive hot reload of the running Bridge.
- Do not expose bearer tokens in user-facing output unless the user asks for debug details.
