from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from compose_topotrail_reference_style_publication import (
    OUT,
    REPORT,
    SRC,
    draw_utm_grid,
    fit,
    fit_exact,
    font,
    line,
    paragraph,
    red_risk_surface,
    risk_ramp,
    swatch,
)


def draw_north_arrow(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rounded_rectangle((x - 11, y - 38, x + 55, y + 96), radius=8, fill="#FFFFFF", outline="#C7C7C7", width=2)
    draw.polygon([(x + 22, y), (x + 38, y + 58), (x + 22, y + 43), (x + 6, y + 58)], fill="#111111")
    draw.line((x + 22, y + 47, x + 22, y + 78), fill="#111111", width=5)
    draw.text((x + 10, y - 32), "N", fill="#111111", font=font(24, True))


def draw_scale_bar(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.text((x, y - 28), "1 km", fill="#1E2725", font=font(19))
    draw.rectangle((x, y, x + 104, y + 12), fill="#111111")
    draw.rectangle((x + 104, y, x + 208, y + 12), fill="#FFFFFF", outline="#111111")
    draw.line((x, y + 16, x + 208, y + 16), fill="#111111", width=2)


def draw_axis_labels(draw: ImageDraw.ImageDraw, main_box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = main_box
    draw.text((x0 + 455, y1 + 34), "Coordenada UTM E (m) - SIRGAS 2000 / UTM 23S", fill="#111111", font=font(24))
    # Vertical label drawn as rotated text.
    tmp = Image.new("RGBA", (520, 48), (255, 255, 255, 0))
    td = ImageDraw.Draw(tmp)
    td.text((0, 5), "Coordenada UTM N (m)", fill="#111111", font=font(24))
    return tmp.rotate(90, expand=True)


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_png = OUT / f"SIGMAI_TopoTrail_RPPN_Batedor_MAPA_HIBRIDO_PUBLICACAO_{timestamp}.png"
    out_pdf = OUT / f"SIGMAI_TopoTrail_RPPN_Batedor_MAPA_HIBRIDO_PUBLICACAO_{timestamp}.pdf"
    stable_png = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_MAPA_HIBRIDO_PUBLICACAO.png"
    stable_pdf = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_MAPA_HIBRIDO_PUBLICACAO.pdf"

    src = Image.open(SRC).convert("RGB")
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    main_extent = report.get("extents", {}).get("main")

    main_map = red_risk_surface(src.crop((120, 360, 2380, 1875)))
    context = src.crop((2575, 355, 3228, 1045))

    canvas = Image.new("RGBA", (2600, 1600), "#FFFFFF")
    draw = ImageDraw.Draw(canvas)
    ink = "#111817"
    muted = "#47544F"

    draw.text((430, 24), "Risco Topográfico, Zonas Potenciais e Trilhas - TopoTrail 0.5.0", fill="#111111", font=font(44, True))
    draw.text(
        (430, 78),
        "Conectividade entre trilhas existentes, limites ambientais e áreas de maior restrição topográfica em Cruzeiro/SP",
        fill=muted,
        font=font(22),
    )

    main_box = (185, 116, 2015, 1430)
    x0, y0, x1, y1 = main_box
    draw.rectangle((x0 - 2, y0 - 2, x1 + 2, y1 + 2), fill="#FFFFFF", outline="#111111", width=3)
    canvas.paste(fit_exact(main_map, (x1 - x0, y1 - y0)), (x0, y0))
    if main_extent:
        draw_utm_grid(canvas, main_box, main_extent, interval=2000)
        draw = ImageDraw.Draw(canvas)

    # Inset municipal inside the map body, following the strongest reference example.
    inset_box = (232, 150, 575, 410)
    draw.rectangle((inset_box[0], inset_box[1], inset_box[2], inset_box[3]), fill="#FBFAF3", outline="#111111", width=2)
    context_fit = fit(context, (305, 170))
    canvas.paste(context_fit, (inset_box[0] + 20, inset_box[1] + 58))
    draw.text((inset_box[0] + 20, inset_box[1] + 18), "Cruzeiro (SP)", fill=ink, font=font(26, True))
    draw.rectangle((inset_box[0] + 32, inset_box[1] + 74, inset_box[0] + 145, inset_box[1] + 143), outline="#D6452F", width=3)
    draw.ellipse((inset_box[0] + 110, inset_box[1] + 104, inset_box[0] + 122, inset_box[1] + 116), fill="#D71920")

    draw_north_arrow(draw, 2440, 96)
    draw_scale_bar(draw, x0 + 115, y1 - 118)

    rotated_axis = draw_axis_labels(draw, main_box)
    canvas.alpha_composite(rotated_axis, (30, 555))

    # Right-side legend, clean and closer to the reference, but with SIGMAI's clearer colors.
    lx0, ly0, lx1, ly1 = 2085, 390, 2538, 1266
    draw.rectangle((lx0, ly0, lx1, ly1), fill="#FFFFFF", outline="#C9C9C9", width=2)
    draw.text((lx0 + 148, ly0 + 36), "Legenda", fill="#111111", font=font(30, True))
    draw.line((lx0 + 46, ly0 + 88, lx1 - 46, ly0 + 88), fill="#E0E0E0", width=2)

    y = ly0 + 124
    swatch(draw, lx0 + 46, y, "Zonas potenciais", "fill", "#ECECEC", "#995640")
    y += 52
    swatch(draw, lx0 + 46, y, "Trilha RCN/RPPN", "line", "#FFE600")
    y += 52
    swatch(draw, lx0 + 46, y, "Trilha Itaguaré pelo Batedor", "line", "#00A6FF")
    y += 52
    swatch(draw, lx0 + 46, y, "Limite RCN/RPPN", "outline", "#16F000")
    y += 52
    swatch(draw, lx0 + 46, y, "Limite Fazenda Batedor", "outline", "#153E9C")
    y += 52
    swatch(draw, lx0 + 46, y, "Município de Cruzeiro", "outline", "#111111")

    y += 105
    draw.text((lx0 + 46, y), "Risco topográfico", fill="#111111", font=font(26, True))
    risk_ramp(draw, lx0 + 46, y + 52, 300, 42)
    draw.text((lx0 + 46, y + 102), "baixo", fill="#111111", font=font(19))
    draw.text((lx0 + 294, y + 102), "alto", fill="#111111", font=font(19))
    paragraph(
        draw,
        (lx0 + 46, y + 155),
        "Vermelho mais intenso indica maior restrição topográfica potencial. As trilhas coloridas permitem comparar continuidade, passagem por áreas críticas e relação com os limites ambientais.",
        355,
        "#3F4946",
        font(17),
    )

    draw.text((300, 1518), "Fonte: processamento TopoTrail 0.5.0; dados DataGEO, Secretaria Municipal de Meio Ambiente e RPPN Gigante do Itaguaré.", fill="#202A28", font=font(19))
    draw.text((2108, 1518), "Autor: Luan da Silva Cortes Maciel", fill="#202A28", font=font(19))
    draw.text((2108, 1546), "CRS: SIRGAS 2000 / UTM 23S", fill="#202A28", font=font(19))
    draw.text((2355, 36), "SIGMAI/QGIS", fill="#0B5E4A", font=font(18, True))

    final = canvas.convert("RGB")
    final.save(stable_png, quality=96)
    final.save(stable_pdf, resolution=300.0)
    final.save(out_png, quality=96)
    final.save(out_pdf, resolution=300.0)
    print(stable_png)
    print(stable_pdf)
    print(out_png)
    print(out_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
