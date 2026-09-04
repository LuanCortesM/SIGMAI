"""Ajusta um texto gerado à largura do retângulo do layout que vai recebê-lo.

``QgsLayoutItemLabel`` não recusa nem quebra texto largo demais para a caixa
reservada: ele simplesmente desenha a linha inteira, que sai da caixa para os
dois lados e é cortada pela borda da página. Um título chinês de ~90
caracteres numa A4 paisagem some no meio — o começo e o fim ficam fora do
papel — e isso acontece **em silêncio**: a composição termina com sucesso, a
auditoria não tem como medir "texto cortado", e o agente de IA não teria como
saber que algo deu errado.

A causa não é a escrita: chinês, japonês e tailandês escrevem sem espaço
entre palavras, então o único lugar onde o QGIS sabe quebrar linha — um
espaço em branco — nunca aparece. Um título em português sem espaços sofre
exatamente o mesmo corte (é o cenário ``stress-pt-nospace`` da bancada de
escritas, que prova isso).

Este módulo resolve com três alavancas, que ``fit_text`` combina em ordem —
tenta cada tamanho de fonte, do original até o piso, e em cada um tenta
primeiro uma linha só e depois quebrar:

1. **Quebrar em pontos seguros.** Para as escritas em que separar dois
   caracteres adjacentes é tipograficamente correto (han, kana, hangul,
   tailandês — ver ``_BREAKABLE_RANGES``), qualquer par de caracteres é um
   ponto de quebra válido, contanto que não corte uma marca combinante do seu
   caractere base (ver ``_is_combining``: é isso que protege o dakuten
   japonês em forma NFD e os sinais de tom/vogal tailandeses de saírem
   separados do que modificam). Devanágari fica de fora de propósito: uma
   consoante conjunta ligada por virama não tem uma regra simples de "aqui é
   seguro cortar", e arriscar errado é pior do que não tentar — a mesma
   escolha que o regulamento deste defeito pede explicitamente.
2. **Reduzir o corpo da fonte**, com piso: nunca abaixo de
   ``MIN_PRINT_FONT_PT`` (regra CART044 do regulamento — abaixo disso o texto
   já reprova em qualquer revisão editorial, então respeitar o piso aqui evita
   resolver um defeito criando outro).
3. **Recusar**, só quando nem reduzir até o piso nem quebrar nos pontos
   seguros disponíveis resolve — um único "token" sem nenhum ponto de quebra
   (a palavra portuguesa sem espaços) que continua largo demais mesmo a
   6pt. A recusa diz quantos caracteres cabem, para a mensagem ser acionável
   e não um "não" sem saída.

Português sem espaço nenhum (o cenário de controle) normalmente cabe só
reduzindo a fonte — não há onde quebrar uma palavra em português com
segurança, e este módulo não inventa uma: quebrar no meio de uma palavra
latina não é a mesma coisa que quebrar entre dois ideogramas.

Python puro, sem PyQGIS: a medição real de largura (que depende de fonte e
DPI) é injetada como ``measure_fn`` — quem mede é ``compose.py``, que tem o
``QgsRenderContext`` disponível. Isso deixa a lógica de quebra/encolhimento
testável em CI com uma medição sintética, como o resto do pacote (ver
``scaling.py``, ``layoutgrid.py``).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Callable

from .rulebook import MIN_PRINT_FONT_PT

#: (texto, tamanho em pt) -> largura em mm, para o tamanho de fonte e (quando
#: aplicável) negrito já decididos por quem chama ``fit_text``.
MeasureFn = Callable[[str, float], float]

#: Alias público: código que só precisa do piso de fonte não precisa saber
#: que ele mora em rulebook.py (CART044) por baixo.
MIN_FONT_PT = MIN_PRINT_FONT_PT

#: A medição de largura (QFontMetricsF/QgsTextRenderer por baixo, em
#: compose.py) é uma estimativa: hinting e antialiasing variam um pouco entre
#: a resolução usada para medir e a resolução final de exportação. Esta
#: margem evita que um texto que "quase cabe" na medição estoure por um
#: milímetro no PNG/PDF de verdade.
_SAFETY = 0.99


class TextTooLongError(ValueError):
    """Nem reduzir a fonte até o piso nem quebrar nos pontos seguros coube."""

    def __init__(self, message: str, max_chars: int) -> None:
        super().__init__(message)
        #: Quantos caracteres (grafemas — ver ``_cluster_boundaries``) do
        #: texto pedido cabem na largura disponível, no piso de fonte. É o
        #: número que a mensagem de recusa cita, para a recusa ser acionável.
        self.max_chars = max_chars


@dataclass(frozen=True)
class FitResult:
    """O texto final a desenhar, já dividido em linhas, e o que mudou."""

    lines: tuple[str, ...]
    font_pt: float
    shrunk: bool
    wrapped: bool

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _is_combining(ch: str) -> bool:
    """``ch`` é uma marca que se desenha grudada no caractere anterior?

    Cobre tanto o mecanismo formal do Unicode (classe de combinação, usada
    por acentos que já vêm prontos) quanto a categoria geral Mn/Mc/Me, que é
    o que realmente marca o dakuten japonês em forma NFD e os sinais de
    vogal/tom tailandeses — a checagem por classe de combinação sozinha não
    cobre todos esses.
    """
    return unicodedata.combining(ch) != 0 or unicodedata.category(ch) in ("Mn", "Mc", "Me")


#: Blocos Unicode em que quebrar entre dois caracteres adjacentes — sem
#: espaço nenhum entre eles — é tipograficamente aceito: ideogramas han, kana,
#: hangul e o alfabeto tailandês formam "palavras" sem espaço, e a convenção
#: dessas escritas já é quebrar em qualquer ponto quando a linha não cabe
#: inteira. Fica de fora, de propósito, qualquer escrita cuja regra de quebra
#: segura dependa de um dicionário de palavras (não é o caso de nenhuma das
#: acima) ou de reconhecer conjuntas complexas (devanágari e afins — ver o
#: docstring do módulo).
_BREAKABLE_RANGES: tuple[tuple[int, int], ...] = (
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x3000, 0x303F),  # Pontuação CJK
    (0xFF00, 0xFFEF),  # Formas de largura total
    (0xAC00, 0xD7A3),  # Hangul (sílabas precompostas)
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x0E00, 0x0E7F),  # Tailandês
)


def _is_breakable_script(ch: str) -> bool:
    cp = ord(ch)
    return any(low <= cp <= high for low, high in _BREAKABLE_RANGES)


#: "kinsoku shori" básico: uma linha não deveria começar com fechamento ou
#: pontuação de continuação, nem terminar com abertura. Sem isto a quebra
#: continua segura (nenhuma marca combinante é separada do que modifica), só
#: fica visualmente estranha — por isso é uma lista pequena e best-effort, não
#: uma implementação completa da regra.
_NO_LINE_START = set("、。，,．.！!？?：:；;）)」』】”’")
_NO_LINE_END = set("（(「『【“‘")


def _candidate_breaks(text: str) -> list[int]:
    """Índices ``i`` tais que ``text[:i] + "\\n" + text[i:]`` é uma quebra segura.

    Sempre inclui limites de espaço em branco — funciona para qualquer
    escrita, inclusive as que não estão em ``_BREAKABLE_RANGES`` (árabe,
    devanágari, latim...). Para as escritas de ``_BREAKABLE_RANGES`` também
    inclui o limite depois de qualquer caractere dessas escritas, contanto que
    o caractere seguinte não seja uma marca combinante (o que empurraria a
    quebra para depois do fim do agrupamento seguinte, não para dentro dele).
    """
    breaks: list[int] = []
    n = len(text)
    for i in range(1, n):
        prev_ch, next_ch = text[i - 1], text[i]
        if _is_combining(next_ch):
            continue  # nunca separa uma marca combinante do seu caractere base
        if next_ch in _NO_LINE_START or prev_ch in _NO_LINE_END:
            continue
        if prev_ch.isspace() or next_ch.isspace():
            breaks.append(i)
        elif _is_breakable_script(prev_ch):
            breaks.append(i)
    return breaks


def _cluster_boundaries(text: str) -> list[int]:
    """Limites de "grafema": caractere base + toda marca combinante seguinte.

    Usado só por ``_max_chars_fitting``, para a contagem de "quantos
    caracteres cabem" da mensagem de recusa não cortar um agrupamento ao
    meio — cortar bem no meio dele para "contar" mais um caractere seria
    reportar um número que, se usado ao pé da letra, produziria exatamente o
    corte inseguro que este módulo existe para evitar.
    """
    n = len(text)
    bounds = [0]
    i = 0
    while i < n:
        i += 1
        while i < n and _is_combining(text[i]):
            i += 1
        bounds.append(i)
    return bounds


def _measure(measure_fn: MeasureFn, text: str, font_pt: float) -> float:
    stripped = text.strip()
    return float(measure_fn(stripped, font_pt)) if stripped else 0.0


def _wrap_at(text: str, font_pt: float, max_width_mm: float, measure_fn: MeasureFn) -> list[str] | None:
    """Quebra gulosa nos pontos de ``_candidate_breaks``, a um tamanho de fonte fixo.

    Devolve ``None`` quando, mesmo depois de quebrar em todos os pontos
    disponíveis, algum trecho entre duas quebras consecutivas continua largo
    demais — sinal de que só um tamanho de fonte menor resolve, não mais
    quebra (é o caso do cenário de controle em português sem espaços: não há
    nenhum ponto de quebra, então o "trecho" é o texto inteiro).
    """
    limit = max_width_mm * _SAFETY
    if _measure(measure_fn, text, font_pt) <= limit:
        return [text.strip()]

    boundaries = _candidate_breaks(text)
    if not boundaries:
        return None
    boundaries = boundaries + [len(text)]

    lines: list[str] = []
    start = 0
    while start < len(text):
        best = None
        for boundary in boundaries:
            if boundary <= start:
                continue
            # A largura de text[start:boundary] só cresce conforme boundary
            # aumenta (mais caracteres), então parar no primeiro que não cabe
            # é seguro: nenhum boundary maior vai caber depois dele.
            if _measure(measure_fn, text[start:boundary], font_pt) <= limit:
                best = boundary
            else:
                break
        if best is None:
            # Nem o primeiro pedaço até o próximo ponto de quebra cabe: este
            # tamanho de fonte não é viável para este texto, mesmo quebrando.
            return None
        line = text[start:best].strip()
        if line:
            lines.append(line)
        start = best
    return lines or [text.strip()]


def _max_chars_fitting(text: str, font_pt: float, max_width_mm: float, measure_fn: MeasureFn) -> int:
    """Quantos "caracteres" (grafemas) do início de ``text`` cabem, no piso de fonte."""
    bounds = _cluster_boundaries(text)
    limit = max_width_mm * _SAFETY
    lo, hi, best = 0, len(bounds) - 1, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _measure(measure_fn, text[: bounds[mid]], font_pt) <= limit:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def fit_text(
    text: str,
    max_width_mm: float,
    base_font_pt: float,
    measure_fn: MeasureFn,
    *,
    min_font_pt: float = MIN_FONT_PT,
    font_step_pt: float = 0.5,
) -> FitResult:
    """Encontra o maior tamanho de fonte (com ou sem quebra) que cabe.

    Para cada tamanho de fonte, do ``base_font_pt`` até ``min_font_pt`` em
    passos de ``font_step_pt``, tenta primeiro uma linha só e depois quebrar
    nos pontos seguros disponíveis; devolve o primeiro que couber — ou seja,
    o resultado visualmente menos alterado que ainda cabe: mesma fonte sem
    quebra é preferido a mesma fonte quebrada, que é preferido a uma fonte
    menor. Levanta ``TextTooLongError`` (com quantos caracteres cabem, no
    piso) só quando nada nessa faixa inteira coube.
    """
    stripped = text.strip()
    if not stripped:
        return FitResult(lines=("",), font_pt=base_font_pt, shrunk=False, wrapped=False)

    font_pt = float(base_font_pt)
    min_font_pt = float(min_font_pt)
    while True:
        wrapped_lines = _wrap_at(stripped, font_pt, max_width_mm, measure_fn)
        if wrapped_lines is not None:
            shrunk = font_pt < base_font_pt - 1e-9
            wrapped = len(wrapped_lines) > 1
            return FitResult(tuple(wrapped_lines), font_pt, shrunk, wrapped)
        if font_pt <= min_font_pt + 1e-9:
            break
        font_pt = max(min_font_pt, font_pt - font_step_pt)

    max_chars = _max_chars_fitting(stripped, min_font_pt, max_width_mm, measure_fn)
    raise TextTooLongError(
        f"o texto não cabe no espaço reservado ({max_width_mm:.0f} mm de largura) nem reduzindo "
        f"a fonte até o piso de {min_font_pt:g}pt (regra CART044) nem quebrando linha nos pontos "
        f"de quebra seguros disponíveis. Nesse tamanho de fonte, cerca de {max_chars} caracteres "
        "cabem nessa largura.",
        max_chars,
    )
