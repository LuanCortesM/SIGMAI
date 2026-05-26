from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
SRC = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_REFERENCIA_VISIVEL_BASE.png"
PNG = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_MAPA_PROFISSIONAL_REFERENCIA.png"
PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_MAPA_PROFISSIONAL_REFERENCIA.pdf"
PNG_REFINED = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_MAPA_FINAL_REFINADO.png"
PDF_REFINED = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_MAPA_FINAL_REFINADO.pdf"
REPORT = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_REFERENCIA_VISIVEL.json"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def fit(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    copy = img.copy()
    copy.thumbnail(box, Image.Resampling.LANCZOS)
    return copy


def fit_exact(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    return img.resize(box, Image.Resampling.LANCZOS)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def red_risk_surface(img: Image.Image) -> Image.Image:
    src = img.convert("RGB")
    out = Image.new("RGB", src.size)
    px = src.load()
    opx = out.load()
    low = (255, 246, 242)
    mid = (240, 118, 105)
    high = (168, 24, 33)
    for y in range(src.height):
        for x in range(src.width):
            r, g, b = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            lum = (r * 0.299 + g * 0.587 + b * 0.114) / 255.0
            if mx - mn > 36 or lum < 0.10 or lum > 0.97:
                opx[x, y] = (r, g, b)
                continue
            risk_value = 1.0 - lum
            if risk_value < 0.45:
                base = _mix(low, mid, risk_value / 0.45)
            else:
                base = _mix(mid, high, min(1.0, (risk_value - 0.45) / 0.55))
            opx[x, y] = _mix((r, g, b), base, 0.88)
    return out


def paragraph(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, width: int, fill: str, text_font: ImageFont.ImageFont, line_spacing: int = 6) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=text_font) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    x, y = xy
    line_height = text_font.size + line_spacing if hasattr(text_font, "size") else 24
    for index, line_text in enumerate(lines):
        draw.text((x, y + index * line_height), line_text, fill=fill, font=text_font)


def line(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, width: int = 3) -> None:
    draw.line(xy, fill=fill, width=width)


def swatch(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, kind: str, color: str, outline: str = "#222222") -> None:
    if kind == "fill":
        draw.rounded_rectangle((x, y + 2, x + 44, y + 28), radius=2, fill=color, outline=outline, width=3)
    elif kind == "line":
        line(draw, (x, y + 16, x + 44, y + 16), color, 8)
    elif kind == "dash":
        for i in range(0, 44, 16):
            line(draw, (x + i, y + 16, min(x + i + 10, x + 44), y + 16), color, 8)
    elif kind == "outline":
        draw.rounded_rectangle((x + 4, y + 2, x + 40, y + 28), radius=4, outline=color, width=5)
    if "\n" in label:
        draw.multiline_text((x + 58, y - 4), label, fill="#1F2A2A", font=font(22), spacing=2)
    else:
        draw.text((x + 58, y), label, fill="#1F2A2A", font=font(24))


