# Chat dentro do SIGMAI (versão 1.4.0): desenho para aprovação

Rascunho de 31/10/2026. Nada foi programado. O autor aprova ou muda este desenho antes do código.

## O que é

Um painel de conversa no próprio QGIS. A pessoa escolhe o provedor e o modelo, cola a chave de API uma vez e conversa: "faça um mapa dos registros do GBIF no parque, 88 mm, para a revista". O modelo trabalha só com as 20 ferramentas do SIGMAI, as mesmas que um cliente MCP externo recebe, pelo mesmo caminho: catálogo fechado, consentimento, auditoria e receita.

O modelo do chat não tem nenhuma outra ferramenta. Ele não lê arquivos, não roda código e não acessa a internet. O que ele sabe dos dados é o que as ferramentas do SIGMAI devolvem.

Os clientes MCP externos (Claude Desktop, Codex, Cursor) continuam funcionando como hoje.

## Uma volta da conversa

1. A pessoa escreve no painel.
2. O painel manda à API do provedor três coisas:
   - as instruções do servidor MCP, as mesmas que todo cliente recebe, mais um parágrafo próprio do chat;
   - as 20 ferramentas;
   - a conversa até ali.
3. O modelo responde com texto, chamadas de ferramenta ou os dois.
4. O painel executa cada chamada pela ponte local, como um cliente MCP faria, e a mostra na conversa numa linha curta (por exemplo, "compose_map → nota A, 95"). Em seguida devolve o resultado ao modelo.
5. Os passos 3 e 4 se repetem até o modelo encerrar a vez. Há um limite de chamadas por vez e um botão Parar.

**Detalhes de funcionamento:**
- **Uma fonte só:** o chat importa a tabela de ferramentas e as instruções do servidor MCP (`sigmai/mcp/sigmai_mcp.py`) e chama os mesmos manipuladores, que falam com a ponte em 127.0.0.1. Validação, consentimento, registro e desfazer são os de sempre.
- **Ponte:** o chat liga a ponte se ela estiver desligada.
- **QGIS livre:** as chamadas ao provedor e às ferramentas rodam numa thread de trabalho, e o QGIS não trava. No modo "perguntar antes de cada escrita", a janela de consentimento aparece como hoje.
- **Rede:** pelo gerenciador de rede do QGIS (`QgsNetworkAccessManager`), que respeita o proxy e os certificados configurados no QGIS. Só HTTPS, só para o endereço do provedor escolhido.
- **Texto ao vivo:** a resposta chega aos poucos (streaming). Assim o texto aparece enquanto é escrito, e uma resposta longa não cai no tempo limite de rede do QGIS (60 s por padrão).

## Provedores

- **Anthropic (Claude), API de Mensagens.** Modelos e preços da tabela da Anthropic de 06/10/2026, por milhão de tokens de entrada e de saída:

  | Modelo | Identificador | Entrada | Saída |
  |---|---|---|---|
  | Claude Opus 5.5 | `claude-opus-5-5` | US$ 4 | US$ 20 |
  | Claude Sonnet 5.5 | `claude-sonnet-5-5` | US$ 2 | US$ 10 |
  | Claude Haiku 5.5 | `claude-haiku-5-5` | US$ 0,10 | US$ 0,50 |

  A parte fixa de cada pedido (instruções e ferramentas) vai com cache. Nas voltas seguintes ela custa uma fração do preço: na tabela, a leitura de cache do Opus 5.5 é US$ 0,20 por milhão.
- **Compatível com OpenAI (decisão 1).** Um segundo adaptador, no formato de chat da OpenAI, que cobre:
  - a própria OpenAI;
  - o Gemini, pelo endpoint compatível do Google, que tem cota gratuita;
  - modelos locais pelo Ollama, de graça e sem mandar dados para fora;
  - outros serviços que usam o mesmo formato.

  Modelos locais pequenos costumam errar com 20 ferramentas; o painel avisa isso.

Os dois adaptadores são escritos em HTTP direto, sem o SDK de nenhum provedor, porque um plugin do QGIS não instala pacotes com dependências compiladas.

## Chave de API

