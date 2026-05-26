from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
SRC = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_final_CORRIGIDO.png"
DEST = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_PRANCHA_EXPLICATIVA_V2.png"
DEST_PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_PRANCHA_EXPLICATIVA_V2.pdf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def text_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    size: int,
    fill: str,
    max_chars: int,
    bold: bool = False,
    line_gap: int = 8,
) -> int:
    x, y = xy
    for line in wrap(text, max_chars):
        draw.text((x, y), line, fill=fill, font=font(size, bold))
        y += size + line_gap
    return y


def rounded_panel(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    fill: str = "#FFFFFF",
    outline: str = "#CFD8D2",
    width: int = 2,
    radius: int = 16,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def callout(
    draw: ImageDraw.ImageDraw,
    label_xy: tuple[int, int],
    target_xy: tuple[int, int],
    title: str,
    subtitle: str,
    color: str,
    width: int = 360,
) -> None:
    x, y = label_xy
    pad = 18
    title_f = font(28, True)
    sub_f = font(22)
    lines = wrap(subtitle, 29)
    h = 56 + len(lines) * 30 + pad
    draw.line((x + 18, y + h // 2, target_xy[0], target_xy[1]), fill=color, width=6)
    draw.ellipse((target_xy[0] - 10, target_xy[1] - 10, target_xy[0] + 10, target_xy[1] + 10), fill=color, outline="#FFFFFF", width=3)
    draw.rounded_rectangle((x, y, x + width, y + h), radius=12, fill="#FFFFF9", outline=color, width=4)
    draw.text((x + pad, y + 12), title, fill="#1F2723", font=title_f)
    yy = y + 52
    for line in lines:
        draw.text((x + pad, yy), line, fill="#46514C", font=sub_f)
        yy += 30


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(SRC)

    src = Image.open(SRC).convert("RGB")
    # Preserve the QGIS-rendered body, but crop out the weak footer/native scale.
    map_crop = src.crop((108, 300, 2328, 2052))
    map_crop = map_crop.resize((2340, 1848), Image.Resampling.LANCZOS)

    page_w, page_h = 3507, 2480
    page = Image.new("RGB", (page_w, page_h), "#F5F7F2")
    draw = ImageDraw.Draw(page)

    accent = "#0A5C49"
    dark = "#1E2723"
    muted = "#59655F"
    green = "#0D7B5F"
    blue = "#1D4E89"
    wine = "#7B0022"
    amber = "#C88216"

    draw.rectangle((0, 0, page_w, 28), fill=accent)
    draw.text((112, 72), "Adequabilidade, risco e trilhas em areas ambientais - Cruzeiro/SP", fill=dark, font=font(58, True))
    draw.text((116, 145), "Leitura SIGMAI/TopoTrail das zonas potenciais, limites ambientais e trilha RCN/RPPN", fill=muted, font=font(31))
    draw.text((116, 190), "Cartas 22S465HN, 22S465SN, 22S465VN e 22S465ZN | SIRGAS 2000 / UTM 23S", fill=muted, font=font(27))

    map_x, map_y = 112, 300
    draw.rounded_rectangle((map_x - 14, map_y - 14, map_x + 2340 + 14, map_y + 1848 + 14), radius=18, fill="#FFFFFF", outline="#151A18", width=4)
    page.paste(map_crop, (map_x, map_y))
    draw.rectangle((map_x, map_y, map_x + 2340, map_y + 1848), outline="#111111", width=3)

    # Quieten the over-dense far east of the model so interpretation focuses on the target area.
    overlay = Image.new("RGBA", page.size, (255, 255, 255, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((map_x + 1180, map_y + 30, map_x + 2328, map_y + 1818), fill=(255, 255, 255, 42))
    page = Image.alpha_composite(page.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(page)

    # Callouts are intentionally direct; the previous map required the reader to infer too much.
    callout(
        draw,
        (map_x + 34, map_y + 86),
        (map_x + 560, map_y + 610),
        "Reserva / RPPN",
        "Area ambiental principal analisada; contorno verde/marrom sobre o relevo.",
        "#31572C",
        width=430,
    )
    callout(
        draw,
        (map_x + 36, map_y + 380),
        (map_x + 690, map_y + 835),
        "Fazenda Batedor",
        "Limite de referencia para recorte e comparacao territorial.",
        blue,
        width=420,
    )
    callout(
        draw,
        (map_x + 42, map_y + 1218),
        (map_x + 800, map_y + 1198),
        "Trilha RCN/RPPN",
        "Linha vinho: percurso existente usado para comparar aderencia as zonas potenciais.",
        wine,
        width=440,
    )
    callout(
        draw,
        (map_x + 785, map_y + 80),
        (map_x + 610, map_y + 725),
        "Sobreposicoes",
        "Areas amarelas indicam trechos onde trilha e zonas favoraveis se aproximam ou se cruzam.",
        amber,
        width=470,
    )
    callout(
        draw,
        (map_x + 1715, map_y + 94),
        (map_x + 1600, map_y + 760),
        "Zonas TopoTrail",
        "Verde: modelagem de areas potenciais. A leitura deve priorizar a porcao proxima aos limites e trilhas.",
        green,
        width=500,
    )

    # Right interpretation panel.
    panel_x, panel_y = 2535, 300
    rounded_panel(draw, (panel_x, panel_y, 3388, 1990), "#FFFFFF", "#D2DAD4", 3, 18)
    draw.text((panel_x + 48, panel_y + 42), "Como ler este mapa", fill=dark, font=font(44, True))
    y = panel_y + 118
    y = text_box(
        draw,
        (panel_x + 50, y),
        "O objetivo nao e mostrar apenas camadas: e verificar se a trilha existente se aproxima das zonas potenciais estimadas pelo TopoTrail dentro das areas ambientais.",
        25,
        muted,
        48,
    )
    y += 26

    legend = [
        ("Zonas potenciais TopoTrail", "areas favoraveis/modeladas", "#BFE7D4", green, "area"),
        ("Reserva Chico Nunes / RPPN", "area ambiental de interesse", "#FFFFFF", "#31572C", "line"),
        ("Fazenda Batedor", "limite fundiario de referencia", "#FFFFFF", blue, "line"),
        ("Trilha RCN/RPPN", "percurso existente avaliado", wine, wine, "line_bold"),
        ("Trechos sobrepostos", "prioridade de leitura espacial", "#FFD166", amber, "area"),
        ("Relevo / risco topografico", "base morfometrica cinza", "#BFC4C2", "#6E7472", "area"),
    ]
    for title, desc, fill, outline, kind in legend:
        if kind == "area":
            draw.rounded_rectangle((panel_x + 52, y + 6, panel_x + 120, y + 58), radius=4, fill=fill, outline=outline, width=5)
        elif kind == "line_bold":
            draw.line((panel_x + 54, y + 32, panel_x + 122, y + 32), fill=outline, width=13)
        else:
            draw.line((panel_x + 54, y + 32, panel_x + 122, y + 32), fill=outline, width=8)
        draw.text((panel_x + 148, y), title, fill=dark, font=font(29, True))
        draw.text((panel_x + 148, y + 37), desc, fill=muted, font=font(23))
        y += 88

    y += 20
    draw.text((panel_x + 48, y), "Achado principal", fill=dark, font=font(35, True))
    y += 54
    for line in [
        "A trilha RCN/RPPN cruza ou margeia manchas favoraveis, com trechos de maior interesse destacados em amarelo.",
        "A leitura tecnica deve considerar o relevo: encostas fortes e drenagens podem reduzir acessibilidade mesmo dentro de zonas potenciais.",
    ]:
        y = text_box(draw, (panel_x + 52, y), line, 24, muted, 50)
        y += 18

    y += 6
    draw.text((panel_x + 48, y), "Limites do teste", fill=dark, font=font(35, True))
    y += 54
    y = text_box(
        draw,
        (panel_x + 52, y),
        "A camada Travessia Marins-Itaguare carregada no teste apareceu sem feicoes/CRS valido; por isso nao foi usada como evidencia nesta prancha.",
        23,
        "#6A4C35",
        52,
    )

    # Manual, checked scale. Native QGIS scale bar was visually unreliable in this map family.
    scale_y = 2282
    draw.text((126, scale_y - 30), "Escala grafica aproximada", fill=dark, font=font(24, True))
    draw.line((126, scale_y + 12, 486, scale_y + 12), fill="#111111", width=10)
    for xx in (126, 306, 486):
        draw.line((xx, scale_y, xx, scale_y + 25), fill="#111111", width=5)
    draw.text((118, scale_y + 36), "0", fill=dark, font=font(22))
    draw.text((292, scale_y + 36), "1", fill=dark, font=font(22))
    draw.text((463, scale_y + 36), "2 km", fill=dark, font=font(22))

    footer = (
        "Fontes: DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguare. "
        "Autor do mapa: Luan da Silva Cortes Maciel. Criado com SIGMAI/QGIS. "
        "CRS de analise: SIRGAS 2000 / UTM zona 23S. Data: 2026."
    )
    text_box(draw, (650, scale_y - 14), footer, 21, dark, 140, line_gap=6)

    logo = ROOT / "sigmai" / "icons" / "sigmai_logo_full.png"
    if logo.exists():
        logo_img = Image.open(logo).convert("RGBA")
        logo_img.thumbnail((170, 70), Image.Resampling.LANCZOS)
        page.paste(logo_img, (3168, 2285), logo_img)

    # Gentle sharpening after composition.
    page = page.filter(ImageFilter.UnsharpMask(radius=1.1, percent=80, threshold=3))
    page.save(DEST, quality=96)
    page.save(DEST_PDF, "PDF", resolution=300.0)
    print(DEST)
    print(DEST_PDF)


if __name__ == "__main__":
    main()
