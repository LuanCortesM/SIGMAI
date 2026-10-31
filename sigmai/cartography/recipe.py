"""Receita reproduzível de um mapa e o parágrafo de Métodos que a descreve.

Um script de 353 linhas reproduz um mapa só para quem o escreveu; uma
chamada JSON do SIGMAI reproduz para qualquer um — desde que fique
guardada. ``build_recipe`` reúne, no momento da composição, tudo o que é
preciso para refazer o mapa: os parâmetros como foram pedidos, cada camada
com fonte (sem senha), CRS, contagem e o hash SHA-256 do arquivo quando é
local, as versões do QGIS e do SIGMAI, a página, a escala e o laudo. A
receita vai para as propriedades do layout (sobrevive no ``.qgz``), para
os metadados do PNG exportado (``tEXt`` ``sigmai:recipe``) e, se pedido,
para um JSON ao lado.

``methods_paragraph`` transforma a receita no texto que uma dissertação
precisa na seção de Métodos — em português, inglês ou espanhol; outras
línguas do mapa caem no inglês, com nota.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

RECIPE_PROPERTY = "sigmai/recipe"
RECIPE_PNG_KEY = "sigmai:recipe"
RECIPE_SCHEMA = "sigmai-map-recipe/1"

#: Arquivos maiores que isto não são hasheados (levaria segundos dentro do
#: QGIS); ficam registrados por tamanho e data de modificação.
HASH_MAX_BYTES = 256 * 1024 * 1024


def file_fingerprint(path: str | Path) -> dict[str, Any]:
    """SHA-256 (ou tamanho+mtime, para arquivos grandes) de um arquivo local."""
    p = Path(str(path))
    if not p.is_file():
        return {"path": str(p), "exists": False}
    size = p.stat().st_size
    info: dict[str, Any] = {"path": str(p), "exists": True, "size_bytes": size,
                            "modified": _dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
    if size <= HASH_MAX_BYTES:
        digest = hashlib.sha256()
        with p.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        info["sha256"] = digest.hexdigest()
    return info


def local_file_of_source(source: str) -> str | None:
    """Caminho local dentro de uma fonte OGR/GDAL ("/x/a.shp|layername=..."), ou ``None``."""
    text = str(source or "").strip()
    if not text or "://" in text or text.lower().startswith(("dbname=", "service=", "host=", "type=xyz", "crs=", "url=")):
        return None
    candidate = text.split("|", 1)[0]
    if candidate.startswith("/vsizip/") or candidate.startswith("/vsi"):
        return None
    return candidate if Path(candidate).exists() else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_recipe(
    params: dict[str, Any],
    layers: list[dict[str, Any]],
    result: dict[str, Any],
    *,
    sigmai_version: str,
    qgis_version: str,
    project_path: str = "",
) -> dict[str, Any]:
    """Monta a receita a partir do pedido, das camadas e do resultado da composição."""
    audit = result.get("audit") or {}
    return {
        "schema": RECIPE_SCHEMA,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sigmai_version": sigmai_version,
        "qgis_version": qgis_version,
        "project_path": project_path,
        "params": _json_safe(params),
        "layers": layers,
        "layout_name": result.get("layout_name", ""),
        "template": result.get("template", ""),
        "page": result.get("page", {}),
        "print_width_mm": result.get("print_width_mm"),
        "map_crs": result.get("map_crs", ""),
        "map_crs_description": result.get("map_crs_description", ""),
        "scale_denominator": result.get("scale_denominator"),
        "extent": result.get("extent", {}),
        "output": {"path": result.get("output_path", ""), "format": result.get("format", ""),
                   "dpi": (result.get("export") or {}).get("dpi")},
        "audit": {"grade": audit.get("grade"), "score": audit.get("score"), "rule_count": len(audit.get("results") or []),
                  "failed": [c["id"] for c in (audit.get("results") or []) if c.get("status") == "fail"]},
    }


def recipe_to_json(recipe: dict[str, Any]) -> str:
    return json.dumps(recipe, ensure_ascii=False, indent=1, sort_keys=False, default=str)


def recipe_from_json(text: str) -> dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("schema") != RECIPE_SCHEMA:
        raise ValueError(f"Não é uma receita do SIGMAI (schema esperado {RECIPE_SCHEMA!r}).")
    return data


def data_changes(recipe: dict[str, Any]) -> list[str]:
    """Camadas cujo arquivo local mudou desde a receita (hash ou tamanho diferente)."""
    changed: list[str] = []
    for layer in recipe.get("layers") or []:
        fp = layer.get("file") or {}
        if not fp.get("exists"):
            continue
        now = file_fingerprint(fp["path"])
        if not now.get("exists"):
            changed.append(f"{layer.get('name')}: o arquivo {fp['path']} não existe mais")
        elif fp.get("sha256") and now.get("sha256") and fp["sha256"] != now["sha256"]:
            changed.append(f"{layer.get('name')}: conteúdo diferente (SHA-256 mudou)")
        elif fp.get("size_bytes") != now.get("size_bytes"):
            changed.append(f"{layer.get('name')}: tamanho diferente ({fp.get('size_bytes')} → {now.get('size_bytes')} bytes)")
    return changed


# ---------------------------------------------------------------------------
# Parágrafo de Métodos
# ---------------------------------------------------------------------------

_METHODS_LANGS = {"pt-BR", "en", "es"}


def _fmt_scale(denominator: Any, lang: str) -> str:
    try:
        value = int(denominator)
    except (TypeError, ValueError):
        return ""
    sep = "." if lang in ("pt-BR", "es") else ","
    return "1:" + f"{value:,}".replace(",", sep)


def _sources_text(recipe: dict[str, Any]) -> str:
    params = recipe.get("params") or {}
    source = params.get("data_source")
    layers = recipe.get("layers") or []
    names = {layer.get("id"): layer.get("name") for layer in layers}
    if isinstance(source, dict):
        pairs = [(str(value), str(names.get(key, key))) for key, value in source.items()]
    elif isinstance(source, list):
        pairs = [(str(e.get("source")), str(names.get(e.get("layer"), e.get("layer")))) for e in source if isinstance(e, dict)]
    elif source:
        return str(source)
    else:
        pairs = [(str(layer.get("source_text")), str(layer.get("name"))) for layer in layers if layer.get("source_text")]
    # A mesma fonte de duas camadas (os registros e os locais derivados deles)
    # sai uma vez, com as camadas juntas.
    grouped: dict[str, list[str]] = {}
    for text, name in pairs:
        grouped.setdefault(text, []).append(name)
    # "CNUC/MMA (2025) [Parque]", como na legenda da figura (compose.resolve_data_sources).
    opening, closing = ("[", "]") if any("(" in text for text in grouped) else ("(", ")")
    return "; ".join(f"{text} {opening}{', '.join(layer_names)}{closing}" for text, layer_names in grouped.items())


def _page_phrase(page: dict[str, Any], params: dict[str, Any], lang: str) -> str:
    """', em página A4 paisagem' — ou, para a figura de revista, as dimensões e a coluna."""
    name = str(page.get("name", "")).strip()
    orientation = str(page.get("orientation", ""))
    if name != "figura":
        if lang == "pt-BR":
            orient = {"portrait": "retrato", "landscape": "paisagem"}.get(orientation, orientation)
            return f", em página {name} {orient}".rstrip()
        if lang == "es":
            orient = {"portrait": "vertical", "landscape": "horizontal"}.get(orientation, orientation)
            return f", en página {name} {orient}".rstrip()
        article = "an" if name[:1].upper() in "AEIOU" else "a"
        return f", on {article} {name} {orientation} page".replace("  ", " ")
    width, height = page.get("width_mm"), page.get("height_mm")
    dims = f"{width:g} × {height:g} mm" if isinstance(width, (int, float)) and isinstance(height, (int, float)) else ""
    column = str(params.get("journal_column") or "").strip()
    column_txt = {
        "pt-BR": {"single": "coluna simples", "one_and_half": "coluna e meia", "double": "coluna dupla"},
        "es": {"single": "columna simple", "one_and_half": "columna y media", "double": "columna doble"},
        "en": {"single": "single column", "one_and_half": "one-and-a-half column", "double": "double column"},
    }.get(lang, {}).get(column, column)
    detail = ", ".join(part for part in (dims, column_txt) if part)
    if lang == "pt-BR":
        return f", como figura para periódico na largura final impressa ({detail})"
    if lang == "es":
        return f", como figura para revista en el ancho final impreso ({detail})"
    return f", as a journal figure at its final printed width ({detail})"


#: DOI de todas as versões do SIGMAI no Zenodo (o mesmo do CITATION.cff); resolve para a versão mais recente.
SOFTWARE_DOI = "10.5281/zenodo.20389286"

#: Formatos em que a receita vai dentro do arquivo exportado.
_RECIPE_EMBEDDED_FORMATS = {"PNG"}

#: Provedores de camada raster, que o PDF e o SVG gravam como imagem.
_RASTER_PROVIDERS = {"gdal", "wms", "wcs", "arcgismapserver", "xyz"}


def _export_phrase(fmt: str, dpi: Any, layers: list[dict[str, Any]], lang: str) -> str:
    """", exportada em PDF, com os rasters a 300 dpi" — o dpi só vale para o que é imagem."""
    if not fmt:
        return ""
    words = {"pt-BR": (", exportada em", " a", ", com os rasters a"), "es": (", exportada en", " a", ", con los rásteres a"),
             "en": (", exported as", " at", ", with raster layers at")}[lang]
    if fmt in ("PDF", "SVG"):
        rasters = any(str(layer.get("provider") or "") in _RASTER_PROVIDERS for layer in layers)
        return f"{words[0]} {fmt}" + (f"{words[2]} {dpi} dpi" if rasters and dpi else "")
    return f"{words[0]} {fmt}" + (f"{words[1]} {dpi} dpi" if dpi else "")


#: Onde a receita fica (layout, PNG, JSON), a conjunção e a frase, por língua.
_RECIPE_PLACE_TEXT = {
    "pt-BR": ("nas propriedades do layout", "nos metadados do PNG exportado", "num arquivo JSON distribuído com a figura",
              " e ", "A receita completa da composição (parâmetros, camadas, hashes dos arquivos e versões de software) "
              "está gravada {}, o que permite reproduzir o mapa."),
    "es": ("en las propiedades del diseño", "en los metadatos del PNG exportado",
           "en un archivo JSON distribuido con la figura", " y ",
           "La receta completa de la composición (parámetros, capas, hashes de los archivos y versiones del software) "
           "queda registrada {}, lo que permite reproducir el mapa."),
    "en": ("in the layout properties", "in the metadata of the exported PNG", "in a JSON file distributed with the figure",
           " and ", "The full composition recipe (parameters, layers, file hashes and software versions) is stored {}, "
           "so the map can be reproduced."),
}


def _recipe_place(fmt: str, json_written: bool, lang: str) -> str:
    """Onde a receita ficou gravada: no PNG ela vai dentro do arquivo; no PDF e no SVG, não."""
    layout, png, json_file, conjunction, sentence = _RECIPE_PLACE_TEXT[lang]
    places = [layout] + ([png] if fmt in _RECIPE_EMBEDDED_FORMATS else []) + ([json_file] if json_written else [])
    joined = places[0] if len(places) == 1 else ", ".join(places[:-1]) + conjunction + places[-1]
    return sentence.format(joined)


def methods_paragraph(recipe: dict[str, Any], language: str = "pt-BR") -> dict[str, Any]:
    """Texto de Métodos + referência do software, na língua pedida."""
    lang = language if language in _METHODS_LANGS else "en"
    note = "" if language in _METHODS_LANGS else f"Parágrafo em inglês: a língua {language!r} ainda não tem modelo de Métodos."
    params = recipe.get("params") or {}
    page = recipe.get("page") or {}
    output = recipe.get("output") or {}
    audit = recipe.get("audit") or {}
    year = str(recipe.get("created_at", ""))[:4] or str(_dt.date.today().year)
    title = str(params.get("title") or recipe.get("layout_name") or "").strip()
    sources = _sources_text(recipe)
    crs = f"{recipe.get('map_crs_description') or ''} ({recipe.get('map_crs') or ''})".strip()
    scale = _fmt_scale(recipe.get("scale_denominator"), lang)
    page_phrase = _page_phrase(page, params, lang)
    fmt = str(output.get("format") or "").upper()
    dpi = output.get("dpi")
    export = _export_phrase(fmt, dpi, recipe.get("layers") or [], lang)
    place = _recipe_place(fmt, bool(str(params.get("recipe_path") or "").strip()), lang)
    author = str(params.get("map_author") or "").strip()
    grade = audit.get("grade")
    score = audit.get("score")
    rule_count = audit.get("rule_count")
    qgis = str(recipe.get("qgis_version") or "").split("-")[0]
    sigmai = str(recipe.get("sigmai_version") or "")
    all_layers = recipe.get("layers") or []
    derived = [layer for layer in all_layers if layer.get("derived_from")]
    layer_names = ", ".join(str(layer.get("name")) for layer in all_layers if not layer.get("derived_from"))
    derived_names = ", ".join(str(layer.get("name")) for layer in derived)

    if lang == "pt-BR":
        text = (
            f"O mapa{(' ' + repr(title)) if title else ''} foi elaborado no QGIS {qgis} por meio do complemento SIGMAI {sigmai} "
            f"(MACIEL, {year}), que compõe o layout a partir de parâmetros declarados e o audita segundo um regulamento "
            f"cartográfico explícito. As camadas utilizadas foram: {layer_names}"
            + (f"; fontes dos dados: {sources}" if sources else "")
            + (f"; camadas de anotação derivadas delas no QGIS (divisas e nomes): {derived_names}" if derived_names else "") + ". "
            f"O sistema de referência adotado foi {crs}"
            + (f", na escala {scale}" if scale else "") + page_phrase
            + export + ". "
            + (f"A composição foi auditada contra {rule_count} regras e recebeu nota {grade} ({score}/100). " if grade else "")
            + (f"Elaboração: {author}. " if author else "")
            + place
        )
        reference = (f"MACIEL, L. S. C. SIGMAI: Secure GIS-AI Interface. Versão {sigmai}. Zenodo, {year}. "
                     f"Disponível em: https://doi.org/{SOFTWARE_DOI}.")
    elif lang == "es":
        text = (
            f"El mapa{(' ' + repr(title)) if title else ''} fue elaborado en QGIS {qgis} mediante el complemento SIGMAI {sigmai} "
            f"(Maciel {year}), que compone el diseño a partir de parámetros declarados y lo audita según un reglamento "
            f"cartográfico explícito. Las capas utilizadas fueron: {layer_names}"
            + (f"; fuentes de los datos: {sources}" if sources else "")
            + (f"; capas de anotación derivadas de ellas en QGIS (límites y nombres): {derived_names}" if derived_names else "") + ". "
            f"El sistema de referencia adoptado fue {crs}"
            + (f", a escala {scale}" if scale else "") + page_phrase
            + export + ". "
            + (f"La composición fue auditada contra {rule_count} reglas y obtuvo la nota {grade} ({score}/100). " if grade else "")
            + (f"Elaboración: {author}. " if author else "")
            + place
        )
        reference = f"Maciel, L. S. C. {year}. SIGMAI: Secure GIS-AI Interface, versión {sigmai}. Zenodo. https://doi.org/{SOFTWARE_DOI}"
    else:
        text = (
            f"The map{(' ' + repr(title)) if title else ''} was produced in QGIS {qgis} through the SIGMAI plugin {sigmai} "
            f"(Maciel {year}), which composes the layout from declared parameters and audits it against an explicit "
            f"cartographic rulebook. Layers used: {layer_names}"
            + (f"; data sources: {sources}" if sources else "")
            + (f"; annotation layers derived from them in QGIS (boundaries and names): {derived_names}" if derived_names else "") + ". "
            f"The coordinate reference system was {crs}"
            + (f", at scale {scale}" if scale else "") + page_phrase
            + export + ". "
            + (f"The composition was audited against {rule_count} rules and graded {grade} ({score}/100). " if grade else "")
            + (f"Prepared by: {author}. " if author else "")
            + place
        )
        reference = f"Maciel, L. S. C. {year}. SIGMAI: Secure GIS-AI Interface, version {sigmai}. Zenodo. https://doi.org/{SOFTWARE_DOI}"
    text = re.sub(r"\s+", " ", text).strip()
    return {"language": lang, "paragraph": text, "software_reference": reference, "note": note}
