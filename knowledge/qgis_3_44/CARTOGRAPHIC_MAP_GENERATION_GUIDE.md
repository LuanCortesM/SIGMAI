# Cartographic Map Generation Guide for SIGMAI

Guia derivado da documentacao local oficial QGIS 3.44, com prioridade no problema observado: o SIGMAI exportou layout, mas o mapa ficou praticamente branco.

## 1. Como criar layout corretamente?

Use `QgsPrintLayout` ligado ao projeto atual:

```python
project = QgsProject.instance()
layout = QgsPrintLayout(project)
layout.initializeDefaults()
layout.setName("SIGMAI Map")
project.layoutManager().addLayout(layout)
```

No SIGMAI, isso corresponde a `create_layout`.

Ponto essencial: isso cria a pagina/layout, nao cria automaticamente um mapa visivel.

## 2. Como adicionar mapa visível?

Use `QgsLayoutItemMap`:

```python
map_item = QgsLayoutItemMap(layout)
map_item.setRect(20, 20, 20, 20)
map_item.attemptMove(QgsLayoutPoint(10, 25, QgsUnitTypes.LayoutMillimeters))
map_item.attemptResize(QgsLayoutSize(190, 150, QgsUnitTypes.LayoutMillimeters))
map_item.setExtent(layer.extent())
layout.addLayoutItem(map_item)
```

No SIGMAI, isso deve ser `add_layout_map`.

Sem `QgsLayoutItemMap`, o export pode funcionar e ainda gerar uma pagina branca.

## 3. Como definir extent?

Use a extensao da camada ou uma extensao manual validada:

```python
extent = layer.extent()
map_item.setExtent(extent)
map_item.refresh()
```

Para melhorar enquadramento, aplicar margem percentual ao `QgsRectangle` antes de chamar `setExtent`.

No SIGMAI, isso deve ser `set_layout_extent`.

## 4. Como evitar mapa branco?

Checklist minimo:

- O layout existe.
- Existe ao menos um `QgsLayoutItemMap`.
- O item de mapa tem largura e altura maiores que zero.
- O item de mapa tem extent valido.
- A camada usada esta valida.
- A camada tem geometria/extent nao vazio.
- A camada esta visivel no projeto ou foi explicitamente associada ao mapa.
- A simbologia tem contraste com o fundo.
- O export gerou arquivo com tamanho minimo aceitavel.

O SIGMAI deve tratar `export_layout ok=true` apenas como sucesso tecnico de exportacao, nao como sucesso cartografico completo.

## 5. Como adicionar título?

Use `QgsLayoutItemLabel`:

```python
label = QgsLayoutItemLabel(layout)
label.setText("SIGMAI Test Map")
label.attemptMove(QgsLayoutPoint(10, 8, QgsUnitTypes.LayoutMillimeters))
label.attemptResize(QgsLayoutSize(190, 12, QgsUnitTypes.LayoutMillimeters))
layout.addLayoutItem(label)
```

No SIGMAI: `add_layout_label`.

## 6. Como adicionar legenda?

Use `QgsLayoutItemLegend` e vincule ao mapa quando possivel:

```python
legend = QgsLayoutItemLegend(layout)
legend.setTitle("Legenda")
legend.setLinkedMap(map_item)
legend.attemptMove(QgsLayoutPoint(205, 25, QgsUnitTypes.LayoutMillimeters))
layout.addLayoutItem(legend)
```

No SIGMAI: `add_layout_legend`.

Se a vinculacao falhar, retornar warning e criar legenda simples.

## 7. Como adicionar escala?

Use `QgsLayoutItemScaleBar`:

```python
scale_bar = QgsLayoutItemScaleBar(layout)
scale_bar.setStyle("Single Box")
scale_bar.setLinkedMap(map_item)
scale_bar.applyDefaultSize()
scale_bar.attemptMove(QgsLayoutPoint(10, 180, QgsUnitTypes.LayoutMillimeters))
layout.addLayoutItem(scale_bar)
```

