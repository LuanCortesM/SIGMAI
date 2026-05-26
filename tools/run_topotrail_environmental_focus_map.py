from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from textwrap import wrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_plugin.client.sigmai_client import SigmaiClient


OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
BASE_PNG = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_BASE.png"
BASE_PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_BASE.pdf"
FINAL_PNG = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_FINAL.png"
FINAL_PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_FINAL.pdf"
REPORT_JSON = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_REPORT.json"
REPORT_MD = OUT / "RELATORIO_SIGMAI_TOPOtrail_ENVIRONMENTAL_FOCUS_MAP.md"


MAP_PARAMETERS: dict[str, Any] = {
    "map_intent": "environmental_focus_map",
    "message_focus": "Mostrar se a trilha RCN/RPPN cruza ou margeia zonas potenciais TopoTrail dentro do contexto RPPN/Fazenda Batedor.",
    "spatial_question": "A trilha existente atravessa areas potenciais ou trechos prioritarios no setor RPPN/Fazenda Batedor?",
    "template": "environmental_focus_map",
    "crs": "SIRGAS 2000 / UTM zone 23S",
    "scale_policy": "metric_projected_scale",
    "north_policy": "small_subordinate",
    "legend_policy": "semantic_grouped_legend",
    "palette": "environmental_focus_palette",
    "layer_roles": {
        "primary_result": ["Trechos sobrepostos", "Zonas potenciais na RPPN", "Zonas potenciais na Fazenda Batedor"],
        "route_or_trail": ["Trilha RCN/RPPN"],
        "primary_boundary": ["Reserva Chico Nunes / RPPN"],
        "secondary_boundary": ["Fazenda Batedor"],
        "terrain_context": ["Risco TopoTrail"],
        "administrative_context": ["Cruzeiro/SP"],
    },
}


def command(client: SigmaiClient, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
    payload = {
        "schema_version": "0.3",
        "request_id": f"topotrail-env-focus-{action}",
        "action": action,
        "params": params or {},
        "dry_run": dry_run,
    }
    response = client.command(payload)
    if not response.get("ok"):
        raise RuntimeError(json.dumps(response, ensure_ascii=False, indent=2))
    return response.get("data", {})


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill: str, chars: int, bold: bool = False) -> int:
    x, y = xy
    for line in wrap(text, chars):
        draw.text((x, y), line, fill=fill, font=font(size, bold))
        y += size + 8
    return y


def panel(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str = "#FFFFFF", outline: str = "#CCD6CE") -> None:
    draw.rounded_rectangle(xy, radius=18, fill=fill, outline=outline, width=3)


