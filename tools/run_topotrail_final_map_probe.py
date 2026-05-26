from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_plugin.client.sigmai_client import SigmaiClient

OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"


def command(client: SigmaiClient, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    payload = {
        "schema_version": "0.3",
        "request_id": f"topotrail-final-{action}",
        "action": action,
        "params": params or {},
        "dry_run": dry_run,
    }
    response = client.command(payload)
    if not response.get("ok"):
        raise RuntimeError(json.dumps(response, ensure_ascii=False, indent=2))
    return response["data"]


def main() -> None:
    client = SigmaiClient(timeout=180)
    layers: dict[str, dict[str, Any]] = {}

    vector_inputs = {
        "Zonas potenciais TopoTrail": OUT / "final2_zonas_clip_cruzeiro.gpkg",
        "Cruzeiro/SP": OUT / "final2_cruzeiro_epsg31983.gpkg",
        "Reserva e RPPN": OUT / "final2_reserva_epsg31983.gpkg",
        "Fazenda Batedor": OUT / "final2_fazenda_epsg31983.gpkg",
        "Trilha RCN e RPPN": OUT / "final2_trilha_rcn_epsg31983.gpkg",
        "Travessia Marins-Itaguare": OUT / "final2_trilha_marins_epsg31983.gpkg",
        "Trechos sobrepostos": OUT / "final2_intersecao_trilha_rcn.gpkg",
    }
    raster_inputs = {
        "Adequabilidade TopoTrail": OUT / "topotrail_rppn_batedor_4cartas_adequabilidade.tif",
        "Risco topografico TopoTrail": OUT / "topotrail_rppn_batedor_4cartas_risco_topografico.tif",
    }

    for name, path in raster_inputs.items():
        layers[name] = command(client, "load_raster_layer", {"path": str(path), "name": name})
    for name, path in vector_inputs.items():
        layers[name] = command(client, "load_vector_layer", {"path": str(path), "name": name})

    style_requests = [
        ("Zonas potenciais TopoTrail", "#2E8B57", "#0B3D2E", 0.32, 0.55),
        ("Cruzeiro/SP", "#FFFFFF", "#555555", 0.03, 0.45),
        ("Reserva e RPPN", "#FFFFFF", "#345C2C", 0.04, 0.65),
        ("Fazenda Batedor", "#FFFFFF", "#1F4E79", 0.04, 0.65),
        ("Trilha RCN e RPPN", "#5B1020", "#5B1020", 1.0, 0.85),
        ("Travessia Marins-Itaguare", "#0E3A5B", "#0E3A5B", 1.0, 0.85),
        ("Trechos sobrepostos", "#FFD166", "#7A3E00", 0.8, 1.2),
    ]
    for name, fill, stroke, opacity, width in style_requests:
        command(
            client,
            "set_layer_style",
            {
                "layer_id": layers[name]["layer_id"],
                "fill_color": fill,
                "stroke_color": stroke,
                "stroke_width": width,
                "opacity": opacity,
            },
        )

    map_layer_order = [
        layers["Trechos sobrepostos"]["layer_id"],
        layers["Travessia Marins-Itaguare"]["layer_id"],
        layers["Trilha RCN e RPPN"]["layer_id"],
        layers["Zonas potenciais TopoTrail"]["layer_id"],
        layers["Fazenda Batedor"]["layer_id"],
        layers["Reserva e RPPN"]["layer_id"],
        layers["Cruzeiro/SP"]["layer_id"],
        layers["Risco topografico TopoTrail"]["layer_id"],
        layers["Adequabilidade TopoTrail"]["layer_id"],
    ]
    legend_layers = [
        layers["Zonas potenciais TopoTrail"]["layer_id"],
        layers["Reserva e RPPN"]["layer_id"],
        layers["Fazenda Batedor"]["layer_id"],
        layers["Trilha RCN e RPPN"]["layer_id"],
        layers["Travessia Marins-Itaguare"]["layer_id"],
        layers["Trechos sobrepostos"]["layer_id"],
    ]

    png_path = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_final_CORRIGIDO.png"
    pdf_path = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_final_CORRIGIDO.pdf"
    common = {
        "layer_id": layers["Zonas potenciais TopoTrail"]["layer_id"],
        "map_layer_ids": map_layer_order,
        "legend_layers": legend_layers,
        "title": "Adequabilidade e risco TopoTrail - Cruzeiro/SP",
        "subtitle": "TopoTrail: cartas 22S465HN, 22S465SN, 22S465VN e 22S465ZN",
        "layout_template": "scientific_publication",
        "style_profile": "environmental_green",
        "map_crs": "EPSG:31983",
        "map_author": "Luan da Silva Cortes Maciel",
        "organization": "Herpeto Mantiqueira",
        "data_source": "DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguare",
        "source_text": "Fonte: DataGEO; SMMA; RPPN Gigante do Itaguare. Autor: Luan da Silva Cortes Maciel. CRS: SIRGAS 2000 / UTM 23S. SIGMAI/QGIS.",
        "include_grid": True,
        "include_scale_bar": False,
        "include_north_arrow": True,
        "include_source": True,
        "include_authorship": True,
        "include_logo": True,
        "public_mode": True,
        "confirm_overwrite": True,
        "units_per_segment": 0.2,
    }
    png_result = command(client, "generate_professional_map", {**common, "output_path": str(png_path), "format": "png"})
    command(
        client,
        "add_layout_label",
        {
            "layout_name": png_result["layout_name"],
            "item_id": "manual_scale_bar",
            "text": "Escala grafica: 0 |----|----| 2 km",
            "x": 14,
            "y": 174,
            "width": 70,
            "height": 8,
            "font_size": 8,
            "bold": True,
            "align": "left",
        },
    )
    command(client, "export_layout", {"layout_name": png_result["layout_name"], "format": "png", "path": str(png_path), "confirm_overwrite": True})
    pdf_result = command(client, "generate_professional_map", {**common, "output_path": str(pdf_path), "format": "pdf"})
    command(
        client,
        "add_layout_label",
        {
            "layout_name": pdf_result["layout_name"],
            "item_id": "manual_scale_bar",
            "text": "Escala grafica: 0 |----|----| 2 km",
            "x": 14,
            "y": 174,
            "width": 70,
            "height": 8,
            "font_size": 8,
            "bold": True,
            "align": "left",
        },
    )
    command(client, "export_layout", {"layout_name": pdf_result["layout_name"], "format": "pdf", "path": str(pdf_path), "confirm_overwrite": True})
    quality = command(client, "evaluate_map_quality", {"layout_name": png_result["layout_name"], "output_path": str(png_path)})
    report = {
        "layers": layers,
        "png_result": png_result,
        "pdf_result": pdf_result,
        "quality": quality,
        "outputs": {"png": str(png_path), "pdf": str(pdf_path)},
    }
    report_path = OUT / "SIGMAI_TOPOtrail_RPPN_BATEDOR_FINAL_CORRIGIDO.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
