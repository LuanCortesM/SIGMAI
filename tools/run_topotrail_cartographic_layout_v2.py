from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_plugin.client.sigmai_client import SigmaiClient


OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"


def command(client: SigmaiClient, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    payload = {
        "schema_version": "0.3",
        "request_id": f"topotrail-v2-{action}",
        "action": action,
        "params": params or {},
        "dry_run": dry_run,
    }
    response = client.command(payload)
    if not response.get("ok"):
        raise RuntimeError(json.dumps(response, ensure_ascii=False, indent=2))
    return response["data"]


def load_layers(client: SigmaiClient) -> dict[str, dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    inputs = {
        "Adequabilidade TopoTrail": ("load_raster_layer", OUT / "topotrail_rppn_batedor_4cartas_adequabilidade.tif"),
        "Risco TopoTrail": ("load_raster_layer", OUT / "topotrail_rppn_batedor_4cartas_risco_topografico.tif"),
        "Zonas potenciais": ("load_vector_layer", OUT / "final2_zonas_clip_cruzeiro.gpkg"),
        "Cruzeiro/SP": ("load_vector_layer", OUT / "final2_cruzeiro_epsg31983.gpkg"),
        "Reserva e RPPN": ("load_vector_layer", OUT / "final2_reserva_epsg31983.gpkg"),
        "Fazenda Batedor": ("load_vector_layer", OUT / "final2_fazenda_epsg31983.gpkg"),
        "Trilha RCN/RPPN": ("load_vector_layer", OUT / "final2_trilha_rcn_epsg31983.gpkg"),
        "Trechos sobrepostos": ("load_vector_layer", OUT / "final2_intersecao_trilha_rcn.gpkg"),
    }
    for name, (action, path) in inputs.items():
        layers[name] = command(client, action, {"path": str(path), "name": name})
    return layers


def style_layers(client: SigmaiClient, layers: dict[str, dict[str, Any]]) -> None:
    styles = {
        "Zonas potenciais": {"fill_color": "#6CC5A2", "stroke_color": "#006B4A", "stroke_width": 0.35, "opacity": 0.40},
        "Cruzeiro/SP": {"fill_color": "#FFFFFF", "stroke_color": "#636363", "stroke_width": 0.25, "opacity": 0.05},
        "Reserva e RPPN": {"fill_color": "#FFFFFF", "stroke_color": "#31572C", "stroke_width": 0.85, "opacity": 0.03},
        "Fazenda Batedor": {"fill_color": "#FFFFFF", "stroke_color": "#1D4E89", "stroke_width": 0.85, "opacity": 0.03},
        "Trilha RCN/RPPN": {"fill_color": "#6A0019", "stroke_color": "#6A0019", "stroke_width": 1.25, "opacity": 0.95},
        "Trechos sobrepostos": {"fill_color": "#FFD166", "stroke_color": "#7A3E00", "stroke_width": 0.9, "opacity": 0.88},
    }
    for name, style in styles.items():
        command(client, "set_layer_style", {"layer_id": layers[name]["layer_id"], **style})


def make_layout(client: SigmaiClient, layers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stamp = datetime.now().strftime("%H%M%S")
    layout_name = f"SIGMAI TopoTrail cartografia v2 {stamp}"
    command(client, "create_layout", {"layout_name": layout_name})

    main_layers = [
        layers["Trechos sobrepostos"]["layer_id"],
        layers["Trilha RCN/RPPN"]["layer_id"],
        layers["Reserva e RPPN"]["layer_id"],
        layers["Fazenda Batedor"]["layer_id"],
        layers["Zonas potenciais"]["layer_id"],
        layers["Cruzeiro/SP"]["layer_id"],
        layers["Risco TopoTrail"]["layer_id"],
        layers["Adequabilidade TopoTrail"]["layer_id"],
    ]
    command(
        client,
        "add_layout_map",
        {
            "layout_name": layout_name,
            "layer_id": layers["Zonas potenciais"]["layer_id"],
            "layer_ids": main_layers,
            "item_id": "main_map",
            "x": 12,
            "y": 30,
            "width": 176,
            "height": 122,
            "margin_percent": 6,
            "map_crs": "EPSG:31983",
        },
    )
    command(
        client,
        "set_layout_extent",
        {
            "layout_name": layout_name,
            "map_item_id": "main_map",
            "layer_id": layers["Zonas potenciais"]["layer_id"],
            "layer_ids": main_layers,
            "margin_percent": 6,
            "map_crs": "EPSG:31983",
        },
    )
    command(client, "add_layout_grid", {"layout_name": layout_name, "map_item_id": "main_map"})

    inset_layers = [
        layers["Zonas potenciais"]["layer_id"],
        layers["Reserva e RPPN"]["layer_id"],
        layers["Fazenda Batedor"]["layer_id"],
        layers["Cruzeiro/SP"]["layer_id"],
    ]
    command(
        client,
        "add_layout_map",
        {
            "layout_name": layout_name,
            "layer_id": layers["Cruzeiro/SP"]["layer_id"],
            "layer_ids": inset_layers,
            "item_id": "inset_map",
            "x": 202,
            "y": 112,
            "width": 70,
            "height": 47,
            "margin_percent": 8,
            "map_crs": "EPSG:31983",
        },
    )
    command(
        client,
        "set_layout_extent",
        {
            "layout_name": layout_name,
            "map_item_id": "inset_map",
            "layer_id": layers["Cruzeiro/SP"]["layer_id"],
            "layer_ids": inset_layers,
            "margin_percent": 8,
            "map_crs": "EPSG:31983",
        },
    )

    command(client, "add_layout_label", {"layout_name": layout_name, "item_id": "title", "text": "Adequabilidade e risco topografico para trilhas - Cruzeiro/SP", "x": 12, "y": 7, "width": 264, "height": 10, "font_size": 16, "bold": True, "align": "center"})
    command(client, "add_layout_label", {"layout_name": layout_name, "item_id": "subtitle", "text": "Modelagem TopoTrail com cartas 22S465HN, 22S465SN, 22S465VN e 22S465ZN", "x": 12, "y": 18, "width": 264, "height": 7, "font_size": 9, "align": "center"})
    command(client, "add_layout_label", {"layout_name": layout_name, "item_id": "scale_manual", "text": "Escala grafica: 0 |----|----| 2 km", "x": 14, "y": 155, "width": 80, "height": 8, "font_size": 8, "bold": True})
    command(client, "add_layout_north_arrow", {"layout_name": layout_name, "item_id": "north_arrow", "x": 178, "y": 33, "width": 9, "height": 15})
    command(client, "add_layout_label", {"layout_name": layout_name, "item_id": "inset_title", "text": "Localizacao no municipio", "x": 202, "y": 104, "width": 70, "height": 7, "font_size": 8, "bold": True, "align": "center"})
    command(
        client,
        "add_layout_legend",
        {
            "layout_name": layout_name,
            "item_id": "legend",
            "title": "Legenda",
            "x": 198,
            "y": 31,
            "width": 84,
            "height": 70,
            "linked_map_item_id": "main_map",
            "legend_layers": [
                layers["Zonas potenciais"]["layer_id"],
                layers["Reserva e RPPN"]["layer_id"],
                layers["Fazenda Batedor"]["layer_id"],
                layers["Trilha RCN/RPPN"]["layer_id"],
                layers["Trechos sobrepostos"]["layer_id"],
            ],
            "filter_to_map_layers": True,
        },
    )
    source = "Fonte: DataGEO; SMMA; RPPN Gigante do Itaguare. Autor: Luan da Silva Cortes Maciel. CRS: SIRGAS 2000 / UTM 23S. SIGMAI/QGIS."
    command(client, "add_layout_label", {"layout_name": layout_name, "item_id": "source", "text": source, "x": 12, "y": 184, "width": 230, "height": 8, "font_size": 7})
    logo = ROOT / "sigmai" / "icons" / "sigmai_logo_full.png"
    if logo.exists():
        command(client, "add_layout_picture", {"layout_name": layout_name, "item_id": "sigmai_logo", "path": str(logo), "x": 248, "y": 176, "width": 25, "height": 11})

    png_path = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_FINAL_V2.png"
    pdf_path = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_FINAL_V2.pdf"
    png = command(client, "export_layout", {"layout_name": layout_name, "format": "png", "path": str(png_path), "confirm_overwrite": True})
    pdf = command(client, "export_layout", {"layout_name": layout_name, "format": "pdf", "path": str(pdf_path), "confirm_overwrite": True})
    quality = command(client, "evaluate_map_quality", {"layout_name": layout_name, "output_path": str(png_path)})
    return {"layout_name": layout_name, "png": png, "pdf": pdf, "quality": quality, "outputs": {"png": str(png_path), "pdf": str(pdf_path)}}


def main() -> None:
    client = SigmaiClient(timeout=180)
    layers = load_layers(client)
    style_layers(client, layers)
    result = {"layers": layers, "layout": make_layout(client, layers)}
    report = OUT / "SIGMAI_TOPOtrail_RPPN_BATEDOR_FINAL_V2.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
