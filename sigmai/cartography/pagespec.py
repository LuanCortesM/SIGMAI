"""Geometria de página para layouts do QGIS.

O motor antigo do SIGMAI trazia as coordenadas dos itens em milímetros
absolutos, calculadas à mão para uma única página A4 em paisagem. Qualquer
outro formato — A3, retrato, um recorte para dissertação — colocava itens fora
da página sem nenhum aviso.

Aqui a página é um objeto explícito com área útil (a página menos as margens),
e os templates passam a descrever posições como frações dessa área útil. O
mesmo template serve para A5 e A0.
"""

from __future__ import annotations

import difflib
import math
from dataclasses import dataclass, field
from typing import Any


#: Formatos ISO 216 e norte-americanos em milímetros, sempre (largura, altura)
#: no sentido *retrato*. A orientação é aplicada depois, por ``resolve_page``.
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "B4": (250.0, 353.0),
    "B5": (176.0, 250.0),
    "LETTER": (215.9, 279.4),
    "LEGAL": (215.9, 355.6),
    "TABLOID": (279.4, 431.8),
}

#: Margem mínima defensável para impressão. Abaixo disso muitas impressoras
#: cortam conteúdo e a maioria das normas de trabalho acadêmico é violada.
MIN_MARGIN_MM = 5.0

ORIENTATIONS = ("portrait", "landscape")


# ---------------------------------------------------------------------------
# Vocabulário de orientação
# ---------------------------------------------------------------------------
#
# Um pedido de orientação não chega sempre em inglês nem sempre em português:
# a IA do outro lado da ferramenta responde na língua de quem está pedindo o
# mapa. A tabela abaixo é a fonte única de verdade — usada tanto para o texto
# solto de ``page`` (``"A4 paysage"``) quanto para o argumento ``orientation``
# passado sozinho (``orientation="Hochformat"``) — para que os dois caminhos
# nunca divirjam de novo.
#
# Cada termo foi conferido individualmente; onde a tradução não era certa o
# bastante, ficou de fora (é melhor cobrir menos línguas do que inventar uma
# palavra errada). Chaves com espaço são frases de mais de uma palavra e são
# comparadas à parte, contra a sequência de tokens, não por token isolado.
_ORIENTATION_VOCAB: dict[str, str] = {
    # Inglês — os dois termos literais que o motor sempre aceitou, mais dois
    # sinônimos informais comuns em pedidos de leigos.
    "portrait": "portrait",
    "landscape": "landscape",
    "horizontal": "landscape",
    "vertical": "portrait",
    "wide": "landscape",
    "tall": "portrait",

    # Português (Brasil e Portugal).
    "retrato": "portrait",
    "paisagem": "landscape",
    "ao alto": "portrait",
    "deitado": "landscape",
    "apaisado": "landscape",  # pt-PT e também comum em espanhol.

    # Espanhol. "horizontal"/"vertical" e "apaisado" já cobertos acima
    # (compartilhados com português).
    "tumbado": "landscape",  # regional (ex.: "hoja tumbada"), como "deitado" em pt.

    # Francês.
    "paysage": "landscape",
    "à l'italienne": "landscape",  # termo tipográfico francês clássico p/ paisagem.
    "à la française": "portrait",  # o par oposto, para retrato.

    # Italiano.
    "orizzontale": "landscape",
    "verticale": "portrait",
    "panoramico": "landscape",

    # Alemão — Querformat/Hochformat são os termos padrão de impressão; quer/hoch
    # são a forma curta do dia a dia ("imprimir quer" = imprimir em paisagem).
    "querformat": "landscape",
    "hochformat": "portrait",
    "quer": "landscape",
    "hoch": "portrait",

    # Japonês.
    "横": "landscape",
    "横向き": "landscape",
    "縦": "portrait",
    "縦向き": "portrait",

    # Chinês simplificado e tradicional.
    "横向": "landscape",
    "橫向": "landscape",
    "横式": "landscape",
    "纵向": "portrait",
    "縱向": "portrait",
    "直式": "portrait",

    # Coreano.
    "가로": "landscape",
    "세로": "portrait",

    # Russo — álbum/livro são os termos oficiais do Word em russo; os literais
    # горизонтальная/вертикальная também circulam.
    "альбомная": "landscape",
    "горизонтальная": "landscape",
    "книжная": "portrait",
    "вертикальная": "portrait",

    # Árabe.
    "أفقي": "landscape",
    "عمودي": "portrait",

    # Hebraico.
    "לרוחב": "landscape",
    "לאורך": "portrait",

    # Grego.
    "οριζόντιος": "landscape",
    "κατακόρυφος": "portrait",

    # Tailandês.
    "แนวนอน": "landscape",
    "แนวตั้ง": "portrait",

    # Hindi.
    "अनुप्रस्थ": "landscape",
    "ऊर्ध्वाधर": "portrait",
}

