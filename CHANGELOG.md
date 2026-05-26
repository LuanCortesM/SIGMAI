# Changelog

## 0.1.0 - 2026-05-25

Initial public release preparation for SIGMAI.

### Added

- QGIS plugin package under `sigmai/`.
- Local secure bridge with bearer-token session authentication.
- Capability registry, permissions, command validation and audit-friendly responses.
- Cartography, vector, raster, workflow, plugin diagnostics and developer-mode foundations.
- Public release audit, packaging checklist and authorship policy.

### Security

- Localhost-only bridge.
- Token-protected command endpoint.
- Normal mode blocks unrestricted Python execution.
- Developer Mode is explicit, warning-protected and disabled by default.
