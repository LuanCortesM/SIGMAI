"""Que parâmetros cada ação da ponte lê — extraído do próprio código.

Um assistente remoto só conhece uma ação pelo que o catálogo diz dela, e o
catálogo dizia grupo, permissão e flags: nenhum parâmetro. Ele descobria os
nomes por tentativa — e, pior, um parâmetro errado era engolido em silêncio:
``sample_features`` com ``filter=...`` devolvia as dez primeiras feições
como se tivesse filtrado. Isso contraria a tese do plugin (o que a resposta
diz aconteceu, aconteceu).

Este módulo lê o código-fonte de cada manipulador e coleta os nomes que ele
acessa de forma literal — ``params.get("x")``, ``params["x"]``,
``require_param(params, "x")``, ``as_text(params, "x")``, ``"x" in params``.
Se TODA ocorrência de ``params`` no corpo for uma dessas, o manipulador é
"fechado": o conjunto extraído é exatamente o que ele lê, e a ponte pode
avisar quando o chamador manda um nome fora dele. Se alguma ocorrência for
outra coisa — ``params`` repassado inteiro a outra função, iterado, copiado —
o manipulador é "aberto": os nomes viram só uma dica, e nenhum aviso é
emitido, porque a extração não tem como saber o que a função de baixo lê.

É deliberadamente conservador: prefere não avisar a avisar errado.
"""

from __future__ import annotations

import inspect
import re
from functools import lru_cache
from typing import Any, Callable

_LITERAL_ACCESS = (
    re.compile(r'params\.get\(\s*["\']([\w-]+)["\']'),
    re.compile(r'params\.pop\(\s*["\']([\w-]+)["\']'),
    re.compile(r'params\[\s*["\']([\w-]+)["\']\s*\]'),
    re.compile(r'\w+\(\s*params\s*,\s*["\']([\w-]+)["\']'),
    re.compile(r'["\']([\w-]+)["\']\s+(?:not\s+)?in\s+params\b'),
)
_ANY_PARAMS = re.compile(r"\bparams\b")


def _strip_signature_and_docstring(source: str) -> str:
    lines = source.splitlines()
    body = []
    in_def = True
    for line in lines:
        if in_def:
            if line.rstrip().endswith(":") and "def " in source.splitlines()[0]:
                in_def = False
            continue
        body.append(line)
    text = "\n".join(body)
    # docstring no início do corpo
    match = re.match(r'\s*[rbuRBU]*("""|\'\'\')', text)
    if match:
        quote = match.group(1)
        end = text.find(quote, match.end())
        if end != -1:
            text = text[end + 3:]
    # comentários
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


@lru_cache(maxsize=1024)
def _analyse(source: str) -> tuple[tuple[str, ...], bool]:
    body = _strip_signature_and_docstring(source)
    names: list[str] = []
    covered = 0
    for pattern in _LITERAL_ACCESS:
        for match in pattern.finditer(body):
            names.append(match.group(1))
            covered += 1
    total = len(_ANY_PARAMS.findall(body))
    closed = total == covered
    ordered = list(dict.fromkeys(names))
    return tuple(ordered), closed


def declared_parameters(handler: Callable[..., Any]) -> tuple[tuple[str, ...], bool]:
    """``(nomes, fechado)`` para um manipulador ``handler(params, context)``."""
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        return (), False
    return _analyse(source)


def unread_parameters(handler: Callable[..., Any], params: dict[str, Any]) -> tuple[list[str], tuple[str, ...]]:
    """Chaves de ``params`` que um manipulador FECHADO não lê; vazio se aberto."""
    names, closed = declared_parameters(handler)
    if not closed or not isinstance(params, dict):
        return [], names
    known = set(names)
    return sorted(key for key in params if key not in known), names
