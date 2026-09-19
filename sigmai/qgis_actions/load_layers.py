"""Carregar uma camada vetorial no projeto — arquivo OGR ou planilha de pontos.

Os sítios de uma campanha de campo quase nunca chegam como shapefile: chegam
numa planilha (CSV) com uma coluna de longitude e uma de latitude — ou de
E/N em UTM. Na emulação da 1.1.0 o assistente não tinha como pôr esses
pontos no mapa: ``load_vector_layer`` só aceitava OGR. Com ``.csv``/``.txt``/
``.tsv`` a camada é montada pelo provedor ``delimitedtext`` do QGIS, com o
separador e o ponto decimal detectados no próprio arquivo, e as colunas de
coordenada reconhecidas pelo nome (ou ditas em ``x_field``/``y_field``).
Longitude/latitude sem ``crs`` assume EPSG:4326; E/N sem ``crs`` é recusado
com o nome das colunas, porque adivinhar a zona UTM põe os pontos noutro
estado.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..security import normalize_output_path
from ..validators import ValidationError, require_param
from .common import project


ALLOWED_VECTOR_EXTENSIONS = {".shp", ".gpkg", ".geojson", ".json", ".kml", ".gpx"}
DELIMITED_EXTENSIONS = {".csv", ".txt", ".tsv"}

#: Nomes de coluna reconhecidos como coordenada, em ordem de preferência.
LON_FIELD_HINTS = ("lon", "long", "longitude", "x", "coord_x", "este", "east", "easting", "utm_e", "e")
LAT_FIELD_HINTS = ("lat", "latitude", "y", "coord_y", "norte", "north", "northing", "utm_n", "n")
GEOGRAPHIC_HINTS = {"lon", "long", "longitude", "lat", "latitude"}
SAMPLE_BYTES = 64 * 1024


def _sniff(path: Path) -> tuple[str, str, list[str], str]:
    """(separador, ponto decimal, cabeçalho, codificação) lidos do arquivo."""
    raw = path.read_bytes()[:SAMPLE_BYTES]
    encoding = "utf-8-sig"
    try:
        sample = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        encoding = "ISO-8859-1"
        sample = raw.decode("ISO-8859-1")
    lines = [line for line in sample.splitlines() if line.strip()]
    if not lines:
        raise ValidationError("EMPTY_FILE", f"O arquivo {path.name!r} está vazio.", {"path": str(path)})
    delimiter = ","
    if path.suffix.lower() == ".tsv":
        delimiter = "\t"
    else:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            for candidate in (";", "\t", "|", ","):
                if candidate in lines[0]:
                    delimiter = candidate
                    break
    header = [cell.strip().strip('"') for cell in next(csv.reader([lines[0]], delimiter=delimiter))]
    # Ponto decimal: com ';' como separador, vírgula decimal é o comum no Brasil.
    decimal = "."
    body = lines[1:6]
    if delimiter != "," and body:
        comma_numbers = sum(1 for line in body for cell in line.split(delimiter) if _looks_decimal(cell.strip(), ","))
        dot_numbers = sum(1 for line in body for cell in line.split(delimiter) if _looks_decimal(cell.strip(), "."))
        if comma_numbers > dot_numbers:
            decimal = ","
    return delimiter, decimal, header, encoding


def _looks_decimal(cell: str, mark: str) -> bool:
    if mark not in cell:
        return False
    return cell.replace(mark, "", 1).lstrip("-").isdigit()


def _pick(header: list[str], hints: tuple[str, ...], explicit: str | None, label: str) -> str:
    if explicit:
        for column in header:
            if column.lower() == explicit.lower():
                return column
        raise ValidationError(
            "FIELD_NOT_FOUND", f"A coluna {explicit!r} ({label}) não existe no arquivo. Colunas: {', '.join(header)}.",
            {"field": explicit, "columns": header},
        )
    lowered = {column.lower(): column for column in header}
    for hint in hints:
        if hint in lowered:
            return lowered[hint]
    for hint in hints:
        for low, original in lowered.items():
            if low.startswith(hint + "_") or low.endswith("_" + hint):
                return original
    return ""


def delimited_text_uri(
    path: Path, *, x_field: str | None = None, y_field: str | None = None, crs: str | None = None,
    delimiter: str | None = None, decimal: str | None = None,
) -> dict[str, Any]:
    """Monta a URI do provedor ``delimitedtext`` e diz o que foi detectado."""
    wanted = {"x_field": x_field, "y_field": y_field, "crs": crs, "delimiter": delimiter, "decimal": decimal}
    delimiter, decimal, header, encoding = _sniff(path)
    x_field = _pick(header, LON_FIELD_HINTS, wanted["x_field"], "x/longitude")
    y_field = _pick(header, LAT_FIELD_HINTS, wanted["y_field"], "y/latitude")
    if not x_field or not y_field:
        raise ValidationError(
            "COORDINATE_FIELDS_NOT_FOUND",
            "Não achei as colunas de coordenada no arquivo. Diga x_field e y_field. Colunas: " + ", ".join(header) + ".",
            {"columns": header},
        )
    geographic = x_field.lower() in GEOGRAPHIC_HINTS and y_field.lower() in GEOGRAPHIC_HINTS
    crs = str(wanted["crs"] or "").strip()
    if not crs:
        if geographic:
            crs = "EPSG:4326"
        else:
            raise ValidationError(
                "CRS_REQUIRED",
                f"As colunas {x_field!r}/{y_field!r} não são longitude/latitude: diga o crs das coordenadas "
                "(por exemplo 'EPSG:31984' para SIRGAS 2000 / UTM 24S). Adivinhar a zona põe os pontos noutro estado.",
                {"x_field": x_field, "y_field": y_field, "columns": header},
            )
    if str(wanted["delimiter"] or ""):
        delimiter = str(wanted["delimiter"])
    if str(wanted["decimal"] or "") in (".", ","):
        decimal = str(wanted["decimal"])
    # O provedor lê ``delimiter`` e ``decimalPoint`` literalmente (``%3B`` não
    # é ';' para ele, e a tabulação é o par de caracteres ``\t``); os nomes de
    # coluna e o caminho podem ir percent-encoded.
    delimiter_literal = "\\t" if delimiter == "\t" else delimiter
    uri = (
        f"file://{quote(str(path))}?type=csv&delimiter={delimiter_literal}"
        f"&xField={quote(x_field, safe='')}&yField={quote(y_field, safe='')}&crs={crs}"
        f"&decimalPoint={decimal}&encoding={'UTF-8' if encoding == 'utf-8-sig' else encoding}&detectTypes=yes&geomType=point"
    )
    return {
        "uri": uri, "delimiter": delimiter, "decimal": decimal, "x_field": x_field, "y_field": y_field,
        "crs": crs, "columns": header, "encoding": encoding,
    }


def handle(params: dict[str, Any], context: dict[str, Any]):
    path_value = require_param(params, "path", str)
    name = params.get("name") or Path(path_value).stem
    provider = params.get("provider", "ogr")

    path = normalize_output_path(path_value)
    if not path.exists() or not path.is_file():
        raise ValidationError("FILE_NOT_FOUND", "Vector file was not found.", {"path": str(path)})
    suffix = path.suffix.lower()
    delimited = suffix in DELIMITED_EXTENSIONS
    if delimited:
        if provider not in ("ogr", "delimitedtext"):
            raise ValidationError("BAD_REQUEST", "Para CSV o provedor é 'delimitedtext'.", {"provider": provider})
        provider = "delimitedtext"
        detected = delimited_text_uri(
            path, x_field=params.get("x_field"), y_field=params.get("y_field"), crs=params.get("crs"),
            delimiter=params.get("delimiter"), decimal=params.get("decimal"),
        )
        source = detected["uri"]
    else:
        if provider != "ogr":
            raise ValidationError("BAD_REQUEST", "Only provider 'ogr' is allowed for load_vector_layer.", {"provider": provider})
        if suffix not in ALLOWED_VECTOR_EXTENSIONS:
            raise ValidationError(
                "UNSUPPORTED_VECTOR_FORMAT",
                "Unsupported vector format. Aceitos: " + ", ".join(sorted(ALLOWED_VECTOR_EXTENSIONS | DELIMITED_EXTENSIONS)) + ".",
                {"suffix": path.suffix},
            )
        detected = {}
        source = str(path)

    if context.get("dry_run"):
        return {
            "dry_run": True,
            "would_load": str(path),
            "name": name,
            "provider": provider,
            "detected": detected,
            "changes": ["Add the vector layer to the current QGIS project without modifying the source file."],
        }

    try:
        from qgis.core import QgsVectorLayer  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyQGIS is only available inside QGIS.") from exc

    layer = QgsVectorLayer(source, str(name), provider)
    if not layer.isValid():
        raise ValidationError(
            "INVALID_VECTOR_LAYER", "QGIS could not load this vector layer.",
            {"path": str(path), "provider": provider, "detected": detected},
        )
    if delimited and layer.featureCount() == 0:
        raise ValidationError(
            "EMPTY_LAYER",
            f"A planilha foi lida mas nenhuma linha virou ponto: confira x_field/y_field ({detected['x_field']}/"
            f"{detected['y_field']}), o ponto decimal ({detected['decimal']!r}) e o crs ({detected['crs']}).",
            {"detected": detected},
        )
    project().addMapLayer(layer)
    result = {
        "layer_id": layer.id(),
        "name": layer.name(),
        "path": str(path),
        "provider": provider,
        "crs": layer.crs().authid() if layer.crs().isValid() else "",
        "valid": True,
        "feature_count": int(layer.featureCount()),
    }
    if delimited:
        result["detected"] = detected
        result["notes"] = [
            f"Pontos lidos de {detected['x_field']}/{detected['y_field']} em {detected['crs']} (separador "
            f"{detected['delimiter']!r}, decimal {detected['decimal']!r}). A camada aponta para o CSV e é somente leitura; "
            "export_layer grava um GeoPackage se precisar editar."
        ]
    return result
