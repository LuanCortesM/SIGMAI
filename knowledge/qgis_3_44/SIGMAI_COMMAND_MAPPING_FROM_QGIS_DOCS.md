# SIGMAI Command Mapping from QGIS 3.44 Documentation

Este mapeamento traduz as APIs e algoritmos documentados no QGIS 3.44 para comandos seguros do SIGMAI.

## Cartografia e layout

| SIGMAI command | QGIS API / pattern | Documentation source | Status recomendado | Observacoes |
|---|---|---|---|---|
| `create_layout` | `QgsPrintLayout(project)`, `initializeDefaults()`, `layoutManager().addLayout(layout)` | PyQGIS Cookbook `composer` | Base | Cria a pagina, mas nao cria mapa visivel por si so. |
| `add_layout_map` | `QgsLayoutItemMap(layout)`, `attemptMove`, `attemptResize`, `setExtent`/`zoomToExtent`, `addLayoutItem` | PyQGIS Cookbook `composer` | Critico | Principal correcao para evitar layout branco. |
| `set_layout_extent` | `QgsLayoutItemMap.setExtent(rect)` ou `zoomToExtent(rect)` | PyQGIS Cookbook `composer` | Critico | Deve validar extent e aplicar margem. |
| `add_layout_label` | `QgsLayoutItemLabel`, `setText`, `setFont`, `adjustSizeToText`, `attemptMove` | PyQGIS Cookbook `composer` | Critico | Titulo, subtitulo, fonte, autoria e CRS. |
| `add_layout_legend` | `QgsLayoutItemLegend`, `setLinkedMap(map)` | PyQGIS Cookbook `composer` | Critico | Legenda deve preferir vinculacao com o item de mapa. |
| `add_layout_scale_bar` | `QgsLayoutItemScaleBar`, `setLinkedMap(map)`, `applyDefaultSize()` | PyQGIS Cookbook `composer` | Critico | Emitir warning para CRS geografico. |
| `add_layout_north_arrow` | `QgsLayoutItemPicture` com SVG ou fallback `QgsLayoutItemLabel` | Print layout/PyQGIS layout APIs | Necessario | Fallback textual `N ↑` e aceitavel quando nao houver asset SVG. |
| `export_layout` | `QgsLayoutExporter.exportToPdf`, `exportToImage` | PyQGIS Cookbook `composer` | Implementado/base | Exportacao bem sucedida nao garante mapa cartografico. |
| `generate_basic_map` | Orquestra comandos acima | Derivado das APIs de layout | Critico | Deve avaliar completude cartografica. |

## Simbologia

| SIGMAI command | QGIS API / pattern | Documentation source | Status recomendado | Observacoes |
|---|---|---|---|---|
| `set_layer_style` | `QgsSingleSymbolRenderer`, `QgsFillSymbol`, `QgsLineSymbol`, `QgsMarkerSymbol`, `triggerRepaint()` | PyQGIS Cookbook `vector` | Critico | Garante contraste antes da exportacao. |
| `apply_single_symbol` | Mesmo padrao de `set_layer_style` | PyQGIS Cookbook `vector` | Futuro/alias | Pode ser alias publico para estilo simples. |
| `apply_categorized_style` | `QgsCategorizedSymbolRenderer`, `QgsRendererCategory` | PyQGIS Cookbook `vector` | Proxima fase | Validar campo e limitar categorias. |
| `apply_graduated_style` | `QgsGraduatedSymbolRenderer`, `QgsRendererRange` | PyQGIS Cookbook `vector` | Proxima fase | Exigir campo numerico. |
| `apply_raster_style` | `QgsRasterShader`, `QgsColorRampShader`, `QgsSingleBandPseudoColorRenderer` | PyQGIS Cookbook `raster` | Futuro | Importante para declividade, hillshade e DEM. |

## Vetores

