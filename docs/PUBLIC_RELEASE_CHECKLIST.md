# SIGMAI Public Release Checklist

## Metadata

- `metadata.txt` uses public name `SIGMAI`.
- Plugin author is `MACIEL, L. S. C.`.
- Email is `herpetomantiqueira@gmail.com`.
- Package path is `sigmai`.
- Homepage, tracker and repository point to `https://github.com/LuanCortesM/SIGMAI`.
- Legacy project names appear only as historical/internal compatibility text, never as public product identity.

## Security

- Bridge binds only to `127.0.0.1`.
- Bearer token is required.
- Session discovery is local.
- Pairing code does not replace token authentication.
- Normal mode does not expose unrestricted Python execution.
- Developer Mode is local, explicit, warning-protected and disabled by default.
- No `eval`, `exec`, shell or unrestricted subprocess command execution in Bridge handlers.
- Dangerous plugin/self-management actions require explicit confirmation.
- Generated reports do not expose full tokens or secrets.

## Cartography And Authorship

- Plugin author is separate from map author.
- Public maps do not automatically use `MACIEL, L. S. C.` as map author.
- Maps support `map_author`, organization, data source and generic SIGMAI/QGIS credit.
- CRS, scale, legend, north arrow and data source are documented in map outputs.

## Packaging

- No user-specific absolute paths in release docs, examples or generated plugin package.
- No workspace-specific local folder names in public release files.
- Local documentation mirrors and QGIS documentation ZIPs are not packaged.
- Logs, caches, `__pycache__`, diagnostics and test outputs are excluded from release ZIP.
- Icons and README are included.
- Public release ZIP is generated in `dist/sigmai.zip`.
- Run `python tools/prepare_public_release.py` before publishing.
- The public repository must not include local diagnostics, generated maps, local documentation mirrors, temporary ZIP files or machine-specific reports.

## Tests

- `python -m compileall -q sigmai codex_plugin tools mcp_server tests`
- `python -m unittest discover tests`
- Contextual capability regression.
- Professional map regression.
- Raster deep regression.
- Workflow deep regression.
- Job queue regression.
- Atlas/report regression.
- Data sources regression.
- Plugin orchestration regression.
- MCP regression.
- Full platform regression.

## Release Decision

Release is blocked if:

- token or credentials appear in logs/docs;
- server can bind to non-local hosts;
- generated maps hard-code plugin author as map author;
- package contains personal paths, diagnostics or test outputs;
- package contains legacy names or local laboratory paths;
- metadata is not suitable for public repository submission;
- critical regressions fail.

