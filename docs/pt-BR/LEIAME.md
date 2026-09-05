<div align="center">

<img src="../../sigmai/icons/sigmai_logo_full.png" alt="SIGMAI" height="72">

**Interface Segura GIS-IA** — uma ponte local e auditável que permite a assistentes de IA operarem o QGIS.

[English](../../README.md) · [Instalar](#instalar) · [Conectar um assistente](#conectar-um-assistente-de-ia) · [Regulamento cartográfico](#o-regulamento-cartográfico) · [Segurança](#modelo-de-segurança)

</div>

---

## O que é

Peça hoje um mapa a um assistente de IA e ele fará uma de duas coisas: escrever PyQGIS para você colar, ou dirigir a sua tela com um robô de mouse. Na primeira, quem executa é você. Na segunda, nada é auditável e tudo quebra na próxima mudança de interface.

O SIGMAI segue um terceiro caminho. Ele roda dentro do QGIS como plugin e expõe uma **interface local de comandos protegida por token**, com um vocabulário fixo de comandos JSON validados. O assistente se conecta pelo **Model Context Protocol**, pergunta o que existe no projeto, e emite comandos que o plugin valida, autoriza segundo as regras que você definiu, executa, registra e então **audita**.

É a última etapa que muda o resultado. Produzir um mapa é fácil; produzir um mapa *cartograficamente correto* não é, e um assistente que não recebe retorno útil não consegue distinguir os dois. O SIGMAI traz um regulamento explícito — a legenda cobre todas as camadas visíveis, a barra de escala ocupa uma fração legível do quadro, a grade de coordenadas de fato aparece, o datum está declarado, a rosa dos ventos é um símbolo e não a letra N — e devolve um laudo dizendo quais regras falharam, por que a regra existe, e qual comando corrige.

## Instalar

**Pelo repositório oficial** — `Complementos ▸ Gerenciar e instalar complementos ▸ Todos`, procure por *SIGMAI*.

**Por arquivo ZIP** — baixe `dist/sigmai.zip` de uma release e use `Complementos ▸ Gerenciar e instalar complementos ▸ Instalar a partir do ZIP`.

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
- reprojeta para o UTM adequado quando o projeto está em coordenadas geográficas, porque uma barra métrica sobre graus está errada em quase toda a folha.

E então audita o que produziu.

## O regulamento cartográfico

29 regras em nove categorias — elementos, escala, orientação, procedência, grade, geometria, tipografia, projeção, dados. Cada uma carrega a severidade, o motivo de existir, a referência que a sustenta e o comando que a satisfaz. O `sigmai_cartographic_rulebook` devolve tudo como dado, para o assistente ler as regras antes de compor em vez de descobri-las falhando.

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

GNU General Public License v3.0 ou posterior. Veja [LICENSE](../../LICENSE).
