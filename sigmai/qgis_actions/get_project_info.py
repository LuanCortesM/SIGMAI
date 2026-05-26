from __future__ import annotations

from .common import crs_authid, project


def handle(params, context):
    qgs_project = project()
    layout_manager = qgs_project.layoutManager()
    layouts = [layout.name() for layout in layout_manager.layouts()]
    layers = list(qgs_project.mapLayers().values())
    return {
        "project_path": qgs_project.fileName(),
        "project_crs": crs_authid(qgs_project.crs()),
        "layer_count": len(layers),
        "layouts": layouts,
        "layer_crs": {
            layer.id(): crs_authid(layer.crs()) if hasattr(layer, "crs") else ""
            for layer in layers
        },
        "layers_without_crs": [
            layer.id()
            for layer in layers
            if hasattr(layer, "crs") and not crs_authid(layer.crs())
        ],
        "invalid_layers": [layer.id() for layer in layers if not layer.isValid()],
    }


def project_crs(params, context):
    qgs_project = project()
    return {"project_crs": crs_authid(qgs_project.crs())}