#: Só os caracteres latinos acentuados que aparecem no vocabulário acima.
#: Aplicado depois de ``.lower()``; alfabetos sem acento latino (grego,
#: cirílico, CJK, árabe, hebraico, tailandês, devanágari) passam intactos —
#: só a caixa é normalizada, o que não muda o sentido dessas escritas. É
#: assim que a comparação "sem depender de acento" fica limitada às línguas
#: em que isso é uma conveniência de digitação real (pt/es/fr/it/de).
_LATIN_ACCENTS = str.maketrans(
    "áàâãäåéèêëíìîïóòôõöúùûüçñý",
    "aaaaaaeeeeiiiiooooouuuucny",
)


def _fold(text: str) -> str:
    """Minúsculas + acentos latinos removidos, para comparar termos de
    orientação sem depender de maiúsculas nem, nas línguas que permitem, de
    acentuação."""
    return text.lower().translate(_LATIN_ACCENTS)


_ORIENTATION_TERMS: dict[str, str] = {
    _fold(term): value for term, value in _ORIENTATION_VOCAB.items() if " " not in term
}
_MULTIWORD_ORIENTATION_TERMS: dict[str, str] = {
    _fold(term): value for term, value in _ORIENTATION_VOCAB.items() if " " in term
}


def _extract_orientation(text: str) -> tuple[str | None, list[str]]:
    """Procura uma orientação dentro de uma string livre.

    Usada tanto para o texto de ``page`` (que também carrega o tamanho, ex.
    ``"A4 paysage"``) quanto para o argumento ``orientation`` sozinho (que às
    vezes chega como frase, ex. ``"portrait haut"``). Primeiro tenta as
    frases de mais de uma palavra (``"à l'italienne"``, ``"ao alto"``); o que
    sobrar é comparado palavra a palavra contra o vocabulário de um só termo.

    Devolve ``(orientação_ou_None, tokens_que_sobraram)`` — quem chamou usa o
    que sobrou para procurar outra coisa (o tamanho da página) ou para
    reportar como desconhecido.
    """
    words = text.replace("-", " ").replace("_", " ").split()
    if not words:
        return None, []
    folded = [_fold(w) for w in words]
    consumed = [False] * len(words)
    found: str | None = None

    # Frases mais longas primeiro: senão uma palavra solta da frase (como o
    # "à" de "à l'italienne") poderia ficar marcada como desconhecida antes
    # de a frase inteira ser reconhecida.
    for phrase in sorted(_MULTIWORD_ORIENTATION_TERMS, key=lambda p: -len(p.split())):
        phrase_words = phrase.split()
        n = len(phrase_words)
        for start in range(len(words) - n + 1):
            if any(consumed[start:start + n]):
                continue
            if folded[start:start + n] == phrase_words:
                if found is None:
                    found = _MULTIWORD_ORIENTATION_TERMS[phrase]
                for i in range(start, start + n):
                    consumed[i] = True
                break

    remaining: list[str] = []
    for word, word_folded, used in zip(words, folded, consumed):
        if used:
            continue
        hit = _ORIENTATION_TERMS.get(word_folded)
        if hit is not None:
            if found is None:
                found = hit
            continue
        remaining.append(word)

    return found, remaining


def _orientation_not_recognized_message(value: str) -> str:
    near = difflib.get_close_matches(_fold(value.strip()), list(_ORIENTATION_TERMS), n=1, cutoff=0.6)
    suggestion = f" Você quis dizer \"{near[0]}\"?" if near else ""
    return (
        f"Orientação não reconhecida: '{value}'.{suggestion} A orientação aceita termos em várias "
        "línguas — por exemplo \"portrait\"/\"landscape\", \"retrato\"/\"paisagem\" ou "
        "\"Hochformat\"/\"Querformat\"."
    )


