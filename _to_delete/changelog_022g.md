
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
