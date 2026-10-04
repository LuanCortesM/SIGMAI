"""Arquivo de sessão que os clientes de IA leem para achar a ponte, gravado com permissões restritas e sem seguir symlink."""

from __future__ import annotations

import errno
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from core.session_paths import (  # type: ignore
        SESSION_SCHEMA_VERSION,
        current_session_file,
        fallback_sessions_dir,
        generate_pairing_code,
        is_safe_session_path,
        pairing_session_file,
        sessions_dir,
    )
except Exception:
    SESSION_SCHEMA_VERSION = "0.3"

    def sessions_dir() -> Path:
        # Espelho exato de core/session_paths.sessions_dir(). O pacote publicado
        # nunca traz core/, então É esta função que roda na máquina do usuário —
        # e ela precisa concordar com onde o servidor MCP procura
        # (sigmai_mcp._sessions_dirs). A versão anterior gravava em
        # ~/SIGMAI/sessions no Linux e no macOS enquanto o servidor procurava
        # em ~/.local/share/sigmai/sessions: a descoberta automática falhava
        # em silêncio e só o SIGMAI_SESSION_FILE explícito salvava.
        if os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                return Path(local_app_data) / "SIGMAI" / "sessions"
            temp = os.environ.get("TEMP")
            if temp:
                return Path(temp) / "SIGMAI" / "sessions"
        if os.name == "posix":
            if "darwin" in sys.platform:
                return Path.home() / "Library" / "Application Support" / "SIGMAI" / "sessions"
            return Path.home() / ".local" / "share" / "sigmai" / "sessions"
        return Path(os.environ.get("TEMP", str(Path.home()))) / "SIGMAI" / "sessions"

    def fallback_sessions_dir() -> Path:
        return Path(os.environ.get("TEMP", str(Path.home()))) / "SIGMAI" / "sessions"

    def current_session_file() -> Path:
        return sessions_dir() / "current_bridge_session.json"

    def pairing_session_file(pairing_code: str) -> Path:
        return sessions_dir() / f"{pairing_code.upper()}.json"

    def is_safe_session_path(path: Path) -> bool:
        return ".git" not in {part.lower() for part in path.resolve().parts}

    def generate_pairing_code() -> str:
        import secrets
        import string

        return "SG-" + "".join(secrets.choice(string.digits) for _ in range(4)) + "-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))

SCHEMA_VERSION = SESSION_SCHEMA_VERSION


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fallback_session_dir() -> Path:
    return fallback_sessions_dir()


def session_file_path() -> Path:
    return current_session_file()


def fallback_session_file_path() -> Path:
    return fallback_session_dir() / "current_bridge_session.json"


def build_session_payload(
    *,
    host: str,
    port: int,
    token: str,
    qgis_version: str,
    plugin_version: str,
    running: bool,
    source: str = "sigmai",
    session_id: str | None = None,
) -> dict[str, Any]:
    code = session_id or generate_pairing_code()
    return {
        "schema_version": SCHEMA_VERSION,
        "host": host,
        "port": int(port),
        "token": token,
        "started_at": utc_now(),
        "expires_at": None,
        "qgis_version": qgis_version,
        "plugin_version": plugin_version,
        "pid": os.getpid(),
        "session_id": code,
        "pairing_code": code,
        "capabilities_url": f"http://{host}:{int(port)}/command",
        "auth_type": "bearer",
        "local_only": True,
        "running": running,
        "active": running,
        "source": source,
    }


#: O(s) flag(s) que fazem o kernel recusar seguir um symlink no componente
#: final do caminho, atomicamente com a própria abertura (sem a janela de um
#: "checar depois abrir" separado). Existe no Linux e no macOS (POSIX 2008).
#: No Windows o CPython não expõe ``os.O_NOFOLLOW`` — ``getattr`` cai para 0
#: e o flag vira um no-op ali; a defesa nesse caso fica só no
#: ``path.is_symlink()`` explícito logo abaixo (com uma janela TOCTOU, mas
#: criar symlink no Windows exige privilégio elevado ou modo desenvolvedor,
#: o que reduz bastante o risco prático de um symlink pré-posicionado).
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _refuse_symlink(path: Path) -> None:
    """Recusa continuar se ``path`` já é (ou virou) um symlink.

    O ataque provado é um symlink pré-posicionado no caminho de sessão,
    previsível e, no Linux, sob um diretório compartilhado entre usuários:
    sem esta checagem, gravar a "sessão atual" grava através do link e
    sobrescreve o alvo dele com o token em texto puro.
    """
    if path.is_symlink():
        raise RuntimeError(f"Refusing to use session file path through a symlink: {path}")


def _write_text_secure(path: Path, content: str) -> None:
    """Escreve ``content`` em ``path`` sem seguir symlink, já com modo 0600.

    O modo vai para ``os.open`` na própria criação: não existe um
    ``write_text()`` seguido de ``chmod()`` depois, quando o arquivo já
    existiria por um instante com a permissão mais aberta do umask (o
    defeito original). Em POSIX, ``mode`` só pode restringir bits do que o
    umask já teria concedido — nunca abrir mais — então o resultado final é
    sempre ≤ 0600, sem janela. O ``chmod`` de reforço no final cobre o caso
    (raro) de o arquivo já existir de uma gravação anterior a esta correção,
    com permissão mais aberta herdada.
    """
    _refuse_symlink(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _NOFOLLOW
    try:
        fd = os.open(str(path), flags, 0o600)
    except OSError as exc:
        if _NOFOLLOW and exc.errno in (errno.ELOOP, errno.EMLINK):
            raise RuntimeError(f"Refusing to write session file through a symlink: {path}") from exc
        raise
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _read_text_secure(path: Path) -> str:
    """Lê ``path`` sem seguir symlink — companheiro de leitura de ``_write_text_secure``."""
    _refuse_symlink(path)
    flags = os.O_RDONLY | _NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        if _NOFOLLOW and exc.errno in (errno.ELOOP, errno.EMLINK):
            raise RuntimeError(f"Refusing to read session file through a symlink: {path}") from exc
        raise
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        return handle.read()


def write_session_file(payload: dict[str, Any]) -> Path:
    errors = []
    paths = [session_file_path(), pairing_session_file(str(payload["session_id"])), fallback_session_file_path()]
    for path in paths:
        try:
            if not is_safe_session_path(path):
                raise ValueError(f"Refusing to write session file under .git: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_text_secure(path, json.dumps(payload, indent=2))
            return path
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Could not write SIGMAI session file. " + " | ".join(errors))


def invalidate_session_file(session_id: str | None = None) -> None:
    """Marca como encerrada a sessão desta instância.

    Com ``session_id``, só os arquivos que essa instância gravou. Sem ele,
    marcava todos — e com dois QGIS abertos, fechar um derrubava a sessão que
    o outro tinha acabado de gravar em ``current_bridge_session.json``: o
    cliente de IA ficava sem ponte embora uma continuasse no ar.
    """
    for path in list(sessions_dir().glob("SG-*.json")) + [session_file_path(), fallback_session_file_path()]:
        try:
            if path.exists():
                data = json.loads(_read_text_secure(path))
                if session_id is not None and str(data.get("session_id", "")) != str(session_id):
                    continue
                data["running"] = False
                data["active"] = False
                data["stopped_at"] = utc_now()
                _write_text_secure(path, json.dumps(data, indent=2))
        except Exception:
            pass


def cleanup_old_sessions(max_files: int = 20) -> None:
    try:
        files = sorted(sessions_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[max_files:]:
            path.unlink(missing_ok=True)
    except Exception:
        pass
