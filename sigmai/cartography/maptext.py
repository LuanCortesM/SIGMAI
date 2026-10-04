"""Traduções dos textos que o próprio compositor escreve no mapa.

``compose_map`` já aceita título, subtítulo, legenda, fonte e autoria na
língua do usuário — mas até aqui tudo que o *compositor* escrevia sozinho na
moldura ("Fonte:", "Elaboração:", "Legenda", o título padrão quando ninguém
pedia um, "Painel A"/"Painel B", "Produzido com SIGMAI/QGIS", a letra de
reserva da rosa dos ventos) estava cravado em português. Um usuário que
conversa e pede tudo em japonês recebia de volta um mapa bilíngue: o conteúdo
dele em japonês, a moldura em português — o oposto do que se espera de uma
ferramenta que existe para conversar na língua do usuário.

Este módulo é a mesma ideia que ``sigmai/ui/strings.py`` já resolve para a
interface do plugin (uma tabela ``{língua: {chave: texto}}`` e uma função de
busca com queda para um padrão), aplicada aos textos que ``compose.py`` grava
no papel. As duas tabelas não se fundem porque servem propósitos diferentes:
``ui/strings.py`` é a interface do plugin (roda sempre em pt-BR/en, escolhida
pelo usuário no próprio painel); esta aqui é por-mapa, escolhida a cada
chamada de ``compose_map`` via o parâmetro ``map_language``, e cobre línguas
que a interface do plugin não precisa cobrir.

Duas garantias, deliberadas:

* **nunca estoura por falta de tradução.** Uma língua que a tabela não tem, ou
  uma chave que falta na língua pedida (tradução parcial, de propósito — é
  melhor uma língua a menos do que uma tradução errada num mapa que vai para
  uma dissertação) caem em português. ``compose.py`` nunca vê uma exceção
  daqui.
* **o código de língua é tratado com a mesma tolerância que o resto do
  pacote trata entrada escrita por um agente de IA** (ver ``params.py``):
  ``"pt"``, ``"pt_BR"``, ``"PT-br"``, ``"zh"``, ``"zh-CN"`` resolvem para a
  entrada certa da tabela, sem que ninguém precise escrever a grafia exata.
"""

from __future__ import annotations

#: A tabela em português é a "língua completa" de garantia: toda chave usada
#: em compose.py existe aqui, e é para onde ``maptext()`` cai quando a língua
#: pedida não tem a chave. As demais línguas só precisam declarar o que
#: realmente foi traduzido — não precisam repetir chaves que herdam do
#: fallback (ver ``norte_reserva`` abaixo: várias línguas usam a mesma letra
#: latina "N" que já é o padrão em português, e por isso simplesmente não
#: reescrevem a chave).
_PT_BR: dict[str, str] = {
    "fonte": "Fonte: ",
    "elaboracao": "Elaboração: ",
    "credito_ferramenta": "Produzido com SIGMAI/QGIS",
    "escala_prefixo": "Escala ",
    "escalas_por_painel": "Escalas indicadas em cada painel",
    "legenda_padrao": "Legenda",
    "painel_a": "Painel A",
    "painel_b": "Painel B",
    "titulo_padrao": "Mapa",
    "norte_reserva": "N",
    # Separador de milhar do denominador da escala ("1:250.000"). Um leitor
    # anglófono lê "1:250.000" como duzentos e cinquenta; o símbolo de
    # agrupamento é dado por língua a partir do Unicode CLDR (número
    # "group" de cada locale), a mesma fonte que Qt/QLocale e ICU usam.
    "separador_milhar": ".",
    # Nomes das camadas que add_context_annotations cria ("Divisa — Piauí"):
    # entram na legenda, então seguem a língua do mapa.
    "camada_divisa": "Divisa",
    "camada_nomes": "Nomes",
    "camada_rotulos_avulsos": "Rótulos avulsos",
}

