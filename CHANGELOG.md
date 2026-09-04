# Changelog

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o versionamento é [semântico](https://semver.org/lang/pt-BR/).

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

### Novo — briefing de outro plugin, numa chamada

A pergunta era se seria preciso um RAG interno para o assistente aprender como funciona o plugin que se quer auditar, ou se daria para consertar plugin a plugin. Nenhum dos dois: **um plugin do QGIS já declara o próprio contrato**. Quando registra um provedor de Processing, ele publica id, nome, grupo, cada parâmetro com tipo, obrigatoriedade e valor padrão, e cada saída. Isso é dado estruturado e pequeno — cabe inteiro no contexto do assistente. RAG serve para corpus grande e não estruturado; aqui seria indexar o que já vem indexado, com um índice que se desatualiza e passa a mentir sobre o código, que é o pior modo de falha possível num auditor.

Nova ferramenta MCP `sigmai_brief_plugin` e nova ação `brief_plugin`, somente leitura. Numa chamada devolve:

- **identidade e estado** — versão, autor, caminho, se está instalado, carregado e ativo;
- **saúde do provedor de Processing**, com diagnóstico dos dois modos de falha que aparecem na prática (abaixo);
- **o que é dirigível por programa** — cada algoritmo com o contrato inteiro: parâmetros, tipos, obrigatoriedade, padrões, saídas e classificação de risco. Os primeiros doze vêm completos; o resto vem com id e nome, para que um plugin de cem algoritmos não consuma a janela do assistente com contratos que ele não vai usar;
- **o que NÃO é dirigível** — menus, botões, painéis e diálogos que o plugin registra, com os rótulos detectados, e a explicação de por quê: essas coisas só respondem a clique, e acioná-las por programa abriria um diálogo modal que congela a ponte esperando alguém clicar. O assistente é instruído a descrever onde o botão está e pedir que a pessoa clique, e depois conferir o resultado lendo o projeto — nunca a prometer que vai apertá-lo;
- **um plano de teste em ordem segura**, montado a partir do que aquele plugin tem: estrutura, imports, simulação e só então execução. Cada passo diz por que existe.

Nenhum código-fonte do plugin sai da máquina: o briefing é o contrato declarado ao QGIS, não uma leitura do código.

### Novo — diagnóstico de provedor mal registrado

Dizer "este plugin não tem algoritmos" quando o provedor existe e está quebrado manda quem depura o próprio plugin para o caminho errado. Dois modos de falha passam a ser nomeados:

- **Provedor com `id()` vazio.** O objeto Python foi coletado depois de `addProvider()` porque a referência não foi guardada em `self`, e o que restou no registro não responde mais aos métodos virtuais. O aviso diz exatamente isso e como corrigir. Caí neste erro escrevendo o próprio ensaio, o que é a melhor evidência de que ele é comum.
- **Provedor registrado com zero algoritmos.** `loadAlgorithms()` não chamou `addAlgorithm()`, ou levantou exceção em silêncio.

Segundo plugin de ensaio, `tests/fixtures/botaoteste`, que só expõe menu, barra, painel e diálogo — sem nenhum algoritmo. Serve para provar que os dois lados do briefing estão certos: ele reporta zero algoritmos dirigíveis, detecta as quatro superfícies de interface, extrai os rótulos reais das ações e encerra o plano com "nada — parte deste plugin é só de interface".

### Corrigido — exercitar o plugin de outra pessoa (ou o seu segundo plugin)

O caso é o de quem está desenvolvendo um plugin e quer que a IA o teste: *eu peço → a IA traduz → o SIGMAI dirige o QGIS → o plugin executa*. A corrente inteira existia e parava no último elo.

- **`run_plugin_algorithm_generic_safe` fazia `import processing` cru.** `processing` é o *plugin* Processing: com ele desativado, ou num QGIS sem interface, o import falha e a resposta era `PROCESSING_NOT_AVAILABLE` — "QGIS Processing is not available", como se o QGIS não tivesse Processing, quando o núcleo tem tudo. O caminho comum (`run_processing`) já usava o bootstrap que contorna isso desde a 0.2.1; este tinha ficado para trás, e o efeito era **não executar algoritmo de plugin nenhum** nesse cenário.
- **`run_plugin_algorithm_safe` recusava sem dizer que havia outro caminho.** Ele tem uma lista fixa de adaptadores dedicados com uma única entrada (`topotrail:topotrail`), e a recusa dizia apenas "não está na lista permitida". Quem estivesse auditando o próprio plugin concluía, com razão, que o SIGMAI não executa plugin de terceiro. A recusa agora aponta `run_plugin_algorithm_generic_safe`, que serve qualquer plugin, e explica o que esse caminho faz a mais.
- **O caminho chamado "safe" era o menos protegido dos dois.** O adaptador dedicado encaminhava direto para a execução, sem classificação de risco, sem confirmações e sem guarda de sobrescrita — tudo isso só existia no caminho "genérico". Agora o dedicado passa pelo mesmo portão.

As instruções do servidor MCP passam a ensinar a sequência de auditoria — `inspect_plugin` e `check_plugin_structure`, `list_plugin_processing_algorithms`, `get_plugin_algorithm_info`, `dry_run_plugin_algorithm_generic`, `run_plugin_algorithm_generic_safe` — e a dizer o limite: só é alcançável por programa o que o plugin registrar como **algoritmo de Processing**. Botão de barra e janela de diálogo não são chamáveis assim; para esses o SIGMAI audita a estrutura, mas não aperta o botão.

Nova bancada `tools/exercise_third_party_plugin.py`, 23 verificações, e o plugin de ensaio `tests/fixtures/trilhateste` — que registra um provedor de Processing de verdade, com um algoritmo que mede o comprimento de uma trilha. A prova é de ponta a ponta: o algoritmo do plugin de terceiro executou pela ponte e devolveu 8.648,62 m para a trilha do Itaguaré, e 17.297,25 m com o fator de sinuosidade em 2,0.

### Corrigido — mapas de base e serviços OGC eram esqueleto

`load_wms_layer`, `load_wfs_layer`, `load_xyz_tile_layer` e `load_arcgis_rest_layer` apareciam no catálogo de comandos e no `sigmai_capabilities`, validavam a URL e então recusavam com `NETWORK_LOAD_NOT_ENABLED` — *"requires an explicit future network-enabled workflow"*. A capacidade era anunciada e não existia: nenhum mapa de base, nenhum serviço público de dados, nenhum WMS de órgão ambiental podia ser carregado. É o mesmo defeito de fundo desta versão inteira — o que a ferramenta diz que faz precisa ser o que ela faz.

Os quatro passam a carregar de verdade, com quatro guardas:

- **A camada inválida não entra no projeto.** Antes o padrão da casa seria devolver sucesso e deixar uma entrada morta na árvore de camadas; agora a recusa nomeia as três causas usuais em ordem de probabilidade — servidor sem resposta, nome de camada inexistente no serviço, CRS não oferecido por ele — e aponta `inspect_ogc_service`.
- **Atribuição é obrigatória.** Um mapa de base é dado de terceiro sob licença, e quase toda licença de tiles exige o crédito na peça publicada. Fontes conhecidas (OpenStreetMap, OpenTopoMap) já trazem o crédito correto; qualquer outra exige `attribution`, com recusa explicando o porquê. O crédito então **entra sozinho na linha de fonte do mapa** — depender de o usuário lembrar de repeti-lo em `data_source` é como perder a procedência.
- **Saída de rede é consentida.** Carregar de servidor externo exige `confirm_network=true`, do mesmo jeito que o acesso ao repositório de plugins.
- **Cache de tiles no disco não é rede.** Um XYZ apontando para `file://` é o caso de campo sem sinal, funciona sem confirmação, e é como esta correção foi testada de ponta a ponta.

### Novo — o mapa de base que não desenha nada

Uma camada XYZ com `zmax` 7 num mapa a 1:32.000 desenha um quadro em branco, aparece na legenda e passava com nota A. É o defeito "está na legenda e não no mapa", só que por resolução em vez de por recorte. O compositor converte a escala impressa em nível de tile pelo esquema Web Mercator, na latitude do mapa, e avisa quando a base não alcança: *"só tem tiles até o zoom 7, e a escala 1:32.000 exige o zoom 14"*.

### Corrigido — a recusa por confirmação não dizia o que passar

`CONFIRMATION_REQUIRED` respondia *"pass a confirmation flag"* sem nunca nomear quais. São cinco nomes aceitos, e quem chama tinha de adivinhar — o mesmo defeito que o compositor já não comete. A mensagem passa a listar as flags válidas para aquela ação e a avisar que algumas exigem uma segunda, específica (`confirm_network`).

### Corrigido — o guarda de extração de ZIP comparava caminhos por prefixo

Com destino `/x/plugins`, o caminho `/x/plugins_maligno` também "começa com" `/x/plugins` e passava na verificação. Nenhum arquivo escapou de fato — quem continha a extração era o `extractall` do CPython, que neutraliza os `..` —, mas depender de um detalhe de implementação do interpretador para não gravar fora da pasta do usuário não é garantia. A verificação passa a ser por relação de caminho.

### O que foi verificado, e o que não pôde ser

Nova bancada `tools/exercise_plugins_and_basemaps.py`, 31 verificações pela ponte HTTP de verdade — mesmo caminho que um assistente usa. Cobre carregamento de tiles do disco, recusas de URL, atribuição, consentimento de rede, catálogo de plugins, instalação a partir de ZIP, os bloqueios de repositório de terceiro e de HTTP, e a auto-proteção do SIGMAI.

Fica registrado o que **não** foi possível verificar neste ambiente: a rede para `plugins.qgis.org` e para servidores de tiles está bloqueada no contêiner de desenvolvimento. O que se provou foi que a falha de rede vira recusa explicada e não quebra; o download real do repositório oficial e o consumo de tiles online continuam por confirmar numa máquina com saída de rede.

Também por desenho, e não por defeito: **toda ação de plugin exige aprovação humana no painel do SIGMAI**, mesmo no modo "liberar nesta sessão". A IA busca, inspeciona, simula e propõe; quem instala, habilita ou desinstala é a pessoa, um clique por vez.

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

### Novo — a aba Ajuda

O painel tinha quatro abas voltadas a quem já entende de SIG: ligar a ponte, definir permissões, ver a auditoria, mexer em token e porta. Nenhuma dizia *o que fazer depois de conectar*. As chaves de texto da Ajuda existiam no código desde a 0.2.0 e a aba nunca havia sido construída.

A aba responde, sem jargão, às seis perguntas de quem nunca abriu um SIG: o que é isto; que frases dizer ao assistente (seis exemplos copiáveis, do "quais camadas estão abertas?" ao "dois mapas na mesma folha"); as duas coisas que o assistente vai perguntar de volta (fonte dos dados e autoria); o que significa a nota do mapa; por que o SIGMAI às vezes recusa; e onde os dados ficam. Em português e inglês, com troca de idioma.

### Corrigido — o pedido mais simples possível quebrava

Foram encontrados fazendo o pedido mínimo que uma IA faria sem saber nada do projeto: só o id da camada e um título.

- **Projeto sem sistema de coordenadas definido derrubava a composição.** Um CRS inválido não é geográfico nem projetado, então a reprojeção automática não disparava, os graus da camada eram tomados por metros, a escala saía 1:0 e a barra de escala estourava com um `ValueError` cru — a 300 linhas da causa. Agora o compositor herda o CRS da primeira camada válida e diz isso na resposta, ou recusa explicando como definir o CRS.
- **`choose_publication_scale` podia devolver zero.** Um denominador arredondado a zero significa escala abaixo de 1:1, ou seja, unidades erradas. O piso passa a ser 1, e o diagnóstico fica com quem tem contexto para dá-lo.
- **CART007 conferia presença de rodapé, não procedência.** O compositor sempre escreve o sistema de referência, a data e "Produzido com SIGMAI/QGIS"; com isso, um mapa sem nenhuma fonte e sem nenhuma autoria declaradas passava com nota A e chegava ao usuário parecendo citável. A regra agora exige que a linha de crédito diga de onde vieram os dados **e** quem assina o mapa, nomeando qual dos dois falta. É o mecanismo que faz o assistente perguntar ao usuário em vez de assinar sozinho.

### Corrigido — defeitos que só apareceram olhando o mapa impresso

A auditoria dava nota A a mapas com problemas visíveis a olho nu. Cada um destes foi encontrado abrindo o PNG exportado e comparando com o que o assistente tinha dito que produziria.

- **Campo de rótulo presente mas vazio.** O KML do CNUC tem um campo `Name` inteiramente nulo — o nome real mora em `Nome_UC`. Rotular por `Name` devolvia `labels` entre os itens criados e um mapa sem um único rótulo. O compositor agora recusa, dizendo que o campo está vazio e listando os campos que têm conteúdo.
- **Estilo embutido em KML/KMZ não gerava amostra na legenda.** O QGIS usa `QgsEmbeddedSymbolRenderer` quando o arquivo traz o próprio estilo; o traço fino herdado do Google Earth aparecia sem preenchimento, e a entrada da legenda saía em branco. Esse renderizador passa a contar como "sem intenção temática declarada" e recebe a paleta padrão, com nota explicando como preservar o original (`apply_style='none'`).
- **Dois polígonos com o mesmo preenchimento.** O preenchimento era um azul-claro fixo para toda camada de polígono; só o traço as distinguia, e no papel nada as distinguia. O preenchimento passa a ser derivado do próprio matiz de destaque da paleta Okabe-Ito.
- **O inserto vinha na cor aleatória do QGIS.** Um localizador existe para que o retângulo vermelho do recorte salte aos olhos; com o estado inteiro em roxo saturado, o retângulo desaparecia. As camadas que só existem no inserto passam a um cinza neutro; as que também estão no mapa principal mantêm a cor, que é como o leitor reconhece a mesma feição nos dois quadros.
- **A legenda ignorava o segundo painel.** Numa folha de comparação, a legenda listava apenas as camadas do quadro principal, e o leitor via no painel b) uma feição sem identificação. A legenda passa a cobrir os dois quadros, as camadas do segundo painel entram na mesma passada de estilo, e as regras CART020 e CART021 avaliam a união dos quadros — antes CART021 acusava de "fantasma" uma camada bem visível no painel b).
- **Camada que entra na legenda e não aparece no mapa.** Quando uma camada de contexto não tem nenhuma feição dentro do recorte, o compositor agora avisa: ela apareceria na legenda e não no mapa.

