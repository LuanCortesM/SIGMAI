from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from compose_topotrail_reference_style_publication import (
    OUT,
    REPORT,
    SRC,
    draw_utm_grid,
    fit,
    fit_exact,
    font,
    paragraph,
    red_risk_surface,
    risk_ramp,
    swatch,
)


STRESS = OUT / "stress_500_designs"
MAPS = STRESS / "maps"
SHEETS = STRESS / "sheets"
BEST = STRESS / "best"
REPORT_JSON = STRESS / "SIGMAI_TOPO_TRAIL_500_DESIGN_STRESS.json"
REPORT_MD = STRESS / "SIGMAI_TOPO_TRAIL_500_DESIGN_STRESS.md"


@dataclass
class Variant:
    index: int
    family: str
    output: str
    score: int
    grade: str
    passed: bool
    warnings: list[str]
    map_area_percent: float
    legend_area_percent: float
    north_position: str
    inset_position: str
    palette: str


def ensure_dirs() -> None:
    for path in (STRESS, MAPS, SHEETS, BEST):
        path.mkdir(parents=True, exist_ok=True)


def draw_north(draw: ImageDraw.ImageDraw, box: tuple[int, int], style: str = "compact") -> tuple[int, int, int, int]:
    x, y = box
    if style == "outside":
        rect = (x - 10, y - 35, x + 52, y + 92)
        draw.rounded_rectangle(rect, radius=8, fill="#FFFFFF", outline="#BFC8C3", width=2)
    else:
        rect = (x - 8, y - 30, x + 46, y + 82)
    draw.text((x + 8, y - 30), "N", fill="#111111", font=font(22, True))
    draw.polygon([(x + 20, y), (x + 34, y + 52), (x + 20, y + 39), (x + 6, y + 52)], fill="#111111")
    draw.line((x + 20, y + 42, x + 20, y + 76), fill="#111111", width=4)
    return rect


def draw_scale(draw: ImageDraw.ImageDraw, x: int, y: int, small: bool = False) -> tuple[int, int, int, int]:
    seg = 64 if small else 88
    h = 10 if small else 13
    label_font = font(14 if small else 17)
    draw.text((x, y - 24), "1 km", fill="#1B2422", font=label_font)
    draw.rectangle((x, y, x + seg, y + h), fill="#111111")
    draw.rectangle((x + seg, y, x + 2 * seg, y + h), fill="#FFFFFF", outline="#111111")
    draw.line((x, y + h + 5, x + 2 * seg, y + h + 5), fill="#111111", width=2)
    return (x, y - 24, x + 2 * seg, y + h + 12)


def make_legend(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], compact: bool, risk_title: str = "Risco topográfico") -> None:
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill="#FFFFFF", outline="#C9C9C9", width=2)
    draw.text((x0 + 95, y0 + 28), "Legenda", fill="#111111", font=font(25 if compact else 30, True))
    draw.line((x0 + 35, y0 + 76, x1 - 35, y0 + 76), fill="#E0E0E0", width=2)
    y = y0 + 105
    step = 42 if compact else 52
    swatch(draw, x0 + 40, y, "Zonas potenciais", "fill", "#ECECEC", "#995640")
    y += step
    swatch(draw, x0 + 40, y, "Trilha RCN/RPPN", "line", "#FFE600")
    y += step
    swatch(draw, x0 + 40, y, "Trilha Itaguaré pelo Batedor", "line", "#00A6FF")
    y += step
    swatch(draw, x0 + 40, y, "Limite RCN/RPPN", "outline", "#16F000")
    y += step
    swatch(draw, x0 + 40, y, "Limite Fazenda Batedor", "outline", "#153E9C")
    y += step
    swatch(draw, x0 + 40, y, "Município de Cruzeiro", "outline", "#111111")
    y += 74 if compact else 98
    draw.text((x0 + 40, y), risk_title, fill="#111111", font=font(22 if compact else 26, True))
    risk_ramp(draw, x0 + 40, y + 46, min(280, x1 - x0 - 95), 35)
    draw.text((x0 + 40, y + 90), "baixo", fill="#111111", font=font(15 if compact else 18))
    draw.text((x1 - 98, y + 90), "alto", fill="#111111", font=font(15 if compact else 18))
    if not compact:
        paragraph(
            draw,
            (x0 + 40, y + 138),
            "Vermelho mais intenso indica maior restrição topográfica potencial. Compare as trilhas com os limites ambientais.",
            x1 - x0 - 80,
            "#3F4946",
            font(16),
        )