No SIGMAI: `add_layout_scale_bar`.

Se CRS for geografico, emitir warning porque unidades de mapa podem estar em graus.

## 8. Como adicionar norte?

Preferencial:

- `QgsLayoutItemPicture` com SVG de seta norte.

Fallback seguro:

- `QgsLayoutItemLabel` com texto `N ↑`.

No SIGMAI: `add_layout_north_arrow`.

Esse comando nao deve falhar apenas porque o asset SVG nao existe.

## 9. Como exportar PDF/PNG?

Use `QgsLayoutExporter`:

```python
exporter = QgsLayoutExporter(layout)
exporter.exportToPdf(path, QgsLayoutExporter.PdfExportSettings())
exporter.exportToImage(path, QgsLayoutExporter.ImageExportSettings())
```

No SIGMAI: `export_layout`.

Depois da exportacao, validar:

- arquivo existe;
- tamanho maior que limite minimo;
- layout continha item de mapa;
- layout continha titulo/legenda/escala/norte/fonte se requisitado.

## 10. Quais APIs devem ser usadas no SIGMAI?

- `QgsPrintLayout`
- `QgsLayoutItemMap`
- `QgsLayoutItemLabel`
- `QgsLayoutItemLegend`
- `QgsLayoutItemScaleBar`
- `QgsLayoutItemPicture`
- `QgsLayoutExporter`
- `QgsLayoutPoint`
- `QgsLayoutSize`
- `QgsUnitTypes.LayoutMillimeters`
- `QgsRectangle`
- `QgsProject.instance().layoutManager()`
- `QgsProject.instance().mapLayer(layer_id)`

## 11. Quais APIs são arriscadas?

- Qualquer chamada que dependa de dialogo modal ou interacao do usuario.
- Uso de canvas (`iface.mapCanvas()`) como unica fonte de extent em automacao; em bridge e preferivel usar layer extent ou extent manual.
- Hot reload de layout/plugin durante comando HTTP.
- Exportar sem verificar itens e extent.
- Depender de arquivos SVG externos nao versionados para seta norte.

## 12. Quais testes devem validar se o mapa não ficou vazio?

Testes de estrutura no QGIS:

- `list_layouts` mostra layout criado.
- Layout tem item `main_map`.
- `main_map` tem extent valido e dimensoes positivas.
- Layout tem `title`, `legend`, `scale_bar`, `north_arrow` e `source`.
- `export_layout` gera PDF/PNG com tamanho minimo.

Testes visuais/heuristicos:

- PNG nao deve ter tamanho muito pequeno.
- PNG nao deve ser todo branco ou quase todo branco, quando houver ferramenta para verificar pixels.
- PDF deve ter tamanho minimo maior que pagina vazia.

Veredito cartografico:

- A: item de mapa + titulo + legenda + escala + norte + fonte + output valido.
- B: mapa usavel com pequena ausencia.
- C: layout gerado, mas sem elementos cartograficos completos.
- D: export tecnicamente OK, mas provavelmente branco.
- E: falha.

## Sequencia recomendada para `generate_basic_map`

1. Validar `layer_id`.
2. Aplicar `set_layer_style` se solicitado.
3. Criar layout com `create_layout`.
4. Adicionar mapa com `add_layout_map`.
5. Ajustar extent com `set_layout_extent`.
6. Adicionar titulo com `add_layout_label`.
7. Adicionar legenda com `add_layout_legend`.
8. Adicionar escala com `add_layout_scale_bar`.
9. Adicionar norte com `add_layout_north_arrow`.
10. Adicionar fonte/autoria/CRS com `add_layout_label`.
11. Exportar com `export_layout`.
12. Avaliar completude com `evaluate_layout_cartographic_completeness`.
13. Retornar relatorio JSON com itens criados, warnings e outputs.