def _resolve_orientation_value(value: Any, *, strict: bool, source: str) -> str | None:
    """Reconhece uma orientação vinda de um valor solto: o argumento
    ``orientation`` ou o campo ``orientation`` de um dicionário ``page``.

    Um tipo que não é texto (``123``, ``["landscape"]``) nunca teve uma
    leitura válida — isso sempre vira recusa, em qualquer modo, porque não é
    uma questão de tolerância e sim de a entrada não fazer sentido. Uma
    string não reconhecida, por outro lado, segue a mesma regra do resto do
    arquivo: recusa em modo estrito, ``None`` (cai no padrão) em modo
    tolerante.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"{source} precisa ser texto (por exemplo \"portrait\" ou \"paisagem\"); "
            f"recebido {type(value).__name__}."
        )
    if not value.strip():
        return None
    found, _ = _extract_orientation(value)
    if found is not None:
        return found
    if strict:
        raise ValueError(_orientation_not_recognized_message(value))
    return None


def _raise_unknown_page_name(name: str) -> None:
    near = difflib.get_close_matches(name.upper(), list(PAGE_SIZES), n=1, cutoff=0.6)
    suggestion = f" Você quis dizer '{near[0]}'?" if near else ""
    sizes = ", ".join(sorted(PAGE_SIZES))
    raise ValueError(f"Formato de página não reconhecido: '{name}'.{suggestion} Formatos aceitos: {sizes}.")


def _coerce_float(value: Any, field_name: str) -> float:
    """Converte um valor solto para ``float``, com mensagem para humano em
    vez do texto cru que ``float()`` levanta (ex. ``could not convert string
    to float: '300mm'``)."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} não pode ser um booleano.")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"{field_name} precisa ser um número; recebido '{value}'.") from None
    else:
        raise ValueError(f"{field_name} precisa ser um número; recebido {type(value).__name__}.")
    if not math.isfinite(number):
        raise ValueError(f"{field_name} precisa ser um número finito; recebido {value!r}.")
    return number


def _to_positive_float(value: Any, field_name: str) -> float:
    number = _coerce_float(value, field_name)
    if number <= 0:
        raise ValueError(f"{field_name} precisa ser positivo; recebido {value!r}.")
    return number


def _to_nonnegative_float(value: Any, field_name: str) -> float:
    number = _coerce_float(value, field_name)
    if number < 0:
        raise ValueError(f"{field_name} não pode ser negativo; recebido {value!r}.")
    return number


@dataclass(frozen=True)
class PageSpec:
    """Uma página de layout com sua área útil já resolvida."""

    name: str
    width_mm: float
    height_mm: float
    margin_top_mm: float = 10.0
    margin_right_mm: float = 10.0
    margin_bottom_mm: float = 10.0
    margin_left_mm: float = 10.0
    orientation: str = "landscape"

    # ---- área útil -----------------------------------------------------
    @property
    def content_x_mm(self) -> float:
        return self.margin_left_mm

    @property
    def content_y_mm(self) -> float:
        return self.margin_top_mm

    @property
    def content_width_mm(self) -> float:
        return self.width_mm - self.margin_left_mm - self.margin_right_mm

    @property
    def content_height_mm(self) -> float:
        return self.height_mm - self.margin_top_mm - self.margin_bottom_mm

    @property
    def aspect(self) -> float:
        return self.width_mm / self.height_mm if self.height_mm else 1.0

    def contains(self, x: float, y: float, width: float, height: float, tolerance: float = 0.01) -> bool:
        """A caixa cabe dentro da página (não da área útil)?"""
        return (
            x >= -tolerance
            and y >= -tolerance
            and x + width <= self.width_mm + tolerance
            and y + height <= self.height_mm + tolerance
        )

    def within_margins(self, x: float, y: float, width: float, height: float, tolerance: float = 0.01) -> bool:
        """A caixa respeita as margens da página?"""
        return (
            x >= self.content_x_mm - tolerance
            and y >= self.content_y_mm - tolerance
            and x + width <= self.content_x_mm + self.content_width_mm + tolerance
            and y + height <= self.content_y_mm + self.content_height_mm + tolerance
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "orientation": self.orientation,
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
            "margins_mm": {
                "top": self.margin_top_mm,
                "right": self.margin_right_mm,
                "bottom": self.margin_bottom_mm,
                "left": self.margin_left_mm,
            },
            "content_area_mm": {
                "x": round(self.content_x_mm, 2),
                "y": round(self.content_y_mm, 2),
                "width": round(self.content_width_mm, 2),
                "height": round(self.content_height_mm, 2),
            },
        }


