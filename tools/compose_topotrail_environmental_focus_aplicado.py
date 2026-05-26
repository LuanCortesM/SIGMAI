from __future__ import annotations

import json
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
SRC = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_final_CORRIGIDO.png"
DEST = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_APLICADO.png"
DEST_PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_APLICADO.pdf"
REPORT = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_ENVIRONMENTAL_FOCUS_APLICADO.json"


PARAMETERS = {
    "template": "environmental_focus_map",
    "map_intent": "interpretar trilha, limites ambientais/fundiarios e zonas potenciais TopoTrail",
    "spatial_question": "A trilha RCN/RPPN cruza ou margeia zonas potenciais no contexto da RPPN/Reserva e da Fazenda Batedor?",
    "dominant_layer": "trechos prioritarios e trilha RCN/RPPN",
    "supporting_context": "risco/relevo TopoTrail em cinza e zonas potenciais em verde",
    "legend_policy": "semantic_grouped_legend",
    "north_policy": "small_subordinate",
    "scale_policy": "metric_projected_scale",
    "crs": "SIRGAS 2000 / UTM zone 23S",
    "known_limitation": "Travessia Marins-Itaguare carregada sem feicoes/CRS valido; nao usada como evidencia.",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill: str, chars: int, bold: bool = False, gap: int = 8) -> int:
    x, y = xy
    for line in wrap(text, chars):
        draw.text((x, y), line, fill=fill, font=font(size, bold))
        y += size + gap
    return y


def panel(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str = "#FFFFFF", outline: str = "#CCD6CE", width: int = 3) -> None:
    draw.rounded_rectangle(xy, radius=18, fill=fill, outline=outline, width=width)


