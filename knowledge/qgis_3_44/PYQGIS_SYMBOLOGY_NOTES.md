# PyQGIS Symbology Notes for SIGMAI

Fonte local analisada: `local QGIS documentation mirror/qgis_3_44/_sources/docs/pyqgis_developer_cookbook/vector.rst.txt` e `raster.rst.txt`.

## APIs/classes relevantes

Vetores:

- `QgsSingleSymbolRenderer`
- `QgsCategorizedSymbolRenderer`
- `QgsGraduatedSymbolRenderer`
- `QgsRendererCategory`
- `QgsRendererRange`
- `QgsMarkerSymbol`
- `QgsLineSymbol`
- `QgsFillSymbol`
- `QgsSymbol`
- `QColor`
- `layer.setRenderer(renderer)`
- `layer.triggerRepaint()`

Raster:

- `QgsRasterShader`
- `QgsColorRampShader`
- `QgsSingleBandPseudoColorRenderer`
- `QgsSingleBandGrayRenderer`
- `QgsHillshadeRenderer`
- `rlayer.setRenderer(renderer)`
- `rlayer.triggerRepaint()`

## Padrões corretos de uso

Estilo simples para vetor:

```python
symbol = QgsFillSymbol.createSimple({
    "color": "#D8E1E8",
    "outline_color": "#075D68",
    "outline_width": "0.4",
})
renderer = QgsSingleSymbolRenderer(symbol)
layer.setRenderer(renderer)
layer.setOpacity(0.85)
layer.triggerRepaint()
```

Renderer categorizado:

```python
categories = []
category = QgsRendererCategory(value, symbol, label)
categories.append(category)
renderer = QgsCategorizedSymbolRenderer(field_name, categories)
layer.setRenderer(renderer)
```

Renderer graduado:

```python
ranges = []
renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
layer.setRenderer(renderer)
```

Raster pseudo-colorido:

```python
shader = QgsRasterShader()
color_ramp = QgsColorRampShader()
color_ramp.setColorRampType(QgsColorRampShader.Interpolated)
shader.setRasterShaderFunction(color_ramp)
renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
layer.setRenderer(renderer)
layer.triggerRepaint()
```

## Cuidados

- Simbologia deve respeitar tipo geometrico: ponto, linha ou poligono.
- Cores devem ser validadas como hex antes de criar `QColor`.
- A opacidade deve ficar entre 0 e 1.
- Campo categorizado/graduado deve existir.
- O renderer deve ser serializavel apenas como resumo na resposta JSON, nao como objeto PyQGIS.
- Atualizar repaint depois de `setRenderer`.
- Para layout/exportacao, aplicar estilo antes de exportar.

## Relação com comandos SIGMAI

- `set_layer_style`: comando base para mapa legivel e nao branco.
- `apply_single_symbol`: alias ou evolucao especifica de `set_layer_style`.
- `apply_categorized_style`: deve validar campo, categorias e cores.
- `apply_graduated_style`: deve validar campo numerico e classes.
- `apply_raster_style`: deve validar raster, banda e rampa.
- `generate_basic_map`: deve aplicar estilo default quando `apply_default_style=true`.

## Riscos de implementação

- Mapa exportado "branco" por simbologia invisivel: preenchimento branco, contorno claro ou opacidade zero.
- Renderer aplicado no layer errado se a IA inventar `layer_id`.
- Campo inexistente em categorized/graduated.
- Simbologia muito pesada em camadas grandes se gerar categoria para cada valor sem limite.

## Pontos para testar no QGIS real

- Aplicar `set_layer_style` em poligono com preenchimento claro e contorno escuro.
- Exportar layout antes/depois do estilo para confirmar diferenca visual.
- Testar `apply_categorized_style` com campo de UF/municipio quando implementado.
- Testar que `set_layer_style` dry-run nao altera renderer.

