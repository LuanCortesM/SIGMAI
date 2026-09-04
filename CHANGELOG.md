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
