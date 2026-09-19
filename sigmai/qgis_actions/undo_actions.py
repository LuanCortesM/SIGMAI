"""Ações de desfazer: ``undo_last_action`` e ``list_undo_history`` (ver ``sigmai/undo.py``)."""

from __future__ import annotations

from typing import Any

from ..validators import ValidationError


def _stack(context: dict[str, Any]):
    stack = context.get("undo_stack")
    if stack is None:
        raise ValidationError("UNDO_UNAVAILABLE", "A pilha de desfazer não está disponível nesta sessão.", {})
    return stack


def undo_last_action(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    stack = _stack(context)
    if context.get("dry_run"):
        history = stack.history()
        return {"dry_run": True, "would_undo": history[0] if history else None}
    return stack.undo_last()


def list_undo_history(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    history = _stack(context).history()
    return {"entries": history, "count": len(history),
            "notes": ["Só ações desta sessão do QGIS; arquivos gravados em disco não são desfeitos."]}