def resolve_page(
    page: str | dict[str, Any] | PageSpec | None = None,
    orientation: str | None = None,
    margin_mm: float | dict[str, float] | list[float] | None = None,
    strict: bool = False,
) -> PageSpec:
    """Constrói um :class:`PageSpec` a partir de entrada tolerante.

    Aceita ``"A3"``, ``"a3 portrait"``, ``{"width_mm": 300, "height_mm": 200}``
    ou um ``PageSpec`` já pronto. Entrada desconhecida cai em A4 paisagem, que
    é o que ``QgsPrintLayout.initializeDefaults()`` cria.

    ``orientation`` (sozinho ou dentro de ``page``) aceita termos em várias
    línguas — veja ``_ORIENTATION_VOCAB`` — comparados sem diferenciar
    maiúsculas e, nas línguas latinas, sem depender de acento.

    Com ``strict=True`` a entrada desconhecida vira ``ValueError`` em vez de cair
    no padrão. É o modo usado quando quem pediu foi um assistente: aceitar em
    silêncio um formato que não existe entrega uma página diferente da pedida.
    Nesse modo, ``page`` também precisa ser do tipo certo (texto, dicionário
    ou ``PageSpec``) e, se for dicionário com ``width_mm``/``height_mm``, os
    dois campos precisam vir juntos e serem números positivos.

    Independente do modo, uma combinação de margens que não deixa área útil
    (margens somando mais do que a largura ou a altura da página) é sempre
    recusada — não existe leitura tolerante para uma página sem espaço para
    nada.
    """
    if isinstance(page, PageSpec):
        return page

    width = height = None
    name = "A4"
    resolved_orientation = _resolve_orientation_value(orientation, strict=strict, source="orientation")

    if page is not None and not isinstance(page, (str, dict)):
        if strict:
            raise ValueError(
                "page precisa ser texto (por exemplo \"A4 paisagem\"), um dicionário com "
                "'name'/'size' ou 'width_mm'+'height_mm', ou pode ser omitido; recebido "
                f"{type(page).__name__}."
            )
        # Tolerante: um tipo que a ferramenta não sabe interpretar cai no
        # padrão A4, do mesmo jeito que um texto desconhecido também cairia.
    elif isinstance(page, dict):
        has_width = "width_mm" in page and page["width_mm"] is not None
        has_height = "height_mm" in page and page["height_mm"] is not None
        if has_width and has_height:
            width = _to_positive_float(page["width_mm"], "page['width_mm']")
            height = _to_positive_float(page["height_mm"], "page['height_mm']")
            name = str(page.get("name", "custom"))
        elif has_width or has_height:
            if strict:
                faltou = "height_mm" if has_width else "width_mm"
                raise ValueError(
                    f"page com 'width_mm' precisa também de 'height_mm' (e vice-versa); faltou '{faltou}'."
                )
            # Tolerante: a metade solta do par é ignorada, cai no name/size.
            name = str(page.get("name", page.get("size", "A4")))
        else:
            name = str(page.get("name", page.get("size", "A4")))
            if strict and name.upper() not in PAGE_SIZES:
                _raise_unknown_page_name(name)
        if resolved_orientation is None:
            resolved_orientation = _resolve_orientation_value(
                page.get("orientation"), strict=strict, source="page['orientation']"
            )
        if margin_mm is None:
            margin_mm = page.get("margin_mm", page.get("margins_mm"))
    elif isinstance(page, str) and page.strip():
        orient_found, remaining_tokens = _extract_orientation(page)
        if resolved_orientation is None and orient_found is not None:
            resolved_orientation = orient_found
        unknown_tokens: list[str] = []
        matched_size = False
        for token in remaining_tokens:
            if token.upper() in PAGE_SIZES:
                name = token.upper()
                matched_size = True
            else:
                unknown_tokens.append(token)
        if strict and (unknown_tokens or not matched_size):
            offending = unknown_tokens or [page.strip()]
            sizes = ", ".join(sorted(PAGE_SIZES))
            hints = []
            for token in offending:
                near_size = difflib.get_close_matches(token.upper(), list(PAGE_SIZES), n=1, cutoff=0.6)
                if near_size:
                    hints.append(f"{token} -> {near_size[0]}")
                    continue
                near_orientation = difflib.get_close_matches(
                    _fold(token), list(_ORIENTATION_TERMS), n=1, cutoff=0.6
                )
                if near_orientation:
                    hints.append(f"{token} -> {near_orientation[0]}")
            suggestion = f" Você quis dizer {'; '.join(hints)}?" if hints else ""
            raise ValueError(
                f"Formato de página não reconhecido: {', '.join(offending)}."
                f"{suggestion} Formatos aceitos: {sizes}."
                " A orientação aceita termos em várias línguas — por exemplo \"paisagem\"/\"retrato\", "
                "\"landscape\"/\"portrait\" ou \"Querformat\"/\"Hochformat\"."
            )

    if width is None or height is None:
        width, height = PAGE_SIZES.get(name.upper(), PAGE_SIZES["A4"])
        name = name.upper() if name.upper() in PAGE_SIZES else name

    final_orientation = (resolved_orientation or "landscape").lower()
    if final_orientation not in ORIENTATIONS:
        final_orientation = "landscape"

    # PAGE_SIZES está em retrato; troca os eixos para paisagem.
    if final_orientation == "landscape" and height > width:
        width, height = height, width
    elif final_orientation == "portrait" and width > height:
        width, height = height, width

    top, right, bottom, left = _resolve_margins(margin_mm, width, height)

    content_width = width - left - right
    content_height = height - top - bottom
    if content_width <= 0 or content_height <= 0:
        # Uma margem que engole a página inteira não é uma questão de
        # interpretação — não existe leitura tolerante possível para uma
        # área útil negativa. Por isso a checagem vale nos dois modos.
        raise ValueError(
            f"As margens pedidas (topo {top:g}, direita {right:g}, baixo {bottom:g}, "
            f"esquerda {left:g} mm) não cabem numa página {name} de {width:g}x{height:g} mm: "
            f"sobrariam {content_width:g}x{content_height:g} mm de área útil. Reduza as margens "
            "ou use uma página maior."
        )

    return PageSpec(
        name=name,
        width_mm=width,
        height_mm=height,
        margin_top_mm=top,
        margin_right_mm=right,
        margin_bottom_mm=bottom,
        margin_left_mm=left,
        orientation=final_orientation,
    )


