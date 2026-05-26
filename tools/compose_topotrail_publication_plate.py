from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
SRC = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_final_CORRIGIDO.png"
DEST = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_PRANCHA_PUBLICACAO.png"
DEST_PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_PRANCHA_PUBLICACAO.pdf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def box(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, outline: str, width: int = 2) -> None:
    draw.rounded_rectangle(xy, radius=10, fill=fill, outline=outline, width=width)


def main() -> None:
    src = Image.open(SRC).convert("RGB")
    # Crop the QGIS-rendered map body while removing the broken native scale/footer area.
    map_crop = src.crop((110, 300, 2325, 2050))
    map_crop = map_crop.resize((2480, 2020), Image.Resampling.LANCZOS)

    page = Image.new("RGB", (3507, 2480), "#F7F8F5")
    draw = ImageDraw.Draw(page)

    accent = "#0B5D4A"
    dark = "#1F2723"
    muted = "#5D6863"
    panel = "#FFFFFF"

    draw.rectangle((0, 0, 3507, 24), fill=accent)
    draw.text((120, 70), "Adequabilidade e risco topografico para trilhas - Cruzeiro/SP", fill=dark, font=font(64, True))
    draw.text((124, 150), "Modelagem TopoTrail com cartas 22S465HN, 22S465SN, 22S465VN e 22S465ZN", fill=muted, font=font(32))
    draw.text((124, 195), "Reserva Chico Nunes, RPPN Gigante do Itaguare e Fazenda Batedor", fill=muted, font=font(30))

    # Main map frame.
    map_x, map_y = 115, 290
    draw.rounded_rectangle((map_x - 10, map_y - 10, map_x + 2480 + 10, map_y + 2020 + 10), radius=12, fill="#FFFFFF", outline="#1A1A1A", width=3)
    page.paste(map_crop, (map_x, map_y))
    draw.rectangle((map_x, map_y, map_x + 2480, map_y + 2020), outline="#111111", width=3)

    # Side panel.
    panel_x, panel_y = 2680, 292
    box(draw, (panel_x, panel_y, 3375, 1655), panel, "#D5DCD7", 2)
    draw.text((panel_x + 42, panel_y + 40), "Legenda", fill=dark, font=font(48, True))

    legend = [
        ("Zonas potenciais TopoTrail", "#BFE7D4", "#0B7A5A", "area"),
        ("Reserva e RPPN", "#FFFFFF", "#31572C", "line"),
        ("Fazenda Batedor", "#FFFFFF", "#1D4E89", "line"),
        ("Trilha RCN/RPPN", "#6A0019", "#6A0019", "line_bold"),
        ("Trechos sobrepostos", "#FFD166", "#8A5A13", "area"),
        ("Relevo / risco topografico", "#BFC4C2", "#6E7472", "area"),
    ]
    y = panel_y + 140
    for label, fill, outline, kind in legend:
        if kind == "line":
            draw.line((panel_x + 50, y + 24, panel_x + 130, y + 24), fill=outline, width=8)
        elif kind == "line_bold":
            draw.line((panel_x + 50, y + 24, panel_x + 130, y + 24), fill=outline, width=14)
        else:
            draw.rectangle((panel_x + 50, y, panel_x + 130, y + 48), fill=fill, outline=outline, width=5)
        draw.text((panel_x + 155, y + 3), label, fill=dark, font=font(32))
        y += 74

    # Method notes.
    draw.text((panel_x + 42, y + 35), "Leitura tecnica", fill=dark, font=font(38, True))
    notes = [
        "As trilhas existentes foram sobrepostas",
        "as zonas potenciais geradas pelo TopoTrail.",
        "Trechos em amarelo indicam intersecoes",
        "entre trilha e areas favoraveis.",
        "Analise projetada em SIRGAS 2000 / UTM 23S.",
    ]
    yy = y + 92
    for line in notes:
        draw.text((panel_x + 45, yy), line, fill=muted, font=font(25))
        yy += 38

    # Location panel placeholder, explicit but modest.
    loc_y = 1255
    draw.text((panel_x + 42, loc_y), "Contexto", fill=dark, font=font(38, True))
    draw.rounded_rectangle((panel_x + 45, loc_y + 58, panel_x + 645, loc_y + 325), radius=8, fill="#F2F4F1", outline="#C7D0CA", width=2)
    draw.text((panel_x + 78, loc_y + 94), "Municipio de Cruzeiro/SP", fill=dark, font=font(28, True))
    draw.text((panel_x + 78, loc_y + 140), "Area de estudo destacada no setor", fill=muted, font=font(24))
    draw.text((panel_x + 78, loc_y + 178), "serrano associado a Mantiqueira.", fill=muted, font=font(24))
    draw.ellipse((panel_x + 490, loc_y + 155, panel_x + 525, loc_y + 190), fill=accent)
    draw.text((panel_x + 535, loc_y + 155), "area-alvo", fill=muted, font=font(22))

    # Scale and credits outside the map body.
    scale_y = 2345
    draw.text((125, scale_y), "Escala grafica", fill=dark, font=font(24, True))
    draw.line((315, scale_y + 16, 620, scale_y + 16), fill="#111111", width=10)
    draw.line((315, scale_y + 6, 315, scale_y + 26), fill="#111111", width=5)
    draw.line((467, scale_y + 6, 467, scale_y + 26), fill="#111111", width=5)
    draw.line((620, scale_y + 6, 620, scale_y + 26), fill="#111111", width=5)
    draw.text((300, scale_y + 35), "0", fill=dark, font=font(22))
    draw.text((450, scale_y + 35), "1", fill=dark, font=font(22))
    draw.text((596, scale_y + 35), "2 km", fill=dark, font=font(22))

    credit = "Fonte: DataGEO; SMMA; RPPN Gigante do Itaguare. Autor: Luan da Silva Cortes Maciel. CRS: SIRGAS 2000 / UTM 23S. Criado com SIGMAI/QGIS."
    draw.text((760, scale_y + 18), credit, fill=dark, font=font(22))

    logo = ROOT / "sigmai" / "icons" / "sigmai_logo_full.png"
    if logo.exists():
        logo_img = Image.open(logo).convert("RGBA")
        logo_img.thumbnail((190, 78), Image.Resampling.LANCZOS)
        page.paste(logo_img, (3150, 2300), logo_img)

    page.save(DEST, quality=96)
    page.save(DEST_PDF, "PDF", resolution=300.0)
    print(DEST)
    print(DEST_PDF)


if __name__ == "__main__":
    main()