### Corrigido — ferramentas de teste

- **Encerramento seguro do QGIS em scripts autônomos** (`tools/qgis_lifecycle.py`). Uma camada criada num script e não adicionada ao projeto pertence ao Python: o interpretador a destrói no encerramento, depois de `exitQgis()` já ter derrubado o registro de provedores, e o destrutor em C++ acessa memória liberada. O resultado era uma falha de segmentação *depois* de o script imprimir todos os resultados. Não afeta o plugin dentro do QGIS, onde o ciclo de vida pertence ao QGIS e as camadas pertencem ao projeto.
- `tools/ci_compose_smoke_test.py` passou a exercitar também os caminhos de saída inválidos, e `tests/test_cartography_regressions.py` fixa cada defeito desta rodada.

## [0.2.1] — 2026-09-04

Correções encontradas ao testar a 0.2.0 no QGIS 4.1 e ao exercitar o catálogo de comandos contra a malha municipal do IBGE.

### Corrigido — o plugin não abria no QGIS 4

- **`QSizePolicy.Fixed`**, no construtor do painel. O PyQt5 aceita a forma curta do enum; o PyQt6 só aceita a qualificada. O painel morria ao ser construído e clicar no ícone não fazia nada. Como o plugin declara `qgisMaximumVersion=4.99`, era uma promessa quebrada.
- Mais quinze acessos do mesmo tipo, quatro deles graves: **`QgsLayoutExporter.Success`** (no caminho de exportação — todo `compose_map` quebraria no QGIS 4), `QgsVectorFileWriter.NoError`, `QgsProcessingParameterDefinition.FlagOptional` e os enums de geometria usados pela simbologia.
- Novo **`tools/check_qt6_compat.py`**: varre o pacote em duas passagens e enxerga também o acesso via dicionário (`imports["QgsUnitTypes"].LayoutMillimeters`), que nenhuma análise de atributos simples encontraria.
- Novo **`tools/qt6_panel_check.py`**: fabrica um `qgis.PyQt` apontando para o PyQt6 real e constrói o painel inteiro, como o QGIS 4 faz. Ambos viraram teste e job de CI, para que a classe de defeito não volte.