def callout(draw: ImageDraw.ImageDraw, xy: tuple[int, int], target: tuple[int, int], title: str, body: str, color: str, w: int = 470) -> None:
    x, y = xy
    lines = wrap(body, 34)
    h = 62 + len(lines) * 30 + 18
    draw.line((x + w // 2, y + h // 2, target[0], target[1]), fill=color, width=6)
    draw.ellipse((target[0] - 12, target[1] - 12, target[0] + 12, target[1] + 12), fill=color, outline="#FFFFFF", width=4)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill="#FFFFFA", outline=color, width=4)
    draw.text((x + 18, y + 13), title, fill="#1E2723", font=font(30, True))
    yy = y + 56
    for line in lines:
        draw.text((x + 18, yy), line, fill="#45514B", font=font(22))
        yy += 30


def main() -> None:
    src = Image.open(SRC).convert("RGB")
    full = src.crop((108, 300, 2328, 2052)).resize((720, 570), Image.Resampling.LANCZOS)

    # This crop keeps the relief and the valid vector overlays from the successful QGIS render.
    focus = src.crop((235, 600, 1240, 1815)).resize((2180, 1880), Image.Resampling.LANCZOS)
    focus = focus.filter(ImageFilter.UnsharpMask(radius=1.25, percent=85, threshold=3))

    page = Image.new("RGB", (3507, 2480), "#F5F6F0")
    draw = ImageDraw.Draw(page)

    dark = "#1F2824"
    muted = "#59645F"
    accent = "#0A5C49"
    rppn = "#31572C"
    batedor = "#155799"
    trail = "#7B0022"
    overlap = "#C88216"
    potential = "#0C7A5B"
    risk = "#6F7672"

    draw.rectangle((0, 0, 3507, 30), fill=accent)
    draw.text((112, 64), "RPPN, Fazenda Batedor e trilha RCN/RPPN", fill=dark, font=font(62, True))
    draw.text((116, 142), "Adequabilidade TopoTrail, relevo/risco e trechos prioritários - Cruzeiro/SP", fill=muted, font=font(32))
    draw.text((116, 190), "Mapa ambiental focado: pergunta espacial, hierarquia visual e legenda semântica", fill=muted, font=font(27))

    map_x, map_y = 112, 300
    panel(draw, (map_x - 15, map_y - 15, map_x + 2180 + 15, map_y + 1880 + 15), "#FFFFFF", "#171D1A", 4)
    page.paste(focus, (map_x, map_y))
    draw.rectangle((map_x, map_y, map_x + 2180, map_y + 1880), outline="#111111", width=3)
    draw.rectangle((map_x + 18, map_y + 18, map_x + 675, map_y + 72), fill=accent, outline="#FFFFFF", width=2)
    draw.text((map_x + 30, map_y + 28), "PAINEL PRINCIPAL: RPPN/Fazenda/trilha", fill="#FFFFFF", font=font(27, True))

    callout(draw, (map_x + 34, map_y + 96), (map_x + 565, map_y + 560), "Reserva / RPPN", "Área ambiental principal. O contorno verde/marrom delimita a referência de conservação.", rppn, 505)
    callout(draw, (map_x + 34, map_y + 375), (map_x + 645, map_y + 815), "Fazenda Batedor", "Limite fundiário usado para recorte e comparação com a trilha e zonas potenciais.", batedor, 485)
    callout(draw, (map_x + 38, map_y + 1400), (map_x + 890, map_y + 1280), "Trilha RCN/RPPN", "Percurso existente, simbolizado em vinho para permanecer legível sobre o relevo.", trail, 500)
    callout(draw, (map_x + 900, map_y + 92), (map_x + 690, map_y + 710), "Trechos prioritários", "Áreas amarelas: onde trilha e zonas potenciais se aproximam ou se sobrepõem.", overlap, 520)
    callout(draw, (map_x + 1510, map_y + 345), (map_x + 1590, map_y + 1020), "Zonas TopoTrail", "Verde: favorabilidade modelada. É contexto analítico para interpretar a trilha.", potential, 500)

    # Side panel.
    side_x = 2390
    panel(draw, (side_x, 300, 3388, 2180), "#FFFFFF", "#D0D9D3", 3)
    draw.text((side_x + 48, 348), "Como interpretar", fill=dark, font=font(43, True))
    y = 424
    y = wrapped(draw, (side_x + 52, y), PARAMETERS["spatial_question"], 25, muted, 58)
    y += 28

    groups = [
        ("Resultado da análise", [(overlap, "#FFD166", "Trechos prioritários", "interseção/proximidade trilha-zona"), (potential, "#BFE7D4", "Zonas potenciais", "favorabilidade TopoTrail")]),
        ("Limites", [(rppn, "#FFFFFF", "Reserva Chico Nunes / RPPN", "área ambiental"), (batedor, "#FFFFFF", "Fazenda Batedor", "limite fundiário")]),
        ("Trilha", [(trail, trail, "Trilha RCN/RPPN", "percurso existente")]),
        ("Contexto físico", [(risk, "#C5CAC7", "Relevo / risco TopoTrail", "base morfométrica")]),
    ]
    for header, items in groups:
        draw.text((side_x + 52, y), header, fill=accent, font=font(26, True))
        y += 46
        for outline, fill, title, desc in items:
            if fill == outline:
                draw.line((side_x + 58, y + 32, side_x + 138, y + 32), fill=outline, width=14)
            elif title in {"Reserva Chico Nunes / RPPN", "Fazenda Batedor"}:
                draw.line((side_x + 58, y + 32, side_x + 138, y + 32), fill=outline, width=8)
            else:
                draw.rounded_rectangle((side_x + 58, y + 7, side_x + 138, y + 62), radius=5, fill=fill, outline=outline, width=5)
            draw.text((side_x + 166, y), title, fill=dark, font=font(28, True))
            draw.text((side_x + 166, y + 38), desc, fill=muted, font=font(22))
            y += 82
        y += 8

    draw.text((side_x + 48, y), "Síntese", fill=dark, font=font(34, True))
    y += 50
    y = wrapped(draw, (side_x + 52, y), "A leitura principal é local: a trilha existente se aproxima de manchas potenciais, e os trechos amarelos indicam pontos que merecem validação em campo.", 23, muted, 62)
    y += 24

    draw.text((side_x + 48, y), "Visão geral", fill=dark, font=font(34, True))
    y += 50
    draw.rounded_rectangle((side_x + 52, y, side_x + 772, y + 570), radius=10, fill="#FFFFFF", outline="#AEBAB2", width=3)
    page.paste(full, (side_x + 52, y))
    draw.rectangle((side_x + 52, y, side_x + 772, y + 570), outline="#111111", width=2)
    draw.rectangle((side_x + 102, y + 110, side_x + 365, y + 460), outline="#E23D28", width=6)
    draw.text((side_x + 392, y + 112), "área ampliada", fill="#E23D28", font=font(23, True))

    y += 610
    draw.text((side_x + 48, y), "Limitação registrada", fill=dark, font=font(31, True))
    y += 46
    wrapped(draw, (side_x + 52, y), PARAMETERS["known_limitation"], 21, "#684B35", 64)

    scale_y = 2290
    draw.text((120, scale_y - 34), "Escala gráfica aproximada", fill=dark, font=font(24, True))
    draw.line((120, scale_y + 10, 520, scale_y + 10), fill="#111111", width=10)
    for xx in (120, 320, 520):
        draw.line((xx, scale_y - 2, xx, scale_y + 24), fill="#111111", width=5)
    draw.text((112, scale_y + 36), "0", fill=dark, font=font(22))
    draw.text((305, scale_y + 36), "1", fill=dark, font=font(22))
    draw.text((497, scale_y + 36), "2 km", fill=dark, font=font(22))

    footer = "Fontes: DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguaré. Autor do mapa: Luan da Silva Cortes Maciel. Criado com SIGMAI/QGIS. CRS: SIRGAS 2000 / UTM zona 23S. Data: 2026."
    wrapped(draw, (660, scale_y - 20), footer, 22, dark, 122)

    logo = ROOT / "qgis_plugin" / "icons" / "sigmai_logo_full.png"
    if logo.exists():
        logo_img = Image.open(logo).convert("RGBA")
        logo_img.thumbnail((175, 70), Image.Resampling.LANCZOS)
        page.paste(logo_img, (3170, 2286), logo_img)

    page.save(DEST, quality=96)
    page.save(DEST_PDF, "PDF", resolution=300.0)
    REPORT.write_text(json.dumps({"parameters": PARAMETERS, "outputs": {"png": str(DEST), "pdf": str(DEST_PDF)}, "source_render": str(SRC)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(DEST)
    print(DEST_PDF)


if __name__ == "__main__":
    main()
