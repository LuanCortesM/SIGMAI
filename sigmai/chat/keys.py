"""A chave de API do chat, no cofre de autenticação do QGIS.

O cofre (``QgsAuthManager``) é criptografado com a senha mestra do QGIS; na
primeira vez o QGIS pede para criá-la. A chave nunca vai para as
configurações do QGIS, para os registros nem para as receitas. Sem cofre
disponível, vale a variável de ambiente do provedor, se a pessoa a tiver
definido, ou a chave só para esta sessão, guardada em memória.
"""

from __future__ import annotations

import os

ENV_VARIABLES = {"anthropic": "ANTHROPIC_API_KEY", "openai_compatible": "OPENAI_API_KEY"}
_session_keys: dict[str, str] = {}


def _auth_key(provider: str) -> str:
    return f"sigmai/chat/{provider}_api_key"


def _manager():
    from qgis.core import QgsApplication  # type: ignore

    manager = QgsApplication.authManager()
    return None if manager is None or manager.isDisabled() else manager


def load_key(provider: str) -> tuple[str, str]:
    """(chave, origem): origem é 'cofre', 'sessão', 'ambiente' ou ''."""
    if _session_keys.get(provider):
        return _session_keys[provider], "sessão"
    try:
        manager = _manager()
        if manager is not None and manager.existsAuthSetting(_auth_key(provider)):
            # Ler do cofre pode pedir a senha mestra, uma vez por sessão do QGIS.
            value = manager.authSetting(_auth_key(provider), "", True)
            if value:
                return str(value), "cofre"
    except Exception:
        pass
    value = os.environ.get(ENV_VARIABLES.get(provider, ""), "")
    return (value, "ambiente") if value else ("", "")


def save_key(provider: str, key: str) -> str:
    """Guarda no cofre; sem cofre, só nesta sessão. Devolve onde ficou."""
    key = key.strip()
    try:
        manager = _manager()
        if manager is not None and manager.setMasterPassword(True) and manager.storeAuthSetting(_auth_key(provider), key, True):
            _session_keys.pop(provider, None)
            return "cofre"
    except Exception:
        pass
    _session_keys[provider] = key
    return "sessão"


def remove_key(provider: str) -> None:
    _session_keys.pop(provider, None)
    try:
        manager = _manager()
        if manager is not None and manager.existsAuthSetting(_auth_key(provider)):
            manager.removeAuthSetting(_auth_key(provider))
    except Exception:
        pass


def masked(key: str) -> str:
    return "" if not key else (key[:7] + "…" + key[-4:] if len(key) > 14 else "…")