- Fica guardada no cofre de autenticação do QGIS (`QgsAuthManager`), criptografada com a senha mestra do QGIS. Na primeira vez, o QGIS pede para criar essa senha.
- Nunca vai para as configurações do QGIS, os registros, as receitas, o parágrafo de Métodos nem as mensagens de erro. Quando aparece na tela, aparece mascarada.
- Há um botão para apagar a chave.
- Quem cola a chave no painel é a pessoa. Eu não digito a chave de ninguém, nem nos testes.

## Privacidade (mostrada na tela antes da primeira conversa)

**Vai para o provedor:**
- a conversa e as instruções;
- o que as ferramentas devolvem: nomes de camadas e campos, sistema de referência, contagens, valores de atributos de exemplo, caminhos de arquivo e o laudo da auditoria;
- a imagem do mapa exportado, se a opção "o modelo vê o mapa" estiver ligada (decisão 3).

**Não vai:** os arquivos de dados. O modelo nunca lê arquivos; só recebe o que as ferramentas resumem. Para quem não pode mandar dados para fora, há o modelo local (Ollama).

Vale a política de dados do provedor escolhido, e o painel aponta para ela.

## Economia de tokens

O plugin carrega as regras, e o modelo não precisa descobrir sozinho o que está errado no mapa: a auditoria diz o problema e o comando que o corrige. Para isso valer em tokens, as respostas das ferramentas têm de trazer só o que o modelo usa.

Medido nas 113 chamadas reais da sessão do exemplo (`artigo/testes/2026-10-28_exemplo_candidata2_1.3.2/chamadas.jsonl`):
- As ferramentas devolveram cerca de 1 milhão de caracteres, uns 290 mil tokens.
- Cada auditoria de `compose_map` tem uns 18 mil caracteres. Três quartos disso são as regras aprovadas e os dados brutos da inspeção (`observation`).
- `map_recipe` devolve a receita inteira, com o estilo QML de cada camada: 148 mil caracteres por chamada.

**Resposta enxuta, para o chat e para os clientes MCP externos:**
- **Auditoria:** nota, pontuação e contagens; só as regras reprovadas, cada uma com o problema e o comando que corrige; e os próximos passos.
- **Receita:** sem o QML das camadas; diz só que o estilo está guardado.
- **Formatação:** JSON sem recuo.
- **Detalhe sob pedido:** quem quiser tudo pede com `detail: "full"`.

Na mesma sessão, isso levaria as respostas de uns 288 mil a uns 101 mil tokens, 65 % a menos.

**Outras economias:**
- cache das instruções e das ferramentas;
- esforço médio;
- prévia do mapa em baixa resolução e só depois de uma exportação.

A comparação do artigo mede tokens e custo por figura terminada nos dois lados, com e sem o SIGMAI.

## Custo

- O painel mostra um contador por conversa: tokens de entrada, de saída e de cache, e o custo estimado pelo preço de tabela, com a data da tabela.
- Há um teto opcional por conversa. Ao passar dele, o chat para e pergunta se continua (decisão 4).
- A conta é da pessoa, no provedor dela.

## Modelo, esforço e recursos da Anthropic

- **Modelo padrão:** Claude Opus 5.5, o mesmo do exemplo do artigo, com troca no painel (decisão 2).
- **Raciocínio:**
  - No Opus 5.5 o raciocínio fica sempre ligado; o que se escolhe é o esforço (baixo, médio ou alto). O padrão do modelo é médio.
  - Entre uma chamada e outra, o modelo pode mandar notas curtas de progresso, que o painel mostra em cinza.
- **Recusa:** se o filtro de segurança do provedor recusar um pedido (o que pode acontecer com dados de espécies ameaçadas, por exemplo), a API refaz o pedido em outro modelo. Isso fica ligado por padrão (é um recurso beta da Anthropic) e o painel avisa quando acontece.
- **Conversa longa:** o histórico vai inteiro e só cresce (append-only), como a API pede. Num chat muito longo, o painel sugere começar outro.

## O modelo vê o mapa (decisão 3)

Depois de cada exportação, o chat pode mandar ao modelo uma prévia em PNG do mapa, para ele conferir à vista, como fez o assistente do exemplo ao abrir o PDF. Isso custa alguns milhares de tokens por imagem. A auditoria continua sendo a conferência principal.

## Registro

- Cada conversa é salva no próprio computador, na pasta de registros do SIGMAI, em JSONL, sem a chave. O registro tem as mensagens, as chamadas e os resultados, o modelo e os tokens.
- Há um botão "Exportar conversa".
- A ponte continua registrando cada comando, como hoje.

