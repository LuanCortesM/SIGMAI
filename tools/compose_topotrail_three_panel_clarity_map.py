from __future__ import annotations

import json
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "sigmai_topotrail_scientific_map"
SRC = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_mapa_final_CORRIGIDO.png"
DEST = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_TRES_PAINEIS_CLAREZA.png"
DEST_PDF = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_TRES_PAINEIS_CLAREZA.pdf"
REPORT = OUT / "SIGMAI_TopoTrail_RPPN_Batedor_TRES_PAINEIS_CLAREZA.json"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill: str, chars: int, bold: bool = False) -> int:
    x, y = xy
    for line in wrap(text, chars):
        draw.text((x, y), line, fill=fill, font=font(size, bold))
        y += size + 7
    return y


def panel(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], title: str, letter: str) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=12, fill="#FFFFFF", outline="#18201D", width=3)
    draw.rectangle((x1, y1, x2, y1 + 52), fill="#0A5C49")
    draw.text((x1 + 14, y1 + 11), f"{letter}) {title}", fill="#FFFFFF", font=font(25, True))


def legend_item(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, desc: str, color: str, kind: str = "area", outline: str | None = None) -> int:
    outline = outline or color
    if kind == "line":
        draw.line((x, y + 20, x + 82, y + 20), fill=color, width=8)
    elif kind == "line_bold":
        draw.line((x, y + 20, x + 82, y + 20), fill=color, width=14)
    else:
        draw.rounded_rectangle((x, y, x + 82, y + 44), radius=5, fill=color, outline=outline, width=5)
    draw.text((x + 105, y - 2), label, fill="#1F2824", font=font(25, True))
    draw.text((x + 105, y + 31), desc, fill="#59645F", font=font(20))
    return y + 70


