"""Experiment 1 — fault injection: does QGIS report silent cartographic faults, and does the audit?

Each base map is composed by SIGMAI and audited. Each fault operator then
damages a fresh copy of the base layout through the PyQGIS layout API — the
way a script or a hand edit would — and the layout is exported and audited
again. For every (base, operator) pair the script records:

* what QGIS itself signals: the ``QgsLayoutExporter`` result code, any Python
  exception, and every message of level Warning or Critical sent to the QGIS
  message log while the fault is applied and the layout exported;
* what the audit reports: the status of the rule the operator targets, the
  grade and score, and every rule that fails.

The operators were written from the rule definitions, so detection of the
targeted rule measures whether the audit implements what it claims (a
verification), not how it generalises to faults nobody anticipated; that is
what Experiment 2 looks at, on maps written by an AI agent.

Run with the Python of a QGIS installation::

    python e1_fault_injection.py --data <_teste_sigmai> --dem <DEM_GLO90> --out <results/e1> --work <scratch>

Resumable: a (base, operator) pair already present in ``results.jsonl`` is skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------------------
# Base maps
# ---------------------------------------------------------------------------

#: Composition parameters of each base. Layer keys are resolved in load_layers().
BASES = {
    "B1_state_A4_portrait": {
        "layers": ["state", "municipalities"], "subject": "state",
        "params": {"page": "A4", "orientation": "portrait", "include_grid": True, "include_inset": False,
                   "title": "Piauí State", "subtitle": "Municipal boundaries, 2024"},
    },
    "B2_park_A4_greyscale_inset": {
        "layers": ["park", "municipalities"], "subject": "park", "inset": ["state"],
        "params": {"page": "A4", "orientation": "portrait", "include_grid": True, "include_inset": True,
                   "colour_mode": "greyscale", "apply_style": "all",
                   "title": "Carnaúbas State Park", "subtitle": "Location"},
    },
    "B3_terrain_A4_landscape_inset": {
        "layers": ["dem", "municipalities"], "subject": "dem", "inset": ["state"],
        "params": {"page": "A4", "orientation": "landscape", "include_grid": True, "include_inset": True,
                   "title": "Terrain of northern Piauí", "subtitle": "Copernicus DEM GLO-90"},
    },
    "B4_state_journal_column_greyscale": {
        "layers": ["state", "municipalities"], "subject": "state",
        "params": {"journal_column": "single", "include_grid": True, "colour_mode": "greyscale", "apply_style": "all",
                   "title": "Piauí", "subtitle": "Municipalities"},
    },
    "B5_trail_sites_A5_landscape": {
        "layers": ["sites", "trail"], "subject": ["sites", "trail"],
        "params": {"page": "A5", "orientation": "landscape", "include_grid": True,
                   "title": "Itaguaré trail", "subtitle": "Collection sites", "label_layer": "sites", "label_field": "codigo"},
    },
    "B6_state_A3_labels": {
        "layers": ["state", "municipalities"], "subject": "state",
        "params": {"page": "A3", "orientation": "landscape", "include_grid": True,
                   "title": "Piauí State", "subtitle": "Municipalities", "label_layer": "municipalities",
                   "label_field": "NM_MUN"},
    },
}

COMMON = {"map_author": "Experiment E1", "data_source": "IBGE (2024); SEMA (2024); Copernicus DEM GLO-90",
          "format": "png", "dpi": 110, "map_language": "en"}


def load_layers(data: Path, dem_dir: Path, sites_csv: Path) -> dict[str, object]:
    from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

    project = QgsProject.instance()
    project.clear()
    layers = {
        "municipalities": QgsVectorLayer(str(data / "PI_Municipios_2024.shp"), "Municipalities of Piauí", "ogr"),
        "state": QgsVectorLayer(str(data / "PI_UF_2024.shp"), "Piauí state boundary", "ogr"),
        "park": QgsVectorLayer(str(data / "PE Carnaubas.kml"), "Carnaúbas State Park", "ogr"),
        "trail": QgsVectorLayer(str(data / "trilha" / "Trilha Itaguaré pelo batedor.shp"), "Itaguaré trail", "ogr"),
        "dem": QgsRasterLayer(str(next(dem_dir.glob("*.tif"))), "Elevation (Copernicus DEM)"),
        "sites": QgsVectorLayer(
            f"file:///{sites_csv.as_posix()}?delimiter=,&xField=lon&yField=lat&crs=EPSG:4326", "Collection sites", "delimitedtext"),
    }
    for key, layer in layers.items():
        if not layer.isValid():
            raise SystemExit(f"invalid layer {key}")
    project.addMapLayers(list(layers.values()))
    project.setCrs(layers["state"].crs())
    return layers


def compose_base(name: str, layers: dict, out_png: Path) -> dict:
    from sigmai.cartography.compose import compose_map

    spec = BASES[name]
    params = dict(COMMON)
    params.update({k: v for k, v in spec["params"].items() if k not in ("label_layer",)})
    params["layer_ids"] = [layers[key].id() for key in spec["layers"]]
    subject = spec["subject"]
    params["subject_layer_id"] = [layers[k].id() for k in subject] if isinstance(subject, list) else layers[subject].id()
    if spec.get("inset"):
        params["inset_layer_ids"] = [layers[k].id() for k in spec["inset"]]
    if spec["params"].get("label_layer"):
        params["label_layer_id"] = layers[spec["params"]["label_layer"]].id()
    params["layout_name"] = f"E1 {name}"
    params["output_path"] = str(out_png)
    params["confirm_overwrite"] = True
    return compose_map(params, {"dry_run": False})


# ---------------------------------------------------------------------------
# Fault operators: (id, target rule, applies(base_spec, layout) -> bool, apply(layout, ctx))
# ---------------------------------------------------------------------------

def _mm(x, y):
    from qgis.core import QgsLayoutPoint, QgsUnitTypes

    return QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters) if hasattr(QgsUnitTypes, "LayoutMillimeters") else QgsLayoutPoint(x, y)


def _point(x, y):
    from qgis.core import Qgis, QgsLayoutPoint

    try:
        return QgsLayoutPoint(x, y, Qgis.LayoutUnit.Millimeters)
    except AttributeError:
        from qgis.core import QgsUnitTypes
        return QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters)


def _size(w, h):
    from qgis.core import Qgis, QgsLayoutSize

    try:
        return QgsLayoutSize(w, h, Qgis.LayoutUnit.Millimeters)
    except AttributeError:
        from qgis.core import QgsUnitTypes
        return QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters)


def _item(layout, item_id):
    return layout.itemById(item_id)


def _remove(layout, item_id):
    item = _item(layout, item_id)
    if item is not None:
        layout.removeLayoutItem(item)


def _page_size(layout):
    size = layout.pageCollection().page(0).pageSize()
    return float(size.width()), float(size.height())


def _grid(layout):
    return _item(layout, "main_map").grid()


def op_remove_title(layout, ctx):
    _remove(layout, "title")


def op_remove_legend(layout, ctx):
    _remove(layout, "legend")


def op_legend_missing_layer(layout, ctx):
    legend = _item(layout, "legend")
    legend.setAutoUpdateModel(False)
    root = legend.model().rootGroup()
    subject_names = {layer.name() for layer in ctx["subject_layers"]}
    for node in list(root.findLayers()):
        if node.layer() is not None and node.layer().name() in subject_names:
            node.parent().removeChildNode(node)
            break
    legend.updateLegend()


def op_legend_phantom(layout, ctx):
    from qgis.core import QgsProject, QgsVectorLayer

    phantom = QgsVectorLayer("LineString?crs=EPSG:4674", "Highways", "memory")
    QgsProject.instance().addMapLayer(phantom, False)
    legend = _item(layout, "legend")
    legend.setAutoUpdateModel(False)
    legend.model().rootGroup().addLayer(phantom)
    legend.updateLegend()


def op_legend_box_too_small(layout, ctx):
    legend = _item(layout, "legend")
    legend.setResizeToContents(False)
    legend.attemptResize(_size(12, 6))


def op_remove_scale(layout, ctx):
    _remove(layout, "scale_bar")
    _remove(layout, "scale_text")


def op_remove_scale_text(layout, ctx):
    _remove(layout, "scale_text")


def op_scalebar_too_small(layout, ctx):
    bar = _item(layout, "scale_bar")
    bar.setNumberOfSegments(1)
    bar.setNumberOfSegmentsLeft(0)
    bar.setUnitsPerSegment(bar.unitsPerSegment() / 20.0)
    bar.update()


def op_geographic_crs(layout, ctx):
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

    main = _item(layout, "main_map")
    geographic = QgsCoordinateReferenceSystem("EPSG:4674")
    transform = QgsCoordinateTransform(main.crs(), geographic, QgsProject.instance())
    extent = transform.transformBoundingBox(main.extent())
    main.setCrs(geographic)
    main.zoomToExtent(extent)
    main.grid().setEnabled(False)  # a metric grid interval would be meaningless in degrees


def op_remove_north(layout, ctx):
    _remove(layout, "north_arrow")
    _grid(layout).setAnnotationEnabled(False)


def op_north_as_text(layout, ctx):
    from qgis.core import QgsLayoutItemLabel

    arrow = _item(layout, "north_arrow")
    position, size = arrow.positionWithUnits(), arrow.sizeWithUnits()
    layout.removeLayoutItem(arrow)
    label = QgsLayoutItemLabel(layout)
    label.setText("N ↑")
    label.setId("north_arrow")
    layout.addLayoutItem(label)
    label.attemptMove(position)
    label.attemptResize(size)


def op_remove_source(layout, ctx):
    _remove(layout, "source")


def op_grid_zero_interval(layout, ctx):
    grid = _grid(layout)
    grid.setIntervalX(0.0)
    grid.setIntervalY(0.0)


def op_grid_no_annotations(layout, ctx):
    _grid(layout).setAnnotationEnabled(False)


def op_item_off_page(layout, ctx):
    width, _ = _page_size(layout)
    _item(layout, "legend").attemptMove(_point(width + 15.0, 20.0))


def op_item_in_margin(layout, ctx):
    bar = _item(layout, "scale_bar")
    position = bar.positionWithUnits()
    bar.attemptMove(_point(1.0, position.y()))


def op_items_overlap(layout, ctx):
    legend = _item(layout, "legend")
    _item(layout, "north_arrow").attemptMove(legend.positionWithUnits())


def op_tiny_font(layout, ctx):
    from qgis.core import QgsTextFormat

    label = _item(layout, "source")
    try:
        fmt = QgsTextFormat(label.textFormat())
        fmt.setSize(4.0)
        label.setTextFormat(fmt)
    except AttributeError:
        font = label.font()
        font.setPointSizeF(4.0)
        label.setFont(font)
    label.refresh()


def op_subtitle_larger_than_title(layout, ctx):
    from qgis.core import QgsTextFormat

    title, subtitle = _item(layout, "title"), _item(layout, "subtitle")
    try:
        title_size = QgsTextFormat(title.textFormat()).size()
        fmt = QgsTextFormat(subtitle.textFormat())
        fmt.setSize(title_size * 1.3)
        subtitle.setTextFormat(fmt)
    except AttributeError:
        font = subtitle.font()
        font.setPointSizeF(title.font().pointSizeF() * 1.3)
        subtitle.setFont(font)
    subtitle.refresh()


def op_extent_off_data(layout, ctx):
    from qgis.core import QgsRectangle

    main = _item(layout, "main_map")
    extent = main.extent()
    shift = extent.width() * 6.0
    main.zoomToExtent(QgsRectangle(extent.xMinimum() + shift, extent.yMinimum(), extent.xMaximum() + shift, extent.yMaximum()))


def op_blank_frame(layout, ctx):
    from qgis.core import QgsProject, QgsVectorLayer

    empty = QgsVectorLayer("Polygon?crs=EPSG:4674", "Empty", "memory")
    QgsProject.instance().addMapLayer(empty, False)
    main = _item(layout, "main_map")
    main.setKeepLayerSet(True)
    main.setLayers([empty])
    main.grid().setEnabled(False)


def op_confusable_colours(layout, ctx):
    from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer

    for layer, colour in zip(ctx["polygon_layers"][:2], ("#8B0000", "#006400")):
        layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": colour, "outline_color": "#000000"})))
        layer.triggerRepaint()


def op_colour_in_greyscale(layout, ctx):
    from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer

    layer = ctx["polygon_layers"][0]
    layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "#D9EAF4", "outline_color": "#0B4F6C"})))
    layer.triggerRepaint()


def op_inset_misplaced(layout, ctx):
    from qgis.core import QgsRectangle

    inset = _item(layout, "inset_map")
    extent = inset.extent()
    shift = extent.width() * 3.0
    inset.zoomToExtent(QgsRectangle(extent.xMinimum() + shift, extent.yMinimum(), extent.xMaximum() + shift, extent.yMaximum()))


def op_labels_dropped(layout, ctx):
    from qgis.core import QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling

    layer = ctx["label_layer"]
    settings = QgsPalLayerSettings(layer.labeling().settings()) if layer.labeling() else QgsPalLayerSettings()
    fmt = QgsTextFormat(settings.format())
    fmt.setSize(150.0)
    settings.setFormat(fmt)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()


def _has(item_id):
    return lambda layout, ctx: _item(layout, item_id) is not None


def _grid_on(layout, ctx):
    main = _item(layout, "main_map")
    return main is not None and main.grid().enabled()


OPERATORS = [
    ("F01_remove_title", "CART001", _has("title"), op_remove_title),
    ("F02_remove_legend", "CART002", _has("legend"), op_remove_legend),
    ("F03_legend_missing_layer", "CART020", _has("legend"), op_legend_missing_layer),
    ("F04_legend_phantom_layer", "CART021", _has("legend"), op_legend_phantom),
    ("F05_legend_box_too_small", "CART072", _has("legend"), op_legend_box_too_small),
    ("F06_remove_scale", "CART003", _has("scale_bar"), op_remove_scale),
    ("F07_remove_numeric_scale", "CART005", _has("scale_text"), op_remove_scale_text),
    ("F08_scalebar_too_small", "CART022", _has("scale_bar"), op_scalebar_too_small),
    ("F09_scalebar_on_geographic_crs", "CART024", _has("scale_bar"), op_geographic_crs),
    ("F10_remove_north_and_grid_labels", "CART006", _has("north_arrow"), op_remove_north),
    ("F11_north_as_text", "CART025", _has("north_arrow"), op_north_as_text),
    ("F12_remove_source_line", "CART007", _has("source"), op_remove_source),
    ("F13_grid_zero_interval", "CART026", _grid_on, op_grid_zero_interval),
    ("F14_grid_without_labels", "CART027", _grid_on, op_grid_no_annotations),
    ("F15_item_off_page", "CART040", _has("legend"), op_item_off_page),
    ("F16_item_in_margin", "CART041", _has("scale_bar"), op_item_in_margin),
    ("F17_items_overlap", "CART042", lambda l, c: _has("legend")(l, c) and _has("north_arrow")(l, c), op_items_overlap),
    ("F18_font_below_minimum", "CART044", _has("source"), op_tiny_font),
    ("F19_subtitle_larger_than_title", "CART045", lambda l, c: _has("title")(l, c) and _has("subtitle")(l, c), op_subtitle_larger_than_title),
    ("F20_extent_misses_data", "CART061", _has("main_map"), op_extent_off_data),
    ("F21_blank_frame", "CART062", _has("main_map"), op_blank_frame),
    ("F22_colours_confused_by_dichromats", "CART070", lambda l, c: len(c["polygon_layers"]) >= 2, op_confusable_colours),
    ("F23_colour_in_greyscale_figure", "CART073", lambda l, c: c["colour_mode"] == "greyscale" and c["polygon_layers"], op_colour_in_greyscale),
    ("F24_inset_does_not_locate_frame", "CART067", _has("inset_map"), op_inset_misplaced),
    ("F25_labels_dropped", "CART068", lambda l, c: c.get("label_layer") is not None, op_labels_dropped),
]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class MessageTrap:
    """Collects Warning/Critical messages sent to the QGIS message log."""

    def __init__(self):
        from qgis.core import Qgis, QgsApplication

        self.messages: list[dict] = []
        self._levels = {}
        for name in ("Warning", "Critical"):
            member = getattr(getattr(Qgis, "MessageLevel", Qgis), name)
            self._levels[int(member) if not hasattr(member, "value") else member.value] = name
        QgsApplication.messageLog().messageReceived.connect(self._receive)
        self.armed = False

    def _receive(self, message, tag, level):
        if not self.armed:
            return
        value = level.value if hasattr(level, "value") else int(level)
        if value in self._levels:
            self.messages.append({"level": self._levels[value], "tag": tag, "message": str(message)[:300]})

    def start(self):
        self.messages = []
        self.armed = True

    def stop(self):
        self.armed = False
        return list(self.messages)


def export_png(layout, path: Path, dpi: int) -> dict:
    from qgis.core import QgsLayoutExporter

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = dpi
    code = exporter.exportToImage(str(path), settings)
    success = getattr(getattr(QgsLayoutExporter, "ExportResult", QgsLayoutExporter), "Success")
    return {"result_code": str(code), "success": code == success}


def audit(layout_name: str, png: Path, colour_mode: str | None) -> dict:
    from sigmai.qgis_actions.cartography_engine import audit_map_layout

    params = {"layout_name": layout_name, "output_path": str(png)}
    if colour_mode:
        params["colour_mode"] = colour_mode
    report = audit_map_layout(params, {"dry_run": False})
    results = report.get("results") or []
    return {
        "grade": report.get("grade"), "score": report.get("score"),
        "status": {entry["id"]: entry["status"] for entry in results},
        "detail": {entry["id"]: str(entry.get("detail") or entry.get("detail_pt") or "")[:240] for entry in results},
        "failing": [entry["id"] for entry in results if entry["status"] == "fail"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--dem", required=True)
    parser.add_argument("--sites", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()

    from qgis.core import Qgis, QgsApplication, QgsProject

    app = QgsApplication([], False)
    app.initQgis()
    out, work = Path(args.out), Path(args.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    results_path = out / "results.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done.add((row["base"], row["operator"]))
    trap = MessageTrap()

    from sigmai.bridge_server import plugin_version
    meta = {"sigmai_version": plugin_version(), "qgis_version": Qgis.version(), "python": sys.version.split()[0],
            "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (out / "environment.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

    with results_path.open("a", encoding="utf-8") as sink:
        for base_name, spec in BASES.items():
            for op_id, target, applies, apply in [("F00_none", None, None, None)] + OPERATORS:
                if (base_name, op_id) in done:
                    continue
                layers = load_layers(Path(args.data), Path(args.dem), Path(args.sites))
                png = work / f"{base_name}__{op_id}.png"
                row = {"base": base_name, "operator": op_id, "target_rule": target}
                try:
                    composed = compose_base(base_name, layers, work / f"{base_name}__base.png")
                    layout_name = composed["layout_name"]
                    layout = QgsProject.instance().layoutManager().layoutByName(layout_name)
                    subject = spec["subject"] if isinstance(spec["subject"], list) else [spec["subject"]]
                    drawn = [layers[k] for k in spec["layers"]]
                    ctx = {
                        "subject_layers": [layers[k] for k in subject],
                        "polygon_layers": [l for l in drawn if hasattr(l, "geometryType") and l.geometryType() == getattr(getattr(Qgis, "GeometryType", None), "Polygon", 2)],
                        "colour_mode": spec["params"].get("colour_mode", "colour"),
                        "label_layer": layers[spec["params"]["label_layer"]] if spec["params"].get("label_layer") else None,
                    }
                    if apply is not None and not applies(layout, ctx):
                        row["applicable"] = False
                        sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                        sink.flush()
                        continue
                    row["applicable"] = True
                    trap.start()
                    exception = None
                    try:
                        if apply is not None:
                            apply(layout, ctx)
                        export = export_png(layout, png, COMMON["dpi"])
                    except Exception as exc:  # recorded: a fault that raises is not silent
                        exception = f"{type(exc).__name__}: {exc}"
                        export = {"result_code": None, "success": False}
                    row["qgis"] = {"export": export, "exception": exception, "log_messages": trap.stop()}
                    row["audit"] = audit(layout_name, png, ctx["colour_mode"] if ctx["colour_mode"] == "greyscale" else None)
                    if target:
                        row["target_status"] = row["audit"]["status"].get(target)
                        row["target_detail"] = row["audit"]["detail"].get(target)
                except Exception as exc:
                    row["harness_error"] = f"{type(exc).__name__}: {exc}"
                    row["traceback"] = traceback.format_exc()[-1500:]
                sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                sink.flush()
                print(base_name, op_id, row.get("target_status"), row.get("audit", {}).get("grade"), row.get("harness_error", ""), flush=True)
    QgsProject.instance().clear()
    app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
