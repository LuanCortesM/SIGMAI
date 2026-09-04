
### Novo — bancada de cenários e a rodada multilíngue

`tools/scenario_runner.py` roda uma lista de pedidos em JSON contra o compositor e classifica cada desfecho em três: **ok** (compôs, com nota da auditoria), **recusa** (`CompositionError` — contrato cumprido) e **quebra** (qualquer outra exceção — sempre defeito, porque a IA do outro lado recebe um erro de programador e não tem como se corrigir). Um pedido legítimo recusado e um pedido inválido aceito também contam como defeito, e a bancada os separa. Os 242 cenários usados nesta rodada ficam versionados em `tests/cenarios/`.

Com ela, três agentes escreveram pedidos como usuários reais escreveriam — iniciante e experiente, com erro de digitação, em espanhol, francês, italiano, alemão, inglês, japonês, chinês, coreano, árabe, hebraico, russo, grego, tailandês e hindi. **242 cenários, 18 quebras e 21 defeitos distintos.** Todas as quebras foram eliminadas.

### Corrigido — a ferramenta perdia o controle com valor de tipo errado

Um `ValueError`, `TypeError` ou `AttributeError` vazando não é uma recusa: é a ferramenta desistindo. Novo módulo `sigmai/cartography/params.py` centraliza a leitura de parâmetro, e cada função explica no docstring o defeito que impede.

- **`confirm_overwrite: "false"` apagava o arquivo do usuário.** Em Python `bool("false")` é `True`. Era o defeito mais grave do lote: perda silenciosa de dado. Todas as doze bandeiras booleanas passam por `as_flag`, que aceita booleano de verdade e as strings inequívocas (`"false"`, `"não"`, `"0"`), registra a conversão numa nota, e recusa o resto.
- **`dpi`, `margin_percent`, `label_font_size`, `inset_zoom_factor` e `margin_mm`** estouravam com string não numérica, `null` ou lista. `dpi` ganhou faixa (50 a 1200): `dpi: 0` virava 300 em silêncio, `dpi: 1` gerava imagem de 11×8 pixels e `dpi: 20000` gerava 992 milhões de pixels — risco real de derrubar o QGIS do usuário.
- **`layer_ids: 42`** produzia `TypeError: 'int' object is not iterable`.
- **Vírgula decimal.** `"7,5"` é como se escreve sete e meio em francês, alemão, italiano, espanhol e português, e só tem uma leitura: passa a ser aceito. Já `"1,500"` vale mil e quinhentos em inglês e um e meio em francês — recusado, porque escolher entre as duas seria adivinhar.
- **`null` virava o texto "None"** no título e na linha de crédito.
- **`page` só era validado quando era string**: `page: 150000`, `page: ["A4","landscape"]` e `page: {"name":"A9"}` escapavam do modo estrito e viravam A4 em silêncio.

### Corrigido — quem não escreve em português ou inglês não conseguia pedir a orientação

`"A4 paysage"`, `"A4 apaisado"`, `"A3 orizzontale"`, `"A4 Querformat"`, `"A4 横"`, `"A3 أفقي"` — todos recusados. O vocabulário de orientação agora cobre quinze línguas, em tabela de dados comentada por origem, e o mesmo vocabulário vale para o parâmetro `orientation` passado sozinho — que antes não reconhecia nem português e caía em paisagem sem avisar, entregando o oposto do pedido. Erro de digitação na orientação passa a receber sugestão, como já acontecia com `template` e `label_field`.

### Corrigido — o mapa saía bilíngue

Título em japonês e "Escala", "Fonte:", "Elaboração:", "Legenda", "Produzido com SIGMAI/QGIS" em português. Novo parâmetro `map_language` e novo módulo `sigmai/cartography/maptext.py` traduzem tudo que o compositor escreve sozinho para quinze línguas, com queda para o português quando a língua não existe. Em árabe e hebraico os rótulos gerados passam a ser alinhados à direita. O nome das camadas continua como está no projeto do usuário — é dado dele, não texto da ferramenta.

### Corrigido — título longo sem espaço era cortado em silêncio

Um título de 93 caracteres em chinês perdia o começo e o fim, sem aviso. A causa não é a escrita: o QGIS só quebra linha em espaço, e chinês, japonês e tailandês escrevem sem espaço — um título em português sem espaços sofria o mesmo corte. Novo módulo `sigmai/cartography/textfit.py` mede o texto contra o retângulo reservado e, nesta ordem, reduz o corpo até o piso da regra CART044, insere quebra onde a escrita permite (entre ideogramas sim, no meio de um agrupamento devanágari não), e só então recusa dizendo quantos caracteres cabem. Vale para título, subtítulo e legendas de painel, e a mudança fica registrada nas notas.

### Novo — `scale`, e o custo de igualar escalas

- **`scale` era aceito e não fazia nada.** Passa a fixar a escala impressa: "faça em 1:25.000" é o pedido cartográfico mais comum que existe, porque numa dissertação a escala costuma ser imposta pela norma. Uma escala que cortaria os dados é recusada dizendo qual é a maior que ainda os contém. `style_profile`, que também não fazia nada e não tinha semântica definida, foi removido.
- **Igualar as escalas de dois painéis é honesto e pode ser inútil.** Comparando um parque de 10.000 ha com um estado inteiro, a escala comum é a do estado e o parque ocupa 0,3% do quadro. O compositor agora mede isso e recomenda `comparison_same_scale=false` ou o inserto de localização, que é o elemento próprio para situar um recorte pequeno numa área grande.

### Corrigido — outros

- **`format` e extensão divergentes**: `output_path:"mapa.png"` com `format:"pdf"` gerava um PDF chamado `.png` sem avisar.
- **`grid_style` e `apply_style` inválidos** caíam num padrão em silêncio; `apply_style` errado se comportava como `"all"`, reestilizando todas as camadas.
- **`template` era sensível a caixa** (`"CIENTIFICO"` recusado) enquanto `page` não.
- **`map_crs: "EPSG: 4674"`** com espaço era recusado sem nenhuma dica.
- **Margem que não deixa área útil** ora quebrava, ora produzia um mapa quase em branco, dependendo de `include_grid` — um parâmetro sem relação nenhuma com o problema.