def callout(draw: ImageDraw.ImageDraw, xy: tuple[int, int], target: tuple[int, int], title: str, body: str, color: str, width: int = 460) -> None:
    x, y = xy
    lines = wrap(body, 34)
    h = 62 + len(lines) * 30 + 18
    draw.line((x + width // 2, y + h // 2, target[0], target[1]), fill=color, width=6)
    draw.ellipse((target[0] - 12, target[1] - 12, target[0] + 12, target[1] + 12), fill=color, outline="#FFFFFF", width=4)
    draw.rounded_rectangle((x, y, x + width, y + h), radius=12, fill="#FFFFFA", outline=color, width=4)
    draw.text((x + 18, y + 13), title, fill="#1E2723", font=font(30, True))
    yy = y + 55
    for line in lines:
        draw.text((x + 18, yy), line, fill="#45514B", font=font(22))
        yy += 30


def load_layers(client: SigmaiClient) -> dict[str, dict[str, Any]]:
    inputs = {
        "Risco TopoTrail": ("load_raster_layer", OUT / "topotrail_rppn_batedor_4cartas_risco_topografico.tif"),
        "Zonas potenciais na RPPN": ("load_vector_layer", OUT / "final2_zonas_clip_reserva.gpkg"),
        "Zonas potenciais na Fazenda Batedor": ("load_vector_layer", OUT / "final2_zonas_clip_fazenda.gpkg"),
        "Zonas potenciais - Cruzeiro": ("load_vector_layer", OUT / "final2_zonas_clip_cruzeiro.gpkg"),
        "Cruzeiro/SP": ("load_vector_layer", OUT / "final2_cruzeiro_epsg31983.gpkg"),
        "Reserva Chico Nunes / RPPN": ("load_vector_layer", OUT / "final2_reserva_epsg31983.gpkg"),
        "Fazenda Batedor": ("load_vector_layer", OUT / "final2_fazenda_epsg31983.gpkg"),
        "Trilha RCN/RPPN": ("load_vector_layer", OUT / "final2_trilha_rcn_epsg31983.gpkg"),
        "Trechos sobrepostos": ("load_vector_layer", OUT / "final2_intersecao_trilha_rcn.gpkg"),
    }
    layers: dict[str, dict[str, Any]] = {}
    for name, (action, path) in inputs.items():
        layers[name] = command(client, action, {"path": str(path), "name": name})
    return layers


def apply_semantic_styles(client: SigmaiClient, layers: dict[str, dict[str, Any]]) -> None:
    styles = {
        "Zonas potenciais na RPPN": {"fill_color": "#A9DCC7", "stroke_color": "#0C7A5B", "stroke_width": 0.45, "opacity": 0.45},
        "Zonas potenciais na Fazenda Batedor": {"fill_color": "#CDEDDC", "stroke_color": "#0C7A5B", "stroke_width": 0.40, "opacity": 0.42},
        "Zonas potenciais - Cruzeiro": {"fill_color": "#BFE7D4", "stroke_color": "#0C7A5B", "stroke_width": 0.20, "opacity": 0.22},
        "Cruzeiro/SP": {"fill_color": "#FFFFFF", "stroke_color": "#777777", "stroke_width": 0.25, "opacity": 0.04},
        "Reserva Chico Nunes / RPPN": {"fill_color": "#FFFFFF", "stroke_color": "#31572C", "stroke_width": 1.15, "opacity": 0.20},
        "Fazenda Batedor": {"fill_color": "#FFFFFF", "stroke_color": "#155799", "stroke_width": 1.15, "opacity": 0.20},
        "Trilha RCN/RPPN": {"fill_color": "#7B0022", "stroke_color": "#7B0022", "stroke_width": 1.45, "opacity": 1.0},
        "Trechos sobrepostos": {"fill_color": "#FFD166", "stroke_color": "#8A4F00", "stroke_width": 1.0, "opacity": 0.90},
    }
    for name, style in styles.items():
        command(client, "set_layer_style", {"layer_id": layers[name]["layer_id"], **style})


def create_base_qgis_layout(client: SigmaiClient, layers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stamp = datetime.now().strftime("%H%M%S")
    layout_name = f"SIGMAI TopoTrail Environmental Focus {stamp}"
    command(client, "create_layout", {"layout_name": layout_name, "page_size": "A4", "orientation": "landscape"})

    main_layers = [
        layers["Trechos sobrepostos"]["layer_id"],
        layers["Trilha RCN/RPPN"]["layer_id"],
        layers["Reserva Chico Nunes / RPPN"]["layer_id"],
        layers["Fazenda Batedor"]["layer_id"],
        layers["Zonas potenciais na RPPN"]["layer_id"],
        layers["Zonas potenciais na Fazenda Batedor"]["layer_id"],
        layers["Risco TopoTrail"]["layer_id"],
    ]
    overview_layers = [
        layers["Trechos sobrepostos"]["layer_id"],
        layers["Trilha RCN/RPPN"]["layer_id"],
        layers["Reserva Chico Nunes / RPPN"]["layer_id"],
        layers["Fazenda Batedor"]["layer_id"],
        layers["Zonas potenciais - Cruzeiro"]["layer_id"],
        layers["Cruzeiro/SP"]["layer_id"],
        layers["Risco TopoTrail"]["layer_id"],
    ]

    # Base QGIS page intentionally keeps only cartographic map frames.
    command(
        client,
        "add_layout_map",
        {
            "layout_name": layout_name,
            "layer_id": layers["Trechos sobrepostos"]["layer_id"],
            "layer_ids": main_layers,
            "item_id": "main_focus_map",
            "x": 8,
            "y": 8,
            "width": 210,
            "height": 183,
            "margin_percent": 120,
            "map_crs": "EPSG:31983",
        },
    )
    command(
        client,
        "set_layout_extent",
        {
            "layout_name": layout_name,
            "map_item_id": "main_focus_map",
            "layer_id": layers["Trechos sobrepostos"]["layer_id"],
            "layer_ids": main_layers,
            "margin_percent": 120,
            "map_crs": "EPSG:31983",
        },
    )
    command(
        client,
        "add_layout_map",
        {
            "layout_name": layout_name,
            "layer_id": layers["Zonas potenciais - Cruzeiro"]["layer_id"],
            "layer_ids": overview_layers,
            "item_id": "overview_map",
            "x": 224,
            "y": 20,
            "width": 65,
            "height": 60,
            "margin_percent": 6,
            "map_crs": "EPSG:31983",
        },
    )
    command(
        client,
        "set_layout_extent",
        {
            "layout_name": layout_name,
            "map_item_id": "overview_map",
            "layer_id": layers["Zonas potenciais - Cruzeiro"]["layer_id"],
            "layer_ids": overview_layers,
            "margin_percent": 6,
            "map_crs": "EPSG:31983",
        },
    )
    png = command(client, "export_layout", {"layout_name": layout_name, "format": "png", "path": str(BASE_PNG), "confirm_overwrite": True})
    pdf = command(client, "export_layout", {"layout_name": layout_name, "format": "pdf", "path": str(BASE_PDF), "confirm_overwrite": True})
    quality = command(client, "evaluate_map_quality", {"layout_name": layout_name, "output_path": str(BASE_PNG)})
    return {"layout_name": layout_name, "png": png, "pdf": pdf, "quality": quality}


def compose_final_plate() -> None:
    src = Image.open(BASE_PNG).convert("RGB")

    # The base layout contains a big main map on the left and an overview map on the right.
    main = src.crop((90, 92, 2575, 2260)).resize((2170, 1840), Image.Resampling.LANCZOS)
    overview = src.crop((2630, 240, 3420, 960)).resize((720, 650), Image.Resampling.LANCZOS)

    # Soften background model contrast while preserving valid QGIS geometry render.
    main = main.filter(ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=3))
    overview = overview.filter(ImageFilter.UnsharpMask(radius=1.0, percent=70, threshold=3))

    page = Image.new("RGB", (3507, 2480), "#F6F7F1")
    draw = ImageDraw.Draw(page)

    dark = "#1F2824"
    muted = "#59645F"
    accent = "#0A5C49"
    rppn = "#31572C"
    batedor = "#155799"
    trail = "#7B0022"
    overlap = "#C88216"
    potential = "#0C7A5B"

    draw.rectangle((0, 0, 3507, 30), fill=accent)
    draw.text((112, 66), "RPPN, Fazenda Batedor e trilha RCN/RPPN", fill=dark, font=font(62, True))
    draw.text((116, 143), "Adequabilidade TopoTrail e trechos prioritários para verificação de campo - Cruzeiro/SP", fill=muted, font=font(32))
    draw.text((116, 190), "Template: environmental_focus_map | CRS: SIRGAS 2000 / UTM zona 23S", fill=muted, font=font(27))

    map_x, map_y = 112, 300
    panel(draw, (map_x - 15, map_y - 15, map_x + 2170 + 15, map_y + 1840 + 15), "#FFFFFF", "#171D1A")
    page.paste(main, (map_x, map_y))
    draw.rectangle((map_x, map_y, map_x + 2170, map_y + 1840), outline="#111111", width=3)
    draw.rectangle((map_x + 18, map_y + 18, map_x + 625, map_y + 68), fill=(10, 92, 73), outline="#FFFFFF", width=2)
    draw.text((map_x + 30, map_y + 26), "PAINEL PRINCIPAL: detalhe ambiental", fill="#FFFFFF", font=font(26, True))

    callout(draw, (map_x + 42, map_y + 110), (map_x + 620, map_y + 585), "Reserva Chico Nunes / RPPN", "Limite ambiental principal. Deve ser lido junto aos trechos amarelos e à trilha.", rppn, 520)
    callout(draw, (map_x + 42, map_y + 405), (map_x + 720, map_y + 850), "Fazenda Batedor", "Limite fundiário de referência para recorte e interpretação local.", batedor, 480)
    callout(draw, (map_x + 42, map_y + 1390), (map_x + 970, map_y + 1265), "Trilha RCN/RPPN", "Percurso existente. A linha vinho deve permanecer legível sobre o relevo.", trail, 500)
    callout(draw, (map_x + 850, map_y + 100), (map_x + 710, map_y + 715), "Trechos prioritários", "Amarelo: interseção ou proximidade funcional entre trilha e zonas potenciais.", overlap, 510)
    callout(draw, (map_x + 1495, map_y + 370), (map_x + 1555, map_y + 1010), "Zonas TopoTrail", "Verde: áreas potenciais. Nesta prancha elas são contexto analítico, não o único foco.", potential, 500)

    side_x = 2390
    panel(draw, (side_x, 300, 3388, 2180), "#FFFFFF", "#D0D9D3")
    draw.text((side_x + 48, 348), "Leitura cartográfica", fill=dark, font=font(43, True))
    y = 422
    y = draw_text(draw, (side_x + 52, y), MAP_PARAMETERS["spatial_question"], 25, muted, 56)
    y += 30

    legend = [
        ("Resultado da análise", None, None, "header"),
        ("Trechos prioritários", "sobreposição trilha-zona potencial", "#FFD166", overlap),
        ("Zonas potenciais TopoTrail", "adequabilidade/favorabilidade", "#BFE7D4", potential),
        ("Limites", None, None, "header"),
        ("Reserva Chico Nunes / RPPN", "área ambiental principal", "#FFFFFF", rppn),
        ("Fazenda Batedor", "limite fundiário", "#FFFFFF", batedor),
        ("Trilhas", None, None, "header"),
        ("Trilha RCN/RPPN", "percurso existente", trail, trail),
        ("Contexto físico", None, None, "header"),
        ("Risco/relevo TopoTrail", "base topográfica em cinza", "#C5CAC7", "#6F7672"),
    ]
    for title, desc, fill, outline in legend:
        if outline == "header":
            draw.text((side_x + 52, y + 8), title, fill=accent, font=font(26, True))
            y += 48
            continue
        if fill == outline and title == "Trilha RCN/RPPN":
            draw.line((side_x + 58, y + 32, side_x + 138, y + 32), fill=outline, width=14)
        elif title in {"Reserva Chico Nunes / RPPN", "Fazenda Batedor"}:
            draw.line((side_x + 58, y + 32, side_x + 138, y + 32), fill=outline, width=8)
        else:
            draw.rounded_rectangle((side_x + 58, y + 7, side_x + 138, y + 62), radius=5, fill=fill, outline=outline, width=5)
        draw.text((side_x + 166, y), title, fill=dark, font=font(28, True))
        draw.text((side_x + 166, y + 38), desc, fill=muted, font=font(22))
        y += 84

    y += 12
    draw.text((side_x + 48, y), "Visão geral", fill=dark, font=font(36, True))
    y += 56
    draw.rounded_rectangle((side_x + 52, y, side_x + 772, y + 650), radius=10, fill="#FFFFFF", outline="#AEBAB2", width=3)
    page.paste(overview, (side_x + 52, y))
    draw.rectangle((side_x + 52, y, side_x + 772, y + 650), outline="#111111", width=2)
    draw.rectangle((side_x + 110, y + 115, side_x + 370, y + 500), outline="#E23D28", width=6)
    draw.text((side_x + 400, y + 120), "área ampliada", fill="#E23D28", font=font(23, True))

    y += 690
    draw.text((side_x + 48, y), "Nota técnica", fill=dark, font=font(34, True))
    y += 50
    y = draw_text(draw, (side_x + 52, y), "A camada Travessia Marins-Itaguaré foi registrada no QGIS sem feições/CRS válido, portanto não foi usada como evidência nesta versão.", 22, "#684B35", 62)

    # Footer and scale.
    scale_y = 2290
    draw.text((120, scale_y - 34), "Escala gráfica aproximada", fill=dark, font=font(24, True))
    draw.line((120, scale_y + 10, 520, scale_y + 10), fill="#111111", width=10)
    for xx in (120, 320, 520):
        draw.line((xx, scale_y - 2, xx, scale_y + 24), fill="#111111", width=5)
    draw.text((112, scale_y + 36), "0", fill=dark, font=font(22))
    draw.text((305, scale_y + 36), "1", fill=dark, font=font(22))
    draw.text((497, scale_y + 36), "2 km", fill=dark, font=font(22))

    footer = "Fontes: DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguaré. Autor do mapa: Luan da Silva Cortes Maciel. Criado com SIGMAI/QGIS. CRS: SIRGAS 2000 / UTM zona 23S. Data: 2026."
    draw_text(draw, (660, scale_y - 20), footer, 22, dark, 122)

    logo = ROOT / "qgis_plugin" / "icons" / "sigmai_logo_full.png"
    if logo.exists():
        logo_img = Image.open(logo).convert("RGBA")
        logo_img.thumbnail((175, 70), Image.Resampling.LANCZOS)
        page.paste(logo_img, (3170, 2286), logo_img)

    page.save(FINAL_PNG, quality=96)
    page.save(FINAL_PDF, "PDF", resolution=300.0)


def write_reports(result: dict[str, Any]) -> None:
    result["outputs"] = {
        "base_png": str(BASE_PNG),
        "base_pdf": str(BASE_PDF),
        "final_png": str(FINAL_PNG),
        "final_pdf": str(FINAL_PDF),
    }
    result["map_parameters"] = MAP_PARAMETERS
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(
        "\n".join(
            [
                "# SIGMAI TopoTrail Environmental Focus Map",
                "",
                "## Objetivo",
                MAP_PARAMETERS["message_focus"],
                "",
                "## Template aplicado",
                "`environmental_focus_map`",
                "",
                "## Parâmetros cartográficos",
                f"- CRS: {MAP_PARAMETERS['crs']}",
                f"- Legenda: {MAP_PARAMETERS['legend_policy']}",
                f"- Escala: {MAP_PARAMETERS['scale_policy']}",
                f"- Norte: {MAP_PARAMETERS['north_policy']}",
                f"- Paleta: {MAP_PARAMETERS['palette']}",
                "",
                "## Outputs",
                f"- PNG final: `{FINAL_PNG}`",
                f"- PDF final: `{FINAL_PDF}`",
                f"- PNG base QGIS: `{BASE_PNG}`",
                f"- PDF base QGIS: `{BASE_PDF}`",
                "",
                "## Limitação registrada",
                "A camada Travessia Marins-Itaguaré apareceu sem feições/CRS válido no teste atual e não foi usada como evidência cartográfica.",
                "",
                "## Veredito",
                "Mapa recriado com hierarquia visual explícita, legenda semântica, painel principal ampliado e overview de contexto. Deve ser avaliado visualmente antes de ser considerado versão final publicável.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = SigmaiClient(timeout=180)
    layers = load_layers(client)
    apply_semantic_styles(client, layers)
    layout = create_base_qgis_layout(client, layers)
    compose_final_plate()
    result = {"layers": layers, "layout": layout}
    write_reports(result)
    print(json.dumps({"ok": True, "final_png": str(FINAL_PNG), "final_pdf": str(FINAL_PDF), "report": str(REPORT_JSON)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
