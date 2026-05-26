# Pairing Code Flow

The pairing code is a short local identifier for the active QGIS bridge session.

Example:

```text
SG-4821-KQ9M
```

The code is not the bearer token. It only helps local clients find the session file in:

```text
%LOCALAPPDATA%\SIGMAI\sessions\
```

Use:

```text
python tools\sigmai.py connect SG-4821-KQ9M
python codex_plugin\client\sigmai_client.py --pairing-code SG-4821-KQ9M status
```

Security:

- Pairing works only on the same machine.
- The bridge still requires the bearer token internally.
- The server still binds only to `127.0.0.1`.
