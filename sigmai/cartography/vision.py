"""Legibilidade das cores por quem tem deficiência na visão de cores.

Revistas pedem figuras legíveis por daltônicos, e cores categóricas são
exatamente onde uma paleta escolhida à mão falha: verde e laranja parecem
distintos para quem escolheu e idênticos para 8% dos leitores homens. A
verificação aqui é determinística e vem da literatura:

* a simulação da deficiência usa as matrizes de Machado, Oliveira & Fernandes
  (2009), *A Physiologically-based Model for Simulation of Color Vision
  Deficiency*, IEEE Transactions on Visualization and Computer Graphics
  15(6), aplicadas em RGB linear com severidade 1,0 (dicromacia);
* a distância entre cores é o ΔE*ab (CIE 1976) no espaço CIELAB, calculado
  sobre a cor simulada. Abaixo de ``CONFUSABLE_DELTA_E`` duas cores de
  legenda deixam de ser distinguíveis com segurança num mapa impresso.

O módulo é Python puro: pode ser testado sem QGIS e reutilizado pelo
regulamento (CART070) sobre a observação de qualquer layout.
"""

from __future__ import annotations

from typing import Iterable

#: Matrizes de Machado et al. (2009), severidade 1,0 — linhas R, G, B.
CVD_MATRICES: dict[str, tuple[tuple[float, float, float], ...]] = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}

#: ΔE*ab abaixo do qual duas cores de legenda são consideradas confundíveis.
#: Calibrado nos pares clássicos: vermelho/verde puros (#FF0000/#00A000) dão
#: ΔE 12 sob deuteranopia, vermelho-escuro/verde-escuro dão 4, laranja/lima
#: dão 7 — todos precisam ser acusados. Pares que diferem bastante em
#: luminosidade (#FF0000/#00FF00, ΔE 28) continuam distinguíveis e passam.
CONFUSABLE_DELTA_E = 15.0

#: Paleta de Okabe & Ito (2008), *Color Universal Design* — a mesma que a
#: composição aplica por padrão (symbology.py). Fica aqui para o regulamento
#: poder sugeri-la pelo nome.
OKABE_ITO = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#000000")


def parse_hex(colour: str) -> tuple[float, float, float] | None:
    """``"#RRGGBB"`` (ou ``"#RRGGBBAA"``) → (r, g, b) em 0..1; ``None`` se inválido."""
    text = str(colour or "").strip().lstrip("#")
    if len(text) not in (6, 8):
        return None
    try:
        r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None
    return (r / 255.0, g / 255.0, b / 255.0)


def _to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _to_srgb(channel: float) -> float:
    channel = min(1.0, max(0.0, channel))
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * (channel ** (1 / 2.4)) - 0.055


def simulate(rgb: tuple[float, float, float], deficiency: str) -> tuple[float, float, float]:
    """Cor sRGB (0..1) como a vê um dicromata do tipo pedido."""
    matrix = CVD_MATRICES[deficiency]
    linear = tuple(_to_linear(c) for c in rgb)
    out = []
    for row in matrix:
        out.append(_to_srgb(sum(coef * value for coef, value in zip(row, linear))))
    return (out[0], out[1], out[2])


def to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """sRGB (0..1) → CIELAB, iluminante D65 (observador 2°)."""
    r, g, b = (_to_linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """ΔE*ab (CIE 1976) entre duas cores sRGB (0..1)."""
    la, lb = to_lab(a), to_lab(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5


def hex_colour(rgb: tuple[float, float, float]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(round(min(1.0, max(0.0, c)) * 255)) for c in rgb))


def confusable_pairs(
    colours: Iterable[tuple[str, str]],
    threshold: float = CONFUSABLE_DELTA_E,
) -> list[dict[str, object]]:
    """Pares de cores que se confundem para algum dicromata.

    ``colours`` é uma sequência ``(nome, "#RRGGBB")`` — uma entrada por
    classe de legenda. Devolve um registro por par confundível, dizendo para
    qual deficiência, com o ΔE simulado e o ΔE para visão normal (para que o
    leitor saiba se o par já era ruim para todo mundo).
    """
    parsed = [(name, rgb) for name, rgb in ((n, parse_hex(h)) for n, h in colours) if rgb is not None]
    findings: list[dict[str, object]] = []
    for i, (name_a, rgb_a) in enumerate(parsed):
        for name_b, rgb_b in parsed[i + 1:]:
            normal = delta_e(rgb_a, rgb_b)
            worst = None
            for deficiency in CVD_MATRICES:
                simulated = delta_e(simulate(rgb_a, deficiency), simulate(rgb_b, deficiency))
                if simulated < threshold and (worst is None or simulated < worst[1]):
                    worst = (deficiency, simulated)
            if worst is not None:
                findings.append({
                    "a": name_a,
                    "b": name_b,
                    "deficiency": worst[0],
                    "delta_e_simulated": round(worst[1], 1),
                    "delta_e_normal": round(normal, 1),
                    "colours": (hex_colour(rgb_a), hex_colour(rgb_b)),
                })
    return findings