#: Línguas cobertas com confiança. Cada uma é um dicionário parcial: só as
#: chaves com tradução verificada — o resto herda de ``_PT_BR`` via
#: ``maptext()``. Ver o relatório da correção para a lista de línguas
#: cogitadas e descartadas por incerteza (notavelmente hindi: o termo correto
#: para "legenda de mapa" em hindi não foi verificado com confiança
#: suficiente para entrar aqui).
MAP_TEXT: dict[str, dict[str, str]] = {
    "pt-BR": _PT_BR,
    "en": {
        "camada_divisa": "Border",
        "camada_nomes": "Names",
        "camada_rotulos_avulsos": "Extra labels",
        "fonte": "Source: ",
        "elaboracao": "Prepared by: ",
        "credito_ferramenta": "Produced with SIGMAI/QGIS",
        "escala_prefixo": "Scale ",
        "escalas_por_painel": "Scales shown on each panel",
        "legenda_padrao": "Legend",
        "painel_a": "Panel A",
        "painel_b": "Panel B",
        "titulo_padrao": "Map",
        "separador_milhar": ",",
    },
    "es": {
        "camada_divisa": "Límite",
        "camada_nomes": "Nombres",
        "camada_rotulos_avulsos": "Rótulos adicionales",
        "fonte": "Fuente: ",
        "elaboracao": "Elaborado por: ",
        "credito_ferramenta": "Producido con SIGMAI/QGIS",
        "escala_prefixo": "Escala ",
        "escalas_por_painel": "Escalas indicadas en cada panel",
        "legenda_padrao": "Leyenda",
        "painel_a": "Panel A",
        "painel_b": "Panel B",
        "titulo_padrao": "Mapa",
        "separador_milhar": ".",
    },
    "fr": {
        "camada_divisa": "Limite",
        "camada_nomes": "Noms",
        "camada_rotulos_avulsos": "Étiquettes supplémentaires",
        "fonte": "Source : ",
        "elaboracao": "Réalisation : ",
        "credito_ferramenta": "Produit avec SIGMAI/QGIS",
        "escala_prefixo": "Échelle ",
        "escalas_por_painel": "Échelles indiquées sur chaque panneau",
        "legenda_padrao": "Légende",
        "painel_a": "Panneau A",
        "painel_b": "Panneau B",
        "titulo_padrao": "Carte",
        "separador_milhar": "\u202f",
    },
    "de": {
        "camada_divisa": "Grenze",
        "camada_nomes": "Namen",
        "camada_rotulos_avulsos": "Zusätzliche Beschriftungen",
        "fonte": "Quelle: ",
        "elaboracao": "Erstellt von: ",
        "credito_ferramenta": "Erstellt mit SIGMAI/QGIS",
        "escala_prefixo": "Maßstab ",
        "escalas_por_painel": "Maßstäbe für jedes Kartenfeld angegeben",
        "legenda_padrao": "Legende",
        "painel_a": "Kartenfeld A",
        "painel_b": "Kartenfeld B",
        "titulo_padrao": "Karte",
        "separador_milhar": ".",
    },
    "it": {
        "camada_divisa": "Confine",
        "camada_nomes": "Nomi",
        "camada_rotulos_avulsos": "Etichette aggiuntive",
        "fonte": "Fonte: ",
        "elaboracao": "A cura di: ",
        "credito_ferramenta": "Prodotto con SIGMAI/QGIS",
        "escala_prefixo": "Scala ",
        "escalas_por_painel": "Scale indicate in ciascun pannello",
        "legenda_padrao": "Legenda",
        "painel_a": "Pannello A",
        "painel_b": "Pannello B",
        "titulo_padrao": "Mappa",
        "separador_milhar": ".",
    },
    "ja": {
        "camada_divisa": "境界",
        "camada_nomes": "名称",
        "camada_rotulos_avulsos": "追加ラベル",
        "fonte": "出典：",
        "elaboracao": "作成：",
        "credito_ferramenta": "SIGMAI/QGISで作成",
        "escala_prefixo": "縮尺 ",
        "escalas_por_painel": "各図に縮尺を表示",
        "legenda_padrao": "凡例",
        "painel_a": "パネルA",
        "painel_b": "パネルB",
        "titulo_padrao": "地図",
        "separador_milhar": ",",
        "norte_reserva": "北",
    },
    "zh-Hans": {
        "camada_divisa": "边界",
        "camada_nomes": "名称",
        "camada_rotulos_avulsos": "附加标注",
        "fonte": "来源：",
        "elaboracao": "编制：",
        "credito_ferramenta": "使用 SIGMAI/QGIS 制作",
        "escala_prefixo": "比例尺 ",
        "escalas_por_painel": "各图比例尺分别标注",
        "legenda_padrao": "图例",
        "painel_a": "图A",
        "painel_b": "图B",
        "titulo_padrao": "地图",
        "separador_milhar": ",",
        "norte_reserva": "北",
    },
    "zh-Hant": {
        "camada_divisa": "邊界",
        "camada_nomes": "名稱",
        "camada_rotulos_avulsos": "附加標註",
        "fonte": "來源：",
        "elaboracao": "編製：",
        "credito_ferramenta": "使用 SIGMAI/QGIS 製作",
        "escala_prefixo": "比例尺 ",
        "escalas_por_painel": "各圖比例尺分別標註",
        "legenda_padrao": "圖例",
        "painel_a": "圖A",
        "painel_b": "圖B",
        "titulo_padrao": "地圖",
        "separador_milhar": ",",
        "norte_reserva": "北",
    },
    "ko": {
        "camada_divisa": "경계",
        "camada_nomes": "이름",
        "camada_rotulos_avulsos": "추가 레이블",
        "fonte": "출처: ",
        "elaboracao": "작성: ",
        "credito_ferramenta": "SIGMAI/QGIS로 제작",
        "escala_prefixo": "축척 ",
        "escalas_por_painel": "각 패널에 축척 표시",
        "legenda_padrao": "범례",
        "painel_a": "패널 A",
        "painel_b": "패널 B",
        "titulo_padrao": "지도",
        "separador_milhar": ",",
    },
    "ru": {
        "camada_divisa": "Граница",
        "camada_nomes": "Названия",
        "camada_rotulos_avulsos": "Дополнительные подписи",
        "fonte": "Источник: ",
        "elaboracao": "Составитель: ",
        "credito_ferramenta": "Создано с помощью SIGMAI/QGIS",
        "escala_prefixo": "Масштаб ",
        "escalas_por_painel": "Масштаб указан на каждой панели",
        "legenda_padrao": "Легенда",
        "painel_a": "Панель А",
        "painel_b": "Панель Б",
        "titulo_padrao": "Карта",
        "separador_milhar": "\u00a0",
        "norte_reserva": "С",
    },
    # Árabe e hebraico: só o CONTEÚDO destes textos é traduzido aqui. A
    # direção de leitura (alinhamento do rodapé, ordem dos pedaços da linha
    # de crédito) é resolvida à parte em compose.py — ver RTL_LANGUAGES e o
    # defeito 3 no relatório da correção, inclusive o limite documentado ali
    # (QgsLayoutItemLabel/QgsTextFormat não expõem controle de direção de
    # texto nesta versão do QGIS).
    "ar": {
        "camada_divisa": "حدود",
        "camada_nomes": "أسماء",
        "camada_rotulos_avulsos": "تسميات إضافية",
        "fonte": "المصدر: ",
        "elaboracao": "الإعداد: ",
        "credito_ferramenta": "أُنتجت باستخدام SIGMAI/QGIS",
        "escala_prefixo": "مقياس الرسم ",
        "escalas_por_painel": "المقاييس موضحة في كل لوحة",
        "legenda_padrao": "وسيلة الإيضاح",
        "painel_a": "اللوحة أ",
        "painel_b": "اللوحة ب",
        "titulo_padrao": "خريطة",
        # O mapa escreve a escala com algarismos ocidentais (os mesmos da
        # grade); o CLDR dá "," para o sistema numérico latn em árabe — o
        # "٬" (U+066C) só acompanha os algarismos arábico-índicos.
        "separador_milhar": ",",
        "norte_reserva": "ش",
    },
    "he": {
        "camada_divisa": "גבול",
        "camada_nomes": "שמות",
        "camada_rotulos_avulsos": "תוויות נוספות",
        "fonte": "מקור: ",
        "elaboracao": "הכנה: ",
        "credito_ferramenta": "הופק באמצעות SIGMAI/QGIS",
        "escala_prefixo": "קנה מידה ",
        "escalas_por_painel": "קנה המידה מצוין בכל פאנל",
        "legenda_padrao": "מקרא",
        "painel_a": "פאנל א",
        "painel_b": "פאנל ב",
        "titulo_padrao": "מפה",
        "separador_milhar": ",",
        "norte_reserva": "צ",
    },
    "el": {
        "camada_divisa": "Όριο",
        "camada_nomes": "Ονόματα",
        "camada_rotulos_avulsos": "Επιπλέον ετικέτες",
        "fonte": "Πηγή: ",
        "elaboracao": "Σύνταξη: ",
        "credito_ferramenta": "Παρήχθη με SIGMAI/QGIS",
        "escala_prefixo": "Κλίμακα ",
        "escalas_por_painel": "Οι κλίμακες αναγράφονται σε κάθε πλαίσιο",
        "legenda_padrao": "Υπόμνημα",
        "painel_a": "Πλαίσιο Α",
        "painel_b": "Πλαίσιο Β",
        "titulo_padrao": "Χάρτης",
        "separador_milhar": ".",
        "norte_reserva": "Β",
    },
    "th": {
        "camada_divisa": "เขตแดน",
        "camada_nomes": "ชื่อ",
        "camada_rotulos_avulsos": "ป้ายกำกับเพิ่มเติม",
        "fonte": "แหล่งที่มา: ",
        "elaboracao": "จัดทำโดย: ",
        "credito_ferramenta": "ผลิตด้วย SIGMAI/QGIS",
        "escala_prefixo": "มาตราส่วน ",
        "escalas_por_painel": "แสดงมาตราส่วนในแต่ละแผง",
        "legenda_padrao": "คำอธิบายสัญลักษณ์",
        "painel_a": "แผง A",
        "painel_b": "แผง B",
        "titulo_padrao": "แผนที่",
        "separador_milhar": ",",
    },
}

