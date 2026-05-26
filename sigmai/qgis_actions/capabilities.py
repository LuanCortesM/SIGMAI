from __future__ import annotations

from ..capabilities import get_capabilities


def handle(params, context):
    return get_capabilities(context)
