<div align="center">

<img src="../../sigmai/icons/sigmai_logo_full.png" alt="SIGMAI" height="72">

**Interface GIS-IA** — uma ponte local e auditável que permite a assistentes de IA operarem o QGIS.

[English](../../README.md) · [Instalar](#instalar) · [Conectar um assistente](#conectar-um-assistente-de-ia) · [Regulamento cartográfico](#o-regulamento-cartográfico) · [Segurança](#modelo-de-segurança)

</div>

---

## O que é

Peça hoje um mapa a um assistente de IA e ele fará uma de duas coisas: escrever PyQGIS para você colar, ou dirigir a sua tela com um robô de mouse. Na primeira, quem executa é você. Na segunda, nada é auditável e tudo quebra na próxima mudança de interface.

O SIGMAI segue um terceiro caminho. Ele roda dentro do QGIS como plugin e expõe uma **interface local de comandos protegida por token**, com um vocabulário fixo de comandos JSON validados. O assistente se conecta pelo **Model Context Protocol**, pergunta o que existe no projeto, e emite comandos que o plugin valida, autoriza segundo as regras que você definiu, executa, registra e então **audita**.

É a última etapa que muda o resultado. Produzir um mapa é fácil; produzir um mapa *cartograficamente correto* não é, e um assistente que não recebe retorno útil não consegue distinguir os dois. O SIGMAI traz um regulamento explícito — a legenda cobre todas as camadas visíveis, a barra de escala ocupa uma fração legível do quadro, a grade de coordenadas de fato aparece, o datum está declarado, a rosa dos ventos é um símbolo e não a letra N — e devolve um laudo dizendo quais regras falharam, por que a regra existe, e qual comando corrige.

## Instalar

**Pelo repositório oficial** — `Complementos ▸ Gerenciar e instalar complementos ▸ Todos`, procure por *SIGMAI*.

**Por arquivo ZIP** — baixe `sigmai-<versão>.zip` da [última versão publicada](https://github.com/LuanCortesM/SIGMAI/releases/latest) e use `Complementos ▸ Gerenciar e instalar complementos ▸ Instalar a partir do ZIP`.

Depois abra o painel do SIGMAI na barra de ferramentas. Nenhum pacote Python externo é necessário: o SIGMAI roda no interpretador que acompanha o QGIS/OSGeo4W.

O painel fala nove línguas — Português (Brasil), English, Español, Français, Deutsch, Italiano, 日本語, 简体中文, 繁體中文 — escolhidas na lista do cabeçalho, cada uma com o nome escrito nela mesma. Ele segue o tema do QGIS (claro ou escuro, inclusive o *Night Mapping*) com uma paleta própria para cada um, e *Avançado ▸ Aparência* força um deles se você preferir. Os mapas que o assistente compõe têm os textos da moldura em quinze línguas (`map_language`), independentes da língua do painel.

## Conectar um assistente de IA

O painel faz isso por você: escolha o programa no passo 2 e ele monta o bloco de configuração com os caminhos absolutos corretos.

| Programa | Onde fica a configuração |
|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code | `.mcp.json` no projeto, ou `~/.claude.json` |
| Cursor | `~/.cursor/mcp.json` |
| Codex CLI | `~/.codex/config.toml` |
| Qualquer outro | qualquer cliente MCP por stdio funciona |

O passo 3 do painel roda um autoteste no caminho inteiro — ponte, autenticação, arquivo de sessão, servidor MCP, projeto e modo de acesso — e nomeia a etapa que falhou, em vez de deixar você adivinhando.

Guias detalhados: [Claude](../CONNECT_WITH_CLAUDE.md) · [Cursor](../CONNECT_WITH_CURSOR.md) · [Codex](../CONNECT_WITH_CODEX.md).

## Chat dentro do QGIS

Sem cliente MCP? Clique em **API e Chat** no cabeçalho do painel do SIGMAI: as abas dão lugar ao chat, no mesmo visual, e **Voltar ao painel** volta. Na primeira vez, o cartão *Conecte sua IA* pede o provedor e a sua chave de API; depois, só a conversa aparece, e a configuração fica a um clique. O modelo do chat só tem as ferramentas do SIGMAI: não lê arquivos, não roda código e não acessa a internet, e cada comando passa pelo mesmo catálogo, modo de acesso, pastas autorizadas, auditoria e receita de um cliente externo.

- **Provedores:** a API de Mensagens da Anthropic (Claude Opus 5.5 por padrão, esforço médio; Sonnet 5.5 e Haiku 5.5 à escolha) e qualquer serviço no formato de chat da OpenAI: a OpenAI, o endpoint compatível do Gemini, um modelo local no Ollama e outros.
- **A chave** fica no cofre criptografado do QGIS, nunca nas configurações, nos registros ou nas receitas.
- **O que vai para o provedor:** a conversa e o que as ferramentas devolvem (nomes de camadas e campos, contagens, valores de atributos de exemplo, caminhos de arquivo, laudos e, se ligada, uma prévia do mapa exportado). Os arquivos de dados não vão. O painel avisa isso antes da primeira mensagem; para nada sair da máquina, use um modelo local.
- **Custo:** contador de tokens com o custo estimado pelo preço de tabela e um teto por conversa (US$ 5 por padrão).
- **Menos tokens:** as ferramentas respondem resumido (o laudo traz só as regras reprovadas, cada uma com o comando que corrige), e o modelo não precisa examinar o mapa sozinho. `detail: "full"` devolve tudo.

Detalhes, em inglês: [docs/CHAT.md](../CHAT.md).

## Controle de acesso

Comandos de leitura e simulações funcionam sempre. Tudo que altera o projeto ou grava arquivo passa pela camada de consentimento, que você controla na aba **Acesso**:

- **Somente leitura** (padrão) — o assistente inspeciona e simula. Uma escrita recusada devolve uma mensagem mandando ele mostrar o plano e pedir liberação, então ele para em vez de insistir.
- **Perguntar sempre** — cada ação que altera algo abre uma caixa nomeando a ação, a categoria e os arquivos que seriam gravados.
- **Liberar nesta sessão** — sem perguntas, dentro das pastas e limites que você definiu.

Independentemente do modo: as **pastas de saída** restringem onde arquivos podem ser gravados; os **limites de sessão** limitam alterações, exportações e execuções de Processing; a aba **Atividade** registra todas as decisões. Instalar, remover ou recarregar plugins e executar Python nunca são cobertos pelo consentimento — exigem o Modo DEV, ativado à mão.

## O motor cartográfico

`compose_map` não preenche um gabarito. Para uma página e um conjunto de camadas ele:

- resolve a página (A5 a A0, retrato ou paisagem, ou milímetros customizados) e soluciona um layout cujas posições, por construção, ficam dentro das margens — página larga ganha coluna lateral, página alta ganha faixa inferior;
- expande a extensão para a razão de aspecto do quadro **antes** de aplicar a margem, para que a margem pedida seja a margem obtida nos dois eixos;
- fecha a escala na série cartográfica (1:250.000, não 1:257.090), declarando a margem que resultou disso;
- dimensiona a barra de escala para ocupar de 15% a 45% do quadro, terminando num número redondo e na unidade adequada;
- calcula o intervalo da grade de coordenadas a partir da extensão e põe os rótulos fora do quadro, na vertical nas laterais;
- monta a legenda com **todas as camadas do quadro**, e não só a principal;
- insere uma rosa dos ventos de verdade, ligada ao norte da grade;
- declara datum, projeção, fonte, autoria e data;
- reprojeta para o UTM adequado quando o projeto está em coordenadas geográficas, porque uma barra métrica sobre graus está errada em quase toda a folha — julgado pelo recorte que vai ao papel, com uma Transversa de Mercator centrada no mapa quando ele não cabe em nenhum fuso; com `map_crs: "auto"` projeta também mapas continentais (Lambert azimutal de áreas iguais centrada nos dados) e mapas-múndi (Equal Earth), com grade em graus e sem rosa dos ventos;
- escolhe a orientação da página pela forma dos dados quando você pede `orientation: "auto"` ou não diz orientação nenhuma, e aceita um pedido de figura para revista pela largura da coluna (`journal_column`, `figure_width_mm`) em vez do tamanho do papel, e em tons de cinza para impressão (`colour_mode: "greyscale"`, conferido na imagem exportada pela `CART073`);
- compõe dois, três ou mais painéis — `second_map` ou `panels` — na grade em que eles saem maiores (um sobre o outro na coluna simples, a legenda na célula vazia da grade), com a letra no estilo da revista e escala comum; quando cada painel cabe no anterior (país, estado, área de estudo), faz uma figura de localização, cada painel com escala, projeção e barra próprias e o recorte do seguinte marcado em vermelho;
- conhece as normas de figura de 17 revistas e editoras (`journal`, ou `journal_profile` para outra): larguras das colunas, altura máxima, fonte e linha mínimas, formatos aceitos, resolução, letra dos painéis. Um recorte alto numa coluna larga estreita para a coluna menor em que o mapa sai do mesmo tamanho; traços abaixo da linha mínima são engrossados; o EPS sai vetorial pelo Ghostscript que o QGIS para Windows instala; a `CART083` confere a figura contra a revista;
- faz figuras de artigo do jeito que as revistas pedem: com `title_placement: "caption"`, título e créditos (fontes com DOI, sistema de referência, ferramenta) saem da imagem e voltam como legenda pronta para o manuscrito, enquanto escala, norte, legenda de símbolos e grade ficam no mapa; `"none"` faz o mapa sem título;
- põe a legenda de símbolos onde a figura precisa (`legend_placement`): ao lado do mapa, embaixo dele na largura da figura, num arquivo à parte cortado na altura da legenda, para outro lugar do artigo, ou fora da figura; com legenda de mais de 8 linhas, a simulação manda o assistente perguntar a você;
- aceita `data_source` por camada e imprime a fonte de cada camada na legenda, ao lado da camada a que pertence;
- ajusta o símbolo de ponto a quantos pontos caem no quadro — 2,2 mm para dezenas, até 0,45 mm e semitransparente numa nuvem densa —, para os pontos não cobrirem o que está embaixo; registros de ocorrência repetidos nas mesmas coordenadas são mostrados por mapa de calor ou por um símbolo proporcional por local (`count_points_by_site`, `apply_proportional_symbol_style`), com os locais agrupados na escala do próprio mapa para os círculos não se amontoarem — ou numa chamada só, com `dense_points: "sites"`, `"heatmap"` ou `"grid"` (hexágonos de área redonda, contados em classes);
- conhece o caso do mapa de campanha (`compose_campaign_map`): sítios sobre trilha sobre área sobre contexto, com inserto de localização e tabela de coordenadas.

E então audita o que produziu, guarda a **receita** do mapa no layout e no PNG exportado (parâmetros, camadas com SHA-256 e estilo, versões do QGIS e do SIGMAI) e devolve o laudo. A receita pode ser lida de volta (`sigmai_map_recipe`), reexecutada com alterações, até num projeto vazio (`sigmai_recompose_from_recipe`) e transformada num parágrafo de Métodos com a referência do software (`sigmai_methods_paragraph`). Toda escrita no projeto passa por uma pilha de desfazer (`sigmai_undo`).

Antes de assumir onde algo fica, o assistente pode perguntar (`sigmai_spatial_relationship`): que fração de cada feição de A está dentro de B, quais feições de B tocam A, e qual é a mais próxima, com a distância geodésica em metros. Foi assim que se descobriu que um parque pedido "no Piauí" fica no Ceará. E `sigmai_briefing` devolve numa chamada o que o assistente antes levava cinco para saber: versões, projeto, cada camada com o campo de nome provável e exemplos, layouts, o que você liberou, o regulamento resumido e o caminho recomendado para os pedidos mais comuns.

## O regulamento cartográfico

45 regras em dez categorias — elementos, escala, orientação, procedência, grade, geometria, tipografia, projeção, dados, simbologia. Cada uma carrega a severidade, o motivo de existir, a referência que a sustenta e o comando que a satisfaz. O `sigmai_cartographic_rulebook` devolve tudo como dado, para o assistente ler as regras antes de compor em vez de descobri-las falhando.

Cinco regras nasceram do experimento da 1.0.3, em que o mesmo pedido foi dado a um agente escrevendo PyQGIS puro e a um agente operando o SIGMAI, a auditoria rodou sobre os dois mapas e a versão nova foi então operada de ponta a ponta por um assistente emulado: rótulos que o motor de rotulagem não conseguiu colocar (`CART068`), uma faixa vazia do quadro que a forma da página deixou sem uso (`CART069`), pares de cores que um leitor com deficiência de visão de cores não distingue, simulados com as matrizes de Machado, Oliveira & Fernandes (2009) (`CART070`), fontes que ficam abaixo do legível quando a figura é impressa na largura da coluna (`CART071`), e uma legenda cujo conteúdo é maior que a caixa, que o QGIS corta em silêncio (`CART072`). A auditoria também aprendeu a ler layouts feitos à mão — itens sem id, cabeçalhos como "Fontes dos dados", camadas só de rótulo — em vez de reprová-los pelo que não enxergava.

A `CART076` (1.3.0) nasceu de 362.210 registros do GBIF num parque nacional, que estão em 11.742 coordenadas distintas, uma delas com 54.009 registros: em pontos, esse local parecia um local com um registro só, e um mapa com 10.000 desses registros tirava A. A regra conta, em milímetros do quadro, quantos pontos não acrescentam nada visível ao mapa, e avisa quando passam da metade. Mede do mesmo jeito os círculos proporcionais: um círculo por coordenada exata deixava 79 % dos círculos desse parque sobre outros a 1:300.000, e o lugar com mais registros parecia o mais vazio; agrupados na escala do mapa, os 11.224 locais viram 863, e nenhum fica escondido.

A `CART083` (1.5.0) confere a figura contra a revista a que ela se destina: largura, altura, menor fonte, traço mais fino, formato e resolução, lidos na instrução aos autores da própria revista, com o endereço e a data da leitura.

A `CART082` (1.4.0) veio do primeiro teste real do chat embutido, com um modelo gratuito do Gemini: o mapa tirou A com uma legenda que dizia "parna_itatiaia", "municipios_2024" e "relevo_copernicus_glo30". Nome de legenda com sublinhado, extensão de arquivo de dados ou ano colado ao nome reprova, e a correção é renomear a camada (`rename_layer`) para o que o leitor entende.

O exemplo trabalhado está em [CARTOGRAPHIC_QUALITY_MODEL.md](../CARTOGRAPHIC_QUALITY_MODEL.md): o mesmo mapa que o avaliador da 0.1.1 classificava como *"A — Professional map"*, com zero avisos, recebe **E — inválido** no regulamento, com três erros bloqueantes que qualquer leitor perceberia de imediato.

## Modelo de segurança

- A ponte escuta **apenas em 127.0.0.1** e recusa cliente que não seja local.
- Todo comando exige **token bearer**; requisição sem token recebe 401. `/health` é o único endpoint sem autenticação e não devolve nada além de existência e versão.
- A superfície de comandos é uma **allowlist** de manipuladores tipados. Não há avaliador genérico; a operação normal não executa Python arbitrário.
- O **Modo DEV** vem desligado, precisa ser ativado na interface com confirmação digitada, e é a única rota para execução de Python.
- Arquivos existentes nunca são sobrescritos sem `confirm_overwrite`.
- Logs e auditoria nunca contêm tokens, senhas ou credenciais.

## Autoria

Autor do plugin: **MACIEL, L. S. C.** — herpetomantiqueira@gmail.com
Desenvolvido por Luan da Silva Cortes Maciel como produto de pesquisa associado ao Herpeto Mantiqueira.

**O autor do plugin não é o autor dos mapas feitos com ele.** Os mapas gerados creditam o autor que você informar, o perfil de usuário do SIGMAI, ou uma linha neutra `Produzido com SIGMAI/QGIS`. Veja [MAP_AUTHORSHIP_POLICY.md](../MAP_AUTHORSHIP_POLICY.md).

## Licença

Licença MIT. Veja [LICENSE](../../LICENSE).