### Corrigido — defeitos achados exercitando o catálogo

- **Rodar um algoritmo do Processing apagava o projeto do usuário.** A transferência de camadas do contexto para o projeto estava na direção contrária, e o primeiro `buffer` levava o projeto junto. O exercitador passou a conferir, após cada bloco, que o número de camadas não diminuiu.
- **Uma exportação que não desenhou nada recebia nota A.** A regra de quadro em branco olhava só o RGB, e um PNG inteiramente transparente tem RGB zero — era contado como 100% de tinta. Passa a ignorar pixels transparentes e a recusar quadros de cor única.
- **Renderizar fora da thread principal do Qt produz arquivo vazio em silêncio.** O `QPainter` só desenha na thread da aplicação, e `exportToImage` devolve sucesso mesmo assim. O compositor agora recusa com uma mensagem que explica, em vez de entregar um mapa vazio.

### Melhorado

- O Processing deixa de depender do plugin Processing: executa pela API de núcleo quando ele não está disponível. Sem algoritmos registrados, o erro diz que o problema não é o nome e onde ativar o plugin; com nome errado, sugere os parecidos.
- Nova regra **CART064**: UTM esticado além da faixa útil da zona. Mapear o Piauí em UTM 23S dava eastings de 1.250.000 numa zona que termina em 834.000. O limiar da projeção automática passou a olhar o alcance em longitude, e recortes estaduais caem na Policônica do Brasil (EPSG:5880).
- **`tools/exercise_commands.py`** roda 41 comandos contra dados reais; **`tools/end_to_end_mcp_demo.py`** compõe um mapa complexo do handshake MCP ao laudo, sem chamar PyQGIS em lugar nenhum.