## O que não muda

Catálogo fechado, modos de acesso, pastas autorizadas, limites, desfazer, auditoria, receita e o servidor MCP para clientes externos.

## Segurança

- **Melhora:** no chat, o modelo só tem as ferramentas do SIGMAI. Hoje o artigo admite que o SIGMAI não controla o que um assistente externo faz fora do QGIS; com o chat, esse "fora" não existe.
- **Continua igual:**
  - um dado lido pelo modelo ainda pode agir como instrução (injeção de prompt);
  - o que limita o estrago é o mesmo de hoje: modo de acesso, catálogo fechado e pastas autorizadas.
- **Novo:**
  - a chave de API fica no computador, no cofre do QGIS;
  - o QGIS passa a fazer chamadas de rede para o provedor escolhido.

## Repositório de plugins do QGIS

- **Descrição:** a descrição e o `metadata.txt` passam a dizer que o plugin pode mandar dados ao provedor de IA que a pessoa configurar.
- **Varreduras:** o código novo passa pelas mesmas varreduras (Bandit, detect-secrets, Flake8, Qt6). Nenhuma chave no código.

## Testes

- **Automáticos, sem rede:** um provedor falso (um servidor HTTP local com respostas roteirizadas) testa:
  - o laço e a execução das ferramentas;
  - as falhas de API: chave inválida, limite de uso, erro do servidor e queda de rede;
  - a recusa e a resposta cortada;
  - o botão Parar e o limite de chamadas;
  - o contador de custo;
  - que a chave não aparece em nenhum registro.

  Rodam dentro do QGIS 3.40 e 4.0 e no CI.
- **Reais:** você cola a sua chave e fazemos uma conversa curta. Depois disso, o exemplo e a comparação do artigo rodam na 1.4.
- **Rodada completa** antes de lançar (`rodada_final.sh`), como em toda versão.

## O que muda no artigo

- **Descrição do software:** ganha uma subseção sobre o chat, e a Figura 1 passa a mostrar o chat dentro do QGIS.
- **Segurança:** o parágrafo de segurança muda. No chat, o modelo não tem ferramentas fora do QGIS; clientes MCP externos continuam possíveis, com o limite de hoje.
- **Exemplo e comparação:** são refeitos na 1.4. Por qual caminho é a decisão 5.

## Decididas pelo autor (31/10/2026)

1. Anthropic e o adaptador compatível com OpenAI.
2. Claude Opus 5.5, esforço médio, trocáveis no painel.
3. O modelo vê o mapa, mas com economia: a ideia é que as regras do plugin diminuam o gasto de tokens (seção Economia de tokens).
4. Teto de US$ 5 por conversa, ajustável (padrão do desenho, sem objeção).
5. O exemplo do artigo roda pelo chat, com a chave do autor.
6. Chat num painel próprio, aberto por um botão no painel do SIGMAI (padrão do desenho, sem objeção).

## Decisões do autor (como foram propostas)

1. **Provedores:**
   - (a) só a Anthropic;
   - (b) a Anthropic e o adaptador compatível com OpenAI (OpenAI, Gemini, Ollama local e outros).

   Recomendo (b): alcança quem não pode pagar e quem não pode mandar dados para fora. Os testes reais ficam na Anthropic com a sua chave, e o artigo diz quais provedores foram testados.
2. **Modelo e esforço padrão:** recomendo o Claude Opus 5.5 com esforço médio, trocáveis no painel.
3. **O modelo vê o mapa:** recomendo ligado.
4. **Teto de custo por conversa:** recomendo US$ 5 de padrão, ajustável, com aviso antes de passar.
5. **Exemplo do artigo na 1.4:**
   - (a) pelo chat, com a sua chave;
   - (b) pelo cliente MCP externo, como agora, com o chat mostrado à parte.

   Recomendo (a), porque é o caminho que o leitor da revista vai usar. Para o pedido e as revisões serem os mesmos de antes, palavra por palavra, o chat terá um modo de teste que lê as mensagens de um arquivo.
6. **Onde fica o chat:** recomendo um painel próprio (dock) aberto por um botão no painel do SIGMAI, que dá mais espaço à conversa do que uma aba.