def risk_ramp(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
    low = (255, 246, 242)
    mid = (240, 118, 105)
    high = (168, 24, 33)
    for i in range(w):
        t = i / max(w - 1, 1)
        color = _mix(low, mid, t / 0.52) if t < 0.52 else _mix(mid, high, (t - 0.52) / 0.48)
        draw.line((x + i, y, x + i, y + h), fill=color)
    draw.rectangle((x, y, x + w, y + h), outline="#7A1E1E", width=2)


def panel_title(draw: ImageDraw.ImageDraw, x: int, y: int, title: str) -> None:
    draw.text((x, y), title, fill="#172321", font=font(28, True))
    draw.line((x, y + 40, x + 520, y + 40), fill="#D5DEDA", width=2)


def label_chip(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: str) -> None:
    label_font = font(18, True)
    bbox = draw.textbbox((x, y), text, font=label_font)
    draw.rounded_rectangle((bbox[0] - 8, bbox[1] - 5, bbox[2] + 8, bbox[3] + 5), radius=6, fill="#FFFFFF", outline=color, width=3)
    draw.text((x, y), text, fill=color, font=label_font)


def draw_utm_grid(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    extent: dict[str, float],
    interval: int = 2000,
) -> None:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    grid = ImageDraw.Draw(overlay)
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    xmin, xmax = extent["xmin"], extent["xmax"]
    ymin, ymax = extent["ymin"], extent["ymax"]
    label_font = font(14)

    first_x = int(xmin // interval * interval)
    for value in range(first_x, int(xmax) + interval, interval):
        if value < xmin or value > xmax:
            continue
        px = x0 + int((value - xmin) / (xmax - xmin) * w)
        grid.line((px, y0, px, y1), fill=(255, 255, 255, 105), width=1)
        grid.line((px, y1 - 7, px, y1), fill=(34, 42, 40, 150), width=2)
        grid.rectangle((px - 20, y1 - 22, px + 22, y1 - 3), fill=(244, 246, 241, 170))
        grid.text((px - 17, y1 - 21), f"{value//1000}", fill=(45, 55, 52, 230), font=label_font)

    first_y = int(ymin // interval * interval)
    for value in range(first_y, int(ymax) + interval, interval):
        if value < ymin or value > ymax:
            continue
        py = y0 + int((ymax - value) / (ymax - ymin) * h)
        grid.line((x0, py, x1, py), fill=(255, 255, 255, 105), width=1)
        grid.line((x0, py, x0 + 7, py), fill=(34, 42, 40, 150), width=2)
        grid.text((x0 + 10, py - 8), f"{value//1000}", fill=(45, 55, 52, 230), font=label_font)

    canvas.alpha_composite(overlay)


def main() -> int:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_versioned = OUT / f"SIGMAI_TopoTrail_RPPN_Batedor_MAPA_FINAL_REFINADO_{timestamp}.png"
    pdf_versioned = OUT / f"SIGMAI_TopoTrail_RPPN_Batedor_MAPA_FINAL_REFINADO_{timestamp}.pdf"
    src = Image.open(SRC).convert("RGB")
    main_map = red_risk_surface(src.crop((120, 360, 2380, 1875)))
    context = src.crop((2575, 355, 3228, 1045))
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    main_extent = report.get("extents", {}).get("main")

    canvas = Image.new("RGBA", (2400, 1300), "#F4F6F1")
    draw = ImageDraw.Draw(canvas)
    accent = "#0B5E4A"
    ink = "#172321"
    muted = "#52605D"

    draw.rectangle((0, 0, 2400, 20), fill=accent)
    draw.rectangle((0, 20, 2400, 26), fill="#D5B86A")
    draw.text((70, 48), "Risco topográfico potencial e conectividade de trilhas", fill=ink, font=font(43, True))
    draw.text((70, 101), "As trilhas atravessam áreas de maior restrição topográfica no entorno da RPPN e da Fazenda Batedor?", fill=muted, font=font(23))

    draw.rounded_rectangle((58, 142, 1710, 1120), radius=8, fill="#FFFFFF", outline="#1B1B1B", width=2)
    main_fit = fit_exact(main_map, (1605, 925))
    canvas.paste(main_fit, (80, 166))
    if main_extent:
        draw_utm_grid(canvas, (80, 166, 1685, 1091), main_extent)
        draw = ImageDraw.Draw(canvas)
    label_chip(draw, 355, 505, "Reserva Chico Nunes / RPPN", "#159800")
    label_chip(draw, 835, 315, "Fazenda Batedor", "#153E9C")
    label_chip(draw, 830, 565, "Trilha Batedor x Itaguaré", "#0077B6")
    label_chip(draw, 525, 875, "Trilha RCN/RPPN", "#8A6D00")
    sx, sy = 90, 1154
    draw.text((sx, sy - 28), "Escala gráfica", fill="#1F2A2A", font=font(17, True))
    for i in range(6):
        fill = "#111111" if i % 2 == 0 else "#FFFFFF"
        draw.rectangle((sx + i * 82, sy, sx + (i + 1) * 82, sy + 16), fill=fill, outline="#111111")
        draw.text((sx + i * 82 - 3, sy + 22), str(i), fill="#1F2A2A", font=font(18))
    draw.text((sx + 490, sy + 22), "6 km", fill="#1F2A2A", font=font(18))

    panel_x = 1750
    draw.rounded_rectangle((panel_x, 142, 2330, 452), radius=8, fill="#FFFFFF", outline="#CED8D4", width=2)
    panel_title(draw, panel_x + 25, 168, "Contexto municipal")
    context_fit = fit(context, (510, 205))
    context_xy = (panel_x + 35, 224)
    canvas.paste(context_fit, context_xy)
    draw.rectangle(
        (context_xy[0] + 18, context_xy[1] + 18, context_xy[0] + 112, context_xy[1] + 84),
        outline="#D6452F",
        width=3,
    )
    draw.text((context_xy[0] + 22, context_xy[1] + 88), "área do mapa", fill="#D6452F", font=font(13, True))
    draw.text((panel_x + 35, 424), "Cruzeiro/SP e áreas-alvo no setor norte.", fill=muted, font=font(16))

    draw.rounded_rectangle((panel_x, 482, 2330, 1140), radius=8, fill="#FFFFFF", outline="#CED8D4", width=2)
    panel_title(draw, panel_x + 25, 508, "Legenda interpretativa")
    draw.text((panel_x + 30, 570), "Resultado topográfico", fill="#1F2A2A", font=font(21, True))
    risk_ramp(draw, panel_x + 30, 606, 235, 28)
    draw.text((panel_x + 30, 640), "baixo", fill=muted, font=font(16))
    draw.text((panel_x + 214, 640), "alto", fill=muted, font=font(16))
    draw.text((panel_x + 30, 684), "Áreas e rotas", fill="#1F2A2A", font=font(21, True))
    swatch(draw, panel_x + 30, 722, "Zonas potenciais", "fill", "#ECECEC", "#995640")
    swatch(draw, panel_x + 30, 768, "Trilha Batedor x Itaguaré", "line", "#00A6FF")
    swatch(draw, panel_x + 30, 814, "Trilha RCN e RPPN", "line", "#FFE600")
    draw.text((panel_x + 30, 871), "Limites territoriais", fill="#1F2A2A", font=font(21, True))
    swatch(draw, panel_x + 30, 905, "Reserva Chico Nunes /\nRPPN Gigante do Itaguaré", "outline", "#16F000")
    swatch(draw, panel_x + 30, 967, "Fazenda Batedor", "outline", "#153E9C")
    swatch(draw, panel_x + 30, 1013, "Município de Cruzeiro/SP", "outline", "#111111")

    draw.rounded_rectangle((panel_x + 25, 1063, panel_x + 555, 1121), radius=6, fill="#F3F6F1", outline="#D6DEDA", width=1)
    paragraph(
        draw,
        (panel_x + 42, 1078),
        "Leia primeiro as duas trilhas destacadas; depois compare seus trechos com as manchas vermelhas de maior restrição.",
        495,
        "#42504D",
        font(16),
    )

    footer = "Fontes: DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguaré. Autor: Luan da Silva Cortes Maciel. CRS: SIRGAS 2000 / UTM 23S. Criado com SIGMAI/QGIS."
    draw.text((70, 1252), footer, fill="#2F3937", font=font(17))
    draw.text((2190, 1252), "SIGMAI", fill=accent, font=font(18, True))

    final = canvas.convert("RGB")
    final.save(PNG, quality=95)
    final.save(PDF, resolution=300.0)
    final.save(PNG_REFINED, quality=95)
    final.save(PDF_REFINED, resolution=300.0)
    final.save(png_versioned, quality=95)
    final.save(pdf_versioned, resolution=300.0)
    print(PNG)
    print(PDF)
    print(PNG_REFINED)
    print(PDF_REFINED)
    print(png_versioned)
    print(pdf_versioned)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