def callout(draw: ImageDraw.ImageDraw, xy: tuple[int, int], target: tuple[int, int], text: str, color: str) -> None:
    x, y = xy
    lines = wrap(text, 22)
    h = 25 + len(lines) * 24
    w = 300
    draw.line((x + w // 2, y + h // 2, target[0], target[1]), fill=color, width=5)
    draw.ellipse((target[0] - 9, target[1] - 9, target[0] + 9, target[1] + 9), fill=color, outline="#FFFFFF", width=3)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill="#FFFFFB", outline=color, width=3)
    yy = y + 10
    for line in lines:
        draw.text((x + 14, yy), line, fill="#1F2824", font=font(20, True))
        yy += 24


def main() -> None:
    src = Image.open(SRC).convert("RGB")
    full = src.crop((108, 300, 2328, 2052))
    focus = src.crop((235, 600, 1240, 1815))

    # Context panel: full model extent, low contrast, with a focus rectangle.
    context = full.resize((1010, 790), Image.Resampling.LANCZOS)
    context = ImageEnhance.Contrast(context).enhance(0.80)
    context = ImageEnhance.Color(context).enhance(0.80)

    # Boundary panel: zoomed and softened so colored boundary notes become dominant.
    boundary = focus.resize((1010, 790), Image.Resampling.LANCZOS)
    boundary = ImageEnhance.Contrast(boundary).enhance(0.72)
    boundary = ImageEnhance.Color(boundary).enhance(0.58)
    boundary = boundary.filter(ImageFilter.GaussianBlur(radius=0.25))

    # Analysis panel: zoomed with stronger trail/result contrast.
    analysis = focus.resize((1010, 790), Image.Resampling.LANCZOS)
    analysis = ImageEnhance.Contrast(analysis).enhance(1.12)
    analysis = ImageEnhance.Color(analysis).enhance(1.12)
    analysis = analysis.filter(ImageFilter.UnsharpMask(radius=1.2, percent=90, threshold=3))

    page = Image.new("RGB", (3507, 2480), "#F5F6F0")
    draw = ImageDraw.Draw(page)
    dark = "#1F2824"
    muted = "#59645F"
    accent = "#0A5C49"
    green = "#31572C"
    blue = "#155799"
    wine = "#7B0022"
    amber = "#C88216"
    potential = "#0C7A5B"

    draw.rectangle((0, 0, 3507, 30), fill=accent)
    draw.text((112, 66), "TopoTrail, RPPN e Fazenda Batedor - leitura em três escalas", fill=dark, font=font(56, True))
    draw.text((116, 138), "Cruzeiro/SP | recorte municipal, área ambiental e sobreposição da trilha RCN/RPPN", fill=muted, font=font(31))
    draw.text((116, 184), "Objetivo: separar contexto, limites e análise para reduzir poluição visual", fill=muted, font=font(27))

    # Panel positions.
    a = (96, 300, 1116, 1148)
    b = (1244, 300, 2264, 1148)
    c = (96, 1266, 2264, 2188)
    side = (2394, 300, 3388, 2188)

    panel(draw, a, "Contexto municipal / modelo completo", "A")
    page.paste(context, (a[0] + 5, a[1] + 54))
    draw.rectangle((a[0] + 90, a[1] + 154, a[0] + 420, a[1] + 645), outline="#E23D28", width=7)
    draw.text((a[0] + 450, a[1] + 160), "área ampliada nos painéis B/C", fill="#E23D28", font=font(22, True))
    wrapped(draw, (a[0] + 24, a[3] - 88), "O recorte municipal aparece aqui como contexto: o produto TopoTrail foi avaliado dentro do conjunto espacial de Cruzeiro/SP.", 20, "#38433E", 68)

    panel(draw, b, "Recortes: RPPN/Reserva e Fazenda Batedor", "B")
    page.paste(boundary, (b[0] + 5, b[1] + 54))
    # Deliberately strong guide outlines on top of the QGIS render to make the study areas readable.
    draw.rounded_rectangle((b[0] + 215, b[1] + 260, b[0] + 545, b[1] + 548), radius=18, outline=green, width=10)
    draw.rounded_rectangle((b[0] + 465, b[1] + 475, b[0] + 780, b[1] + 742), radius=18, outline=blue, width=10)
    callout(draw, (b[0] + 40, b[1] + 92), (b[0] + 360, b[1] + 390), "Reserva Chico Nunes / RPPN Gigante do Itaguaré", green)
    callout(draw, (b[0] + 625, b[1] + 118), (b[0] + 610, b[1] + 600), "Fazenda Batedor", blue)
    draw.rectangle((b[0] + 22, b[3] - 82, b[2] - 22, b[3] - 22), fill="#FFFDF6", outline="#D8D0BC", width=2)
    draw.text((b[0] + 36, b[3] - 68), "Leitura: este painel isola os recortes. A área verde é ambiental; a azul é fundiária/referência Batedor.", fill="#38433E", font=font(20))

    panel(draw, c, "Análise: trilha existente x zonas potenciais", "C")
    analysis_large = analysis.resize((1425, 820), Image.Resampling.LANCZOS)
    page.paste(analysis_large, (c[0] + 5, c[1] + 54))
    # Add clean route emphasis and area labels.
    callout(draw, (c[0] + 55, c[1] + 648), (c[0] + 645, c[1] + 610), "Trilha RCN/RPPN: percurso real", wine)
    callout(draw, (c[0] + 650, c[1] + 90), (c[0] + 520, c[1] + 410), "Trechos prioritários: interseção/proximidade", amber)
    callout(draw, (c[0] + 1110, c[1] + 150), (c[0] + 1125, c[1] + 520), "Zonas potenciais TopoTrail", potential)
    draw.rectangle((c[0] + 1470, c[1] + 70, c[2] - 35, c[3] - 42), fill="#FFFFFF", outline="#D3DCD5", width=2)
    yy = c[1] + 100
    draw.text((c[0] + 1500, yy), "Interpretação", fill=dark, font=font(31, True))
    yy += 52
    yy = wrapped(draw, (c[0] + 1500, yy), "O mapa deve ser lido pela relação entre a trilha vinho e os trechos amarelos. As manchas verdes amplas são contexto de adequabilidade; não devem dominar a decisão.", 23, muted, 42)
    yy += 26
    yy = wrapped(draw, (c[0] + 1500, yy), "A verificação de campo deve priorizar os pontos onde a trilha cruza ou margeia as zonas favoráveis em relevo movimentado.", 23, muted, 42)

    # Side legend and technical panel.
    panel(draw, side, "Legenda semântica e notas", "")
    sx, sy = side[0] + 45, side[1] + 90
    draw.text((sx, sy), "Legenda", fill=dark, font=font(39, True))
    sy += 72
    draw.text((sx, sy), "Resultado", fill=accent, font=font(25, True)); sy += 42
    sy = legend_item(draw, sx, sy, "Trechos prioritários", "interseção/proximidade", "#FFD166", "area", amber)
    sy = legend_item(draw, sx, sy, "Zonas potenciais", "adequabilidade TopoTrail", "#BFE7D4", "area", potential)
    sy += 18
    draw.text((sx, sy), "Recortes", fill=accent, font=font(25, True)); sy += 42
    sy = legend_item(draw, sx, sy, "Reserva / RPPN", "área ambiental", green, "line")
    sy = legend_item(draw, sx, sy, "Fazenda Batedor", "limite fundiário", blue, "line")
    sy += 18
    draw.text((sx, sy), "Trilhas", fill=accent, font=font(25, True)); sy += 42
    sy = legend_item(draw, sx, sy, "Trilha RCN/RPPN", "percurso existente", wine, "line_bold")
    sy += 18
    draw.text((sx, sy), "Contexto físico", fill=accent, font=font(25, True)); sy += 42
    sy = legend_item(draw, sx, sy, "Relevo / risco", "base cinza TopoTrail", "#C5CAC7", "area", "#6F7672")

    sy += 42
    draw.text((sx, sy), "Notas técnicas", fill=dark, font=font(34, True)); sy += 50
    sy = wrapped(draw, (sx, sy), "CRS de análise: SIRGAS 2000 / UTM zona 23S. Escala gráfica aproximada para leitura local.", 22, muted, 55)
    sy += 20
    sy = wrapped(draw, (sx, sy), "Travessia Marins-Itaguaré não foi usada: a camada carregada no teste apareceu sem feições e sem CRS válido.", 21, "#684B35", 55)

    # Footer and scale.
    scale_y = 2294
    draw.text((110, scale_y - 32), "Escala gráfica aproximada", fill=dark, font=font(23, True))
    draw.line((110, scale_y + 10, 510, scale_y + 10), fill="#111111", width=10)
    for xx in (110, 310, 510):
        draw.line((xx, scale_y - 2, xx, scale_y + 24), fill="#111111", width=5)
    draw.text((102, scale_y + 36), "0", fill=dark, font=font(21))
    draw.text((296, scale_y + 36), "1", fill=dark, font=font(21))
    draw.text((487, scale_y + 36), "2 km", fill=dark, font=font(21))
    footer = "Fontes: DataGEO; Secretaria Municipal de Meio Ambiente; RPPN Gigante do Itaguaré. Autor do mapa: Luan da Silva Cortes Maciel. Criado com SIGMAI/QGIS. CRS: SIRGAS 2000 / UTM zona 23S. Data: 2026."
    wrapped(draw, (650, scale_y - 18), footer, 22, dark, 124)

    logo = ROOT / "qgis_plugin" / "icons" / "sigmai_logo_full.png"
    if logo.exists():
        logo_img = Image.open(logo).convert("RGBA")
        logo_img.thumbnail((175, 70), Image.Resampling.LANCZOS)
        page.paste(logo_img, (3170, 2286), logo_img)

    page.save(DEST, quality=96)
    page.save(DEST_PDF, "PDF", resolution=300.0)
    REPORT.write_text(json.dumps({
        "template": "three_panel_clarity_map",
        "reason": "Separates municipal context, study-area cuts and trail/suitability analysis after user reported visual overload.",
        "outputs": {"png": str(DEST), "pdf": str(DEST_PDF)},
        "source_render": str(SRC),
        "limitations": [
            "Panel B uses guide outlines over the QGIS render to make recortes readable; exact boundary styling should be implemented natively in SIGMAI next.",
            "Travessia Marins-Itaguare was not used because the loaded layer had no features/valid CRS."
        ]
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(DEST)
    print(DEST_PDF)


if __name__ == "__main__":
    main()
