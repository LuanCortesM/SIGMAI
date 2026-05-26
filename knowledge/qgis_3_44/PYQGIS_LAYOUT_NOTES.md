# PyQGIS Layout Notes for SIGMAI

Primary source: `pyqgis_developer_cookbook/composer`.

## Relevant APIs/classes

- `QgsPrintLayout`
- `QgsLayoutItemMap`
- `QgsLayoutItemLabel`
- `QgsLayoutItemLegend`
- `QgsLayoutItemScaleBar`
- `QgsLayoutItemPicture`
- `QgsLayoutPoint`
- `QgsLayoutSize`
- `QgsUnitTypes`
- `QgsLayoutExporter`
- `QgsProject.instance().layoutManager()`

## Correct patterns

1. Create layout:

```python
project = QgsProject.instance()
layout = QgsPrintLayout(project)
layout.initializeDefaults()
layout.setName("MyLayout")
project.layoutManager().addLayout(layout)
```

2. Add visible map item:

```python
map_item = QgsLayoutItemMap(layout)
map_item.attemptMove(QgsLayoutPoint(5, 5, QgsUnitTypes.LayoutMillimeters))
map_item.attemptResize(QgsLayoutSize(200, 200, QgsUnitTypes.LayoutMillimeters))
map_item.zoomToExtent(layer.extent())  # or setExtent(rect)
layout.addLayoutItem(map_item)
```

3. Add label:

```python
label = QgsLayoutItemLabel(layout)
label.setText("Title")
label.adjustSizeToText()
layout.addLayoutItem(label)
```

4. Add legend and link it to a map item:

```python
legend = QgsLayoutItemLegend(layout)
legend.setLinkedMap(map_item)
layout.addLayoutItem(legend)
```

5. Add scale bar and link it to a map item:

```python
scale = QgsLayoutItemScaleBar(layout)
scale.setLinkedMap(map_item)
scale.applyDefaultSize()
layout.addLayoutItem(scale)
```

6. Export:

```python
exporter = QgsLayoutExporter(layout)
exporter.exportToPdf(path, QgsLayoutExporter.PdfExportSettings())
exporter.exportToImage(path, QgsLayoutExporter.ImageExportSettings())
```

## Critical care points

- `create_layout` alone can export a blank page.
- `QgsLayoutItemMap` has zero width/height by default unless moved/resized.
- A map item must have a meaningful extent; use `zoomToExtent(layer.extent())` or `setExtent(QgsRectangle)`.
- Legend and scale bar should link to the same `QgsLayoutItemMap`.
- Export success only means QGIS wrote a file; it does not prove the map is cartographically complete.
- Geographic CRS can be acceptable for location maps but can make metric scale bars and analysis misleading.

## SIGMAI command relation

- `create_layout`: creates page/base.
- `add_layout_map`: creates and sizes `QgsLayoutItemMap`.
- `set_layout_extent`: updates map item extent.
- `add_layout_label`: creates `QgsLayoutItemLabel`.
- `add_layout_legend`: creates `QgsLayoutItemLegend` linked to map.
- `add_layout_scale_bar`: creates `QgsLayoutItemScaleBar` linked to map.
- `add_layout_north_arrow`: should prefer `QgsLayoutItemPicture`; textual fallback is acceptable.
- `export_layout`: wraps `QgsLayoutExporter`.
- `generate_basic_map`: should orchestrate all of the above.

## Tests needed in QGIS real

- Map item exists and has non-zero size.
- Map item extent is not empty/null.
- Exported PDF/PNG size exceeds a minimum threshold.
- Output is not blank by raster pixel inspection if possible.
- Legend and scale bar are linked to `main_map`.
- Geographic CRS warning is returned for scale bar/map items where relevant.

