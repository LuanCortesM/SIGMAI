# Connecting Claude to QGIS

SIGMAI speaks the [Model Context Protocol](https://modelcontextprotocol.io) over stdio. Claude launches the SIGMAI MCP server as a subprocess; that server finds the running QGIS through a local session file and talks to it over `127.0.0.1`.

You never paste a token anywhere. The token stays between the plugin and the session file on your own disk.

## The short version

1. In QGIS, open the SIGMAI panel and press **Iniciar ponte** (step 1).
2. In step 2, choose **Claude Desktop** or **Claude Code** and press **Copiar configuração**.
3. Paste it where the panel says, restart Claude, and ask it: *"check the SIGMAI status"*.

If step 3 of the panel is all green and Claude still cannot see the tools, the problem is on the Claude side of the wire — read on.

## Claude Desktop

Configuration file:

| System | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

You can also reach it from the Claude menu in the system tray: **Settings… ▸ Developer ▸ Edit Config**. Note this is the *Claude menu*, not the settings inside the chat window.

```json
{
  "mcpServers": {
    "sigmai": {
      "command": "C:\\OSGeo4W\\apps\\Python312\\python.exe",
      "args": ["C:\\Users\\you\\AppData\\Roaming\\QGIS\\QGIS3\\profiles\\default\\python\\plugins\\sigmai\\mcp\\sigmai_mcp.py"],
      "env": { "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1" }
    }
  }
}
```

Then **quit Claude Desktop completely** — closing the window is not enough — and reopen it.

Two details cause most failures, and the panel handles both for you:

- **`command` must be a real Python interpreter, given as an absolute path.** Inside QGIS on Windows, `sys.executable` is `qgis-bin.exe`, which cannot run a script; the usable interpreter sits at `apps\PythonXXX\python.exe` in the OSGeo4W tree. And the process Claude launches does not inherit your terminal's `PATH`, so a bare `python` often resolves to nothing.
- **`args` must be absolute too.** The working directory of the launched process is not the plugin folder.

## Claude Code

```bash
claude mcp add sigmai --env PYTHONUNBUFFERED=1 --env PYTHONUTF8=1 -- "/path/to/python" "/path/to/sigmai/mcp/sigmai_mcp.py"
```

The `--` is required: it separates Claude Code's own options from the command it should run. Use `--scope project` to write it into the project's `.mcp.json` instead of your user configuration.

## First conversation

A good opening, because it establishes what exists before anything is decided:

> Check the SIGMAI status, then give me an overview of the open QGIS project.

Claude will call `sigmai_status` and `sigmai_project_overview` and come back with your CRS, layers and layout list. From there:

> Read the SIGMAI cartographic rulebook, then plan an A4 landscape map of the conservation units with the drainage and the occurrence points, and show me the plan before doing anything.

`sigmai_plan_map` runs in any access mode, including read-only, and changes nothing. When you are happy with the plan, unlock writing in the panel's **Acesso** tab and ask for the map itself.

## When it does not connect

Work down this list; it is ordered by how often each one is the cause.

**Claude shows no SIGMAI tools at all.** Claude never launched the server, or the server died on startup. Its stderr is captured for you:

```
Windows:  type "%APPDATA%\Claude\logs\mcp-server-sigmai.log"
macOS:    cat ~/Library/Logs/Claude/mcp-server-sigmai.log
```

A healthy server logs one line on start: `[sigmai-mcp] iniciado (pid …, python …)`. If the file is empty or says the interpreter was not found, the `command` path is wrong. If it is missing entirely, the JSON has a syntax error — a stray comma is the usual culprit — and Claude skipped the whole file.

**Tools appear but every call reports the bridge is unavailable.** The server is running and cannot find QGIS. Either the bridge is stopped (step 1 in the panel), or the session file is not where the server looks. Pin it explicitly by adding to `env`:

```json
"SIGMAI_SESSION_FILE": "C:\\Users\\you\\AppData\\Local\\SIGMAI\\sessions\\current_bridge_session.json"
```

The exact path for your machine is shown in the panel under **Avançado ▸ Arquivo de sessão**. Pinning it matters if you keep several QGIS profiles.

**Everything works until you restart QGIS.** The bridge token changed. Turn on **Manter o mesmo token entre sessões do QGIS** in the **Avançado** tab; without it a fresh token is generated on every start and any client holding the old one is locked out.

**Claude reads the project but refuses to produce anything.** That is not a fault. SIGMAI starts in **Somente leitura**, and the refusal message says so. Change the mode in the **Acesso** tab.

## Related

- [MCP_SERVER.md](MCP_SERVER.md) — the tools, their schemas, and the protocol details
- [MCP_SECURITY_MODEL.md](SECURITY_MODEL.md) — what the consent layer does and does not cover
- [CONNECT_WITH_CURSOR.md](CONNECT_WITH_CURSOR.md) · [CONNECT_WITH_CODEX.md](CONNECT_WITH_CODEX.md)
