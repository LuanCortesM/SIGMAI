"""Compatibilidade: a folha de estilo mudou de lugar.

O tema agora vive em ``sigmai.ui.theme``, junto do painel que ele estiliza.
Este módulo permanece porque scripts e ferramentas externas importavam
``sigmai.theme.get_sigmai_stylesheet``.
"""

from __future__ import annotations

from .ui.theme import get_sigmai_stylesheet

__all__ = ["get_sigmai_stylesheet"]