## [0.2.0] — 2026-09-04

Esta versão conserta os dois motivos pelos quais a ferramenta não entregava o que prometia: nenhum cliente de IA conseguia conectar, e os mapas que ela produzia não eram cartograficamente corretos — mas eram reportados como se fossem.

### Corrigido — conexão

- **O servidor MCP agora é MCP.** O que existia era um laço que lia `{"tool": ..., "arguments": ...}` de stdin, um formato próprio sem JSON-RPC 2.0, sem `initialize`, `tools/list` ou `tools/call`. Nenhum cliente MCP fala isso, então Claude Desktop, Cursor e Codex subiam o processo, não recebiam resposta e marcavam a conexão como falha. O servidor foi reescrito conforme a especificação: enquadramento JSON-Lines em stdio, handshake completo, negociação tolerante de versão de protocolo, e separação correta entre erro de protocolo e erro de execução — este último como `isError`, para que o modelo possa se corrigir em vez de ver uma falha opaca.
- **O servidor MCP viaja dentro do plugin** (`sigmai/mcp/sigmai_mcp.py`), sem depender do repositório, para que configurar seja informar um único caminho.
- **Porta com fallback.** A porta 8765 era fixa; ocupada, a ponte falhava com um erro de socket. Agora procura a próxima livre e registra a escolha.
- **Token estável entre sessões.** O token era gerado a cada abertura do QGIS, invalidando a configuração do cliente de IA todo dia. Passa a ser mantido no perfil do usuário, com opção de desligar e botão para gerar um novo.
- **O arquivo de sessão grava a porta real**, e não a constante — com o fallback de porta, apontava para o lugar errado.
- **HTTP/1.1 com conexão persistente.** Cada comando abria um socket novo.