def grade(score: int) -> str:
    if score >= 92:
        return "A+"
    if score >= 84:
        return "A"
    if score >= 74:
        return "B"
    if score >= 62:
        return "C"
    if score >= 48:
        return "D"
    return "E"


def intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def palette_variant(img: Image.Image, palette: str, index: int) -> Image.Image:
    out = img.copy()
    if palette == "deep_red":
        out = ImageEnhance.Contrast(out).enhance(1.12)
        out = ImageEnhance.Color(out).enhance(1.16)
    elif palette == "soft_red":
        out = ImageEnhance.Contrast(out).enhance(0.92)
        out = ImageEnhance.Brightness(out).enhance(1.04)
        out = ImageEnhance.Color(out).enhance(0.88)
    elif palette == "terrain_red":
        out = ImageEnhance.Contrast(out).enhance(1.04)
        out = ImageEnhance.Color(out).enhance(0.98)
        overlay = Image.new("RGB", out.size, "#F5F0DE")
        out = Image.blend(out, overlay, 0.08)
    if index % 9 == 0:
        out = ImageEnhance.Sharpness(out).enhance(1.18)
    if index % 11 == 0:
        out = ImageEnhance.Brightness(out).enhance(0.98)
    return out


def crop_variant(img: Image.Image, index: int) -> Image.Image:
    # Tiny framing variations preserve the same data while testing layout tolerance.
    w, h = img.size
    dx = [0, 18, -18, 0, 26, -26][index % 6]
    dy = [0, 0, 0, 14, -14, 8][index % 6]
    zoom = 0.0 if index % 10 else 0.025
    left = max(0, int(w * zoom / 2 + dx))
    top = max(0, int(h * zoom / 2 + dy))
    right = min(w, int(w * (1 - zoom / 2) + dx))
    bottom = min(h, int(h * (1 - zoom / 2) + dy))
    if right - left < w * 0.85 or bottom - top < h * 0.85:
        return img
    return img.crop((left, top, right, bottom))