| SIGMAI command | QGIS API / algorithm | Documentation source | Permissao | Observacoes |
|---|---|---|---|---|
| `validate_geometries` | `QgsGeometry`, `QgsWkbTypes`, feature iteration | PyQGIS Cookbook `geometry` | `read_only` | Limitar amostras e nao modificar camada. |
| `fix_geometries` | `native:fixgeometries` | Processing algorithms | `safe_write` | Saida temporaria ou `test_outputs/`. |
| `buffer` | `native:buffer` | Processing vector geometry | `safe_write` | Warning se CRS geografico. |
| `clip` | `native:clip` | Processing vector overlay | `safe_write` | Overlay deve ser poligonal. |
| `dissolve` | `native:dissolve` | Processing vector geometry | `safe_write` | Validar campos se fornecidos. |
| `reproject_layer` | `native:reprojectlayer` | Processing vector general/CRS | `safe_write` | Validar CRS alvo antes. |
| `export_layer` | `QgsVectorFileWriter` / provider export | PyQGIS vector APIs | `safe_write` | Bloquear sobrescrita sem confirmacao. |
| `intersection` | `native:intersection` | Processing vector overlay | Futuro | Entrar como comando alto nivel. |
| `union` | `native:union` | Processing vector overlay | Futuro | Pode gerar muitas feicoes/campos. |
| `difference` | `native:difference` | Processing vector overlay | Futuro | Validar overlay e CRS. |

## Raster

| SIGMAI command | QGIS API / algorithm | Documentation source | Status recomendado | Observacoes |
|---|---|---|---|---|
| `raster_info` | `QgsRasterLayer.width`, `height`, `extent`, `bandCount`, `bandName` | PyQGIS Cookbook `raster` | Proxima fase segura | Read-only e essencial para diagnostico. |
| `raster_slope` | `native:slope` | Processing raster terrain analysis | Futuro | Exigir raster DEM e output seguro. |
| `raster_aspect` | `native:aspect` | Processing raster terrain analysis | Futuro | Exigir DEM e documentar unidades. |
| `raster_hillshade` | `native:hillshade` | Processing raster terrain analysis | Futuro | Bom para cartografia. |
| `raster_reproject` | GDAL warp/reproject | GDAL Processing algorithms | Futuro | Requer validacao forte de output. |
| `raster_clip` | GDAL clip raster | GDAL Processing algorithms | Futuro | Cuidado com NoData e extent. |

## Plugins

| SIGMAI command | QGIS API / pattern | Documentation source | Status recomendado | Observacoes |
|---|---|---|---|---|
| `inspect_plugin` | plugin folder, metadata, `qgis.utils.plugins` | PyQGIS plugin docs | Implementado/base | Nao importar plugin para inspecao estatica. |
| `validate_metadata_txt` | `metadata.txt` required fields | PyQGIS plugin docs | Implementado/base | Necessario para repository/publicacao. |
| `check_plugin_imports` | AST/static scan | SIGMAI safety design | Implementado/base | Nao executar codigo. |
| `package_plugin_zip` | zip seguro com exclusoes | QGIS packaging practice | Implementado/base | Excluir logs, cache, sessions e diagnostics. |
| `self_health_check` | composicao de status/capabilities/structure | SIGMAI design | Implementado/base | Nao fazer hot reload agressivo. |

## Implicações principais para o SIGMAI

1. `create_layout` nao deve ser tratado como "gerar mapa"; ele apenas cria a base.
2. `add_layout_map` e `set_layout_extent` sao comandos obrigatorios para evitar pagina branca.
3. `set_layer_style` deve acontecer antes da exportacao para garantir contraste minimo.
4. `add_layout_legend` e `add_layout_scale_bar` devem vincular ao item de mapa.
5. O resultado de `export_layout` deve ser validado por existencia, tamanho minimo e presenca dos itens esperados.
6. Processing deve permanecer protegido por allowlist; comandos alto nivel devem ser preferidos a `run_processing` generico.