### Adicionado — a IA pode, enfim, executar

- **Camada de consentimento.** Toda ação de escrita era forçada a `dry_run=True` no proxy MCP: nenhum mapa jamais era produzido. Agora há três modos — somente leitura (padrão), perguntar sempre, liberar nesta sessão — com caixa de confirmação que nomeia a ação, a categoria e os arquivos a gravar.
- **Sandbox de pastas de saída**, resistente a travessia de diretório.
- **Limites por sessão** para alterações, exportações e execuções de Processing.
- **Trilha de auditoria** de todas as decisões, visível no painel e exportável. Nenhum token aparece nela.
- Instalar, remover, recarregar plugins e executar Python **nunca** são cobertos pelo consentimento: continuam exigindo ação no painel e o Modo DEV.

### Adicionado — motor cartográfico

- **Layout consciente da página**, de A5 a A0, retrato ou paisagem, ou milímetros customizados. Os templates eram tabelas de milímetros fixos para uma única A4 paisagem; qualquer outro formato punha itens fora da folha sem aviso.
- **Ajuste de extensão à razão de aspecto do quadro antes da margem**, para que a margem pedida seja a obtida nos dois eixos.
- **Escala fechada na série cartográfica**, com a margem efetiva declarada. Quando a série não oferece um degrau próximo sem inflar a margem, usa uma escala de dois algarismos significativos em vez de desperdiçar meia folha.
- **Barra de escala dimensionada** para 15%–45% do quadro, terminando em número redondo e na unidade adequada. Antes era fixa em 10 km por segmento, o que dava barras de 4% do quadro em mapas municipais.
- **Grade de coordenadas com intervalo calculado.** A grade era habilitada sem intervalo; o padrão do QGIS é `0.0`, então nada era desenhado — e o orquestrador reportava a grade como criada.
- **Legenda com todas as camadas do quadro**, não só a principal.
- **Rosa dos ventos como símbolo** ligado ao norte da grade, no lugar de um rótulo com a letra N.
- **Reprojeção automática para o UTM adequado** quando o projeto está em coordenadas geográficas.
- **Simbologia padrão segura para daltônicos**, aplicada apenas a camadas que ainda não têm simbologia temática definida.

