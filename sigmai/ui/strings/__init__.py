"""Textos da interface do painel, em nove línguas.

Uma tabela por língua, um módulo por tabela (``pt_br.py``, ``en.py``, …), e
:func:`translate` como único ponto de busca. ``LANGUAGES`` é a lista que o
seletor do cabeçalho mostra, com o nome de cada língua escrito nela mesma —
quem não lê português precisa achar a sua língua sem ler português.

Duas garantias:

* **toda chave existe em toda língua.** ``tests/test_ui_languages.py`` varre
  as nove tabelas contra a de referência (pt-BR), inclusive os marcadores de
  formatação (``{host}``, ``{port}``…), para que nenhuma língua devolva a
  chave crua nem estoure num ``str.format``. A queda para inglês e depois
  para português existe por robustez, não por preguiça de traduzir.
* **o código de língua é tolerante**, como em ``cartography/maptext.py``:
  ``"PT"``, ``"pt_BR"``, ``"en-US"``, ``"zh-CN"``, ``"jp"`` resolvem para a
  tabela certa; um código desconhecido cai em pt-BR.

Os textos que o *compositor* escreve no papel dos mapas (``Fonte:``,
``Legenda``…) vivem em ``cartography/maptext.py`` e cobrem quinze línguas —
esta tabela é só a interface do plugin.
"""

from __future__ import annotations

from .de import STRINGS as _DE
from .en import STRINGS as _EN
from .es import STRINGS as _ES
from .fr import STRINGS as _FR
from .it import STRINGS as _IT
from .ja import STRINGS as _JA
from .pt_br import STRINGS as _PT_BR
from .zh_hans import STRINGS as _ZH_HANS
from .zh_hant import STRINGS as _ZH_HANT

DEFAULT_LANGUAGE = "pt-BR"

STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": _PT_BR,
    "en": _EN,
    "es": _ES,
    "fr": _FR,
    "de": _DE,
    "it": _IT,
    "ja": _JA,
    "zh-Hans": _ZH_HANS,
    "zh-Hant": _ZH_HANT,
}

#: (código, nome na própria língua) na ordem em que o seletor os mostra.
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("pt-BR", "Português (Brasil)"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("ja", "日本語"),
    ("zh-Hans", "简体中文"),
    ("zh-Hant", "繁體中文"),
)

_CANON = {code.lower(): code for code, _ in LANGUAGES}
_ALIASES = {
    "pt": "pt-BR", "pt-pt": "pt-BR", "por": "pt-BR",
    "eng": "en", "en-us": "en", "en-gb": "en",
    "spa": "es", "fra": "fr", "fre": "fr", "deu": "de", "ger": "de", "ita": "it",
    "jp": "ja", "jpn": "ja",
    "zh": "zh-Hans", "zho": "zh-Hans", "chi": "zh-Hans", "zh-cn": "zh-Hans", "zh-sg": "zh-Hans",
    "zh-tw": "zh-Hant", "zh-hk": "zh-Hant", "zh-mo": "zh-Hant",
}


def normalize_ui_language(code: object) -> str:
    """Código tolerante → chave exata de ``STRINGS``; desconhecido → pt-BR."""
    if not isinstance(code, str) or not code.strip():
        return DEFAULT_LANGUAGE
    lowered = code.strip().replace("_", "-").lower()
    if lowered in _CANON:
        return _CANON[lowered]
    if lowered in _ALIASES:
        return _ALIASES[lowered]
    primary = lowered.split("-", 1)[0]
    if primary in _CANON:
        return _CANON[primary]
    if primary in _ALIASES:
        return _ALIASES[primary]
    return DEFAULT_LANGUAGE


def language_name(code: str) -> str:
    """Nome da língua escrito nela mesma, para o seletor."""
    resolved = normalize_ui_language(code)
    return dict(LANGUAGES).get(resolved, resolved)


def translate(language: str, key: str, **kwargs: object) -> str:
    table = STRINGS.get(normalize_ui_language(language)) or STRINGS[DEFAULT_LANGUAGE]
    text = table.get(key) or STRINGS["en"].get(key) or STRINGS[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


__all__ = ["DEFAULT_LANGUAGE", "LANGUAGES", "STRINGS", "language_name", "normalize_ui_language", "translate"]
