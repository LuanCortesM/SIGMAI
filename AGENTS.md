# Instruções para agentes de IA

O SIGMAI expõe o QGIS por comandos validados. Estas instruções descrevem como usá-lo bem; o servidor MCP repete as principais no campo `instructions` do handshake.

## Ordem de trabalho

1. **`sigmai_status` primeiro, sempre.** Ele informa se a ponte está online e — o que mais importa — qual é o **modo de acesso**. Em `read_only` nenhuma ação de escrita vai executar, e tentar é desperdício.
2. **`sigmai_project_overview` antes de referenciar qualquer camada.** Os ids vêm daí. Inventar um id é a causa mais comum de mapa vazio, e um id inventado não gera erro: gera um quadro em branco.
3. **Verifique o CRS antes de análise espacial ou de medir qualquer coisa.** Área e distância em coordenadas geográficas estão erradas.
4. **Para mapas: leia `sigmai_cartographic_rulebook` uma vez por conversa**, depois `sigmai_plan_map` para simular e `sigmai_compose_map` para executar.
5. **Leia o campo `audit` da resposta.** Ele traz nota, pontuação e, para cada regra reprovada, o problema observado e o comando que corrige. Nota abaixo de A significa que há trabalho a fazer antes de entregar.

## Regras

- **Use apenas comandos do catálogo.** `sigmai_capabilities` lista todos, com grupo e nível de permissão.
- **Nunca invente ids de camada, nomes de layout ou códigos de CRS.** Consulte.
- **Simulação é gratuita e sempre permitida.** Use `dry_run` para mostrar ao usuário o que faria antes de pedir autorização.
- **Uma recusa não é um obstáculo a contornar.** Se o consentimento for negado, explique o que pretendia e pergunte como prosseguir. Repetir a mesma ação com os mesmos parâmetros é sempre errado.
- **Nunca sobrescreva arquivo sem `confirm_overwrite` explícito do usuário.**
- **Não peça o Modo DEV.** Ele existe para o desenvolvedor do plugin depurar código, é ativado à mão na interface e não faz parte de nenhum fluxo de produção de mapas.
- **Ao falhar, consulte `get_recent_errors`** em vez de tentar variações às cegas.

## Autoria de mapas

O autor do plugin **não** é o autor dos mapas. Pergunte ao usuário o que deve constar em `map_author`, `data_source` e `organization`. Sem fonte declarada o mapa não é citável, e a regra `CART007` reprova.

## Estrutura do projeto

| Parte | Responsabilidade |
|---|---|
| `sigmai/mcp/` | Servidor MCP; roda como processo separado, sem QGIS |
| `sigmai/bridge_server.py` | Ponte HTTP local, token, fila de comandos |
| `sigmai/consent.py` | Modo de acesso, pastas, limites, auditoria |
| `sigmai/qgis_actions/` | Manipuladores dos 218 comandos |
| `sigmai/cartography/` | Página, escala, layout, regulamento, composição |
| `sigmai/ui/` | Painel dentro do QGIS |
| `core/` | Protocolo, esquemas e exemplos |

`pagespec`, `scaling`, `layoutgrid` e `rulebook` não importam PyQGIS de propósito: são as decisões cartográficas, e precisam ser verificáveis em CI. Se uma mudança nesses módulos exigir QGIS para ser testada, a lógica provavelmente está no módulo errado.
