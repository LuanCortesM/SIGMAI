# PyQGIS Vector and Raster Notes for SIGMAI

Fontes locais analisadas:

- `local QGIS documentation mirror/qgis_3_44/_sources/docs/pyqgis_developer_cookbook/geometry.rst.txt`
- `local QGIS documentation mirror/qgis_3_44/_sources/docs/pyqgis_developer_cookbook/vector.rst.txt`
- `local QGIS documentation mirror/qgis_3_44/_sources/docs/pyqgis_developer_cookbook/raster.rst.txt`
- `local QGIS documentation mirror/qgis_3_44/_sources/docs/user_manual/processing_algs/qgis/vectorgeometry.rst.txt`
- `local QGIS documentation mirror/qgis_3_44/_sources/docs/user_manual/processing_algs/qgis/vectoroverlay.rst.txt`
- `local QGIS documentation mirror/qgis_3_44/_sources/docs/user_manual/processing_algs/qgis/rasterterrainanalysis.rst.txt`

## APIs/classes relevantes

Vetores:

- `QgsVectorLayer`
- `QgsFeature`
- `QgsFeatureRequest`
- `QgsGeometry`
- `QgsWkbTypes`
- `QgsProject.instance().mapLayer(layer_id)`
- `QgsVectorFileWriter`

Raster:

- `QgsRasterLayer`
- `QgsRaster`
- `QgsRasterBlock`
- `QgsRasterShader`
- `QgsColorRampShader`
- `QgsSingleBandPseudoColorRenderer`
- `QgsSingleBandGrayRenderer`
- `QgsHillshadeRenderer`

## Padrões corretos de uso

Carregar vetor:

```python
layer = QgsVectorLayer(path, name, "ogr")
if layer.isValid():
    QgsProject.instance().addMapLayer(layer)
```

Inspecionar geometria:

```python
geom = feature.geometry()
wkb_type = geom.wkbType()
geometry_name = QgsWkbTypes.displayString(wkb_type)
is_multipart = geom.isMultipart()
```

Inspecionar raster:

```python
rlayer.width()
rlayer.height()
rlayer.extent()
rlayer.rasterType()
rlayer.bandCount()
rlayer.bandName(1)
```

## Algoritmos vetoriais relevantes

- `native:buffer`
- `native:clip`
- `native:dissolve`
- `native:fixgeometries`
- `native:reprojectlayer`
- `native:intersection`
- `native:union`
- `native:difference`
- `native:centroids`
- `native:multiparttosingleparts`

O manual de Processing confirma que `native:clip` recebe `INPUT`, `OVERLAY` e `OUTPUT`, e que a camada de overlay deve ser poligonal. O SIGMAI deve validar isso antes de chamar o algoritmo.

## Algoritmos raster relevantes

- `native:slope`
- `native:aspect`
- `native:hillshade`
- GDAL warp/reproject
- GDAL clip raster by mask/extent
- GDAL contour
- GDAL polygonize

## Cuidados

- Sempre diferenciar vetor e raster antes de chamar handlers.
- Para vetores, verificar `layer.isValid()` e `layer.geometryType()`.
- Para raster, verificar band count e extent antes de algoritmos de terreno.
- Geometrias vazias ou nulas devem ser contadas separadamente de geometrias invalidas.
- Processing pode retornar objetos de camada temporaria ou paths; o SIGMAI deve normalizar a resposta.
- Nao modificar camada original em operacoes de correcao, buffer, clip ou dissolve. Saidas devem ir para `TEMPORARY_OUTPUT` ou `test_outputs/`.

## Relação com comandos SIGMAI

- `list_layers`: deve distinguir vector/raster e retornar provider, CRS, extent e validade.
- `get_layer_info`: deve trazer campos, feature count, geometry type, raster bands quando aplicavel.
- `validate_geometries`: deve iterar features com limite e retornar amostras de ids problematicos.
- `fix_geometries`: deve usar `native:fixgeometries`.
- `buffer`: deve usar `native:buffer`.
- `clip`: deve usar `native:clip`.
- `dissolve`: deve usar `native:dissolve`.
- `export_layer`: deve usar escrita segura e bloquear sobrescrita sem confirmacao.
- `raster_info`: deve usar metodos de `QgsRasterLayer`.
- `raster_slope`, `raster_aspect`, `raster_hillshade`: devem ficar atras de allowlist e validacao de raster DEM.

## Riscos de implementação

- Processar camada invalida e travar ou retornar erro pouco claro.
- Rodar overlay com CRS divergente sem warning.
- Salvar shapefile parcial sem seus arquivos auxiliares.
- Exportar raster/vetor com driver errado.
- Confundir camada temporaria com arquivo persistente.

## Pontos para testar no QGIS real

- Carregar `BR_Pais_2025.shp`, `BR_UF_2025.shp`, `SP_Municipios_2025.shp`.
- Validar geometrias nas tres camadas.
- Rodar `fix_geometries` com `TEMPORARY_OUTPUT` e com GeoPackage em `test_outputs/`.
- Rodar `buffer`, `clip`, `dissolve` e `reproject_layer` com dry-run e execucao real segura.
- Carregar rasters `.tif` de teste e executar apenas `raster_info` inicialmente.