#: Línguas em que o texto corre da direita para a esquerda. ``compose.py``
#: usa isto para alinhar o rodapé à direita e inverter a ordem dos pedaços da
#: linha de crédito (defeito 3) — não para nada neste módulo.
RTL_LANGUAGES = frozenset({"ar", "he"})

#: Índice em minúsculas de cada chave real de MAP_TEXT para si mesma. Existe
#: para reconhecer "zh-hans"/"ZH-HANS" e devolver a chave com a caixa exata
#: ("zh-Hans") que o dicionário usa — sem isto um agente que manda tudo em
#: minúsculas (comum) cairia sempre no fallback pt-BR mesmo pedindo uma
#: língua coberta.
_CANON_LOOKUP: dict[str, str] = {key.lower(): key for key in MAP_TEXT}

#: Grafias adicionais que claramente correspondem a uma língua coberta, mas
#: não são a própria chave nem resolvem só cortando a região (ex.: "pt" já
#: "zh" sozinho é ambíguo entre simplificado e tradicional, então precisa de
#: uma escolha explícita — chinês simplificado, por ser o mais falado, é o
#: padrão razoável quando só "zh" ou um código regional que não diz o script
#: chega. "pt" e "pt-PT" entram aqui, e não por corte de região: a chave
#: canônica é "pt-BR" (com região), então cortar "pt-BR" na primeira parte dá
#: "pt" — mas o inverso não é automático, ninguém deriva "pt-BR" a partir de
#: "pt" sozinho sem essa entrada explícita.
_ALIASES: dict[str, str] = {
    "pt": "pt-BR", "pt-pt": "pt-BR", "por": "pt-BR",
    "eng": "en", "en-us": "en", "en-gb": "en",
    "spa": "es",
    "fra": "fr", "fre": "fr",
    "deu": "de", "ger": "de",
    "ita": "it",
    "jp": "ja", "jpn": "ja",
    "zh": "zh-Hans", "zho": "zh-Hans", "chi": "zh-Hans",
    "zh-cn": "zh-Hans", "zh-sg": "zh-Hans", "zh-hans-cn": "zh-Hans",
    "zh-tw": "zh-Hant", "zh-hk": "zh-Hant", "zh-mo": "zh-Hant", "zh-hant-tw": "zh-Hant",
    "kor": "ko", "kr": "ko",
    "rus": "ru",
    "ara": "ar",
    "heb": "he", "iw": "he",
    "gre": "el", "grc": "el",
    "tha": "th",
}