### Adicionado — regulamento e auditoria

- **26 regras cartográficas explícitas** em nove categorias, cada uma com severidade, motivo, referência e o comando que a corrige. Disponíveis à IA como dado por `sigmai_cartographic_rulebook`.
- **Auditoria de qualquer layout**, inclusive feitos à mão, por `audit_map_layout`.
- **Detecção de quadro em branco** por análise do raster exportado — a falha mais perigosa, porque todos os códigos de retorno dizem sucesso.
- O avaliador anterior só conferia presença de itens e classificava como "A — Professional map" um mapa com legenda incompleta, barra de escala inútil, grade invisível e rosa dos ventos escrita como texto. O mesmo mapa recebe **E — inválido** no regulamento novo.

### Alterado — interface

- **Painel acoplável** no lugar do diálogo único com onze botões de mesmo peso.
- **Fluxo de conexão em três passos numerados**, com destaque no passo pendente.
- **Configuração pronta para colar** por cliente de IA, com os caminhos absolutos corretos. O botão anterior copiava `SIGMAI pairing code: SG-1234-ABCD`, que não é configurável em lugar nenhum.
- **Autoteste de conexão** que percorre ponte, autenticação, arquivo de sessão, servidor MCP, projeto e modo de acesso, e nomeia a etapa que falhou.
- **Token oculto por padrão**, com aviso de que deve ser tratado como senha.
- Abas de **Acesso**, **Atividade** e **Avançado**; textos em português e inglês.

### Corrigido — robustez

- **Falsos positivos na varredura de tokens bloqueados.** A varredura rodava sobre o comando inteiro e recusava um campo chamado `code`, uma expressão contendo `"code"`, o plugin `PythonConsole` ou um título mencionando Python. Ficou restrita aos campos que carregam código; travessia de diretório em campos de caminho passou a ser recusada explicitamente.
- **Versão lida do `metadata.txt`.** Estava escrita à mão em quatro pontos, e o pacote publicado (0.1.1) já divergia do repositório (0.1.0). Há verificação em CI contra a reincidência.
- **Comando normalizado é o executado**, e não o cru: validava-se uma coisa e executava-se outra.
- **`IndexError` cru** ao instalar plugin sem perfil do QGIS virou erro explicado.
- **Fila processa até quatro comandos por tique**, contra um.
- **BOM UTF-8 removido de 19 arquivos**; no `pyproject.toml` ele impedia o pytest de ler a configuração.
- **`.gitattributes` com `text=auto eol=lf`**, encerrando a divergência CRLF/LF que fazia a árvore inteira aparecer como modificada.

### Testes

- 167 testes, sem exigir QGIS: núcleo numérico da cartografia, solucionador de layout, regulamento, consentimento, conformidade MCP contra o servidor real e geração de configuração de cliente.
- CI em três sistemas operacionais e duas versões de Python, mais um teste de fumaça que compõe e audita mapas dentro do contêiner oficial do QGIS.

## [0.1.1] — 2026-05-27

- Compatibilidade com Qt6 e diálogo responsivo.

## [0.1.0] — 2026-05-25

- Primeira versão pública: ponte local com token, registro de comandos, permissões, dry-run e fundações de cartografia, vetor, raster e diagnóstico de plugins.

[0.2.1]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.2.1
[0.2.0]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.2.0
[0.1.1]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.1.1
[0.1.0]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.1.0
