"""Codificação de texto das camadas: detectar e corrigir "Piau�".

Shapefiles brasileiros antigos vêm em ISO-8859-1 sem o arquivo ``.cpg``; o
QGIS lê como UTF-8 e cada acento vira o caractere de substituição U+FFFD.
O nome sai errado no rótulo, na legenda e em qualquer resposta do SIGMAI.
``set_layer_encoding`` troca a codificação com que o provedor lê os
atributos (``setProviderEncoding``) — uma propriedade da camada no
projeto, não uma alteração do arquivo.
"""

from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .common import layer_type_name, project

REPLACEMENT_CHAR = "�"
COMMON_ENCODINGS = ("UTF-8", "ISO-8859-1", "windows-1252", "ISO-8859-15", "CP850")


def has_mojibake(text: Any) -> bool:
    return REPLACEMENT_CHAR in str(text or "")


def _text_fields(layer: Any) -> list[str]:
    return [f.name() for f in layer.fields() if f.typeName().lower() in ("string", "text", "varchar", "qstring")]


def _sample_texts(layer: Any, limit: int = 200) -> list[str]:
    fields = _text_fields(layer)
    texts: list[str] = []
    for index, feature in enumerate(layer.getFeatures()):
        if index >= limit:
            break
        for name in fields:
            value = feature[name]
            if value not in (None, "") and str(value) != "NULL":
                texts.append(str(value))
    return texts


def detect_encoding_problem(layer: Any) -> dict[str, Any] | None:
    """``None`` quando os textos estão limpos; senão, o diagnóstico com exemplos."""
    try:
        texts = _sample_texts(layer)
    except Exception:
        return None
    broken = [t for t in texts if has_mojibake(t)]
    if not broken:
        return None
    return {
        "layer_id": layer.id(),
        "layer": layer.name(),
        "current_encoding": str(getattr(layer.dataProvider(), "encoding", lambda: "")() or ""),
        "examples": broken[:5],
        "hint": "Caracteres de substituição (�) nos atributos: a codificação do arquivo provavelmente é "
                "ISO-8859-1/windows-1252. Chame set_layer_encoding com encoding='ISO-8859-1'.",
    }


def set_layer_encoding(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    layer_id = require_param(params, "layer_id", str)
    encoding = str(require_param(params, "encoding", str)).strip()
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", f"Camada não encontrada: {layer_id}.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector":
        raise ValidationError("VECTOR_LAYER_REQUIRED", "set_layer_encoding só se aplica a camadas vetoriais.", {"layer_id": layer_id})
    try:
        import codecs

        codecs.lookup(encoding)
    except LookupError:
        raise ValidationError(
            "BAD_REQUEST", f"Codificação desconhecida: {encoding!r}. Exemplos: {', '.join(COMMON_ENCODINGS)}.",
            {"encoding": encoding},
        )
    before = detect_encoding_problem(layer)
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer_id, "encoding": encoding, "problem_before": before}
    previous = ""
    try:
        previous = str(layer.dataProvider().encoding() or "")
    except Exception:
        pass
    layer.setProviderEncoding(encoding)
    try:
        layer.dataProvider().setEncoding(encoding)
    except Exception:
        pass
    layer.triggerRepaint()
    after = detect_encoding_problem(layer)
    sample = _sample_texts(layer, limit=5)[:5]
    notes = []
    if after is not None:
        notes.append("Ainda há caracteres de substituição depois da troca; experimente outra codificação (windows-1252, CP850).")
    return {
        "layer_id": layer_id,
        "layer": layer.name(),
        "previous_encoding": previous,
        "encoding": encoding,
        "problem_before": before,
        "problem_after": after,
        "sample_texts": sample,
        "notes": notes,
    }