def compose_variant(index: int, base_map: Image.Image, context: Image.Image, extent: dict[str, float], rng: random.Random) -> Variant:
    families = ["reference_topographic", "hybrid_publication", "environmental_focus", "minimal_clean", "wide_scientific"]
    family = families[index % len(families)]
    palettes = ["sigmai_red", "deep_red", "soft_red", "terrain_red"]
    palette = palettes[(index // len(families)) % len(palettes)]
    canvas = Image.new("RGBA", (1800, 1120), "#FFFFFF")
    draw = ImageDraw.Draw(canvas)
    warnings: list[str] = []

    title_size = 27 + (index % 4) * 2
    title_x = 210 if family == "reference_topographic" else 235
    draw.text((title_x, 18), "Risco Topográfico, Zonas Potenciais e Trilhas - TopoTrail 0.5.0", fill="#111111", font=font(title_size, True))
    if family != "minimal_clean":
        draw.text((235, 52), "Conectividade entre trilhas, limites ambientais e áreas de maior restrição topográfica em Cruzeiro/SP", fill="#50605C", font=font(15))

    if family == "wide_scientific":
        map_box = (80, 88, 1345, 960)
        legend_box = (1390, 248, 1740, 860)
        inset_box = (115, 122, 385, 325) if index % 4 else (1040, 126, 1308, 326)
        north_pos = (1655, 94)
    elif family == "minimal_clean":
        map_box = (105, 98, 1375, 970)
        legend_box = (1415, 235, 1745, 820)
        inset_box = (125, 125, 350, 300) if index % 4 else (1110, 128, 1330, 304)
        north_pos = (1660, 72)
    elif family == "environmental_focus":
        map_box = (75, 100, 1358, 965)
        legend_box = (1398, 210, 1748, 900)
        inset_box = (105, 132, 375, 345) if index % 4 else (1030, 130, 1300, 340)
        north_pos = (1640, 80)
    elif family == "reference_topographic":
        map_box = (125, 88, 1340, 952)
        legend_box = (1388, 275, 1745, 840)
        inset_box = (155, 118, 410, 310) if index % 4 else (990, 116, 1244, 306)
        north_pos = (1248, 125)
    else:
        map_box = (85, 100, 1362, 960)
        legend_box = (1405, 235, 1740, 875)
        inset_box = (110, 128, 360, 320) if index % 4 else (1060, 126, 1308, 318)
        north_pos = (1660, 75)

    x0, y0, x1, y1 = map_box
    map_area_percent = ((x1 - x0) * (y1 - y0)) / (1800 * 1120) * 100
    legend_area_percent = ((legend_box[2] - legend_box[0]) * (legend_box[3] - legend_box[1])) / (1800 * 1120) * 100
    draw.rectangle((x0 - 2, y0 - 2, x1 + 2, y1 + 2), fill="#FFFFFF", outline="#151515", width=2)
    themed_map = palette_variant(crop_variant(base_map, index), palette, index)
    canvas.paste(fit_exact(themed_map, (x1 - x0, y1 - y0)), (x0, y0))
    grid_interval = 2000 if index % 3 else 1000
    if family != "minimal_clean":
        draw_utm_grid(canvas, map_box, extent, interval=grid_interval)
        draw = ImageDraw.Draw(canvas)

    inset_fill = "#FBFAF3" if index % 2 else "#FFFFFF"
    draw.rectangle(inset_box, fill=inset_fill, outline="#111111", width=2)
    ix0, iy0, ix1, iy1 = inset_box
    draw.text((ix0 + 12, iy0 + 10), "Cruzeiro (SP)", fill="#111111", font=font(18, True))
    ctx = fit(context, (ix1 - ix0 - 30, iy1 - iy0 - 56))
    canvas.paste(ctx, (ix0 + 15, iy0 + 46))
    draw.rectangle((ix0 + 25, iy0 + 62, ix0 + 108, iy0 + 112), outline="#D6452F", width=2)

    north_style = "outside" if north_pos[0] > x1 else "compact"
    north_box = draw_north(draw, north_pos, north_style)
    scale_box = draw_scale(draw, x0 + 75, y1 - 88, small=(family == "minimal_clean"))
    make_legend(draw, legend_box, compact=(family in {"minimal_clean", "reference_topographic"}))

    # Axis labels stay outside the map body.
    draw.text((x0 + (x1 - x0) // 3, y1 + 30), "Coordenada UTM E (m) - SIRGAS 2000 / UTM 23S", fill="#111111", font=font(17))
    axis = Image.new("RGBA", (360, 34), (255, 255, 255, 0))
    ad = ImageDraw.Draw(axis)
    ad.text((0, 4), "Coordenada UTM N (m)", fill="#111111", font=font(17))
    canvas.alpha_composite(axis.rotate(90, expand=True), (18, y0 + 315))

    draw.text((x0 + 60, 1060), "Fonte: processamento TopoTrail 0.5.0; dados DataGEO, Secretaria Municipal de Meio Ambiente e RPPN Gigante do Itaguaré.", fill="#1F2927", font=font(13))
    draw.text((1390, 1055), "Autor: Luan da Silva Cortes Maciel", fill="#1F2927", font=font(13))
    draw.text((1390, 1076), "CRS: SIRGAS 2000 / UTM 23S", fill="#1F2927", font=font(13))
    draw.text((1640, 20), "SIGMAI/QGIS", fill="#0B5E4A", font=font(14, True))
    draw.text((20, 18), f"{index:03d}", fill="#333333", font=font(20, True))

    score = 100
    if intersects(north_box, map_box):
        score -= 18
        warnings.append("north_arrow_over_map")
    if intersects(legend_box, map_box):
        score -= 25
        warnings.append("legend_over_map")
    if intersects(inset_box, ((map_box[0] + 300), (map_box[1] + 250), map_box[2], map_box[3])):
        score -= 7
        warnings.append("inset_too_close_to_thematic_center")
    if map_area_percent < 50:
        score -= 12
        warnings.append("map_body_too_small")
    if legend_area_percent > 14:
        score -= 6
        warnings.append("legend_too_large")
    if family == "minimal_clean" and index % 7 == 0:
        score -= 5
        warnings.append("minimal_template_lacks_method_note")

    output = MAPS / f"map_{index:03d}_{family}.png"
    canvas.convert("RGB").save(output, quality=92)
    g = grade(score)
    passed = g in {"A+", "A", "B"} and "north_arrow_over_map" not in warnings and "legend_over_map" not in warnings
    return Variant(
        index=index,
        family=family,
        output=str(output),
        score=score,
        grade=g,
        passed=passed,
        warnings=warnings,
        map_area_percent=round(map_area_percent, 2),
        legend_area_percent=round(legend_area_percent, 2),
        north_position="outside" if north_pos[0] > x1 else "inside",
        inset_position="inside_map_upper_left",
        palette=palette,
    )


def make_contact_sheet(items: list[Variant], output: Path, title: str, cols: int = 5, thumb: tuple[int, int] = (320, 199)) -> None:
    rows = math.ceil(len(items) / cols)
    sheet = Image.new("RGB", (cols * thumb[0], rows * (thumb[1] + 34) + 44), "#FFFFFF")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), title, fill="#111111", font=font(22, True))
    for pos, item in enumerate(items):
        x = (pos % cols) * thumb[0]
        y = 44 + (pos // cols) * (thumb[1] + 34)
        img = Image.open(item.output).convert("RGB")
        img.thumbnail((thumb[0] - 8, thumb[1]), Image.Resampling.LANCZOS)
        sheet.paste(img, (x + 4, y))
        label = f"{item.index:03d} {item.grade} {item.score}"
        draw.rectangle((x + 4, y + thumb[1] - 24, x + 108, y + thumb[1] - 2), fill="#FFFFFF")
        draw.text((x + 10, y + thumb[1] - 23), label, fill="#111111", font=font(14, True))
    sheet.save(output, quality=92)


def main() -> int:
    ensure_dirs()
    src = Image.open(SRC).convert("RGB")
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    extent = report.get("extents", {}).get("main") or {"xmin": 486000, "ymin": 7508000, "xmax": 500000, "ymax": 7518000}
    base_map = red_risk_surface(src.crop((120, 360, 2380, 1875)))
    context = src.crop((2575, 355, 3228, 1045))
    rng = random.Random(20260524)

    variants = [compose_variant(i, base_map, context, extent, rng) for i in range(1, 501)]
    records = [asdict(v) for v in variants]
    passed = [v for v in variants if v.passed]
    top = sorted(passed, key=lambda v: (-v.score, v.index))[:50]

    for chunk_start in range(0, len(variants), 25):
        chunk = variants[chunk_start : chunk_start + 25]
        make_contact_sheet(chunk, SHEETS / f"sheet_{chunk[0].index:03d}_{chunk[-1].index:03d}.jpg", f"SIGMAI TopoTrail design stress - mapas {chunk[0].index:03d}-{chunk[-1].index:03d}")
    make_contact_sheet(top, BEST / "best_050_contact_sheet.jpg", "SIGMAI TopoTrail - 50 melhores avaliados", cols=5)
    make_contact_sheet(top[:20], BEST / "best_020_contact_sheet.jpg", "SIGMAI TopoTrail - 20 melhores avaliados", cols=5)

    summary = {
        "total": len(variants),
        "passed": len(passed),
        "failed": len(variants) - len(passed),
        "grade_counts": {g: sum(1 for v in variants if v.grade == g) for g in ["A+", "A", "B", "C", "D", "E"]},
        "best_20": [asdict(v) for v in top[:20]],
        "sheets": [str(p) for p in sorted(SHEETS.glob("sheet_*.jpg"))],
        "best_sheets": [str(BEST / "best_020_contact_sheet.jpg"), str(BEST / "best_050_contact_sheet.jpg")],
        "notes": [
            "Synthetic design regression based on the current QGIS-exported TopoTrail base map.",
            "Does not reload 500 QGIS projects; it stress-tests layout/design compositions to avoid polluting QGIS with 500 layer sets.",
            "Use the best indices to promote the corresponding layout rules into native SIGMAI/QGIS templates.",
        ],
    }
    REPORT_JSON.write_text(json.dumps({"summary": summary, "variants": records}, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# SIGMAI TopoTrail 500 Design Stress",
        "",
        f"- Total: {summary['total']}",
        f"- Passaram na avaliação visual automatizada: {summary['passed']}",
        f"- Reprovados: {summary['failed']}",
        f"- Notas: {summary['grade_counts']}",
        "",
        "## Melhores 20",
        "",
    ]
    for v in top[:20]:
        md.append(f"- {v.index:03d}: grade {v.grade}, score {v.score}, familia `{v.family}`, arquivo `{v.output}`")
    md.extend(
        [
            "",
            "## Contact sheets",
            "",
            "- `best/best_020_contact_sheet.jpg`",
            "- `best/best_050_contact_sheet.jpg`",
            "- `sheets/sheet_001_025.jpg` ... `sheets/sheet_476_500.jpg`",
            "",
            "## Limitacao",
            "",
            "Esta bateria avalia centenas de composicoes a partir do mapa base exportado pelo QGIS/SIGMAI. Ela nao deve ser confundida com 500 execucoes completas do QGIS, porque isso poluiria novamente o projeto com camadas duplicadas. A proxima etapa correta e promover os melhores layouts para templates nativos do QGIS.",
        ]
    )
    REPORT_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