def resolve_language(code: str) -> tuple[str, bool]:
    """Resolve um código de língua tolerante para a chave exata de MAP_TEXT.

    Devolve ``(chave, reconhecida)``. ``chave`` é sempre uma entrada válida de
    ``MAP_TEXT`` (nunca estoura, nunca devolve algo fora da tabela).
    ``reconhecida`` é ``False`` só quando o código não bateu com nada — nem a
    chave exata, nem um apelido, nem o prefixo antes do hífen/underscore — e
    por isso caiu no padrão pt-BR sem que o pedido tenha sido de fato
    entendido; ``compose.py`` usa isso para registrar uma nota, do mesmo jeito
    que ``as_flag`` registra quando converteu um valor em vez de recebê-lo já
    como bool (ver params.py). Ausência de código, string vazia, ou
    ``"pt-BR"``/``"pt"`` pedidos de propósito devolvem ``reconhecida=True``:
    não reconhecer nada é diferente de pedir português.
    """
    if not code or not isinstance(code, str):
        return "pt-BR", True
    normalized = code.strip().replace("_", "-").lower()
    if not normalized:
        return "pt-BR", True
    if normalized in _CANON_LOOKUP:
        return _CANON_LOOKUP[normalized], True
    if normalized in _ALIASES:
        return _ALIASES[normalized], True
    primary = normalized.split("-", 1)[0]
    if primary in _CANON_LOOKUP:
        return _CANON_LOOKUP[primary], True
    if primary in _ALIASES:
        return _ALIASES[primary], True
    return "pt-BR", False


def normalize_language(code: str) -> str:
    """Só a chave resolvida de :func:`resolve_language` — quando o chamador
    não precisa saber se o código foi reconhecido."""
    return resolve_language(code)[0]


def is_rtl(language: str) -> bool:
    """A língua (já resolvida ou não) corre da direita para a esquerda?"""
    return normalize_language(language) in RTL_LANGUAGES


def maptext(language: str, key: str) -> str:
    """Busca ``key`` na tabela de ``language``, com queda garantida para pt-BR.

    Três níveis de queda, do mais para o menos específico, e nenhum deles
    estoura: língua não reconhecida cai em pt-BR (``resolve_language`` já
    resolve isso); língua reconhecida mas sem essa chave especificamente
    (tradução parcial) cai em pt-BR só para aquela chave; e uma chave que nem
    pt-BR tem — o que não deveria acontecer, mas um erro de digitação na
    chamada não pode virar exceção no meio da composição de um mapa — devolve
    a própria chave, visível o bastante para apontar o bug em vez de quebrar
    silenciosamente.
    """
    resolved = normalize_language(language)
    table = MAP_TEXT.get(resolved) or _PT_BR
    return table.get(key) or _PT_BR.get(key, key)
