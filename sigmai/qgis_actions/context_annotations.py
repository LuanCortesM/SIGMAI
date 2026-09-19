"""Contexto derivado dos próprios dados: divisas como linha e nomes de região.

O experimento "PyQGIS puro × SIGMAI" mostrou o que um programador faz à mão
e o compositor não oferecia: a divisa estadual desenhada como linha
tracejada (a fronteira do polígono da UF), os nomes PIAUÍ/CEARÁ posicionados
pelo polo de inacessibilidade, um aviso "malha cearense não disponível"
onde falta dado. Tudo isso vem de camadas que já estão no projeto.

``add_context_annotations`` cria, a partir de uma camada de polígonos:

* uma camada de LINHA com a fronteira (``boundary()``) de cada feição — ou
  da união delas, com ``dissolve=true`` — estilizada como divisa;
* uma camada de PONTOS só-de-rótulo (``QgsNullSymbolRenderer``), um ponto
  por feição no polo de inacessibilidade, rotulada por ``label_field`` ou
  por ``label_text`` (um texto único, para a união);
* rótulos avulsos (``extra_labels``: texto + coordenada + CRS) para nomear o
  que não está na base — o estado vizinho, o oceano.

As camadas novas são de memória por padrão (o QGIS não as grava no
projeto); com ``output_gpkg`` são gravadas num GeoPackage e carregadas de
lá, o que sobrevive ao salvar. Nada aqui altera a camada de origem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cartography.symbology import STYLE_ORIGIN_PALETTE, mark_style_origin
from ..security import ensure_parent_exists, normalize_output_path
from ..validators import ValidationError, require_param
from .common import crs_authid, layer_type_name, project

#: Propriedade que marca uma camada derivada de outra pelo SIGMAI (divisa,
#: nomes, rótulos avulsos): a receita e o parágrafo de Métodos as listam à
#: parte, como anotação, e não como fonte de dados.
DERIVED_FROM_PROPERTY = "sigmai/derived_from"

DEFAULT_BOUNDARY_COLOUR = "#1A1A1A"
DEFAULT_BOUNDARY_WIDTH_MM = 0.7
DEFAULT_LABEL_COLOUR = "#4A4A4A"
DEFAULT_LABEL_SIZE_PT = 10.0

#: Limite de feições para a derivação: fronteira e polo de inacessibilidade
#: de 200 mil lotes travariam o QGIS do usuário.
MAX_FEATURES = 5000


def _imports() -> dict[str, Any]:
    from qgis.core import (  # type: ignore
        Qgis,
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsFeature,
        QgsField,
        QgsFields,
        QgsGeometry,
        QgsLineSymbol,
        QgsNullSymbolRenderer,
        QgsPalLayerSettings,
        QgsPointXY,
        QgsProject,
        QgsSingleSymbolRenderer,
        QgsTextBufferSettings,
        QgsTextFormat,
        QgsVectorFileWriter,
        QgsVectorLayer,
        QgsVectorLayerSimpleLabeling,
        QgsWkbTypes,
    )
    from qgis.PyQt.QtCore import QVariant  # type: ignore
    from qgis.PyQt.QtGui import QColor, QFont  # type: ignore

    return dict(
        Qgis=Qgis, QgsCoordinateReferenceSystem=QgsCoordinateReferenceSystem, QgsCoordinateTransform=QgsCoordinateTransform,
        QgsFeature=QgsFeature, QgsField=QgsField, QgsFields=QgsFields, QgsGeometry=QgsGeometry, QgsLineSymbol=QgsLineSymbol,
        QgsNullSymbolRenderer=QgsNullSymbolRenderer, QgsPalLayerSettings=QgsPalLayerSettings, QgsPointXY=QgsPointXY,
        QgsProject=QgsProject, QgsSingleSymbolRenderer=QgsSingleSymbolRenderer, QgsTextBufferSettings=QgsTextBufferSettings,
        QgsTextFormat=QgsTextFormat, QgsVectorFileWriter=QgsVectorFileWriter, QgsVectorLayer=QgsVectorLayer,
        QgsVectorLayerSimpleLabeling=QgsVectorLayerSimpleLabeling, QgsWkbTypes=QgsWkbTypes, QVariant=QVariant,
        QColor=QColor, QFont=QFont,
    )


def _polygon_layer(layer_id: str):
    layer = project().mapLayer(layer_id)
    if layer is None:
        by_name = [candidate for candidate in project().mapLayers().values() if candidate.name() == layer_id]
        layer = by_name[0] if by_name else None
    if layer is None:
        raise ValidationError("LAYER_NOT_FOUND", f"Camada não encontrada: {layer_id}.", {"layer_id": layer_id})
    if layer_type_name(layer) != "vector" or int(layer.geometryType()) != 2:
        raise ValidationError(
            "GEOMETRY_TYPE_MISMATCH",
            "add_context_annotations precisa de uma camada de polígonos (a divisa é a fronteira do polígono).",
            {"layer_id": layer_id, "geometry_type": int(layer.geometryType()) if layer_type_name(layer) == "vector" else None},
        )
    if layer.featureCount() > MAX_FEATURES:
        raise ValidationError(
            "LAYER_TOO_LARGE",
            f"A camada tem {layer.featureCount()} feições; a derivação de contexto aceita até {MAX_FEATURES}. "
            "Dissolva ou filtre a camada antes (dissolve / query_features).",
            {"layer_id": layer_id, "feature_count": layer.featureCount(), "max": MAX_FEATURES},
        )
    return layer


def _valid_hex(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text
        except ValueError:
            pass
    raise ValidationError("BAD_REQUEST", f"Cor inválida: {text!r}. Use '#RRGGBB'.", {"value": text})


def _mark_derived(layer: Any, source: Any) -> None:
    try:
        layer.setCustomProperty(DERIVED_FROM_PROPERTY, str(source.id()))
    except Exception:
        pass


def derived_from(layer: Any) -> str:
    try:
        return str(layer.customProperty(DERIVED_FROM_PROPERTY, "") or "")
    except Exception:
        return ""


def _normalise_extra_label(entry: Any, index: int) -> dict[str, Any]:
    """Aceita ``{text, x, y, crs?}`` e também ``{text, lon, lat}`` (graus, EPSG:4326).

    Na emulação da 1.1.0 o assistente escreveu lon/lat — a forma natural de
    quem pensa em graus — e levou recusa. Um par lon/lat só tem uma leitura;
    aceitá-lo não é adivinhar.
    """
    if not isinstance(entry, dict) or not str(entry.get("text", "")).strip():
        raise ValidationError("BAD_REQUEST", f"extra_labels[{index}] precisa de text, x e y (e crs opcional), ou text, lon e lat.", {"entry": entry})
    if "x" in entry and "y" in entry:
        return entry
    lon = entry.get("lon", entry.get("longitude"))
    lat = entry.get("lat", entry.get("latitude"))
    if lon is not None and lat is not None:
        try:
            lon_f, lat_f = float(lon), float(lat)
        except (TypeError, ValueError):
            raise ValidationError("BAD_REQUEST", f"extra_labels[{index}]: lon e lat precisam ser números em graus.", {"entry": entry})
        if not (-180.0 <= lon_f <= 180.0 and -90.0 <= lat_f <= 90.0):
            raise ValidationError("BAD_REQUEST", f"extra_labels[{index}]: lon/lat fora do intervalo de graus ({lon_f}, {lat_f}).", {"entry": entry})
        return {"text": entry["text"], "x": lon_f, "y": lat_f, "crs": entry.get("crs") or "EPSG:4326"}
    raise ValidationError("BAD_REQUEST", f"extra_labels[{index}] precisa de text, x e y (e crs opcional), ou text, lon e lat.", {"entry": entry})


def _text_format(imports: dict[str, Any], size_pt: float, colour: str, letter_spacing: float, bold: bool) -> Any:
    fmt = imports["QgsTextFormat"]()
    font = imports["QFont"]()
    font.setPointSizeF(float(size_pt))
    font.setBold(bold)
    if letter_spacing:
        try:
            from ..cartography.qtcompat import qt_enum

            font.setLetterSpacing(qt_enum(imports["QFont"], "SpacingType", "AbsoluteSpacing"), float(letter_spacing))
        except Exception:
            pass
    fmt.setFont(font)
    fmt.setSize(float(size_pt))
    fmt.setColor(imports["QColor"](colour))
    try:
        from ..cartography.qtcompat import qt_enum

        fmt.setSizeUnit(qt_enum(imports["Qgis"], "RenderUnit", "Points"))
    except Exception:
        pass
    halo = imports["QgsTextBufferSettings"]()
    halo.setEnabled(True)
    halo.setSize(1.0)
    halo.setColor(imports["QColor"](255, 255, 255, 230))
    fmt.setBuffer(halo)
    return fmt


def _label_only_layer(imports: dict[str, Any], name: str, crs: Any, fmt: Any, uppercase: bool) -> Any:
    layer = imports["QgsVectorLayer"](f"Point?crs={crs_authid(crs)}&field=rotulo:string(200)", name, "memory")
    layer.setRenderer(imports["QgsNullSymbolRenderer"]())
    settings = imports["QgsPalLayerSettings"]()
    settings.fieldName = "upper(\"rotulo\")" if uppercase else "rotulo"
    settings.isExpression = uppercase
    settings.enabled = True
    try:
        from ..cartography.qtcompat import qt_enum

        settings.placement = qt_enum(imports["QgsPalLayerSettings"], "Placement", "OverPoint")
    except Exception:
        pass
    settings.setFormat(fmt)
    layer.setLabeling(imports["QgsVectorLayerSimpleLabeling"](settings))
    layer.setLabelsEnabled(True)
    return layer


def _persist(imports: dict[str, Any], layer: Any, gpkg: Path, table: str) -> Any:
    """Grava a camada de memória no GeoPackage e devolve a camada lida de lá.

    A primeira escrita cria o arquivo; as seguintes acrescentam tabelas. O
    estilo (renderizador e rótulos) é copiado para a camada persistida.
    """
    writer = imports["QgsVectorFileWriter"]
    options = writer.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = table
    options.actionOnExistingFile = (
        writer.CreateOrOverwriteLayer if gpkg.exists() else writer.CreateOrOverwriteFile
    )
    result = writer.writeAsVectorFormatV3(layer, str(gpkg), imports["QgsProject"].instance().transformContext(), options)
    code = result[0] if isinstance(result, tuple) else result
    if int(code) != 0:
        raise ValidationError(
            "WRITE_FAILED", f"Não foi possível gravar {table!r} em {gpkg}: {result[1] if isinstance(result, tuple) else code}.",
            {"path": str(gpkg), "table": table},
        )
    persisted = imports["QgsVectorLayer"](f"{gpkg}|layername={table}", layer.name(), "ogr")
    if not persisted.isValid():
        raise ValidationError("WRITE_FAILED", f"A camada gravada em {gpkg} não pôde ser lida de volta.", {"path": str(gpkg)})
    persisted.setRenderer(layer.renderer().clone())
    if layer.labeling() is not None:
        persisted.setLabeling(layer.labeling().clone())
        persisted.setLabelsEnabled(layer.labelsEnabled())
    return persisted


def add_context_annotations(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Divisa como linha + nomes de região a partir de uma camada de polígonos."""
    imports = _imports()
    source = _polygon_layer(require_param(params, "boundary_layer_id", str))
    dissolve = bool(params.get("dissolve", True))
    label_field = str(params.get("label_field") or "").strip()
    label_text = str(params.get("label_text") or "").strip()
    include_boundary = params.get("include_boundary", True) is not False
    boundary_colour = _valid_hex(params.get("boundary_color"), DEFAULT_BOUNDARY_COLOUR)
    boundary_width = float(params.get("boundary_width_mm") or DEFAULT_BOUNDARY_WIDTH_MM)
    boundary_style = str(params.get("boundary_style") or "dash").strip().lower()
    if boundary_style not in ("solid", "dash", "dot", "dash dot"):
        raise ValidationError("BAD_REQUEST", f"boundary_style inválido: {boundary_style!r}. Use solid, dash, dot ou 'dash dot'.", {})
    label_size = float(params.get("label_font_size") or DEFAULT_LABEL_SIZE_PT)
    label_colour = _valid_hex(params.get("label_color"), DEFAULT_LABEL_COLOUR)
    letter_spacing = float(params.get("letter_spacing", 2.0) or 0.0)
    uppercase = params.get("uppercase", True) is not False
    extra_labels = params.get("extra_labels") or []
    if not isinstance(extra_labels, list):
        raise ValidationError("BAD_REQUEST", "extra_labels precisa ser uma lista de {text, x, y, crs?}.", {})
    if label_field and label_field not in [f.name() for f in source.fields()]:
        raise ValidationError(
            "FIELD_NOT_FOUND",
            f"O campo {label_field!r} não existe em {source.name()!r}. Campos: {', '.join(f.name() for f in source.fields())}.",
            {"layer_id": source.id(), "field": label_field},
        )
    if label_field and label_text:
        raise ValidationError("BAD_REQUEST", "Use label_field (um nome por feição) OU label_text (um nome para a união), não os dois.", {})
    if label_text and not dissolve:
        raise ValidationError("BAD_REQUEST", "label_text nomeia a UNIÃO das feições; exige dissolve=true.", {})

    gpkg: Path | None = None
    if params.get("output_gpkg"):
        gpkg = normalize_output_path(str(params["output_gpkg"]))
        if gpkg.suffix.lower() != ".gpkg":
            raise ValidationError("BAD_REQUEST", f"output_gpkg precisa terminar em .gpkg: {gpkg}", {"path": str(gpkg)})
        ensure_parent_exists(gpkg)

    plan = {
        "source_layer": {"id": source.id(), "name": source.name(), "features": int(source.featureCount())},
        "boundary_layer": f"Divisa — {source.name()}" if include_boundary else None,
        "label_layer": (f"Nomes — {source.name()}" if (label_field or label_text) else None),
        "extra_labels": len(extra_labels),
        "persisted_to": str(gpkg) if gpkg else None,
    }
    if context.get("dry_run"):
        return {"dry_run": True, **plan}

    crs = source.crs()
    pairs = [
        (imports["QgsGeometry"](feature.geometry()), feature)
        for feature in source.getFeatures()
        if feature.geometry() is not None and not feature.geometry().isEmpty()
    ]
    if not pairs:
        raise ValidationError("EMPTY_LAYER", f"A camada {source.name()!r} não tem geometrias.", {"layer_id": source.id()})
    if dissolve:
        union = imports["QgsGeometry"].unaryUnion([geometry for geometry, _ in pairs])
        parts: list[tuple[Any, Any]] = [(union, None)]
    else:
        parts = pairs

    created: list[dict[str, Any]] = []
    notes: list[str] = []
    prj = project()

    if include_boundary:
        line_layer = imports["QgsVectorLayer"](f"MultiLineString?crs={crs_authid(crs)}&field=origem:string(200)", plan["boundary_layer"], "memory")
        features = []
        for geometry, feature in parts:
            boundary = imports["QgsGeometry"](geometry.constGet().boundary())
            boundary.convertToMultiType()
            f = imports["QgsFeature"](line_layer.fields())
            f.setGeometry(boundary)
            f.setAttribute("origem", source.name())
            features.append(f)
        line_layer.dataProvider().addFeatures(features)
        line_layer.updateExtents()
        symbol = imports["QgsLineSymbol"].createSimple({
            "line_color": boundary_colour, "line_width": str(boundary_width), "line_width_unit": "MM",
            "line_style": boundary_style, "capstyle": "round", "joinstyle": "round",
        })
        line_layer.setRenderer(imports["QgsSingleSymbolRenderer"](symbol))
        if gpkg is not None:
            line_layer = _persist(imports, line_layer, gpkg, "divisa")
        mark_style_origin(line_layer, STYLE_ORIGIN_PALETTE)
        _mark_derived(line_layer, source)
        prj.addMapLayer(line_layer)
        created.append({"id": line_layer.id(), "name": line_layer.name(), "kind": "boundary_line", "features": len(features)})

    if label_field or label_text:
        fmt = _text_format(imports, label_size, label_colour, letter_spacing, bold=True)
        point_layer = _label_only_layer(imports, plan["label_layer"], crs, fmt, uppercase)
        features = []
        for geometry, feature in parts:
            text = label_text if label_text else str(feature[label_field] if feature is not None else "")
            if not text or text == "NULL":
                continue
            try:
                pole, _distance = geometry.poleOfInaccessibility(max(geometry.boundingBox().width(), geometry.boundingBox().height()) / 200.0)
                point = pole.asPoint()
            except Exception:
                point = geometry.centroid().asPoint()
            f = imports["QgsFeature"](point_layer.fields())
            f.setGeometry(imports["QgsGeometry"].fromPointXY(imports["QgsPointXY"](point)))
            f.setAttribute("rotulo", text)
            features.append(f)
        point_layer.dataProvider().addFeatures(features)
        point_layer.updateExtents()
        if gpkg is not None:
            point_layer = _persist(imports, point_layer, gpkg, "nomes")
        mark_style_origin(point_layer, STYLE_ORIGIN_PALETTE)
        _mark_derived(point_layer, source)
        prj.addMapLayer(point_layer)
        created.append({"id": point_layer.id(), "name": point_layer.name(), "kind": "label_only_points", "features": len(features)})

    if extra_labels:
        fmt = _text_format(imports, label_size, label_colour, letter_spacing, bold=True)
        extra_layer = _label_only_layer(imports, f"Rótulos avulsos — {source.name()}", crs, fmt, uppercase)
        features = []
        for index, entry in enumerate(extra_labels):
            entry = _normalise_extra_label(entry, index)
            x, y = float(entry["x"]), float(entry["y"])
            entry_crs = imports["QgsCoordinateReferenceSystem"](str(entry.get("crs") or crs_authid(crs)))
            if not entry_crs.isValid():
                raise ValidationError("BAD_REQUEST", f"extra_labels[{index}].crs inválido: {entry.get('crs')!r}.", {"entry": entry})
            point = imports["QgsPointXY"](x, y)
            if crs_authid(entry_crs) != crs_authid(crs):
                point = imports["QgsCoordinateTransform"](entry_crs, crs, prj).transform(point)
            f = imports["QgsFeature"](extra_layer.fields())
            f.setGeometry(imports["QgsGeometry"].fromPointXY(point))
            f.setAttribute("rotulo", str(entry["text"]).strip())
            features.append(f)
        extra_layer.dataProvider().addFeatures(features)
        extra_layer.updateExtents()
        if gpkg is not None:
            extra_layer = _persist(imports, extra_layer, gpkg, "rotulos_avulsos")
        mark_style_origin(extra_layer, STYLE_ORIGIN_PALETTE)
        _mark_derived(extra_layer, source)
        prj.addMapLayer(extra_layer)
        created.append({"id": extra_layer.id(), "name": extra_layer.name(), "kind": "extra_labels", "features": len(features)})

    if gpkg is None:
        notes.append(
            "As camadas criadas são de memória: o QGIS não as grava no projeto. Passe output_gpkg para "
            "persisti-las num GeoPackage (e liberar a pasta no painel do SIGMAI)."
        )
    notes.append(
        "Inclua os ids criados em layer_ids de compose_map para que apareçam no mapa; as camadas de "
        "rótulo não têm símbolo e não entram na legenda (CART020 as dispensa)."
    )
    return {**plan, "created_layers": created, "notes": notes}
