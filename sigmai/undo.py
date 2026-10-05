"""Desfazer a última ação que alterou o projeto.

O consentimento do SIGMAI diz *o que* aconteceu; ele não desfazia. No
experimento "PyQGIS puro × SIGMAI" o agente direto renomeou camadas do
projeto sem querer (armadilha da legenda) — com um assistente operando o
QGIS, o usuário precisa de um botão de voltar tão explícito quanto o de
autorizar.

Antes de cada ação de escrita no projeto (``safe_write``/``project_write``,
sem ``dry_run``) o registro tira um *snapshot* do que ela pode tocar: o
estilo (QML), o nome, os rótulos e a codificação de cada camada citada nos
parâmetros; o XML de cada layout citado; e a lista de camadas e layouts do
projeto. Depois da ação, anota o que foi criado. ``undo_last_action``
remove o que foi criado e restaura o que foi tocado. Arquivos gravados em
disco não são apagados — o resultado diz quais ficaram.

Só existe estado em memória, nesta sessão do QGIS: fechar o QGIS descarta a
pilha, e nada aqui substitui salvar o projeto antes de uma sessão de
trabalho com o assistente.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

#: Chaves de parâmetro que apontam para camadas do projeto.
LAYER_KEYS = (
    "layer_id", "layer_ids", "subject_layer_id", "inset_layer_ids", "label_layer_id", "boundary_layer_id",
    "points_layer_id", "track_layer_id", "area_layer_ids", "context_layer_ids", "input_layer_id", "overlay_layer_id",
    "other_layer_id", "target_layer_id", "source_layer_id",
)
LAYOUT_KEYS = ("layout_name",)
UNDO_LIMIT = 20

#: Ações que nunca entram na pilha (elas próprias operam a pilha, ou só
#: leem/gravam arquivos sem tocar no projeto).
EXCLUDED_ACTIONS = frozenset({"undo_last_action", "list_undo_history"})


@dataclass
class LayerSnapshot:
    layer_id: str
    name: str
    style_xml: str
    labels_enabled: bool
    encoding: str


@dataclass
class LayoutSnapshot:
    name: str
    xml: str


@dataclass
class UndoEntry:
    action: str
    request_id: str
    started_at: float
    layers: dict[str, LayerSnapshot] = field(default_factory=dict)
    layouts: dict[str, LayoutSnapshot] = field(default_factory=dict)
    layer_ids_before: set[str] = field(default_factory=set)
    layout_names_before: set[str] = field(default_factory=set)
    created_layer_ids: list[str] = field(default_factory=list)
    created_layout_names: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    outcome: str = "pending"

    def describe(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "request_id": self.request_id,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at)),
            "outcome": self.outcome,
            "touched_layers": [s.name for s in self.layers.values()],
            "touched_layouts": list(self.layouts),
            "created_layers": list(self.created_layer_ids),
            "created_layouts": list(self.created_layout_names),
            "files_written": list(self.output_paths),
        }


def _collect_ids(value: Any, keys: tuple[str, ...]) -> list[str]:
    found: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for nested_key, nested in node.items():
                walk(nested, str(nested_key))
        elif isinstance(node, list):
            for nested in node:
                walk(nested, key)
        elif isinstance(node, str) and node and key in keys:
            found.append(node)

    walk(value)
    return list(dict.fromkeys(found))


def _collect_paths(params: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for nested_key, nested in node.items():
                walk(nested, str(nested_key))
        elif isinstance(node, list):
            for nested in node:
                walk(nested, key)
        elif isinstance(node, str) and node:
            lowered = key.lower()
            if lowered.startswith("output") or lowered.endswith("_path") or lowered in {"path", "destination"}:
                found.append(node)

    walk(params)
    return list(dict.fromkeys(found))


def _qgis():
    try:
        from qgis.core import QgsPrintLayout, QgsProject, QgsReadWriteContext  # type: ignore
        from qgis.PyQt.QtXml import QDomDocument  # type: ignore
    except Exception:
        return None
    return {"QgsPrintLayout": QgsPrintLayout, "QgsProject": QgsProject, "QgsReadWriteContext": QgsReadWriteContext,
            "QDomDocument": QDomDocument}


def _layer_snapshot(layer: Any, q: dict[str, Any]) -> LayerSnapshot | None:
    try:
        doc = q["QDomDocument"]()
        layer.exportNamedStyle(doc)
        encoding = ""
        try:
            encoding = str(layer.dataProvider().encoding() or "")
        except Exception:
            pass
        return LayerSnapshot(
            layer_id=str(layer.id()), name=str(layer.name()), style_xml=doc.toString(),
            labels_enabled=bool(getattr(layer, "labelsEnabled", lambda: False)()), encoding=encoding,
        )
    except Exception:
        return None


def _layout_snapshot(layout: Any, q: dict[str, Any]) -> LayoutSnapshot | None:
    try:
        doc = q["QDomDocument"]()
        element = layout.writeXml(doc, q["QgsReadWriteContext"]())
        doc.appendChild(element)
        return LayoutSnapshot(name=str(layout.name()), xml=doc.toString())
    except Exception:
        return None


class UndoStack:
    """Pilha de snapshots por sessão do QGIS (só em memória)."""

    def __init__(self, limit: int = UNDO_LIMIT) -> None:
        self._entries: list[UndoEntry] = []
        self._limit = limit

    # -- captura --------------------------------------------------------
    def snapshot(self, action: str, params: dict[str, Any], request_id: str = "") -> UndoEntry | None:
        q = _qgis()
        if q is None:
            return None
        try:
            project = q["QgsProject"].instance()
        except Exception:
            return None
        entry = UndoEntry(action=action, request_id=request_id, started_at=time.time(), output_paths=_collect_paths(params))
        try:
            entry.layer_ids_before = set(project.mapLayers().keys())
            entry.layout_names_before = {layout.name() for layout in project.layoutManager().layouts()}
        except Exception:
            pass
        for layer_id in _collect_ids(params, LAYER_KEYS):
            layer = project.mapLayer(layer_id)
            if layer is None:
                by_name = [c for c in project.mapLayers().values() if c.name() == layer_id]
                layer = by_name[0] if by_name else None
            if layer is None:
                continue
            snap = _layer_snapshot(layer, q)
            if snap is not None:
                entry.layers[snap.layer_id] = snap
        for layout_name in _collect_ids(params, LAYOUT_KEYS):
            layout = project.layoutManager().layoutByName(layout_name)
            if layout is None:
                continue
            snap = _layout_snapshot(layout, q)
            if snap is not None:
                entry.layouts[snap.name] = snap
        return entry

    def commit(self, entry: UndoEntry | None, outcome: str) -> None:
        if entry is None:
            return
        entry.outcome = outcome
        q = _qgis()
        if q is not None:
            try:
                project = q["QgsProject"].instance()
                entry.created_layer_ids = sorted(set(project.mapLayers().keys()) - entry.layer_ids_before)
                entry.created_layout_names = sorted(
                    {layout.name() for layout in project.layoutManager().layouts()} - entry.layout_names_before
                )
            except Exception:
                pass
        # Uma ação que não tocou nem criou nada não ocupa lugar na pilha.
        if not (entry.layers or entry.layouts or entry.created_layer_ids or entry.created_layout_names):
            return
        self._entries.append(entry)
        del self._entries[:-self._limit]

    # -- consulta e desfazer ---------------------------------------------
    def history(self) -> list[dict[str, Any]]:
        return [entry.describe() for entry in reversed(self._entries)]

    def undo_last(self) -> dict[str, Any]:
        if not self._entries:
            return {"undone": False, "reason": "Nada para desfazer nesta sessão."}
        q = _qgis()
        if q is None:
            return {"undone": False, "reason": "PyQGIS indisponível."}
        entry = self._entries.pop()
        project = q["QgsProject"].instance()
        restored_layers: list[str] = []
        removed_layers: list[str] = []
        removed_layouts: list[str] = []
        restored_layouts: list[str] = []
        problems: list[str] = []

        for layout_name in entry.created_layout_names:
            layout = project.layoutManager().layoutByName(layout_name)
            if layout is not None:
                try:
                    project.layoutManager().removeLayout(layout)
                    removed_layouts.append(layout_name)
                except Exception as exc:
                    problems.append(f"layout {layout_name!r}: {exc}")
        for layer_id in entry.created_layer_ids:
            if project.mapLayer(layer_id) is not None:
                try:
                    name = project.mapLayer(layer_id).name()
                    project.removeMapLayer(layer_id)
                    removed_layers.append(name)
                except Exception as exc:
                    problems.append(f"camada {layer_id}: {exc}")
        for snap in entry.layouts.values():
            try:
                existing = project.layoutManager().layoutByName(snap.name)
                if existing is not None:
                    project.layoutManager().removeLayout(existing)
                doc = q["QDomDocument"]()
                doc.setContent(snap.xml)
                layout = q["QgsPrintLayout"](project)
                layout.readXml(doc.documentElement(), doc, q["QgsReadWriteContext"]())
                layout.setName(snap.name)
                project.layoutManager().addLayout(layout)
                restored_layouts.append(snap.name)
            except Exception as exc:
                problems.append(f"layout {snap.name!r}: {exc}")
        for snap in entry.layers.values():
            layer = project.mapLayer(snap.layer_id)
            if layer is None:
                problems.append(f"camada {snap.name!r} não está mais no projeto; estilo não restaurado")
                continue
            try:
                doc = q["QDomDocument"]()
                doc.setContent(snap.style_xml)
                layer.importNamedStyle(doc)
                if layer.name() != snap.name:
                    layer.setName(snap.name)
                try:
                    layer.setLabelsEnabled(snap.labels_enabled)
                except Exception:
                    pass
                if snap.encoding:
                    try:
                        if str(layer.dataProvider().encoding() or "") != snap.encoding:
                            layer.setProviderEncoding(snap.encoding)
                    except Exception:
                        pass
                layer.triggerRepaint()
                restored_layers.append(snap.name)
            except Exception as exc:
                problems.append(f"camada {snap.name!r}: {exc}")

        return {
            "undone": True,
            "action": entry.action,
            "request_id": entry.request_id,
            "restored_layers": restored_layers,
            "removed_layers": removed_layers,
            "restored_layouts": restored_layouts,
            "removed_layouts": removed_layouts,
            "files_kept": entry.output_paths,
            "problems": problems,
            "remaining": len(self._entries),
            "notes": (
                ["Arquivos gravados em disco não são apagados pelo desfazer: " + ", ".join(entry.output_paths) + "."]
                if entry.output_paths else []
            ),
        }
