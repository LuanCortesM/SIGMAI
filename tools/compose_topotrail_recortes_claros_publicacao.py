from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
SRC = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_RECORTES_CLAROS.png"
PNG = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_RECORTES_CLAROS_PUBLICACAO.png"
PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_RECORTES_CLAROS_PUBLICACAO.pdf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def fit(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    copy = img.copy()
    copy.thumbnail(box, Image.Resampling.LANCZOS)
    return copy


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def colorize_topotrail_surface(img: Image.Image) -> Image.Image:
    """Convert the neutral TopoTrail raster render into an interpretive bicolor surface.

    The QGIS export currently renders the TopoTrail raster as grayscale. This post-process
    recolors only low-saturation pixels, preserving colored boundaries, trails and labels.
    Darker/rougher portions become risk tones; lighter portions become suitability tones.
    """
    src = img.convert("RGB")
    out = Image.new("RGB", src.size)
    px = src.load()
    opx = out.load()
    high_risk = (202, 67, 47)
    moderate_risk = (236, 150, 72)
    transition = (244, 216, 132)
    suitable = (76, 178, 111)
    high_suitable = (25, 132, 91)
    for y in range(src.height):
        for x in range(src.width):
            r, g, b = px[x, y]
            mx = max(r, g, b)
            mn = min(r, g, b)
            lum = (r * 0.299 + g * 0.587 + b * 0.114) / 255.0
            # Preserve vector symbols, labels, frames and white page areas.
            if mx - mn > 30 or lum < 0.12 or lum > 0.96:
                opx[x, y] = (r, g, b)
                continue
            if lum < 0.30:
                t = max(0.0, min(1.0, lum / 0.30))
                base = _mix(high_risk, moderate_risk, t)
            elif lum < 0.52:
                t = max(0.0, min(1.0, (lum - 0.30) / 0.22))
                base = _mix(moderate_risk, transition, t)
            elif lum < 0.72:
                t = max(0.0, min(1.0, (lum - 0.52) / 0.20))
                base = _mix(transition, suitable, t)
            else:
                t = max(0.0, min(1.0, (lum - 0.72) / 0.24))
                base = _mix(suitable, high_suitable, t)
            # Keep just a small portion of the original relief texture.
            opx[x, y] = _mix((r, g, b), base, 0.88)
    return out


def line(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, width: int = 3) -> None:
    draw.line(xy, fill=fill, width=width)


def swatch(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, kind: str, color: str, outline: str = "#333333") -> None:
    if kind == "fill":
        draw.rounded_rectangle((x, y + 2, x + 44, y + 28), radius=2, fill=color, outline=outline, width=3)
    elif kind == "line":
        line(draw, (x, y + 16, x + 44, y + 16), color, 8)
    elif kind == "outline":
        draw.rounded_rectangle((x + 4, y + 2, x + 40, y + 28), radius=4, outline=color, width=5)
    if "\n" in label:
        draw.multiline_text((x + 58, y - 4), label, fill="#1F2A2A", font=font(22), spacing=2)
    else:
        draw.text((x + 58, y), label, fill="#1F2A2A", font=font(24))


def callout(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, color: str) -> None:
    label_font = font(18, True)
    bbox = draw.textbbox((x, y), label, font=label_font)
    pad = 7
    draw.rounded_rectangle(
        (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
        radius=5,
        fill="#FFFFFF",
        outline=color,
        width=3,
    )
    draw.text((x, y), label, fill=color, font=label_font)


def main() -> int:
    src = Image.open(SRC).convert("RGB")
    # Crops are from the SIGMAI/QGIS layout generated immediately before this composition.
    main_map = colorize_topotrail_surface(src.crop((120, 365, 2350, 1880)))
    context = src.crop((2475, 385, 3188, 1038))
    focus = colorize_topotrail_surface(src.crop((2475, 1220, 3265, 1700)))

    canvas = Image.new("RGB", (2200, 1500), "#F7F8F5")
    draw = ImageDraw.Draw(canvas)

    accent = "#0B5E4A"
    draw.rectangle((0, 0, 2200, 18), fill=accent)
    draw.text((70, 55), "Adequabilidade e risco topográfico para trilhas - Cruzeiro/SP", fill="#172321", font=font(44, True))
    draw.text((70, 110), "Reserva Chico Nunes, RPPN Gigante do Itaguaré e Fazenda Batedor", fill="#52605D", font=font(24))

    draw.rounded_rectangle((60, 170, 1535, 1138), radius=8, fill="#FFFFFF", outline="#111111", width=2)
    main_fit = fit(main_map, (1435, 925))
    canvas.paste(main_fit, (80, 190))
    callout(draw, 285, 560, "Reserva Chico Nunes / RPPN", "#126A3A")
    callout(draw, 830, 365, "Fazenda Batedor (KML)", "#174E8C")
    callout(draw, 410, 885, "Trilha RCN/RPPN", "#7B0022")
    draw.text((80, 1108), "Mapa principal: superfície TopoTrail bicolor, recortes reais e trilha RCN/RPPN", fill="#25302E", font=font(21, True))

    # Scale bar, compact and subordinate.
    sx, sy = 90, 1186
    draw.text((sx, sy - 30), "Escala gráfica", fill="#1F2A2A", font=font(17, True))
    draw.rectangle((sx, sy, sx + 95, sy + 16), fill="#111111")
    draw.rectangle((sx + 95, sy, sx + 190, sy + 16), fill="#FFFFFF", outline="#111111", width=2)
    draw.text((sx - 3, sy + 22), "0", fill="#1F2A2A", font=font(18))
    draw.text((sx + 84, sy + 22), "1", fill="#1F2A2A", font=font(18))
    draw.text((sx + 178, sy + 22), "2 km", fill="#1F2A2A", font=font(18))

    panel_x = 1585
    draw.rounded_rectangle((panel_x, 170, 2135, 530), radius=8, fill="#FFFFFF", outline="#CED8D4", width=2)
    draw.text((panel_x + 25, 195), "Contexto municipal", fill="#172321", font=font(28, True))
    canvas.paste(fit(context, (500, 245)), (panel_x + 25, 235))
    draw.text((panel_x + 25, 508), "Município de Cruzeiro/SP com área-alvo no setor norte.", fill="#52605D", font=font(16))

    draw.rounded_rectangle((panel_x, 560, 2135, 930), radius=8, fill="#FFFFFF", outline="#CED8D4", width=2)
    draw.text((panel_x + 25, 585), "Recortes ambientais", fill="#172321", font=font(28, True))
    focus_fit = fit(focus, (500, 245))
    canvas.paste(focus_fit, (panel_x + 25, 625))
    # The QGIS side map crop includes a narrow layout divider at the far right;
    # cover only that divider so the Batedor polygon remains fully visible.
    draw.rectangle((1996, 625, 2044, 625 + focus_fit.height), fill="#FFFFFF")
    draw.rectangle((panel_x + 25 + focus_fit.width - 6, 625, panel_x + 25 + focus_fit.width, 625 + focus_fit.height), fill="#FFFFFF")
    draw.text((panel_x + 25, 900), "Zoom para separar RPPN/Reserva, Fazenda Batedor e trilha.", fill="#52605D", font=font(16))

    draw.rounded_rectangle((panel_x, 960, 2135, 1305), radius=8, fill="#FFFFFF", outline="#CED8D4", width=2)
    draw.text((panel_x + 25, 985), "Legenda interpretativa", fill="#172321", font=font(30, True))
    swatch(draw, panel_x + 28, 1042, "Risco potencial topográfico", "fill", "#B84934", "#7C2D24")
    swatch(draw, panel_x + 28, 1086, "Áreas mais adequadas para caminhada", "fill", "#5B9968", "#2E6B42")
    swatch(draw, panel_x + 28, 1130, "Zonas TopoTrail filtradas", "fill", "#33C481", "#056B4F")
    swatch(draw, panel_x + 28, 1174, "Reserva Chico Nunes /\nRPPN Gigante do Itaguaré", "outline", "#126A3A")
    swatch(draw, panel_x + 28, 1236, "Fazenda Batedor", "outline", "#174E8C")
    swatch(draw, panel_x + 28, 1280, "Trilha RCN/RPPN", "line", "#7B0022")

    draw.rounded_rectangle((60, 1250, 1535, 1358), radius=8, fill="#FFFFFF", outline="#CED8D4", width=2)
    draw.text((85, 1274), "Leitura técnica", fill="#172321", font=font(26, True))
    draw.text(
        (85, 1310),
        "A superfície TopoTrail foi convertida para leitura bicolor: vermelho indica maior risco potencial; verde indica maior adequabilidade para caminhada.\n"
        "A camada vetorial bruta tinha artefato grande; o verde vivo mostra apenas zonas filtradas.",
        fill="#42504D",
        font=font(20),
    )

    footer = "Fontes: DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguaré. Autor: Luan da Silva Cortes Maciel. CRS: SIRGAS 2000 / UTM 23S. Criado com SIGMAI/QGIS."
    draw.text((70, 1432), footer, fill="#2F3937", font=font(17))
    draw.text((1960, 1432), "SIGMAI", fill=accent, font=font(18, True))

    canvas.save(PNG, quality=95)
    canvas.save(PDF, resolution=300.0)
    print(PNG)
    print(PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
