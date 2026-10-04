"""Guardas de segurança: varredura de tokens perigosos em campos que carregam código e normalização de caminhos de saída."""

from __future__ import annotations

import os
import platform
import re
import secrets
from pathlib import Path
from typing import Iterable


DEFAULT_HOST = "127.0.0.1"

#: Toda requisição a ``/command`` exige o token de portador; não há modo sem
#: autenticação. Constante nomeada, e não um ``True`` literal ao lado da chave
#: ``token_required``: o Bandit (B105) lê esse par como senha embutida.
AUTHENTICATION_REQUIRED = True
DEFAULT_PORT = 8765

#: Quantas portas tentar a partir da padrão antes de desistir. Sem isso, uma
#: segunda instância do QGIS — ou qualquer processo que já ocupe a 8765 —
#: fazia a bridge falhar ao iniciar com um erro de socket que não dizia nada
#: ao usuário.
PORT_SCAN_ATTEMPTS = 20


def generate_token() -> str:
    """Create a local session token for bearer authentication."""
    return secrets.token_urlsafe(32)


#: ``SO_REUSEADDR`` no Windows não é o do POSIX: ele deixa um SEGUNDO socket se
#: ligar à mesma porta já em escuta. Com ele, duas instâncias do QGIS subiam a
#: ponte ambas na 8765, o desvio para a 8766 nunca acontecia, e o cliente de IA
#: falava com qualquer uma das duas — inclusive com a que estava travada.
REUSE_ADDRESS = os.name != "nt"


def claim_port(sock: object) -> None:
    """Prepara o socket de escuta para que a porta seja só dele.

    No Windows, ``SO_EXCLUSIVEADDRUSE`` também impede que outro processo local
    se ligue à mesma porta e receba as requisições — com o token — que o
    servidor MCP manda à ponte. Fora do Windows, ``SO_REUSEADDR`` só permite
    religar a porta com conexões em TIME_WAIT, que é o que se quer ao
    recarregar o plugin.
    """
    import socket

    if REUSE_ADDRESS:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # type: ignore[attr-defined]
    elif hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]


def find_available_port(host: str = DEFAULT_HOST, start: int = DEFAULT_PORT, attempts: int = PORT_SCAN_ATTEMPTS) -> int:
    """Primeira porta livre a partir de ``start``.

    Levanta ``OSError`` se nenhuma das ``attempts`` portas estiver disponível,
    com uma mensagem que nomeia a faixa tentada.
    """
    import socket

    for offset in range(max(1, attempts)):
        candidate = int(start) + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            # A mesma regra do socket de escuta: com SO_REUSEADDR no Windows a
            # sonda "conseguia" ligar-se a uma porta ocupada e a devolvia.
            claim_port(probe)
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
            return candidate
    raise OSError(
        f"Nenhuma porta livre entre {start} e {start + attempts - 1} em {host}. "
        "Feche outra instância do QGIS com o SIGMAI ativo ou libere a faixa."
    )


def is_localhost(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def validate_bearer_header(header_value: str | None, expected_token: str) -> bool:
    if not expected_token or not header_value:
        return False
    prefix = "Bearer "
    if not header_value.startswith(prefix):
        return False
    supplied = header_value[len(prefix):].strip()
    return secrets.compare_digest(supplied, expected_token)


class OutputPathError(ValueError):
    """Caminho de saída que não pode ser aceito. ``CommandRegistry`` a devolve
    como BAD_REQUEST — é recusa de parâmetro, não erro interno."""


def normalize_output_path(path_value: str) -> Path:
    """Normalize an output path without creating or deleting anything.

    Only absolute paths of THIS operating system are accepted. Two accidents
    the previous version let through: a Windows path pasted into a QGIS
    running on Linux/macOS ("C:\\Users\\...\\map.png") is, to POSIX, a
    relative file name with backslashes — the export created a file literally
    called ``C:\\Users\\...`` in the current directory and reported success;
    and a relative path ("map.png") landed in the QGIS process's current
    directory, which the user does not know.
    """
    if not path_value or not isinstance(path_value, str) or not path_value.strip():
        raise OutputPathError("Output path must be a non-empty string.")
    text = path_value.strip()
    problem = classify_output_path(text)
    if problem == "foreign":
        raise OutputPathError(
            f"Output path looks like a Windows path ({text!r}) but this QGIS runs on "
            f"{platform.system() or 'another OS'}. Give an absolute path on this computer, "
            f"for example {Path.home() / 'map.png'}."
        )
    if problem == "relative":
        raise OutputPathError(
            f"Output path must be absolute; got {text!r}, which would be written to the QGIS "
            f"process's current directory. Give the full folder, for example {Path.home() / text}."
        )
    return Path(os.path.expandvars(os.path.expanduser(text))).resolve()


def classify_output_path(text: str) -> str:
    """``"foreign"`` (caminho do Windows num sistema POSIX), ``"relative"``
    (sem pasta completa) ou ``"ok"``. É o único lugar que define o que conta
    como caminho aceitável; ``compose_map`` e as ações da ponte só redigem a
    recusa cada um na sua língua."""
    windows_style = bool(re.match(r"^[A-Za-z]:[\\/]", text)) or text.startswith("\\\\")
    if os.name != "nt" and (windows_style or "\\" in text):
        return "foreign"
    if not Path(os.path.expandvars(os.path.expanduser(text))).is_absolute():
        return "relative"
    return "ok"


def ensure_parent_exists(path: Path) -> None:
    if not path.parent.exists():
        raise OutputPathError(f"Output directory does not exist: {path.parent}")


def reject_existing_path_without_confirmation(path: Path, confirm_overwrite: bool) -> None:
    if path.exists() and not confirm_overwrite:
        raise FileExistsError(f"Output path already exists: {path}")


def contains_blocked_token(value: object, blocked: Iterable[str]) -> str | None:
    """Return the first blocked key/value token found in a nested JSON-like object."""
    blocked_lower = {item.lower() for item in blocked}
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in blocked_lower:
                return str(key)
            found = contains_blocked_token(nested, blocked_lower)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = contains_blocked_token(nested, blocked_lower)
            if found:
                return found
    elif isinstance(value, str):
        lowered = value.lower()
        for token in blocked_lower:
            if _blocked_token_in_string(lowered, token):
                return token
    return None


def _blocked_token_in_string(lowered: str, token: str) -> bool:
    if token in {"cmd", "code", "eval", "exec", "os.system", "popen", "python", "shell", "subprocess"}:
        pattern = rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])"
        return re.search(pattern, lowered) is not None
    return token in lowered