def _resolve_margins(
    margin_mm: float | dict[str, float] | list[float] | None,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    """Margens padrão proporcionais ao formato, com piso de impressão.

    Aceita um número (mesma margem nos quatro lados), um dicionário com
    ``top``/``right``/``bottom``/``left`` (e um ``all`` como padrão dos que
    faltarem), ou uma lista de exatamente 4 números na ordem CSS
    topo/direita/baixo/esquerda (``[10, 15, 10, 15]``) — a mesma convenção de
    CSS ``margin: top right bottom left``, escolhida por ser a ordem que mais
    gente já viu antes. Qualquer outro formato, ou um valor que não dá para
    ler como número, é recusado com uma frase para humano em vez do erro cru
    do Python.
    """
    if margin_mm is None:
        # Uma folha A0 com margem de 10 mm parece um pôster mal cortado; uma
        # A5 com margem de 25 mm não sobra mapa. Escala com a menor dimensão.
        smaller = min(width, height)
        value = max(MIN_MARGIN_MM, round(smaller * 0.048, 1))
        return (value, value, value, value)

    if isinstance(margin_mm, dict):
        default = _to_nonnegative_float(margin_mm.get("all", 10.0), "margin_mm['all']")
        return (
            max(MIN_MARGIN_MM, _to_nonnegative_float(margin_mm.get("top", default), "margin_mm['top']")),
            max(MIN_MARGIN_MM, _to_nonnegative_float(margin_mm.get("right", default), "margin_mm['right']")),
            max(MIN_MARGIN_MM, _to_nonnegative_float(margin_mm.get("bottom", default), "margin_mm['bottom']")),
            max(MIN_MARGIN_MM, _to_nonnegative_float(margin_mm.get("left", default), "margin_mm['left']")),
        )

    if isinstance(margin_mm, (list, tuple)):
        if len(margin_mm) != 4:
            raise ValueError(
                "margin_mm como lista precisa de exatamente 4 números, na ordem CSS "
                f"topo/direita/baixo/esquerda (ex.: [10, 15, 10, 15]); recebido {len(margin_mm)} valores."
            )
        top, right, bottom, left = (
            _to_nonnegative_float(v, f"margin_mm[{i}]") for i, v in enumerate(margin_mm)
        )
        return (
            max(MIN_MARGIN_MM, top),
            max(MIN_MARGIN_MM, right),
            max(MIN_MARGIN_MM, bottom),
            max(MIN_MARGIN_MM, left),
        )

    if isinstance(margin_mm, bool):
        raise ValueError("margin_mm não pode ser um booleano; use um número em milímetros.")

    if isinstance(margin_mm, (int, float, str)):
        value = max(MIN_MARGIN_MM, _to_nonnegative_float(margin_mm, "margin_mm"))
        return (value, value, value, value)

    raise ValueError(
        f"margin_mm não reconhecido (tipo {type(margin_mm).__name__}). Aceita um número em milímetros, "
        "um dicionário com top/right/bottom/left (ou 'all'), ou uma lista de 4 números na ordem CSS "
        "topo/direita/baixo/esquerda."
    )
