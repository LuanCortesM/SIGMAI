# MCP security model

What the MCP server adds, and does not add, on top of the bridge. The complete model — bridge, token, consent, folders, limits, audit — is in [SECURITY_MODEL.md](SECURITY_MODEL.md).

- **Local only.** The server (`sigmai/mcp/sigmai_mcp.py`) talks to the bridge on the loopback interface and refuses a session file that points anywhere else. The bridge itself binds only to `127.0.0.1`, takes its port exclusively, and rejects non-local clients.
- **The token never reaches the model.** The server reads the bearer token from the local session file on every call and sends it only in the HTTP header to the bridge. No tool result, error or log line carries it; `tests/test_mcp_protocol.py` checks that a known token never appears in anything the model reads.
- **No code execution.** The 20 tools map to catalogued commands. `sigmai_run_command` reaches only the enabled commands of the catalogue; there is no tool that evaluates Python.
- **Consent is enforced by the bridge, not by the server.** Every write — from a dedicated tool or from `sigmai_run_command` — goes through the consent layer the user controls in the panel (read-only by default, ask every time, or allow for this session), within the authorised output folders and the per-session limits. Simulations (`dry_run`) always run and change nothing.
- **Some actions are never granted to an AI client.** Installing, updating, removing, enabling, disabling or reloading plugins, applying or rolling back a SIGMAI update, and executing Python are refused in every consent mode; they can be simulated, and they are reserved to the user through Developer Mode, enabled by hand in the panel.
- **Everything is recorded.** Consent decisions go to the audit trail shown in the panel's Activity tab, and the bridge log records each command without its token.
