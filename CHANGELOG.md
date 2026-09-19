# Changelog

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o versionamento é [semântico](https://semver.org/lang/pt-BR/).

## [1.1.2] — 2026-09-19

A revisão científica do capítulo da dissertação que descreve o SIGMAI perguntou duas coisas ao regulamento: *em que você se apoia?* e *por que esse número?* As duas respostas estavam fracas, e esta versão as conserta sem mudar uma regra sequer.

### Fundamentos das regras

- **Duas regras citavam normas ABNT erradas.** CART003 (escala indicada) apoiava-se na NBR 6027, que trata de *sumário* de documentos; CART008 (sistema de referência declarado), na NBR 13133, que é execução de levantamento topográfico. Nenhuma diz o que lhes era atribuído. Oito outras regras citavam "convenção cartográfica", "boas práticas" ou "instruções a autores" sem fonte.
- **Cada regra agora nomeia o chão em que pisa**, nesta ordem: normativo — o Decreto nº 89.817/1984 (Instruções Reguladoras das Normas Técnicas da Cartografia Nacional; arts. 12 título, 13 legenda, 14 escala numérica *e* gráfica "sempre", 15 referenciais, 17 quadriculação, 18 diagrama de situação, 19 datas e fonte, 20 SI, 21 Sistema Geodésico Brasileiro), a Resolução IBGE PR nº 1/2015 (SIRGAS2000) e IBGE (1999) *Noções básicas de cartografia*; acadêmico — Brewer (2016), Slocum et al. (2009), Snyder (1987), Machado, Oliveira & Fernandes (2009), Robertson (1977), Okabe & Ito (2008), e as exigências de figura da PLOS ONE (8–12 pt na largura final) e da Rodriguésia (7 cm coluna simples, 15 cm página, 300 dpi); ou **decisão de projeto do SIGMAI**, dita com essas palavras, quando o número é nosso (6 pt, 15–45 % do quadro, 5 % de cobertura, ΔE < 15, 0,5 mm, 3 % de tinta, 10 mm). A documentação do QGIS passa a aparecer como `verificação:` — diz *como* a regra é conferida, não *por que* existe. `tests/test_rule_references_and_sensitivity.py` impede que uma referência vaga ou uma norma errada volte.
- O decreto regula a cartografia sistemática; o SIGMAI o aplica por analogia aos mapas temáticos científicos, e a documentação diz isso.

### Por que esse número

- **`tools/threshold_sensitivity.py`.** Compõe 138 mapas com os dados de teste (a matriz da bateria em PNG mais a matriz de dados), guarda a observação que o inspetor entrega ao regulamento e re-pontua tudo variando um limiar de cada vez; para o compositor, recalcula com as funções puras o ganho de troca de orientação/arranjo, a margem efetiva, o expoente das fontes e a grade de painéis. `docs/experiments/2026-09-19_sensibilidade_limiares/` tem as tabelas (`LEIAME.md`), os dados brutos e uma leitura (`LEITURA.md`).
- O que se aprendeu: máximo da barra, dominância do mapa, tinta em volta de item sobreposto, tolerância da legenda, cobertura do inserto e penalidades de erro e de conselho não mudam nota alguma em faixas largas; cobertura da faixa vazia, piso de 6 pt (acoplado ao piso do compositor), mínimo da barra e penalidade de aviso decidem, e ficam declarados como parâmetros; as pontuações observadas são só 80–100 de 5 em 5, logo "A" é "no máximo um aviso" e "B" é "até quatro"; ΔE < 15 está dentro da única janela — (12,1; 16,1) — que acusa os três pares de calibração sem acusar nenhum par da paleta de Okabe & Ito; e a sequência de preenchimentos do próprio SIGMAI tem **quatro** cores mutuamente distinguíveis por daltônicos, depois das quais a auditoria acusa.
- Os limiares do compositor viraram constantes nomeadas — `LAYOUT_SWITCH_GAIN` (1,12), `MAX_EFFECTIVE_MARGIN_PERCENT` (25), `FONT_SCALE_EXPONENT` (0,62) com `FONT_SCALE_MIN`/`FONT_SCALE_MAX` — em vez de literais espalhados.
- `sigmai_cartographic_rulebook` expunha `colour_vision_delta_e_min: 15.0` como literal; agora lê o valor de `vision.CONFUSABLE_DELTA_E`, publica `inset_min_coverage` e um campo `thresholds_provenance` que diz que os limiares são parâmetros declarados e onde está a análise.

### Testes

- O teste da receita mantém viva a referência ao dataset OGR enquanto lê o CRS (um dataset temporário era coletado e a camada virava `None` no caminho de contingência).

## [1.1.1] — 2026-09-19

Os mapas da 1.1.0 foram compostos de novo para o capítulo da dissertação, com os dados de teste do repositório e um leitor exigente. Quatro coisas apareceram que nenhum teste cobria, e cada uma virou regra numérica e teste antes de entrar.

### Compositor

- **Arranjo pela forma dos dados.** A orientação já era escolhida pela forma do recorte; o arranjo dos itens de apoio não. O Piauí em A4 retrato com a faixa inferior fechava em 1:6 300 000; com a legenda e a barra de escala numa coluna lateral, o quadro alto aproveita 12 % mais a página e o mapa sai em 1:5 000 000. O compositor calcula a escala nos dois arranjos (`coluna_lateral`, `faixa_inferior`) e troca quando o ganho passa de 12 % — o mesmo limiar da orientação —, com nota no resultado. O parâmetro `arrangement` (`auto`, `coluna_lateral`, `faixa_inferior`) força um deles.
- **Grade de painéis pela célula mais próxima do quadrado.** Três painéis em A3 paisagem ficavam em 2 × 2 com uma célula vazia; a grade passa a minimizar |ln(largura ÷ altura da célula)| mais 0,35 por célula vazia: 3 painéis em 270 × 150 mm ficam 3 × 1, em 190 × 250 mm ficam 2 × 2; quatro ficam 2 × 2; seis, 3 × 2.
- **Números da barra de escala na língua do mapa.** `QgsScaleBarSettings` escrevia "1,000 2,000 m" num mapa em português; a barra recebe um `QgsBasicNumericFormat` com o separador de milhar do idioma (`separador_milhar` nas cadeias do mapa) e a vírgula decimal quando o milhar é ponto.

### Simbologia

- **O preenchimento novo desvia dos que já estão em uso.** Quando `apply_style=missing` preserva o estilo de uma camada, o próximo preenchimento da sequência podia ser confundível com ela (o laranja da composição anterior ao lado do laranja da atual — CART070 reprovava o mapa do próprio SIGMAI). `_next_polygon_fill` recebe as cores preservadas e pula as que `vision.confusable_pairs` marca.

### Ponte e testes

- **Estado do projeto na thread do Qt.** `status` lia `QgsProject.instance()` da thread do servidor HTTP; a ponte passa a servir um instantâneo tirado (e renovado) na thread principal.
- Testes: a verificação de Qt6 não importa mais PyQt6 num processo PyQt5 (`importlib.util.find_spec`); `test_catalogue_is_reality` inicia o `QgsApplication` no `setUpModule` e guarda a referência (um `app` local era coletado e derrubava o processo em `QgsProject.clear()`); o teste da receita lida com uma falha intermitente do processo de teste (cerca de 1 corrida em 10 da suíte inteira, nunca em isolamento) em que `QgsCoordinateReferenceSystem.fromWkt` passa a recusar qualquer WKT enquanto EPSG, `fromProj` e o OSR continuam a funcionar: o CRS gravado no GeoPackage é conferido pelo OSR (EPSG:31984) e só então atribuído pela autoridade, com o motivo no comentário do teste.

## [1.1.0] — 2026-09-19

A versão que nasce da pergunta feita depois do experimento da 1.0.3: *o que o SIGMAI pode fazer que um agente escrevendo PyQGIS não faz de graça?* A resposta foi uma lista de treze coisas que nenhum dos dois agentes fez sozinho — auditar rótulos perdidos, saber onde uma área fica antes de desenhá-la, deixar o mapa reproduzível, dimensionar uma figura para a coluna de uma revista, desfazer um erro — e todas as treze estão aqui. Nada de novo entra sem regra ou teste: são 651 testes (94 novos), a bateria de liberação passou nos sete portões (683 verificações) e a versão foi operada de ponta a ponta por um assistente emulado sem acesso ao computador — o que ele encontrou, e o que mudou por causa disso, está em `docs/experiments/2026-09-19_emulacao_1.1.0/`.

### Novo — a auditoria vê o que o leitor vê

- **CART068 — rótulos colocados.** O mapa é renderizado uma segunda vez com `CollectUnplacedLabels`, e cada rótulo que o motor de rotulagem não conseguiu colocar é contado por camada. O mapa do agente direto tinha 207 nomes de sítio e lugar para 40: parecia rotulado e não estava.
- **CART069 — o quadro é ocupado pelos dados.** Cobertura geométrica dos polígonos numa grade 3×3 (até 5 000 feições por camada; acima disso, a tinta do PNG). Uma coluna ou linha inteira com menos de 5 % de cobertura significa que a forma da página não é a dos dados — o Piauí em folha paisagem — e o laudo nomeia a faixa ("coluna oeste", "linha sul"). O critério de cobertura total foi tentado e rejeitado: um mapa de estado legítimo com margem larga reprova nele; uma faixa vazia não mente.
- **CART070 — cores distinguíveis por daltônicos.** As cores de preenchimento e contorno de cada camada visível (e de cada classe dos estilos categorizado e graduado) são transformadas pelas matrizes de protanopia, deuteranopia e tritanopia de Machado, Oliveira & Fernandes (2009, *IEEE TVCG* 15(6)) e comparadas em CIE L\*a\*b\*; um par com ΔE\*ab abaixo de 15 em qualquer simulação é apontado, e a correção sugerida é a paleta de Okabe & Ito (2008). Nova categoria `simbologia`.
- **CART071 — fontes legíveis na largura impressa.** Quando a composição foi pedida como figura de revista (ou a auditoria recebe `print_width_mm`), cada corpo de fonte é reduzido na proporção largura impressa ÷ largura da página. Uma legenda de 7 pt numa A4 vira 3 pt numa coluna simples.
- **CART072 — a legenda cabe na caixa.** `QgsLegendRenderer.minimumSize` diz o tamanho que o conteúdo precisa; quando passa da caixa em mais de 0,5 mm, o QGIS corta os nomes na borda e desenha por cima do que vier abaixo, sem avisar. Foi o que a emulação desta versão mostrou numa figura de coluna simples: "(IBGE, 2024)" sobre a linha de crédito.
- **CART042 aceita sobreposição legítima**: um item sobre o quadro do mapa não é defeito quando o anel de 3 mm em volta dele tem menos de 3 % de tinta — a legenda sobre o mar, o inserto sobre o vazio.

### Novo — o compositor sabe mais

- **Orientação automática** (`orientation: "auto"`): a página é escolhida pela forma dos dados, com o ganho de escala calculado nos dois sentidos; só troca quando o ganho passa de 12 %.
- **Figura para revista**: `journal_column` (`single` 85 mm, `one_and_half` 120 mm, `double` 175 mm) ou `figure_width_mm`/`figure_height_mm`, com a página resolvida em milímetros a partir da extensão e o template `publicacao`; formatos `tif` e `jpg` para os sistemas de submissão; o corpo das fontes é auditado na largura final.
- **Painéis**: `panels=[{...}, {...}, {...}]` compõe três ou mais quadros com letras (a), (b), (c), grade de duas ou três colunas conforme a página, escala comum quando pedida (`second_map` continua para dois).
- **Procedência por camada**: `data_source` aceita um objeto `{camada: fonte}` (por id ou nome), a fonte de cada camada sai na legenda ao lado dela, e a camada que declara fonte nos próprios metadados é usada quando o pedido não diz.
- **Anotações de contexto** (`add_context_annotations`): a divisa e os nomes de uma camada de contexto viram camadas só-de-rótulo (nome no polo de inacessibilidade de cada polígono, `extra_labels` livres, opcionalmente gravadas em GeoPackage) — o mapa passa a dizer em que estado está.
- **Mapa de campanha** (`compose_campaign_map`): sítios sobre trilha sobre área sobre contexto, inserto de localização, recorte que contém pontos *e* trilha, rótulo pelo campo de nome detectado (em duas camadas de dicas, com verificação de distinção — `track_fid` não é nome), no máximo 60 pontos rotulados automaticamente, e a tabela de coordenadas em CSV (`export_coordinate_table`: E/N no CRS pedido mais lon/lat em EPSG:4326).
- **Rótulos de polígono** ficam dentro da feição (`centroidInside`), e camadas só-de-rótulo não entram na legenda.
- **A legenda cabe por construção**: nomes compridos são quebrados na largura da coluna (não só a fonte); depois de posicionada, a legenda é medida com `QgsLegendRenderer.minimumSize` e, se não cabe, a fonte desce até 6 pt e em seguida as fontes por camada saem das entradas (ficam na linha de crédito e na receita), com nota no resultado.
- **Paleta de polígonos que passa na própria regra.** Os preenchimentos eram o matiz de Okabe & Ito clareado 82 %; perto do branco os matizes convergem e CART070 reprovava o mapa que o SIGMAI compunha (azul-claro × verde-claro a ΔE 2,9 sob tritanopia). A sequência nova (`POLYGON_FILLS`) alterna claridade e matizes de eixos opostos — laranja firme para o assunto, azul quase branco para o contexto, amarelo claro, verde-azulado médio — e os quatro primeiros ficam a ΔE ≥ 19 em qualquer simulação; um teste garante.
- **A auditoria de um layout composto usa a receita**: margens e largura impressa vêm da composição, em vez dos 10 mm padrão que reprovavam a figura de revista (margens de 5 mm por desenho) em CART041 e deixavam CART071 sem rodar.

### Novo — reproduzível, citável, reversível

- **Receita do mapa**: cada composição guarda em `sigmai/recipe` (propriedade do layout) e no `tEXt` do PNG (`sigmai:recipe`) os parâmetros, as camadas com provedor, fonte, CRS, contagem e SHA-256 do arquivo local, as versões do QGIS e do SIGMAI, o caminho do projeto e o laudo. `get_map_recipe` lê do layout, do PNG ou do JSON (`recipe_path`) e diz quais dados mudaram desde então; `recompose_from_recipe` refaz com `overrides`, achando as camadas por id e, na falta, por nome; `describe_map_for_methods` escreve o parágrafo de Métodos em pt-BR, en ou es, com a referência bibliográfica do software.
- **Desfazer**: antes de cada escrita no projeto (`safe_write`/`project_write`, sem `dry_run`) o registro guarda o estilo, o nome, os rótulos e a codificação de cada camada citada, o XML de cada layout citado e a lista do que existia. `undo_last_action` restaura o que foi tocado e remove o que foi criado; arquivos em disco ficam, e a resposta lista quais. `list_undo_history` mostra a pilha (20 entradas). Nova categoria de consentimento **Projeto**, nas nove línguas da interface.

### Novo — o assistente pergunta antes de assumir

- **`spatial_relationship`**: fração de cada feição de A dentro de B, feições de B que tocam A, e a mais próxima com distância geodésica (`QgsDistanceArea`, elipsoide do projeto), `radius_m` para limitar a busca; nomes pelo campo de nome ranqueado (`CD_UF` não é nome), com nota quando o nome vem com "�".
- **`set_layer_encoding`** e `encoding_problem` em `get_layer_info`: "Piau�" é detectado e corrigido com a codificação certa.
- **Planilha de pontos vira camada**: `load_vector_layer` aceita `.csv`/`.txt`/`.tsv` pelo provedor `delimitedtext`, com separador, ponto decimal (`-45,059`) e codificação detectados no arquivo e as colunas de coordenada reconhecidas pelo nome (lon/lat, longitude/latitude, x/y, este/norte…) ou ditas em `x_field`/`y_field`; longitude/latitude sem `crs` assume EPSG:4326, E/N sem `crs` é recusado com o nome das colunas. Os sítios de uma campanha quase nunca chegam como shapefile — na emulação o assistente não tinha como pô-los no mapa.
- **`project_briefing`** (`sigmai_briefing`): numa chamada, tudo o que as duas emulações levavam cinco para descobrir — versões, projeto, camadas com campo de nome e exemplos, layouts (e quais o SIGMAI compôs), acesso, regulamento, templates, caminhos recomendados.

### MCP

Vinte ferramentas (nove novas: `sigmai_briefing`, `sigmai_spatial_relationship`, `sigmai_add_context_annotations`, `sigmai_campaign_map`, `sigmai_export_coordinate_table`, `sigmai_map_recipe`, `sigmai_recompose_from_recipe`, `sigmai_methods_paragraph`, `sigmai_undo`); o esquema de `compose_map` publica `orientation: auto`, `panels`, `journal_column`, `figure_*`, `recipe_path`, `data_source` por camada e `subject_layer_id` em lista; as instruções do servidor começam pelo briefing e pela relação espacial.

### Corrigido

- A receita quebrava com camada raster (`featureCount` inexistente) — encontrado pela bateria de liberação, coberto por teste.
- Acesso a `QFont.AbsoluteSpacing` incompatível com Qt6 nas anotações de contexto.
- O teste da receita dependia do CRS deixado por outro teste; fixa o próprio.
- `extra_labels` de `add_context_annotations` aceita `{text, lon, lat}` em graus, além de `{text, x, y, crs}` — a forma que o assistente escreveu na emulação.

## [1.0.3] — 2026-09-06

Um experimento para responder "o SIGMAI serve para quê, se a IA pode escrever PyQGIS direto?": um agente **com acesso total ao computador**, proibido de usar o plugin, atendeu o mesmo pedido da pesquisadora da versão 1.0.2 em PyQGIS puro. O mapa dele — A4 retrato completo, com título, subtítulo, grade anotada, legenda, barra e escala numérica, rosa dos ventos, inserto com quadro-guia, bloco "FONTES DOS DADOS", autoria e data — foi então auditado pelo `sigmai_audit_layout`, que prometia funcionar "inclusive num layout feito à mão". Deu **nota D (50/100)**: "nenhum item com papel de título", "falta a linha de fonte". O laudo mentia, e a mentira tinha três camadas.

### Corrigido — a auditoria era cega para layouts que o SIGMAI não compôs

- **Itens sem `id` eram descartados pelo inspetor.** O QGIS deixa o id vazio em tudo o que se cria pela interface, e scripts raramente o preenchem: a observação de um layout feito à mão saía sem nenhum item, e o regulamento reprovava título, legenda, fonte, norte e grade que estavam lá. Os itens recebem um id sintético (`label#3`, `map#2`) e o papel é inferido do tipo, do texto e da geometria: o título é o rótulo de maior corpo, o subtítulo o rótulo logo abaixo dele, a procedência o rótulo que fala de fonte ou autoria, o quadro principal o maior mapa, os demais quadros — menores e com quadro-guia — são insertos, e uma imagem cujo caminho diz `NorthArrow` é a rosa dos ventos. Cada papel inferido vem marcado (`role_inferred`); um layout do SIGMAI, com ids explícitos, sai intocado.
- **A página 210×297 era lida como paisagem.** `resolve_page` com dimensões explícitas e sem orientação caía no padrão paisagem e trocava os eixos: tudo abaixo de 210 mm ficava "fora da página" (CART040) e a tinta do quadro era medida no lugar errado (CART062 acusava quadro em branco). Dimensões explícitas passam a dizer a orientação por si; `audit_map_layout` mede a tinta no quadro principal (o maior), não no primeiro que aparecer — que era o inserto.
- **`list_layouts` também descartava itens sem id**: um layout feito à mão aparecia vazio. Descreve todos, com `id_missing: true`.
- **"FONTES DOS DADOS" como cabeçalho não contava como fonte** — CART007 só reconhecia "Fonte:" com dois-pontos. Os cabeçalhos usuais em pt, en, es, fr, de e it passam a contar.
- **Camadas só-de-rótulo eram cobradas na legenda.** Uma camada de pontos com `QgsNullSymbolRenderer`, usada só para posicionar o nome do estado, não desenha símbolo nenhum; CART020 exigia entrada para ela. A observação passa a listar `label_only_layer_names`, e a regra as dispensa (a regra dos fantasmas, CART021, continua a aceitá-las).

Com as correções o mapa do agente direto recebe **B (90/100)**, com dois avisos legítimos — margens de 6 mm (o SIGMAI assume 10 mm quando não há PageSpec) e sobreposições (nota sobre o quadro, rosa dos ventos dentro do quadro, caixas de título e subtítulo encostadas). Os 17 testes novos (`tests/test_foreign_layout_audit.py`) fixam cada degrau, inclusive um layout construído em PyQGIS puro sem nenhum `setId`.

### O que o experimento mediu (registrado em docs/MCP_SERVER.md e docs/experiments/2026-09-06_pyqgis_direto_vs_sigmai/)

Mesmo pedido, mesmos dados, mesmo modelo. Pelo SIGMAI, sem acesso ao computador: 17–18 chamadas MCP, 5,5 min, 5–7 mil tokens gerados, nota A. Em PyQGIS puro, com acesso total: 15 execuções (5 iterações do script de 353 linhas), 19 min, 32 mil tokens gerados, 12 armadilhas da API do QGIS resolvidas por tentativa e erro, nota B. O mapa direto é visualmente mais rico (divisa estadual, nomes dos estados, bloco de fontes com decreto e CNUC); o do SIGMAI é reproduzível por uma chamada JSON, ficou registrado na trilha de consentimento e nunca executou código no computador da usuária.

## [1.0.2] — 2026-09-05

Um teste diferente dos anteriores: um agente **emulando um assistente de IA sem acesso ao computador** — proibido de ler qualquer arquivo ou código, só o cliente MCP na mão — recebeu o pedido informal de uma pesquisadora ("mapa do parque em A4 com os municípios em volta e um mapinha de localização") e teve de se virar. Nas duas rodadas o mapa saiu com nota A; o que interessa é o relatório do que o obrigou a adivinhar. Cada item virou correção, e `tools/remote_ai_lab.py` + `tools/mcp_call.py` reproduzem o cenário para quem quiser repetir.

### Corrigido — o assistente não tinha como saber

- **Nome de comando errado recebia `ACTION_NOT_ALLOWED`** ("get_features"), a mesma resposta de uma ação proibida. Passa a `UNKNOWN_ACTION` com sugestões pelo nome (`sample_features`, `query_features`…); `ACTION_NOT_ALLOWED` fica para as ações catalogadas e desabilitadas, com o motivo.
- **`sigmai_capabilities` tinha 70 KB e nenhum filtro** — não cabia no contexto do assistente, que passou a chutar nomes. Aceita `group`, `search` e `names_only`, e **cada comando lista os parâmetros que lê** (`parameters`, com `parameters_complete` dizendo se a lista é exata), extraídos do próprio manipulador.
- **Parâmetro que o comando não lê era engolido em silêncio**: `sample_features` com `filter=…` devolvia as dez primeiras feições como se tivesse filtrado; `apply_boundary_highlight` ignorava `stroke_color`. Para os 145 comandos cujo manipulador lê só nomes literais, a ponte devolve `warnings: ["Parameters not read by 'sample_features' and therefore ignored: filter…"]`; para os que repassam `params` a outra função nenhum aviso é emitido, porque a extração não tem como saber. `apply_boundary_highlight` passa a aceitar cor e espessura.
- **`sigmai_layer_details` prometia amostra, estilo e validade e entregava só os metadados.** Agora compõe as quatro leituras. Foi assim que a segunda rodada descobriu, pelos atributos do próprio KML (`municipios: "Granja; Viçosa do Ceará"`, `Fonte: CEUC…/SEMA`), que o Parque Estadual das Carnaúbas fica no Ceará e não no Piauí — e corrigiu o pedido da usuária em vez de desenhar o que ela pediu errado.
- **`inspect_layer_style` não mostrava o estilo** (só o tipo do renderizador): quem aplicava uma cor não tinha como confirmar. Mostra o símbolo — cores, contorno, largura, preenchimento — e, para estilos categorizados e graduados, as classes.
- **`sigmai_plan_map` e `sigmai_compose_map` não publicavam 14 parâmetros que o compositor aceita** (`production_date`, `auto_projected_crs`, `margin_mm`, `round_scale`, `include_logo`…), e o esquema é fechado: o regulamento mandava usá-los e o cliente não conseguia. Os dois passam a publicar o esquema completo, o mesmo para ambos; um teste o confere contra `KNOWN_PARAMETERS`.
- **`list_layouts` prometia página e itens e devolvia nome e contagem.** Descreve páginas, itens e quadros de mapa (CRS, escala, camadas, grade, insertos).
- **`status.project_loaded` era `null`.** Agora é verdadeiro/falso, com caminho e contagem de camadas.

### Corrigido — o que o assistente acertou por dedução e não devia precisar

- **A nota do inserto dizia "12x a largura do recorte" mesmo quando ele tinha sido ajustado ao estado inteiro.** O assistente, lendo isso, refez o mapa com um fator maior sem necessidade. A nota diz qual camada de contexto ajustou o inserto, e a descrição de `inset_zoom_factor` diz quando ele se aplica.
- **A auditoria não olhava o inserto.** Nova regra **CART067** (aviso): o inserto tem de mostrar a extensão inteira das camadas de contexto e conter o recorte principal — a observação passa a medir a fração de cada camada visível no inserto.
- **`apply_single_symbol` seguido de `compose_map(apply_style="missing")` reestilizava a camada recém-estilizada**, e o relatório dizia "estilizada" contradizendo a documentação. As ações de simbologia marcam a origem do estilo na camada (`sigmai/style_origin`), e a paleta da composição também: um estilo aplicado pelo assistente é preservado, e o mesmo mapa refeito **não muda de cor**.
- **Cada composição criava "Título (2)", "Título (3)"…** Um `layout_name` que já existe passa a ser substituído; sem nome explícito, a nota avisa do acúmulo.
- **"UTM zone 24S" num mapa em português.** O nome do CRS na linha de crédito sai na língua do mapa (zona, Policônica do Brasil) para pt-BR, es, it e fr; o código EPSG continua ao lado.

### O que ficou registrado e não foi feito

O slot do inserto é paisagem mesmo quando o estado é retrato (o Piauí ocupa uma coluna estreita no centro); um slot adaptado à proporção da camada de contexto ficaria melhor. A cor da paleta depende da posição da camada na lista, então dois mapas com listas diferentes podem colorir a mesma camada de modo diferente (a preservação da origem do estilo resolve o caso do mesmo mapa refeito). Não há consulta espacial por retângulo ("quais municípios caem neste recorte"); `query_features` aceita expressão.

## [1.0.1] — 2026-09-05

Dois defeitos apontados no primeiro uso da 1.0.0 dentro do QGIS.

### Corrigido — o painel no tema escuro

No *Night Mapping* (e em qualquer tema escuro do QGIS) o painel ficava ilegível: botões de rádio com fundo preto e texto escuro, rótulos de formulário cinza-claro sobre cartão branco, faixas escuras atrás dos campos numéricos e dos títulos das caixas de grupo. A causa: a folha de estilo só tinha a paleta clara e só estilizava os widgets que nomeava; tudo o que ficava de fora herdava o tema do aplicativo, e o resultado era uma mistura dos dois.

`ui/theme.py` passa a ter **duas paletas com o mesmo desenho** — a escura não é a clara invertida: superfícies azul-ardósia, o verde da marca um tom acima para manter contraste, avisos em pastel sobre fundo fechado; todo par texto/fundo é conferido acima de 4,5:1 (WCAG AA) por um teste — e uma **folha completa**, que declara fundo e texto de todo widget do painel: rótulos, rádios e caixas de seleção (com indicadores desenhados pela própria folha, porque o círculo do rádio sumia no escuro), o viewport das áreas de rolagem, os popups das listas, os spinboxes, as barras de rolagem, as células de tabela e o título das caixas de grupo. O tema é escolhido pela paleta do QGIS (`resolve_theme`) e reaplicado quando o Qt anuncia troca de paleta, então mudar o tema do QGIS com o painel aberto surte efeito na hora; *Avançado ▸ Aparência* força claro ou escuro.

De quebra, dois defeitos de largura que só apareciam noutras línguas: o negrito das abas era pintado pela folha mas medido em regular, e "Verbindung" saía cortado (a fonte do `QTabBar` passa a ser negrito de verdade); e o cabeçalho, sem quebra de linha, impunha ao painel 600 px de largura mínima em alemão — mais que o dock do QGIS. As abas rolam num dock estreito em vez de sumir.

### Novo — nove línguas na interface

O botão que alternava PT/EN virou uma **lista no cabeçalho** com nove línguas — Português (Brasil), English, Español, Français, Deutsch, Italiano, 日本語, 简体中文, 繁體中文 — cada uma com o nome escrito nela mesma, porque quem não lê português precisa achar a sua língua sem ler português. As tabelas vivem em `sigmai/ui/strings/` (um módulo por língua, 190 textos cada); um teste garante que toda chave existe em toda língua com os mesmos marcadores de formatação, que nenhuma tabela é cópia do português e que o pedido de confirmação do Modo DEV pede uma palavra que o plugin aceita.

Também passam a ser traduzidos o que antes saía em português em qualquer idioma: o **autoteste** do passo 3 ("Ponte local — responde em…"), o **diálogo de consentimento** (categoria, descrição, "Grava em"), a **trilha de atividade** e as **instruções de cada cliente de IA** no passo 2. O registro de consentimento continua guardando o nome canônico da categoria, para que trocar de língua não esqueça o que o usuário já aprovou. O código de língua é tolerante (`pt`, `en-US`, `zh-TW`, `jp` resolvem). Os textos que o compositor escreve nos mapas continuam em `cartography/maptext.py`, com quinze línguas.

## [1.0.0] — 2026-09-05

Primeira versão estável. O que separa a 1.0.0 da 0.2.2 não é uma funcionalidade nova, e sim uma propriedade: **o catálogo é igual à realidade**. Toda ação que o `get_capabilities` anuncia executa o que o nome diz; toda ação que não executa foi desabilitada com o motivo escrito; e uma bateria de liberação reproduzível decide se a versão sai.

### Catálogo igual à realidade — 24 esqueletos resolvidos

A auditoria da 0.2.2 encontrou 24 ações que só recusavam com uma marca de "planejado" ou devolviam sucesso sem fazer nada. Dezenove passaram a fazer o que o nome diz; treze foram desabilitadas (208 ações habilitadas de 221 catalogadas):

- **`execute_workflow` executa** passo a passo pelo mesmo `CommandRegistry.execute` da ponte — o mesmo `validate_command`, consentimento, confirmação e `dry_run` por passo que uma chamada direta atravessa. Para no primeiro passo que falha e devolve o que executou e o que falta. Um passo não pode apontar de volta para `execute_workflow`/`run_workflow_template` (`WORKFLOW_UNSAFE_ACTION`). `run_workflow_job` e `run_map_export_job` honram o `dry_run` do chamador em vez de responder "completed" sem ter executado nada.
- **`export_report_pdf` gera PDF** com o `QTextDocument`/`QPdfWriter` que o próprio QGIS traz; `create_report` descreve o projeto real (camadas com tipo, CRS, contagem de feições e extensão; layouts existentes) em vez de duas seções fixas.
- **`repair_data_source_path`, `test_service_connection`, `list_ogc_connections`, `list_database_connections`, `gpx_track_length`, `map_gpx_track`** fazem o que o nome diz: repontam a fonte de uma camada quebrada, testam um serviço com tempo-limite curto, listam as conexões OGC e de banco gravadas nas configurações do QGIS (sem expor credencial), medem uma trilha GPX no elipsoide e a compõem num mapa pelo `compose_map`.
- **`apply_scientific_polygon_style`, `_line_style`, `_point_style`** recusam camada de outra geometria (`GEOMETRY_TYPE_MISMATCH`) — as quatro ações eram aliases do mesmo perfil e produziam saída idêntica; **`apply_boundary_highlight`** ganhou perfil próprio (contorno escuro, sem preenchimento).
- **Desabilitadas, com o motivo em `capabilities.limitations`:** a família de atlas (`create_atlas`, `configure_atlas_coverage_layer`, `set_atlas_filter_expression`, `set_atlas_sort_expression`, `export_atlas_pdf`, `export_atlas_images`, `generate_map_book`) — um atlas de verdade exige `QgsLayoutAtlas`, que esta versão não implementa, e o que existia era um registro em memória fingindo ser um; a família PostGIS (`inspect_database_connection`, `test_postgis_connection`, `list_postgis_tables`, `load_postgis_layer`, `inspect_postgis_layer`) — um teste real contra o provedor `postgres` mostrou `QgsProviderConnectionException` devolvendo a string de conexão inteira, **senha em texto puro incluída**, e sem um servidor PostGIS para validar a redação em todos os caminhos de erro, cinco ações desabilitadas são mais seguras que cinco que ninguém testou; e `create_map_hierarchy`, um nome de escrita para um alias de leitura. Uma ação desabilitada não existe para o assistente: a ponte a recusa com `ACTION_NOT_ALLOWED`, e `requires_confirmation`/`dry_run_supported` deixam de listá-la. Um teste varre as ações habilitadas atrás de marcas de esqueleto para que a classe de defeito não volte.

### Bateria de liberação — `tools/release_battery.py`

Os testes unitários provam cada peça e os exercitadores provam cada caminho; o que nenhum deles prova é a combinação. A bateria é a matriz: **7 portões, 672 verificações, todas obrigatórias** — as 384 combinações de template × página × orientação × formato × elemento omitido (grade, legenda, inserto); 15 tipos de dado (ponto solto, linha, GPX, KML, multipolígono, raster, CRS misturados, estado inteiro, assunto pequeno em contexto grande, escala imposta, comparação com escala igual e própria, rótulos, camada vazia recusada); as 15 línguas de `map_language`, com a auditoria lendo a língua escrita; 16 recusas nomeadas (página, orientação, dpi, formato, template, campo, língua, escala, camada, parâmetro, pasta, sobrescrita, margem, flag ambígua — nunca traceback, nunca arquivo); folhas de comparação em 10 escritas; o catálogo contra a ponte (toda ação habilitada tem função registrada sem marca de esqueleto, toda desabilitada é recusada); e idempotência. A primeira corrida encontrou os defeitos abaixo. `--full` roda a matriz inteira em pouco mais de um minuto.

### Corrigido — o que a bateria encontrou

- **A auditoria fabricava uma grade-fantasma.** `QgsLayoutItemMap.grid()` *cria* uma grade (habilitada, intervalo zero) quando o quadro não tem nenhuma. O inspetor lia por esse caminho: num mapa pedido com `include_grid=false`, a própria observação criava a grade, CART026/CART027 reprovavam o mapa e CART010 aprovava uma grade que não existia. A leitura passa pela pilha (`grids()`), que não altera o layout inspecionado.
- **A barra de escala invadia o rodapé.** O item de barra tem altura própria (segmento + espaço até o rótulo + texto + folga), ~10,6 mm com os padrões do QGIS, e ignorava a faixa reservada — em A5 paisagem, template minimalista, a faixa tem 7 mm e o excedente caía sobre a linha de crédito (CART042). Segmento e folgas passam a ser derivados da faixa; o que ainda sobrar sobe para a calha, nunca desce sobre o rodapé.
- **CART007 acusava falta de fonte em mapas completos em japonês, chinês e francês.** O marcador de procedência era derivado tirando o `:` ASCII; "出典：" (dois-pontos de largura inteira) e "Source : " (espaço francês antes do dois-pontos) viravam marcadores que nunca batem. A comparação passa a normalizar os dois lados.
- **CART043 contava só o quadro principal** numa folha de dois painéis (27% da área útil, "apoio consumindo a página") quando os mapas ocupam mais da metade. Soma todos os quadros; o inserto continua fora, porque é apoio.
- **`output_path` do Windows num QGIS em Linux/macOS gravava um arquivo chamado literalmente `C:\Users\...\mapa.png` na pasta corrente e reportava sucesso** — para o POSIX aquilo é um nome relativo com barras invertidas. Um caminho relativo ia parar na pasta corrente do processo do QGIS, que o usuário não conhece. `normalize_output_path` (toda ação da ponte que escreve arquivo) e `compose_map` passam a recusar os dois, nomeando o sistema e pedindo o caminho absoluto; a ponte devolve a recusa como `BAD_REQUEST`, não como erro interno. `..` num caminho absoluto é normalizado.
- **`format='imagen'` sem `output_path` era aceito calado** — o formato só era validado na hora de exportar. Passa a ser recusado com a lista sempre que informado.
- **`map_language` desconhecido caía em português com uma nota.** O assistente via a nota; o usuário via um mapa em língua que não pediu. Passa a recusar com a lista das quinze línguas, o mesmo tratamento de `page` e `template` (a grafia continua tolerante: `EN`, `en_US`, `jp`, `zh-TW` resolvem).
- **A simbologia era aplicada antes da última validação de parâmetro.** Uma página inexistente recusada deixava o projeto do usuário com a simbologia trocada por um mapa que não saiu. A prévia (sem mutação) continua no início; a aplicação de verdade vai para depois da última recusa.
- **Uma recusa redigida errado:** `.replace(",", ".")` na frase inteira da recusa de `scale` trocava as vírgulas do texto por pontos ("ocupam. cortando parte deles."). O mesmo padrão em CART064 e CART066. Os números passam por um formatador; a frase, não.

### Melhorado

- **O denominador da escala segue a língua do mapa:** `1:250,000` em inglês, `1:250 000` em francês e russo, `1:250.000` em português, espanhol, alemão, italiano e grego — o símbolo de agrupamento do Unicode CLDR de cada língua, conferido contra o `QLocale` do Qt. Um leitor anglófono lia "1:250.000" como duzentos e cinquenta.
- **Painéis sem `panel_title` recebem rótulos simétricos** ("Painel A"/"Painel B" na língua do mapa). Repetir o título da folha sobre o painel da esquerda punha o mesmo texto duas vezes a dois centímetros de distância.
- `margin_percent` limitado a 0–100. O runner de cenários pré-cria os alvos de sobrescrita e só injeta confirmação na saída que ele mesmo inventou, para que os cenários de sobrescrita testem o padrão real do compositor.

### O que esta versão não verificou

Duas coisas não têm como ser provadas do ambiente em que a bateria roda: a abertura do plugin dentro de um QGIS 4.1 com interface (o painel é construído contra PyQt6 de verdade em `tools/qt6_panel_check.py`, mas sem a janela do QGIS), e o download ao vivo de `plugins.qgis.org` e de tiles XYZ (a rede é bloqueada; os carregadores são exercitados contra servidores locais). Os dois constam na lista de verificação manual antes do upload.

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

### Polimento — matemática, línguas e higiene de código

**Matemática e geografia, conferidas contra referência independente (pyproj e a base EPSG).** Os 21 códigos SIRGAS 2000 / UTM (31965–31976 N, 31977–31985 S) batem um a um com o registro; a zona UTM a partir da longitude concorda com o pyproj em seis longitudes-teste; a escala a partir da extensão, a barra de escala, a série cartográfica, o zoom Web Mercator e o intervalo de grade foram conferidos à mão. **Um erro geográfico real:** `BRAZIL_BOUNDS` parava no litoral continental e deixava de fora Fernando de Noronha, Atol das Rocas, São Pedro e São Paulo e Trindade — um mapa de qualquer dessas unidades de conservação recebia uma LAEA genérica em vez da Policônica oficial. Substituído pela área de uso do EPSG:5880 no registro EPSG (−74,01 / −35,71 / −25,28 / 7,04).

**Línguas.** Dois-pontos de largura inteira (`：`) em japonês e chinês, como manda a norma GB/T 15834 e o uso cartográfico japonês; `直向` (retrato) acrescentado ao chinês tradicional; `مقياس الرسم` como termo cartográfico completo em árabe. A direção árabe e hebraica foi reverificada com um caso controlado: a ordem visual é a lógica lida da direita para a esquerda, correta. Inglês da interface sem calcos do português; a confirmação do Modo DEV aceita `SIM` e `YES`, e a janela mostra a palavra da língua ativa.

**Bloqueador de publicação removido.** O changelog do `metadata.txt` tinha `%` cru. O validador do repositório oficial (`qgis-app/plugins/validator.py`) instancia `ConfigParser` sem `interpolation=None` e chama `items("general")` — o upload seria rejeitado com *"Errors parsing metadata.txt"*. Reproduzido com o código deles; o teste agora garante o duplo invariante: o parser interno tolera `%`, o pacote publicado não o carrega.

**Descoberta de sessão quebrada no Linux e no macOS.** O pacote publicado nunca traz `core/`, então é o fallback de `session.py` que roda na máquina do usuário — e ele gravava em `~/SIGMAI/sessions` enquanto o servidor MCP procurava em `~/.local/share/sigmai/sessions`. Nenhum teste via, porque todos carregavam `core/`. O fallback passa a espelhar o `core/`, e um teste força o `ImportError` e confere que o plugin grava onde o servidor procura.

**Higiene.** Três leitores de versão idênticos viraram um; `_safe_call` delega ao `_safe` já existente; o único fallback Qt5/Qt6 feito à mão passou a usar `qt_enum`; conjuntos com itens duplicados, imports e atribuições nunca lidos, `zip` sem `strict`, nome ambíguo `l`; código morto confirmado removido (`DECISION_PENDING`, `preferred_session_dir`, `_zoom_to_scale`, três constantes de painel, uma flag write-only no MCP). Os logs de execução saem da pasta do plugin e vão para o perfil do QGIS — numa instalação de sistema a pasta é somente-leitura. `sigmai/logs/sigmai.jsonl` (log real esquecido na árvore) e `sigmai/icons/sigmai.svg` (órfão) removidos. O validador do pacote passa a montar o zip com o **mesmo** empacotador da ação `package_plugin_zip` — antes validava um artefato diferente do que saía. Docstring de módulo nos oito arquivos de topo que não tinham.

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
