# Emulação: a 1.1.0 operada de ponta a ponta por um assistente sem acesso ao computador (2026-09-19)

Pergunta: as treze funções novas da 1.1.0 funcionam quando quem as usa é um assistente de IA que só tem o cliente MCP na mão — sem ler código, sem ver o QGIS, sem tocar em arquivo?

Montagem: a mesma do experimento de 2026-09-06 — um QGIS sem interface com a ponte do SIGMAI ligada e o acesso liberado numa pasta (`tools/remote_ai_lab.py`), e do outro lado um cliente MCP de uma chamada só (`tools/mcp_call.py`). Os dados são os de `_teste_sigmai` (`PI_UF_2024.shp`, `PI_Municipios_2024.shp`, `PE Carnaubas.kml`, a trilha do Itaguaré) mais uma planilha de cinco sítios de coleta em lon/lat (`sitios_de_coleta.csv`), escrita "pelo lado da usuária" na pasta autorizada.

## O que o assistente fez, na ordem

1. `sigmai_briefing` — uma chamada devolveu as cinco camadas com id, geometria, campo de nome provável ("NM_MUN", "Nome_UC"), o exemplo "Piau�" marcado como problema de codificação com a correção sugerida, o modo de acesso e a pasta liberada.
2. `set_layer_encoding` (ISO-8859-1) no limite estadual.
3. `sigmai_spatial_relationship` (parque × municípios do Piauí): **0 % do parque está dentro; a feição mais próxima sem tocar é Cocal, a 12,0 km** — o assistente sabe que a UC não é do Piauí antes de desenhar.
4. `sigmai_add_context_annotations` — divisa como linha, nome do estado no polo de inacessibilidade e o rótulo avulso "CEARÁ" em lon/lat.
5. `sigmai_compose_map` como figura de revista: `journal_column: "double"`, `format: "tif"`, 300 dpi, `data_source` por camada, inserto no estado. Resultado: `figura_1_revista.png` (aqui exportada em PNG a 200 dpi para o repositório), receita em `figura_1_receita.json`.
6. `sigmai_audit_layout` sobre o layout composto, `sigmai_map_recipe`, `sigmai_methods_paragraph` (en), `sigmai_recompose_from_recipe` com `overrides`.
7. `load_vector_layer` com o `.csv` dos sítios, `sigmai_campaign_map` com a trilha e a tabela de coordenadas em EPSG:31983 (`mapa_de_campanha.png`, `tabela_de_coordenadas.csv`): nota **A (100/100)**, 5 rótulos colocados.
8. `sigmai_undo` duas vezes: o layout da campanha sai, os estilos da trilha e dos sítios voltam, os arquivos ficam (a resposta lista quais); depois a camada dos sítios sai do projeto. `trilha_de_consentimento.json` registra cada escrita.

## O que a emulação encontrou — e o que mudou por causa dela

Todos os itens abaixo estão corrigidos nesta versão e cobertos por teste.

| Encontrado | Causa | Correção |
|---|---|---|
| A figura recebeu **B (90)** com CART070 reprovando a própria paleta do SIGMAI: azul-claro × verde-claro a ΔE 2,9 sob tritanopia. | Os preenchimentos eram o matiz de Okabe & Ito clareado 82 %; perto do branco os matizes convergem, e o que sobrevive à simulação é a diferença de luminosidade. | `POLYGON_FILLS`: sequência que alterna claridade e matizes de eixos opostos (laranja firme para o assunto, azul quase branco, amarelo claro, verde-azulado médio); os quatro primeiros ficam a ΔE ≥ 19 em qualquer simulação. Teste `test_a_paleta_da_composicao_passa_na_propria_regra`. |
| Nomes cortados na borda da legenda ("Limite estadual do Pi"); numa coluna simples, "(IBGE, 2024)" desenhado por cima da linha de crédito (`legenda_coluna_simples_antes.png`). | `QgsLayoutItemLegend` não quebra nem avisa; só a fonte era quebrada, não o nome. | Nome quebrado na largura da coluna; depois de posicionada a legenda é medida com `QgsLegendRenderer.minimumSize` e, se não cabe, a fonte desce até 6 pt e as fontes por camada saem das entradas (`legenda_coluna_simples_depois.png`). Nova regra **CART072**. |
| `sigmai_audit_layout` sobre a figura recém-composta reprovava em CART041 (itens na margem) e não rodava CART071. | A auditoria assumia 10 mm de margem e não sabia a largura impressa; a figura tem 5 mm por desenho. | A auditoria de um layout composto lê margens e `print_width_mm` da receita, e diz que o fez. A nota do compositor e a da auditoria passam a coincidir (A, 95). |
| `extra_labels` com `lon`/`lat` recusado ("precisa de text, x e y"). | Só a forma `x`/`y`/`crs` era aceita. | `{text, lon, lat}` em graus é aceito e publicado no esquema. |
| Nenhum caminho para pôr no mapa os sítios de uma planilha: `load_vector_layer` só aceitava OGR. | — | CSV/TXT/TSV pelo provedor `delimitedtext`, com separador, ponto decimal e codificação detectados no arquivo e as colunas de coordenada reconhecidas pelo nome; E/N sem `crs` é recusado com o nome das colunas. |
| `sigmai_methods_paragraph` escrevia "on a figura landscape page" e listava divisa e nomes como se fossem dados. | O nome interno da página vazava; camadas derivadas não eram distinguidas. | A figura é descrita pelas dimensões e pela coluna; camadas derivadas (`sigmai/derived_from`) entram como anotação, herdam a fonte da origem e ficam fora da linha de crédito. |
| A receita quebrava com camada raster. | `featureCount` inexistente em `QgsRasterLayer` — encontrado pela bateria de liberação. | Coberto por `test_receita_de_mapa_com_raster`. |

O único aviso que sobrou na figura é legítimo: **CART069** — coluna leste e linha sul do quadro sem dado de área, porque a malha do Ceará não está no projeto. É exatamente o que o agente em PyQGIS puro havia escrito à mão no mapa de 2026-09-06 ("malha cearense não disponível"), e agora a auditoria diz onde e por quê.

## Números

Bateria de liberação (`tools/release_battery.py --full`): **LIBERADO, 683 verificações, 0 falhas, 79 s**. Testes: 651 (94 novos nesta versão). Ferramentas MCP: 20. Regras: 34 em dez categorias.
