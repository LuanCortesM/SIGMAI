from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
SRC = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_final_CORRIGIDO.png"
DEST = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_PRANCHA_EXPLICATIVA_V3.png"
DEST_PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_PRANCHA_EXPLICATIVA_V3.pdf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill: str, chars: int, bold: bool = False) -> int:
    x, y = xy
    for line in wrap(text, chars):
        draw.text((x, y), line, fill=fill, font=font(size, bold))
        y += size + 8
    return y


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str = "#FFFFFF", outline: str = "#CDD7D0") -> None:
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=3)


def callout(draw: ImageDraw.ImageDraw, xy: tuple[int, int], target: tuple[int, int], title: str, body: str, color: str, w: int = 460) -> None:
    x, y = xy
    lines = wrap(body, 34)
    h = 62 + len(lines) * 29 + 18
    draw.line((x + w // 2, y + h // 2, target[0], target[1]), fill=color, width=6)
    draw.ellipse((target[0] - 12, target[1] - 12, target[0] + 12, target[1] + 12), fill=color, outline="#FFFFFF", width=4)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill="#FFFFFA", outline=color, width=4)
    draw.text((x + 18, y + 13), title, fill="#1E2723", font=font(30, True))
    yy = y + 55
    for line in lines:
        draw.text((x + 18, yy), line, fill="#45514B", font=font(22))
        yy += 29


def main() -> None:
    src = Image.open(SRC).convert("RGB")

    # Full QGIS map body for the overview inset.
    full = src.crop((108, 300, 2328, 2052)).resize((760, 600), Image.Resampling.LANCZOS)

    # Analytical focus: this crop removes the visually dominant eastern model area and
    # enlarges the RPPN/Fazenda/trail intersection, which is the actual question.
    focus = src.crop((245, 610, 1220, 1810)).resize((2180, 1880), Image.Resampling.LANCZOS)
    focus = focus.filter(ImageFilter.UnsharpMask(radius=1.4, percent=95, threshold=3))

    page = Image.new("RGB", (3507, 2480), "#F6F7F1")
    draw = ImageDraw.Draw(page)

    dark = "#1F2824"
    muted = "#59645F"
    accent = "#0A5C49"
    green = "#0C7A5B"
    rppn = "#31572C"
    batedor = "#155799"
    wine = "#7B0022"
    amber = "#C88216"

    draw.rectangle((0, 0, 3507, 30), fill=accent)
    draw.text((112, 70), "RPPN, Fazenda Batedor e trilha RCN/RPPN", fill=dark, font=font(62, True))
    draw.text((116, 146), "Adequabilidade TopoTrail, risco topográfico e sobreposição de trilhas - Cruzeiro/SP", fill=muted, font=font(32))
    draw.text((116, 193), "Mapa explicativo com foco na leitura territorial das áreas ambientais", fill=muted, font=font(28))

    map_x, map_y = 112, 300
    panel(draw, (map_x - 15, map_y - 15, map_x + 2180 + 15, map_y + 1880 + 15), "#FFFFFF", "#171D1A")
    page.paste(focus, (map_x, map_y))
    draw.rectangle((map_x, map_y, map_x + 2180, map_y + 1880), outline="#111111", width=3)
    draw.text((map_x + 24, map_y + 22), "DETALHE DA ÁREA DE ANÁLISE", fill="#FFFFFF", font=font(28, True))
    draw.rectangle((map_x + 16, map_y + 18, map_x + 510, map_y + 62), outline="#FFFFFF", width=2)

    # Direct labels, with intentionally plain language.
    callout(
        draw,
        (map_x + 36, map_y + 90),
        (map_x + 555, map_y + 520),
        "Reserva Chico Nunes / RPPN",
        "Área ambiental em contorno verde/marrom. É a referência principal de conservação neste teste.",
        rppn,
        500,
    )
    callout(
        draw,
        (map_x + 34, map_y + 360),
        (map_x + 620, map_y + 800),
        "Fazenda Batedor",
        "Limite fundiário usado para recorte e comparação com as zonas potenciais.",
        batedor,
        455,
    )
    callout(
        draw,
        (map_x + 38, map_y + 1415),
        (map_x + 905, map_y + 1280),
        "Trilha RCN/RPPN",
        "Percurso existente. A linha vinho permite comparar caminho real e potencial modelado.",
        wine,
        500,
    )
    callout(
        draw,
        (map_x + 985, map_y + 92),
        (map_x + 685, map_y + 690),
        "Trechos de interesse",
        "Amarelo: onde a trilha e as zonas potenciais se encontram ou ficam muito próximas.",
        amber,
        500,
    )
    callout(
        draw,
        (map_x + 1490, map_y + 360),
        (map_x + 1630, map_y + 1040),
        "Zonas TopoTrail",
        "Verde: áreas potenciais. O foco interpretativo é a proximidade com trilhas e limites ambientais.",
        green,
        500,
    )

    # Right column: legend + method + overview.
    side_x = 2380
    panel(draw, (side_x, 300, 3388, 2180), "#FFFFFF", "#D0D9D3")
    draw.text((side_x + 50, 348), "Legenda interpretativa", fill=dark, font=font(43, True))
    y = 430
    legend = [
        ("Zonas potenciais TopoTrail", "favorabilidade modelada", "#BFE7D4", green, "area"),
        ("Reserva Chico Nunes / RPPN", "área ambiental principal", "#FFFFFF", rppn, "line"),
        ("Fazenda Batedor", "limite de referência", "#FFFFFF", batedor, "line"),
        ("Trilha RCN/RPPN", "trilha existente", wine, wine, "line_bold"),
        ("Trechos sobrepostos", "prioridade espacial", "#FFD166", amber, "area"),
        ("Risco/relevo TopoTrail", "base cinza de encostas", "#BFC4C2", "#6E7472", "area"),
    ]
    for title, desc, fill, outline, kind in legend:
        if kind == "area":
            draw.rounded_rectangle((side_x + 54, y + 7, side_x + 132, y + 61), radius=4, fill=fill, outline=outline, width=5)
        elif kind == "line_bold":
            draw.line((side_x + 58, y + 35, side_x + 134, y + 35), fill=outline, width=14)
        else:
            draw.line((side_x + 58, y + 35, side_x + 134, y + 35), fill=outline, width=8)
        draw.text((side_x + 165, y), title, fill=dark, font=font(29, True))
        draw.text((side_x + 165, y + 38), desc, fill=muted, font=font(23))
        y += 92

    y += 12
    draw.text((side_x + 50, y), "Síntese técnica", fill=dark, font=font(38, True))
    y += 58
    y = draw_wrapped(
        draw,
        (side_x + 54, y),
        "A trilha RCN/RPPN atravessa ou margeia manchas potenciais, indicando trechos com maior interesse para verificação de campo.",
        25,
        muted,
        58,
    )
    y += 18
    y = draw_wrapped(
        draw,
        (side_x + 54, y),
        "A análise foi conduzida em SIRGAS 2000 / UTM 23S para manter coerência métrica entre limites, trilha e resultados derivados.",
        25,
        muted,
        58,
    )

    y += 28
    draw.text((side_x + 50, y), "Visão geral", fill=dark, font=font(38, True))
    y += 58
    draw.rounded_rectangle((side_x + 54, y, side_x + 814, y + 600), radius=10, fill="#FFFFFF", outline="#AEBAB2", width=3)
    page.paste(full, (side_x + 54, y))
    draw.rectangle((side_x + 54, y, side_x + 814, y + 600), outline="#111111", width=2)
    # Approximate focus rectangle in the overview.
    draw.rectangle((side_x + 120, y + 130, side_x + 390, y + 480), outline="#E23D28", width=6)
    draw.text((side_x + 442, y + 128), "área ampliada", fill="#E23D28", font=font(24, True))

    y += 638
    draw.text((side_x + 50, y), "Limitação registrada", fill=dark, font=font(34, True))
    y += 50
    draw_wrapped(
        draw,
        (side_x + 54, y),
        "A camada Travessia Marins-Itaguaré apareceu sem feições e sem CRS válido no teste; por isso não foi usada como evidência cartográfica.",
        22,
        "#684B35",
        62,
    )

    # Footer and manual scale.
    scale_y = 2290
    draw.text((120, scale_y - 34), "Escala gráfica aproximada", fill=dark, font=font(24, True))
    draw.line((120, scale_y + 10, 520, scale_y + 10), fill="#111111", width=10)
    for xx in (120, 320, 520):
        draw.line((xx, scale_y - 2, xx, scale_y + 24), fill="#111111", width=5)
    draw.text((112, scale_y + 36), "0", fill=dark, font=font(22))
    draw.text((305, scale_y + 36), "1", fill=dark, font=font(22))
    draw.text((497, scale_y + 36), "2 km", fill=dark, font=font(22))

    footer = (
        "Fontes: DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguaré. "
        "Autor do mapa: Luan da Silva Cortes Maciel. Criado com SIGMAI/QGIS. "
        "CRS: SIRGAS 2000 / UTM zona 23S. Data: 2026."
    )
    draw_wrapped(draw, (660, scale_y - 20), footer, 22, dark, 122)

    logo = ROOT / "qgis_plugin" / "icons" / "sigmai_logo_full.png"
    if logo.exists():
        logo_img = Image.open(logo).convert("RGBA")
        logo_img.thumbnail((175, 70), Image.Resampling.LANCZOS)
        page.paste(logo_img, (3170, 2286), logo_img)

    page.save(DEST, quality=96)
    page.save(DEST_PDF, "PDF", resolution=300.0)
    print(DEST)
    print(DEST_PDF)


if __name__ == "__main__":
    main()
