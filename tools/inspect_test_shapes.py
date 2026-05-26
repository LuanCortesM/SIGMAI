from __future__ import annotations

import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOT = ROOT.parent
DIAGNOSTICS = ROOT / "diagnostics"
JSON_REPORT = DIAGNOSTICS / "test_shapes_inventory.json"
MD_REPORT = DIAGNOSTICS / "test_shapes_inventory.md"

SHAPE_TYPE_NAMES = {
    0: "Null Shape",
    1: "Point",
    3: "Polyline",
    5: "Polygon",
    8: "MultiPoint",
    11: "PointZ",
    13: "PolylineZ",
    15: "PolygonZ",
    18: "MultiPointZ",
    21: "PointM",
    23: "PolylineM",
    25: "PolygonM",
    28: "MultiPointM",
    31: "MultiPatch",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def find_shapes_folder() -> Path | None:
    candidates = []
    for path in SEARCH_ROOT.rglob("*"):
        if path.is_dir():
            lowered = path.name.lower()
            if "shape" in lowered and ("teste" in lowered or "test" in lowered):
                candidates.append(path)
    return sorted(candidates, key=lambda p: len(str(p)))[0] if candidates else None


def shapefile_components(shp_path: Path) -> dict[str, bool]:
    base = shp_path.with_suffix("")
    return {
        ext: base.with_suffix(ext).exists()
        for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qmd"]
    }


def read_shp_header(shp_path: Path) -> dict[str, Any]:
    try:
        data = shp_path.read_bytes()[:100]
        if len(data) < 100:
            return {"error": "Header shorter than 100 bytes."}
        shape_type = struct.unpack("<i", data[32:36])[0]
        xmin, ymin, xmax, ymax = struct.unpack("<4d", data[36:68])
        file_length_words = struct.unpack(">i", data[24:28])[0]
        return {
            "shape_type_code": shape_type,
            "shape_type": SHAPE_TYPE_NAMES.get(shape_type, f"Unknown ({shape_type})"),
            "extent": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
            "file_length_bytes": file_length_words * 2,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def read_prj(shp_path: Path) -> str:
    prj_path = shp_path.with_suffix(".prj")
    if not prj_path.exists():
        return ""
    return prj_path.read_text(encoding="utf-8", errors="replace").strip()


def try_pyqgis_inventory(shp_path: Path) -> dict[str, Any] | None:
    try:
        from qgis.core import QgsVectorLayer  # type: ignore
    except Exception:
        return None

    layer = QgsVectorLayer(str(shp_path), shp_path.stem, "ogr")
    item: dict[str, Any] = {
        "path": str(shp_path),
        "name": shp_path.stem,
        "valid": bool(layer.isValid()),
        "provider": layer.providerType(),
        "crs": layer.crs().authid() if layer.crs().isValid() else "",
        "geometry_type": layer.geometryType(),
        "wkb_type": layer.wkbType(),
        "feature_count": int(layer.featureCount()) if layer.isValid() else None,
        "extent": None,
        "fields": [],
        "sample_attributes": [],
        "invalid_geometry_count": None,
    }
    if layer.isValid():
        extent = layer.extent()
        item["extent"] = {
            "xmin": extent.xMinimum(),
            "ymin": extent.yMinimum(),
            "xmax": extent.xMaximum(),
            "ymax": extent.yMaximum(),
        }
        item["fields"] = [{"name": field.name(), "type": field.typeName()} for field in layer.fields()]
        invalid_count = 0
        for index, feature in enumerate(layer.getFeatures()):
            if index < 5:
                item["sample_attributes"].append(dict(feature.attributes()))
            geometry = feature.geometry()
            if geometry and not geometry.isGeosValid():
                invalid_count += 1
        item["invalid_geometry_count"] = invalid_count
    return item


def inspect_folder(folder: Path) -> dict[str, Any]:
    shapefiles = []
    for shp_path in sorted(folder.rglob("*.shp")):
        pyqgis_item = try_pyqgis_inventory(shp_path)
        item = pyqgis_item or {
            "path": str(shp_path),
            "name": shp_path.stem,
            "valid": None,
            "crs": "",
            "geometry_type": "",
            "feature_count": None,
            "extent": None,
            "fields": [],
            "sample_attributes": [],
            "invalid_geometry_count": None,
            "note": "PyQGIS not available; only filesystem/header inspection was performed.",
        }
        item["components"] = shapefile_components(shp_path)
        item["header"] = read_shp_header(shp_path)
        item["prj_wkt"] = read_prj(shp_path)
        item["has_prj"] = bool(item["components"].get(".prj"))
        shapefiles.append(item)

    files = [
        {
            "path": str(path),
            "relative_path": str(path.relative_to(folder)),
            "size_bytes": path.stat().st_size,
            "suffix": path.suffix.lower(),
        }
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    ]
    return {
        "generated_at": now(),
        "folder": str(folder),
        "files": files,
        "shapefiles": shapefiles,
        "rasters": [file for file in files if file["suffix"] in {".tif", ".tiff"}],
        "gpx": [file for file in files if file["suffix"] == ".gpx"],
        "kml": [file for file in files if file["suffix"] == ".kml"],
        "missing_prj": [item["path"] for item in shapefiles if not item["has_prj"]],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Test Shapes Inventory",
        "",
        f"Generated at: `{report.get('generated_at')}`",
        f"Folder: `{report.get('folder')}`",
        "",
        "## Files",
        "",
        "| File | Size | Type |",
        "|---|---:|---|",
    ]
    root = Path(report["folder"])
    for file in report.get("files", []):
        lines.append(f"| `{file['relative_path']}` | {file['size_bytes']} | `{file['suffix']}` |")
    lines.extend(["", "## Shapefiles", "", "| Dataset | Complete | PRJ | Shape Type | CRS | Features | Invalid Geometries |", "|---|---:|---:|---|---|---:|---:|"])
    for item in report.get("shapefiles", []):
        components = item.get("components", {})
        complete = all(components.get(ext) for ext in [".shp", ".shx", ".dbf"])
        relative = Path(item["path"]).relative_to(root)
        shape_type = item.get("header", {}).get("shape_type", item.get("geometry_type", ""))
        lines.append(
            f"| `{relative}` | {complete} | {item.get('has_prj')} | {shape_type} | `{item.get('crs', '')}` | {item.get('feature_count')} | {item.get('invalid_geometry_count')} |"
        )
    lines.extend(["", "## Missing PRJ", ""])
    for item in report.get("missing_prj", []):
        lines.append(f"- `{item}`")
    if not report.get("missing_prj"):
        lines.append("- None detected among `.shp` datasets.")
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    folder = find_shapes_folder()
    if folder is None:
        raise SystemExit("Shapes test folder not found.")
    report = inspect_folder(folder)
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_markdown(report)
    print(str(JSON_REPORT))
    print(str(MD_REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
