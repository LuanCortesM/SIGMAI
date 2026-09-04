## [0.2.2] — 2026-09-04

Rodada de estresse com mapas duplos, trilhas, GPX, raster, CRS misturados, camadas filtradas e páginas de A5 a A2. Nove defeitos, quatro deles do tipo que entrega ao usuário um mapa diferente do que o assistente descreveu.

### Novo — o que faltava para a conversa com a IA ser fluida

- **`second_map`** compõe dois quadros na mesma folha. Por padrão os painéis são igualados na escala mais aberta, porque comparar tamanhos entre escalas diferentes engana o leitor; quando as escalas diferem de propósito, cada painel anuncia a sua e a barra única é substituída por essa indicação. Nova regra **CART066** reprova o painel duplo que não declara as escalas.
- **`subject_layer_id`** enquadra a camada de assunto e desenha as demais como contexto. É o que separa "mapa do parque mostrando os municípios em volta" de "mapa dos municípios com um ponto invisível dentro".
- **`include_inset`** acrescenta o inserto de localização com o retângulo do recorte principal — o elemento que responde "onde fica isso?" e o que mais faltava em escala grande.
- **`label_field`** rotula as feições na mesma passada, com halo branco e traçado curvo em linhas.

### Corrigido — a ferramenta improvisava em vez de recusar

Quatro parâmetros eram aceitos e ignorados em silêncio. O assistente dizia ao usuário "aqui está o mapa do parque com o inserto e os nomes das trilhas" e entregava um mapa sem inserto e sem nomes. Agora cada um deles recusa e lista o que é aceito:

- **`label_field` inexistente** — recusa nomeando os campos de cada camada, com sugestão do nome parecido.
- **formato de página inexistente** (`"A9 vertical"`) — recusava-se a existir, mas virava A4 sem avisar.
- **template inexistente** (`"poster_neon"`) — virava `cientifico` sem avisar.
- **`output_path` que é uma pasta, ou sem extensão reconhecida** — o QGIS devolvia sucesso e não escrevia arquivo nenhum; só a auditoria percebia, e tarde. A exportação agora confere que o arquivo existe e tem tamanho, e falha com o código de retorno do `QgsLayoutExporter`.

### Corrigido — erros de medida

- **A barra de escala era medida sem o segmento à esquerda do zero.** O QGIS desenha um segmento antes do zero quando há quatro ou mais à direita; ele faz parte da barra. O comprimento anunciado ficava 25% abaixo do desenhado, o teto da faixa reservada era calculado errado e a fração medida na auditoria não batia com a planejada.
- **A projeção automática era escolhida pelo recorte dos dados, não pelo recorte impresso.** O quadro alarga a extensão para casar com sua proporção, e um segundo painel pode cobrir área muito maior que o primeiro. Um recorte alto e estreito passava no teste de zona UTM e depois aparecia no papel com quase 1.000 km de largura, com eastings de 1.262.000 numa zona que termina em 834.000. A decisão passa a usar a extensão já alargada, e a considerar os dois painéis.
- **O CRS escolhido sem código EPSG era relatado como vazio.** `authid()` devolve string vazia numa Lambert Azimutal definida por parâmetros; o assistente relatava "mapa sem CRS" para um mapa corretamente projetado.

### Melhorado

- **CART022 passa a considerar o comprimento absoluto da barra**, não só a proporção. Numa A2 o quadro tem 37 cm de largura e uma barra de 15% teria 55 mm — mas uma de 50 mm já se mede a olho. O que impede estimar distância é a barra curta em milímetros, não a barra curta em relação a uma folha grande.
- **Quando a coluna lateral é estreita demais para uma barra legível, a barra passa para uma faixa sob o mapa** — colocação clássica em cartas publicadas. A escala só é conhecida depois de ajustar a extensão ao quadro, então o compositor resolve o layout uma segunda vez quando descobre que a barra não cabe.
- O intervalo da grade aparece como `1.000 km` e não como `1e+06 m`.

### Corrigido — ferramentas de teste

- **Encerramento seguro do QGIS em scripts autônomos** (`tools/qgis_lifecycle.py`). Uma camada criada num script e não adicionada ao projeto pertence ao Python: o interpretador a destrói no encerramento, depois de `exitQgis()` já ter derrubado o registro de provedores, e o destrutor em C++ acessa memória liberada. O resultado era uma falha de segmentação *depois* de o script imprimir todos os resultados. Não afeta o plugin dentro do QGIS, onde o ciclo de vida pertence ao QGIS e as camadas pertencem ao projeto.
- `tools/ci_compose_smoke_test.py` passou a exercitar também os caminhos de saída inválidos, e `tests/test_cartography_regressions.py` fixa cada defeito desta rodada.

