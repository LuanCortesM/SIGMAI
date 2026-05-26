from __future__ import annotations

from typing import Any

from ..validators import ValidationError, require_param
from .common import layer_type_name, project


def _root():
    return project().layerTreeRoot()


def _layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", "Layer not found.", {"layer_id": layer_id})
    return layer


def _layer_record(layer: Any) -> dict[str, Any]:
    return {
        "layer_id": layer.id(),
        "name": layer.name(),
        "source": layer.source(),
        "layer_type": layer_type_name(layer),
        "valid": bool(layer.isValid()),
    }


def _remove_layers(layer_ids: list[str], context: dict[str, Any]) -> dict[str, Any]:
    layers = [project().mapLayer(layer_id) for layer_id in layer_ids]
    existing = [layer for layer in layers if layer is not None]
    records = [_layer_record(layer) for layer in existing]
    if context.get("dry_run"):
        return {"dry_run": True, "would_remove_count": len(existing), "layers": records, "disk_files_deleted": False}
    project().removeMapLayers([layer.id() for layer in existing])
    return {"removed_count": len(existing), "layers": records, "disk_files_deleted": False}


def _node(layer_id: str):
    node = _root().findLayer(layer_id)
    if node is None:
        raise ValidationError("LAYER_TREE_NODE_NOT_FOUND", "Layer tree node not found.", {"layer_id": layer_id})
    return node


def _group(name: str, create: bool = False):
    group = _root().findGroup(name)
    if group is None and create:
        group = _root().addGroup(name)
    if group is None:
        raise ValidationError("LAYER_GROUP_NOT_FOUND", "Layer group not found.", {"group_name": name})
    return group


def _walk(node: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": node.name() if hasattr(node, "name") else "",
        "node_type": "group" if hasattr(node, "children") else "layer",
        "visible": bool(node.itemVisibilityChecked()) if hasattr(node, "itemVisibilityChecked") else None,
    }
    if hasattr(node, "layerId"):
        layer_id = node.layerId()
        layer = project().mapLayer(layer_id)
        item.update(
            {
                "node_type": "layer",
                "layer_id": layer_id,
                "layer_name": layer.name() if layer else item["name"],
                "layer_type": layer_type_name(layer) if layer else "unknown",
                "valid": bool(layer and layer.isValid()),
            }
        )
    if hasattr(node, "children"):
        item["children"] = [_walk(child) for child in node.children()]
    return item


def list_layer_tree(params: dict[str, Any], context: dict[str, Any]):
    return _walk(_root())


def list_duplicate_layers(params: dict[str, Any], context: dict[str, Any]):
    by_key: dict[str, list[Any]] = {}
    mode = str(params.get("mode", "source_and_name"))
    for layer in project().mapLayers().values():
        source = layer.source().split("|", 1)[0].lower()
        if mode == "source":
            key = source
        elif mode == "name":
            key = layer.name().lower()
        else:
            key = f"{layer.name().lower()}|{source}"
        by_key.setdefault(key, []).append(layer)
    groups = []
    for key, layers in sorted(by_key.items()):
        if len(layers) > 1:
            groups.append({"key": key, "count": len(layers), "layers": [_layer_record(layer) for layer in layers]})
    return {"duplicate_group_count": len(groups), "duplicate_layer_count": sum(group["count"] for group in groups), "groups": groups}


