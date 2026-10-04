# SIGMAI Workflow Engine

The workflow layer is the foundation for chaining SIGMAI commands into auditable GIS procedures.

## Implemented Foundation

| Command | Purpose |
|---|---|
| `plan_workflow` | Validate and describe a sequence of SIGMAI commands. |
| `dry_run_workflow` | Validate a workflow and report expected steps without changing QGIS. |
| `execute_workflow` | Present but guarded; real execution is blocked until the job runner is enabled. |
| `save_workflow_template` | Save a reusable workflow JSON template. |
| `list_workflow_templates` | List local SIGMAI workflow templates. |
| `run_workflow_template` | Load a template and run it in dry-run mode by default. |

## Safety Policy

- Dangerous plugin/self-management actions are blocked inside workflows.
- Dry-run is preferred by default.
- Real chained execution is intentionally disabled until SIGMAI has a job runner with progress, cancellation and recovery.
- Workflow templates are local JSON files stored under the SIGMAI local application data folder.

## Next Implementation Step

The next phase is a real job queue using QGIS-safe task patterns:

- `start_job`
- `get_job_status`
- `get_job_result`
- `cancel_job`
- `list_jobs`
- `job_logs`

Long raster, atlas and batch Processing workflows should use jobs instead of blocking the Bridge.
