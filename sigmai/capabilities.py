from __future__ import annotations

from typing import Any

from .permissions import capabilities_payload


def get_capabilities(context: dict[str, Any]) -> dict[str, Any]:
    payload = capabilities_payload(
        developer_mode=bool(context.get("developer_mode", False) or context.get("unsafe_developer_mode", False))
    )
    payload["unsafe_developer_mode"] = bool(context.get("unsafe_developer_mode", False))
    try:
        from .qgis_actions.gis_tools import PROCESSING_ALLOWLIST

        payload["processing_allowlist"] = sorted(PROCESSING_ALLOWLIST)
    except Exception:
        payload["processing_allowlist"] = []
    return payload