def remove_layer(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    _layer(layer_id)
    return _remove_layers([layer_id], context)


def remove_layers_by_name(params: dict[str, Any], context: dict[str, Any]):
    name = require_param(params, "name", str)
    match = str(params.get("match", "exact"))
    case_sensitive = bool(params.get("case_sensitive", False))
    needle = name if case_sensitive else name.lower()
    matches = []
    for layer in project().mapLayers().values():
        haystack = layer.name() if case_sensitive else layer.name().lower()
        if (match == "contains" and needle in haystack) or (match != "contains" and haystack == needle):
            matches.append(layer.id())
    return _remove_layers(matches, context)


def remove_layers_by_source_path(params: dict[str, Any], context: dict[str, Any]):
    source_path = require_param(params, "source_path", str)
    needle = source_path.replace("\\", "/").lower()
    matches = []
    for layer in project().mapLayers().values():
        source = layer.source().split("|", 1)[0].replace("\\", "/").lower()
        if source == needle or source.endswith(needle):
            matches.append(layer.id())
    return _remove_layers(matches, context)


def clear_sigmai_temporary_layers(params: dict[str, Any], context: dict[str, Any]):
    name_prefix = str(params.get("name_prefix", "SIGMAI"))
    source_contains = str(params.get("source_contains", "test_outputs"))
    include_topotrail_test_layers = bool(params.get("include_topotrail_test_layers", False))
    matches = []
    for layer in project().mapLayers().values():
        name = layer.name().lower()
        source = layer.source().replace("\\", "/").lower()
        is_sigmai_named = bool(name_prefix) and name.startswith(name_prefix.lower())
        is_test_output = bool(source_contains) and source_contains.lower() in source
        is_topotrail_test = include_topotrail_test_layers and any(token in name for token in ("topotrail", "batedor", "rppn", "risco topografico", "zonas potenciais"))
        if is_sigmai_named or is_test_output or is_topotrail_test:
            matches.append(layer.id())
    return _remove_layers(matches, context)


def deduplicate_layers(params: dict[str, Any], context: dict[str, Any]):
    mode = str(params.get("mode", "source_and_name"))
    keep = str(params.get("keep", "first"))
    duplicates = list_duplicate_layers({"mode": mode}, context)["groups"]
    remove_ids: list[str] = []
    for group in duplicates:
        layers = group["layers"]
        if keep == "last":
            remove_ids.extend(layer["layer_id"] for layer in layers[:-1])
        else:
            remove_ids.extend(layer["layer_id"] for layer in layers[1:])
    return _remove_layers(remove_ids, context)


def create_clean_test_project(params: dict[str, Any], context: dict[str, Any]):
    if not bool(params.get("confirm_new_project")) and not context.get("dry_run"):
        raise ValidationError("CONFIRMATION_REQUIRED", "Creating a clean project requires confirm_new_project=true.", {})
    current_layers = [_layer_record(layer) for layer in project().mapLayers().values()]
    if context.get("dry_run"):
        return {"dry_run": True, "would_clear_layer_count": len(current_layers), "layers": current_layers, "disk_files_deleted": False}
    project().clear()
    return {"cleared_layer_count": len(current_layers), "layers": current_layers, "disk_files_deleted": False}


def set_layer_visibility(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    visible = bool(params.get("visible", True))
    node = _node(layer_id)
    before = bool(node.itemVisibilityChecked())
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer_id, "before": before, "after": visible}
    node.setItemVisibilityChecked(visible)
    return {"layer_id": layer_id, "before": before, "after": bool(node.itemVisibilityChecked())}


def create_layer_group(params: dict[str, Any], context: dict[str, Any]):
    group_name = require_param(params, "group_name", str)
    exists = _root().findGroup(group_name) is not None
    if context.get("dry_run"):
        return {"dry_run": True, "group_name": group_name, "exists": exists, "would_create": not exists}
    group = _group(group_name, create=True)
    return {"group_name": group_name, "created": not exists, "child_count": len(group.children())}


def move_layer_to_group(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    group_name = require_param(params, "group_name", str)
    layer = _layer(layer_id)
    node = _node(layer_id)
    before_parent = node.parent().name() if node.parent() and hasattr(node.parent(), "name") else "root"
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer_id, "layer_name": layer.name(), "before_parent": before_parent, "after_parent": group_name}
    group = _group(group_name, create=True)
    clone = node.clone()
    parent = node.parent()
    parent.removeChildNode(node)
    group.addChildNode(clone)
    return {"layer_id": layer_id, "layer_name": layer.name(), "before_parent": before_parent, "after_parent": group_name}


def move_layer_order(params: dict[str, Any], context: dict[str, Any]):
    layer_id = require_param(params, "layer_id", str)
    index = int(params.get("index", 0))
    if index < 0:
        raise ValidationError("BAD_REQUEST", "index must be zero or greater.", {"index": index})
    node = _node(layer_id)
    parent = node.parent()
    children = list(parent.children())
    before_order = [child.layerId() for child in children if hasattr(child, "layerId")]
    if context.get("dry_run"):
        return {"dry_run": True, "layer_id": layer_id, "before_order": before_order, "target_index": index}
    clone = node.clone()
    parent.removeChildNode(node)
    parent.insertChildNode(min(index, len(parent.children())), clone)
    after_order = [child.layerId() for child in parent.children() if hasattr(child, "layerId")]
    return {"layer_id": layer_id, "before_order": before_order, "after_order": after_order, "target_index": index}
