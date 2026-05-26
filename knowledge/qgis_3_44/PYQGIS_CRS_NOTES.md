# PyQGIS CRS Notes for SIGMAI

Fonte local analisada: `local QGIS documentation mirror/qgis_3_44/_sources/docs/pyqgis_developer_cookbook/crs.rst.txt`.

## APIs/classes relevantes

- `QgsCoordinateReferenceSystem`
- `QgsCoordinateTransform`
- `QgsProject.instance().transformContext()`
- `QgsPointXY`
- `QgsUnitTypes`
- `QgsProject.instance().crs()`
- `QgsMapLayer.crs()`

## Padrões corretos de uso

Criar CRS por string EPSG:

```python
crs = QgsCoordinateReferenceSystem("EPSG:4326")
if not crs.isValid():
    raise ValueError("Invalid CRS")
```

Transformar coordenadas entre sistemas:

```python
source = QgsCoordinateReferenceSystem("EPSG:4326")
target = QgsCoordinateReferenceSystem("EPSG:31983")
context = QgsProject.instance().transformContext()
xform = QgsCoordinateTransform(source, target, context)
point = xform.transform(QgsPointXY(-45.0, -23.0))
```

Coletar informações úteis:

```python
crs.authid()
crs.description()
crs.isValid()
crs.isGeographic()
crs.mapUnits()
crs.postgisSrid()
```

## Cuidados

- CRS deve ser validado com `isValid()` antes de executar reprojecao, buffer metrico ou calculos de area/distancia.
- CRS geografico (`isGeographic() == True`) usa graus como unidade de mapa. Isso e aceitavel para mapas de localizacao, mas perigoso para buffer, distancia, area e escala cartografica metrificada.
- Operacoes metricas devem preferir CRS projetado apropriado para a area, como UTM/SIRGAS 2000 no Brasil quando aplicavel.
- Transformacoes devem usar o `transformContext()` do projeto para respeitar configuracoes do QGIS.
- Camadas sem CRS valido devem ser tratadas como alerta critico; o SIGMAI nao deve "adivinhar" CRS sem confirmacao.

## Relação com comandos SIGMAI

- `diagnose_crs`: deve comparar CRS do projeto e das camadas, validando `isValid()`, `isGeographic()` e divergencias.
- `get_project_crs`: deve usar `QgsProject.instance().crs()`.
- `get_layer_info`: deve retornar `layer.crs().authid()`, descricao, validade e se e geografico.
- `reproject_layer`: deve validar `target_crs` via `QgsCoordinateReferenceSystem(target).isValid()` antes de chamar `native:reprojectlayer`.
- `buffer`: deve alertar quando a camada estiver em CRS geografico.
- `add_layout_scale_bar`: deve alertar se o mapa estiver em CRS geografico, pois escala grafica pode ser menos confiavel em graus.
- `generate_basic_map`: deve incluir CRS no rodape/fonte quando possivel.

## Riscos de implementação

- Executar buffer em graus e apresentar resultado como metros.
- Usar extent de camada em CRS diferente do item de mapa sem considerar transformacao.
- Corrigir CRS de uma camada usando `setLayerCrs` como se fosse reprojecao real. Definir CRS e reprojetar sao operacoes diferentes.
- Aceitar CRS textual invalido e so descobrir o erro no Processing.

## Pontos para testar no QGIS real

- `diagnose_crs` com projeto em EPSG:4674 e camadas em EPSG:4674.
- `diagnose_crs` com uma camada reprojetada para EPSG:3857 ou EPSG:31983.
- `buffer` deve emitir warning em CRS geografico.
- `reproject_layer` deve gerar camada valida com CRS alvo.
- `generate_basic_map` deve escrever CRS no rodape e ainda exportar quando o CRS for geografico.

