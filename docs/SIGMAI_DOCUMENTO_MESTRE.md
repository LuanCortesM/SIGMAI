# SIGMAI - Documento Mestre do Projeto

Status do documento: documento vivo  
Ultima atualizacao: 2026-05-22  
Responsavel por manter atualizado: Codex durante cada nova fase de trabalho  

Este documento e a fonte principal de referencia do SIGMAI. Sempre que uma nova funcionalidade, decisao arquitetural, comando, configuracao, teste, limitacao ou fluxo de uso for alterado, este arquivo deve ser atualizado junto com o codigo.

Nome publico atual: SIGMAI - Secure GIS-AI Interface.  
Nome publico e identidade do plugin: SIGMAI - Secure GIS-AI Interface. A pasta tecnica do plugin QGIS e `sigmai`.  
Author: MACIEL, L. S. C.  
Author email: herpetomantiqueira@gmail.com  
Desenvolvido por: Luan da Silva Cortes Maciel (MACIEL, L. S. C.) como produto de pesquisa de mestrado em Biodiversidade em Unidades de Conservacao, vinculada a Escola Nacional de Botanica Tropical e Jardim Botanico do Rio de Janeiro, sob orientacao de Leandro Freitas. Projeto associado: Herpeto Mantiqueira.

## Snapshot de desenvolvimento atual

- Level 5 - Cartographic Map Generation Capable: validado com tratamento CRS-safe de extents e stress test de 200/200 mapas renderizados.
- Level 6 - Vector Analysis and Attribute Capable: implementado e validado apos reload do QGIS com comandos de layer tree, atributos, expressoes, selecao e analise vetorial.
- Level 7 - Professional Cartography Capable: implementado em disco com templates, perfis de estilo, `generate_professional_map`, avaliacao de qualidade de mapa e inventario de Processing/plugins. Requer reload do QGIS para validacao runtime.
- Raster Core: implementado em disco com wrappers explicitos e algoritmos GDAL allowlisted. Requer reload do QGIS para validacao runtime.

Todas as fases preservam servidor local, token bearer, session discovery, dry-run, protecao contra sobrescrita, logs e self-management com staging, backup e rollback.

## Regra critica: autoria do plugin vs autoria dos mapas gerados

MACIEL, L. S. C. e o autor/desenvolvedor do plugin SIGMAI. Essa autoria deve aparecer em metadata, README, About/HUD, documentacao institucional, relatorios tecnicos do SIGMAI, changelog, package metadata e plugin repository metadata.

Os mapas e produtos gerados pelo SIGMAI pertencem ao usuario/projeto que os criou. O SIGMAI nao deve inserir automaticamente `Author: MACIEL, L. S. C.` como autor do mapa final publico.

Os comandos cartograficos devem usar campos separados:

- `map_author`
- `map_author_email`
- `organization`
- `data_source`
- `created_with`
- `plugin_author`

Quando `map_author` nao for informado, o rodape do mapa deve usar credito generico, por exemplo: `Elaborado com SIGMAI - Secure GIS-AI Interface/QGIS.`

MACIEL, L. S. C. so pode aparecer como autor do mapa quando informado explicitamente em `map_author` ou em modo de desenvolvimento/teste com fallback explicito habilitado.

## 1. Resumo executivo

O SIGMAI e uma plataforma local para conectar agentes de IA ao QGIS de forma segura, estruturada e auditavel.

Ele permite que ferramentas como Codex, Claude, ChatGPT, VS Code, Cursor e outros clientes consigam consultar e operar o QGIS por comandos JSON, sem precisar adivinhar chamadas PyQGIS e sem executar Python arbitrario.

O projeto nasceu como uma bridge local simples, mas evoluiu para uma base de plataforma IA/QGIS com:

- plugin QGIS;
- protocolo core;
- cliente Codex;
- CLI local;
- session discovery;
- pairing code;
- autoteste;
- MCP server local inicial;
- diagnostico de QGIS/PyQGIS/Processing;
- gerenciamento seguro de plugins QGIS;
- self-management da propria Bridge.

## 2. Objetivo do SIGMAI

O objetivo central e transformar linguagem natural e intencoes de agentes de IA em comandos estruturados, seguros e rastreaveis dentro do QGIS.

O SIGMAI deve servir a dois publicos principais:

1. Desenvolvedores QGIS:
   - criar plugins;
   - testar plugins;
   - validar `metadata.txt`;
   - diagnosticar imports;
   - verificar providers Processing;
   - empacotar plugins;
   - preparar publicacao;
   - coletar logs;
   - testar dentro de QGIS real.

2. Usuarios cartograficos:
   - listar camadas;
   - entender CRS;
   - diagnosticar dados;
   - carregar camadas;
   - rodar analises seguras;
   - criar layouts;
   - exportar mapas;
   - gerar relatorios de workflow.

## 3. Principio central

A IA nao deve mexer diretamente dentro do processo do QGIS por improviso.

A IA deve conversar com o QGIS atraves de um protocolo local:

```text
Agente IA / CLI / MCP / Codex Plugin
        |
        v
Cliente SIGMAI
        |
        v
Bridge local em 127.0.0.1
        |
        v
QGIS Plugin
        |
        v
Command Registry
        |
        v
Handlers PyQGIS seguros
```

Isso preserva:

- seguranca;
- rastreabilidade;
- logs;
- validacao;
- permissoes;
- dry-run;
- confirmacao;
- resposta JSON padronizada.

## 4. Estado atual confirmado

O SIGMAI ja foi testado em QGIS real.

Ambiente confirmado:

- Sistema: Windows 11;
- QGIS: 3.40.7-Bratislava;
- Python do QGIS: 3.12.10;
- GDAL: 3.10.3;
- PROJ: 9.6.0;
- GEOS: 3.13.1;
- Bridge: online em `127.0.0.1:8765`;
- autenticacao: Bearer token;
- session discovery: implementado;
- pairing code: implementado;
- autoteste real: executado;
- unit tests locais: executados.

Resultados reais ja observados:

- Bridge online dentro do QGIS;
- `detect_qgis` OK;
- `unit_tests` OK;
- `integration_tests` OK;
- 22 testes de integracao passaram na rodada anterior;
- 0 falhas;
- shapes reais foram carregados;
- `load_vector_layer` funcionou;
- `get_layer_info` funcionou;
- `create_layout` com dry-run funcionou;
- `export_layout` com dry-run funcionou.

Atualizacao de 2026-05-18 — Fase Cartographic Map Generation Capable:

- Inventario tecnico consolidado em `RELATORIO_SIGMAI_INVENTARIO_ATUAL.md`;
- Documentacao QGIS 3.44 analisada em `RELATORIO_QGIS_DOCS_ANALYSIS_FOR_SIGMAI.md`;
- Comandos cartograficos atomicos presentes no registry/capabilities:
  - `add_layout_map`;
  - `set_layout_extent`;
  - `set_layer_style`;
  - `add_layout_label`;
  - `add_layout_legend`;
  - `add_layout_scale_bar`;
  - `add_layout_north_arrow`;
  - `generate_basic_map`;
  - `evaluate_layout_cartographic_completeness`;
  - `generate_workflow_report`.
- `add_layout_map` foi ajustado para tentar associar explicitamente a camada alvo ao `QgsLayoutItemMap` com `setLayers([layer])`, quando disponivel;
- `evaluate_layout_cartographic_completeness` agora e comando read-only exposto e retorna `output_size`, `output_ok`, `map_extent_ok`, `missing_elements` e grade A/B/C/D;
- CLI e cliente Codex passaram a expor `evaluate-layout`;
- O full test passou a executar avaliacao cartografica explicita para layout atomico e mapa basico gerado;
- Atualizacao complementar da mesma fase:
  - `add_layout_grid` foi implementado como comando atomico para grade/graticula, com warnings quando a API de grid do QGIS em runtime nao oferecer algum ajuste;
  - `add_layout_picture` foi implementado para inserir assets locais PNG/JPG/SVG, incluindo a logo SIGMAI;
  - `generate_basic_map` passou a aceitar `include_grid` e `logo_path`;
  - `get_capabilities` passou a declarar nivel de maturidade, formatos suportados, capacidades cartograficas e limitacoes por fase.
- Testes locais desta fase:
  - `python -m compileall -q sigmai codex_plugin tools mcp_server tests`: OK;
  - `python -m unittest discover tests`: 40 testes, OK.

Nivel de maturidade operacional antes da proxima validacao real no QGIS:

- Estado confirmado anteriormente: LEVEL 4 — Basic Map Export Capable;
- Alvo imediato: LEVEL 5 — Cartographic Map Generation Capable;
- Criterio para subir: full test real com mapa PDF/PNG contendo item de mapa, extent valido, estilo, titulo, legenda, escala, norte, fonte/autoria e avaliacao A ou B.

Atualizacao complementar de 2026-05-18 — Varredura ampliada da documentacao QGIS 3.44:

- Foram mapeados 326 arquivos fonte `.rst` da documentacao local QGIS 3.44;
- Foram extraidos 374 IDs de algoritmos nativos/QGIS referenciados;
- Foram extraidos 58 IDs de algoritmos GDAL referenciados;
- Foram criados:
  - `SIGMAI_QGIS_DOCS_KEY_PAGES.md`;
  - `SIGMAI_QGIS_COMMAND_OPPORTUNITY_MATRIX.md`;
  - `SIGMAI_QGIS_3_44_DOCUMENTATION_DEEP_ANALYSIS.md`;
  - `diagnostics/qgis_344_native_algorithm_ids.txt`;
  - `diagnostics/qgis_344_gdal_algorithm_ids.txt`.

Novos grupos de capacidade recomendados para `get_capabilities` em fases futuras:

- `selection`;
- `attribute_table`;
- `expressions`;
- `raster`;
- `layer_tree`;
- `atlas_reports`;
- `jobs`;
- `data_sources`;
- `gps`;
- `network_analysis`;
- `point_cloud`;
- `mesh`;
- `qgis_server`.

Principio de expansao derivado da documentacao: expor o QGIS por comandos seguros de alto nivel e perfis de allowlist, nao por execucao Python arbitraria nem por Processing irrestrito.

Ultima rodada local de testes apos Plugin Management:

```powershell
python -m unittest discover tests
python -m compileall -q sigmai codex_plugin tools mcp_server tests
```

Resultado:

```text
32 testes passaram
0 falhas
```

## 5. Estrutura atual do projeto

Diretorio principal:

```text
%SIGMAI_REPO%
```

Estrutura principal:

```text
sigmai/
├── README.md
├── AGENTS.md
├── LICENSE
├── pyproject.toml
├── core/
├── sigmai/
├── codex_plugin/
├── tools/
├── mcp_server/
├── docs/
├── diagnostics/
├── tests/
├── test_outputs/
└── vscode_extension/
```

## 6. Camadas do sistema

### 6.1 Core Protocol

Pasta:

```text
core/
```

Responsabilidades:

- definir schemas JSON;
- documentar comandos;
- documentar respostas;
- documentar erros;
- manter taxonomia de comandos;
- manter caminhos compartilhados de sessao.

Arquivos importantes:

- `core/schemas/command.schema.json`;
- `core/schemas/response.schema.json`;
- `core/schemas/error.schema.json`;
- `core/command_taxonomy.md`;
- `core/session_paths.py`;
- `core/protocol/commands.md`;
- `core/protocol/responses.md`;
- `core/protocol/errors.md`.

### 6.2 QGIS Plugin

Pasta:

```text
sigmai/
```

Responsabilidades:

- rodar dentro do QGIS;
- iniciar/parar Bridge;
- validar token;
- receber comandos JSON;
- despachar comandos para handlers PyQGIS;
- registrar logs;
- controlar session file;
- expor painel do usuario;
- executar acoes QGIS reais.

Arquivos principais:

- `metadata.txt`;
- `__init__.py`;
- `plugin.py`;
- `bridge_server.py`;
- `command_registry.py`;
- `validators.py`;
- `security.py`;
- `permissions.py`;
- `session.py`;
- `logging_utils.py`;
- `qgis_actions/`.

### 6.3 Codex Plugin

Pasta:

```text
codex_plugin/
```

Responsabilidades:

- orientar Codex a usar a Bridge corretamente;
- fornecer cliente Python;
- oferecer skills;
- documentar fluxo seguro;
- permitir fallback quando MCP nao estiver disponivel.

Arquivos principais:

- `codex_plugin/.codex-plugin/plugin.json`;
- `codex_plugin/client/sigmai_client.py`;
- `codex_plugin/skills/`.

### 6.4 Tools

Pasta:

```text
tools/
```

Responsabilidades:

- detectar QGIS;
- instalar plugin;
- abrir QGIS;
- esperar Bridge;
- rodar autotestes;
- criar relatorios;
- fornecer CLI simples.

Ferramentas importantes:

- `tools/sigmai.py`;
- `tools/sigmai_autotest.py`;
- `tools/wait_for_bridge.py`;
- `tools/run_sigmai_integration_tests.py`;
- `tools/detect_qgis_installation.py`;
- `tools/install_qgis_plugin.py`;
- `tools/launch_qgis_for_tests.py`;
- `tools/package_qgis_plugin_zip.py`;
- `tools/session_discovery.py`.

### 6.5 MCP Server

Pasta:

```text
mcp_server/
```

Responsabilidades:

- expor ferramentas SIGMAI para clientes compativeis com MCP;
- descobrir sessao local;
- chamar Bridge local;
- retornar JSON limpo;
- nunca expor servidor remoto.

Estado atual:

- wrapper local inicial implementado;
- usa JSON-lines por stdio;
- ainda nao acoplado ao SDK MCP formal;
- sem dependencia externa obrigatoria.

Arquivos:

- `mcp_server/sigmai_mcp_server.py`;
- `mcp_server/tools.py`;
- `mcp_server/session_discovery.py`;
- `mcp_server/README.md`.

### 6.6 VS Code Extension

Pasta:

```text
vscode_extension/
```

Estado atual:

- apenas planejamento;
- extensao completa ainda nao implementada.

Objetivo futuro:

- painel lateral;
- listar camadas;
- listar plugins;
- ver logs;
- enviar comandos JSON;
- validar plugins QGIS;
- empacotar plugins;
- integrar com Codex/GitHub.

## 7. Como a Bridge funciona

### 7.1 Transporte atual

A comunicacao atual usa HTTP local:

```text
http://127.0.0.1:8765
```

Endpoint principal:

```text
POST /command
```

Endpoint de status:

```text
GET /status
```

Mesmo sendo HTTP, ele e local e offline:

- nao usa internet;
- nao usa nuvem;
- nao abre servidor publico;
- escuta apenas em `127.0.0.1`.

### 7.2 Autenticacao

Toda requisicao precisa enviar:

```text
Authorization: Bearer TOKEN
```

O token e gerado pelo plugin QGIS a cada sessao.

O usuario nao precisa copiar token manualmente quando session discovery esta ativo.

### 7.3 Session discovery

A Bridge grava um arquivo local de sessao para clientes locais encontrarem host, porta e token.

Diretorio preferencial no Windows:

```text
%LOCALAPPDATA%\SIGMAI\sessions\
```

Arquivo ativo:

```text
current_bridge_session.json
```

Arquivos por pairing code:

```text
SG-XXXX-XXXX.json
```

Formato conceitual:

```json
{
  "schema_version": "0.3",
  "session_id": "SG-4821-KQ9M",
  "host": "127.0.0.1",
  "port": 8765,
  "token": "...",
  "started_at": "...",
  "expires_at": null,
  "qgis_version": "...",
  "plugin_version": "...",
  "pid": 1234,
  "capabilities_url": "http://127.0.0.1:8765/command",
  "auth_type": "bearer",
  "local_only": true
}
```

### 7.4 Pairing code

O pairing code tem formato:

```text
SG-XXXX-XXXX
```

Exemplo:

```text
SG-4821-KQ9M
```

Ele nao e o token.

Ele serve apenas para identificar localmente a sessao correta no diretorio de sessoes.

### 7.5 Fluxo de comando

1. Cliente monta JSON.
2. Cliente descobre sessao ou recebe token manual.
3. Cliente envia `POST /command`.
4. Bridge valida:
   - token;
   - JSON;
   - action;
   - permissao;
   - dry-run;
   - confirmacao;
   - tokens perigosos.
5. Command Registry chama handler.
6. Handler executa PyQGIS ou diagnostico.
7. Bridge retorna JSON padronizado.
8. Log e registrado.

## 8. Padrao de comando

Exemplo:

```json
{
  "schema_version": "0.2",
  "request_id": "req-001",
  "action": "list_layers",
  "params": {},
  "dry_run": false
}
```

Campos:

- `schema_version`: versao do protocolo;
- `request_id`: identificador rastreavel;
- `action`: comando;
- `params`: parametros;
- `dry_run`: simular sem aplicar alteracao.

## 9. Padrao de resposta

Resposta de sucesso:

```json
{
  "schema_version": "0.2",
  "request_id": "req-001",
  "ok": true,
  "action": "list_layers",
  "data": {},
  "warnings": [],
  "errors": [],
  "meta": {
    "timestamp": "...",
    "duration_ms": 0,
    "permission_level": "read_only",
    "qgis_version": "3.40.7"
  }
}
```

Resposta de erro:

```json
{
  "schema_version": "0.2",
  "request_id": "req-001",
  "ok": false,
  "action": "get_layer_info",
  "data": null,
  "warnings": [],
  "errors": [
    {
      "code": "LAYER_NOT_FOUND",
      "message": "Layer not found.",
      "details": {}
    }
  ],
  "meta": {
    "timestamp": "...",
    "duration_ms": 0,
    "permission_level": "read_only"
  }
}
```

## 10. Permissoes

Niveis atuais:

- `read_only`;
- `safe_write`;
- `project_write`;
- `developer`;
- `plugin_write`;
- `dangerous_plugin_write`;
- `unsafe_developer`.

### 10.1 read_only

Leitura e diagnostico sem alteracao.

Exemplos:

- `status`;
- `get_capabilities`;
- `list_layers`;
- `get_layer_info`;
- `inspect_plugin`;
- `validate_metadata_txt`;
- `self_inspect`.

### 10.2 safe_write

Operacoes que podem alterar estado do projeto, mas controladas e com dry-run quando adequado.

Exemplos:

- `load_vector_layer`;
- `run_processing`;
- `create_layout`;
- `export_layout`.

### 10.3 developer

Diagnostico tecnico e empacotamento para desenvolvedores.

Exemplos:

- `check_plugin_menu_actions`;
- `check_plugin_toolbar_actions`;
- `check_processing_provider_registration`;
- `package_plugin_zip`.

### 10.4 plugin_write

Operacoes que alteram plugins instalados.

Exigem confirmacao explicita e suportam dry-run.

Exemplos:

- `install_plugin_from_folder`;
- `update_plugin_from_folder`;
- `enable_plugin`;
- `disable_plugin`;
- `reload_plugin`;
- `self_stage_update`.

### 10.5 dangerous_plugin_write

Operacoes sensiveis.

Exigem confirmacao explicita, backup ou fluxo de protecao.

Exemplos:

- `uninstall_plugin`;
- `self_apply_update`;
- `self_rollback`.

### 10.6 unsafe_developer

Reservado para futuro.

Estado atual:

- desativado;
- nao ha execucao Python arbitraria;
- nao e necessario para o modo usuario;
- nao e necessario para o modo desenvolvedor basico.

## 11. Configuracoes do plugin QGIS

O painel QGIS do SIGMAI mostra e controla:

- status da Bridge;
- host;
- porta;
- token;
- pairing code;
- caminho do session file;
- Start Bridge;
- Stop Bridge;
- Copy Token;
- Regenerate Token;
- Copy Pairing Code;
- Copy Session Path;
- Open Diagnostics Folder;
- Copy CLI Command;
- Copy MCP Hint;
- Auto-start Bridge;
- Write local session file.

### 11.1 Host

Valor padrao:

```text
127.0.0.1
```

Regra:

- nao usar `0.0.0.0`;
- nao expor publicamente;
- A Bridge e apenas local.

### 11.2 Porta

Valor padrao:

```text
8765
```

Se a porta estiver ocupada, o plugin deve reportar erro claro.

### 11.3 Auto-start Bridge

Opcao:

```text
Start Bridge automatically when QGIS starts
```

Estado padrao:

```text
desativada
```

Motivo:

- seguranca;
- usuario precisa optar por iniciar automaticamente.

Quando ativada:

- plugin tenta iniciar Bridge ao carregar QGIS;
- gera novo token;
- grava session file se permitido;
- registra logs.

### 11.4 Write local session file

Opcao:

```text
Write local session file for AI clients
```

Estado:

- ativada quando a Bridge esta ativa, salvo se usuario desativar.

Funcao:

- permitir que Codex/CLI/MCP encontrem a Bridge sem copiar token.

### 11.5 Token

O token e o segredo real da sessao.

Regras:

- sempre exigido;
- nunca removido;
- nunca substituido por pairing code;
- nao deve ser versionado;
- nao deve ser exposto em relatorios publicos.

### 11.6 Pairing code

Codigo curto para conectar localmente.

Ele nao autoriza sozinho.

Ele aponta para um session file local que contem o token.

## 12. Comandos implementados

Esta lista reflete o estado atual de `sigmai/permissions.py`.

### 12.1 Sistema

- `status`;
- `get_capabilities`;
- `get_qgis_environment`;
- `get_bridge_config`;
- `get_logs`;
- `get_recent_errors`.

### 12.2 Projeto

- `get_project_info`;
- `get_project_crs`;
- `list_project_layers`.

### 12.3 Camadas

- `list_layers`;
- `get_layer_info`;
- `load_vector_layer`;
- `export_layer`.

### 12.4 Processing

- `run_processing` com allowlist.

Allowlist inicial:

- `native:buffer`;
- `native:clip`;
- `native:dissolve`;
- `native:fixgeometries`;
- `native:reprojectlayer`;
- `native:multiparttosingleparts`;
- `native:centroids`;
- `native:intersection`;
- `native:union`;
- `native:difference`;
- `native:extractbyattribute`;
- `native:extractbylocation`.

### 12.5 Cartografia e layouts

- `list_layouts`;
- `create_layout`;
- `export_layout`.

### 12.6 Simbologia

Implementado mas desativado:

- `apply_single_symbol`.

Motivo:

- estrutura planejada, mas ainda nao validada o bastante para liberar.

### 12.7 CRS e qualidade de dados

- `diagnose_crs`;
- `validate_geometries`;
- `fix_geometries`.

### 12.8 Vetores

- `buffer`;
- `clip`;
- `dissolve`;
- `reproject_layer`.

### 12.9 Plugin Management

- `list_installed_plugins`;
- `inspect_plugin`;
- `validate_metadata_txt`;
- `check_plugin_imports`;
- `check_plugin_structure`;
- `check_plugin_resources`;
- `check_plugin_icon`;
- `check_plugin_runtime_status`;
- `check_plugin_menu_actions`;
- `check_plugin_toolbar_actions`;
- `check_processing_provider_registration`;
- `check_plugin_algorithm_registration`;
- `collect_plugin_logs`;
- `generate_plugin_report`;
- `package_plugin_zip`;
- `search_qgis_plugin_repository`;
- `download_qgis_plugin_zip`;
- `inspect_qgis_plugin_zip`;
- `install_plugin_from_zip`;
- `install_qgis_plugin_from_repository`;
- `install_plugin_from_folder`;
- `update_plugin_from_folder`;
- `enable_plugin`;
- `disable_plugin`;
- `reload_plugin`;
- `uninstall_plugin`.

### 12.10 Self Management

- `self_inspect`;
- `self_health_check`;
- `self_generate_report`;
- `self_backup`;
- `self_validate_update`;
- `self_stage_update`;
- `self_apply_update`;
- `self_restart_required`;
- `self_rollback`.

## 13. Comandos planejados

Ainda nao implementados ou nao liberados:

- `apply_categorized_style`;
- `apply_graduated_style`;
- `create_basic_map`;
- `generate_basic_map`;
- `generate_workflow_report`;
- `run_plugin_unit_tests`;
- `run_plugin_smoke_tests`;
- `generate_plugin_publication_checklist`;
- executor completo de workflows.

## 14. Modo desenvolvedor

O modo desenvolvedor permite que a IA ajude na criacao, teste, diagnostico e empacotamento de plugins QGIS.

Fluxo recomendado:

1. `status`;
2. `get_capabilities`;
3. `get_qgis_environment`;
4. `list_installed_plugins`;
5. `inspect_plugin`;
6. `validate_metadata_txt`;
7. `check_plugin_structure`;
8. `check_plugin_imports`;
9. `check_plugin_resources`;
10. `check_plugin_icon`;
11. `check_plugin_runtime_status`;
12. `collect_plugin_logs`;
13. `generate_plugin_report`;
14. `package_plugin_zip` com `dry_run=true`;
15. `package_plugin_zip` real se estiver tudo correto.

Regra fundamental:

- diagnosticar nao e executar plugin arbitrariamente.

`check_plugin_imports` usa AST, ou seja, le o codigo sem importar o plugin.

Plugins externos podem ser buscados e instalados pelo SIGMAI somente pelo fluxo seguro do repositorio oficial QGIS:

- `search_qgis_plugin_repository` consulta `https://plugins.qgis.org/plugins/plugins.xml` e exige `confirm_network=true`;
- `download_qgis_plugin_zip` baixa ZIP apenas de `plugins.qgis.org` por HTTPS;
- `inspect_qgis_plugin_zip` valida metadata e estrutura antes de instalar;
- `install_plugin_from_zip` instala ZIP validado com `dry_run` e confirmacao;
- `install_qgis_plugin_from_repository` orquestra busca, download e instalacao, mas continua restrito a rede confirmada, repositorio oficial, permissoes e reinicio posterior do QGIS.

O SIGMAI nao habilita plugin desconhecido automaticamente, nao libera algoritmos Processing externos sem allowlist e nao executa codigo arbitrario de plugins como parte da auditoria.

## 15. Plugin Management Mode

O Plugin Management Mode cuida de plugins QGIS instalados ou em pasta.

Ele permite:

- listar plugins;
- inspecionar plugin;
- validar metadata;
- validar estrutura;
- validar imports;
- validar recursos;
- validar icone;
- verificar runtime;
- verificar menu/toolbar de forma parcial;
- verificar providers Processing;
- gerar relatorio;
- empacotar;
- instalar;
- atualizar;
- habilitar;
- desabilitar;
- recarregar;
- desinstalar com protecao.

Operacoes de escrita:

- exigem confirmacao;
- suportam dry-run quando aplicavel;
- fazem backup quando necessario;
- nao devem ser usadas diretamente sobre `sigmai`.

## 16. Self-Management Mode

O Self-Management Mode existe porque a Bridge deve conseguir gerenciar a si mesma sem se destruir.

Regra principal:

```text
Nunca atualizar sigmai diretamente via update_plugin_from_folder.
```

Fluxo seguro:

1. `self_inspect`;
2. `self_health_check`;
3. `self_validate_update`;
4. `self_stage_update` com `dry_run=true`;
5. `self_stage_update` com confirmacao;
6. `self_backup`;
7. `self_apply_update` com confirmacao;
8. reiniciar QGIS se `restart_required=true`;
9. `self_rollback` se necessario.

Motivo:

- hot reload agressivo da propria Bridge pode derrubar o servidor no meio de uma resposta.

## 17. Modo usuario / cartografico

Estado atual:

- parcialmente implementado;
- comandos basicos prontos;
- comandos cartograficos avancados planejados.

Ja existe:

- listar camadas;
- obter informacoes de camada;
- obter informacoes do projeto;
- listar layouts;
- criar layout basico;
- exportar layout;
- carregar camada vetorial;
- rodar Processing generico controlado;
- diagnosticar CRS;
- validar geometrias;
- corrigir geometrias;
- gerar buffer;
- recortar camada;
- dissolver camada;
- reprojetar camada;
- exportar camada vetorial.

Ainda falta:

- simbologia tematica;
- criacao de mapa final de alto nivel;
- relatorio de workflow.

## 18. Processing Toolbox

Implementado:

- `run_processing`.

Regras:

- valida algoritmo por allowlist;
- protege sobrescrita;
- usa dry-run;
- retorna erro estruturado;
- nao deve ser usado como escape para execucao arbitraria.

Planejado:

- allowlist por categorias;
- comandos de alto nivel para buffer, clip, dissolve etc.;
- validacao de parametros antes da execucao;
- job queue para operacoes longas.

## 19. Dados de teste

Pasta encontrada:

```text
%SIGMAI_TEST_DATA_DIR%
```

Conteudo confirmado:

- 3 shapefiles completos;
- 4 rasters `.tif`;
- 2 arquivos `.gpx`;
- 1 arquivo `.kml`.

Shapefiles:

- `Estados/BR_UF_2025.shp`;
- `Municipios/SP_Municipios_2025.shp`;
- `Pais/BR_Pais_2025.shp`.

Regra:

- nunca alterar os dados originais;
- saidas devem ir para `test_outputs/`.

## 20. CLI simples

Arquivo:

```text
tools/sigmai.py
```

Comandos principais:

```powershell
python tools\sigmai.py status
python tools\sigmai.py capabilities
python tools\sigmai.py qgis-info
python tools\sigmai.py layers
python tools\sigmai.py plugins
python tools\sigmai.py test
python tools\sigmai.py open-qgis
python tools\sigmai.py install-plugin
```

Comandos de plugin:

```powershell
python tools\sigmai.py inspect-plugin sigmai
python tools\sigmai.py plugin-structure sigmai
python tools\sigmai.py plugin-imports sigmai
python tools\sigmai.py plugin-resources sigmai
python tools\sigmai.py plugin-icon sigmai
python tools\sigmai.py plugin-report sigmai
python tools\sigmai.py package-plugin sigmai test_outputs\sigmai_package.zip --dry-run
```

Comandos de self-management:

```powershell
python tools\sigmai.py self-inspect
python tools\sigmai.py self-health-check
python tools\sigmai.py self-backup --dry-run
python tools\sigmai.py self-validate-update C:\caminho\para\sigmai
python tools\sigmai.py self-stage-update C:\caminho\para\sigmai --dry-run
```

## 21. Cliente Codex

Arquivo:

```text
codex_plugin/client/sigmai_client.py
```

Comandos comuns:

```powershell
python codex_plugin\client\sigmai_client.py status
python codex_plugin\client\sigmai_client.py capabilities
python codex_plugin\client\sigmai_client.py environment
python codex_plugin\client\sigmai_client.py list-layers
python codex_plugin\client\sigmai_client.py list-plugins
python codex_plugin\client\sigmai_client.py inspect-plugin --plugin-name sigmai
python codex_plugin\client\sigmai_client.py plugin-imports --plugin-name sigmai
```

Formas de conexao:

1. parametros CLI;
2. variaveis de ambiente;
3. session file;
4. pairing code;
5. token manual.

Variaveis:

- `SIGMAI_SESSION_FILE`;
- `SIGMAI_PAIRING_CODE`;
- `SIGMAI_TOKEN`;
- `SIGMAI_HOST`;
- `SIGMAI_PORT`.

## 22. MCP Server

Estado atual:

- implementado como wrapper local minimo;
- ainda nao e integracao final com SDK MCP formal.

Ferramentas atuais:

- `sigmai_status`;
- `sigmai_get_capabilities`;
- `sigmai_get_qgis_environment`;
- `sigmai_list_layers`;
- `sigmai_get_layer_info`;
- `sigmai_load_vector_layer`;
- `sigmai_list_layouts`;
- `sigmai_inspect_plugin`;
- `sigmai_validate_metadata`;
- `sigmai_run_autotest`.

Seguranca:

- descobre session file local;
- usa token local;
- chama apenas `127.0.0.1`;
- nao abre acesso remoto;
- nao executa Python arbitrario.

## 23. Autoteste

Script principal:

```text
tools/sigmai_autotest.py
```

Cenarios:

```powershell
python tools\sigmai_autotest.py --install-plugin
python tools\sigmai_autotest.py --install-plugin --launch-qgis
python tools\sigmai_autotest.py --wait-bridge
python tools\sigmai_autotest.py --run-integration
python tools\sigmai_autotest.py --full --launch-qgis
```

Com session discovery ativo, nao precisa passar token manualmente.

Relatorios:

- `diagnostics/SIGMAI_AUTOTEST_REPORT.json`;
- `diagnostics/SIGMAI_AUTOTEST_REPORT.md`;
- `diagnostics/integration_test_results.json`;
- `diagnostics/integration_test_results.md`.

## 24. Instalacao do plugin QGIS

Plugin instalado esperado:

```text
%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\sigmai
```

Novo caminho recomendado:

```text
%QGIS_PROFILE%\python\plugins\sigmai
```

ZIP atualizado:

```text
%SIGMAI_REPO%\dist\sigmai.zip
```

Copia tambem em:

```text
%SIGMAI_REPO%\dist\sigmai.zip
```

Observacao importante:

- houve erro de permissao ao tentar sobrescrever diretamente a pasta instalada do plugin pelo Codex;
- o caminho mais confiavel e reinstalar pelo ZIP no QGIS ou fechar QGIS antes de tentar atualizar arquivos.

## 25. Segurança

Regras mantidas:

- host fixo em `127.0.0.1`;
- token bearer obrigatorio;
- session file local;
- sem `0.0.0.0`;
- sem acesso remoto;
- sem autenticacao em nuvem;
- sem multiusuario;
- sem execucao Python arbitraria;
- comandos desconhecidos rejeitados;
- comandos perigosos exigem confirmacao;
- escrita em plugin exige dry-run/confirmacao;
- self-update usa staging, backup e rollback.

Validador bloqueia tokens perigosos em comandos JSON, como:

- `eval`;
- `exec`;
- `subprocess`;
- `os.system`;
- `popen`;
- `shell`;
- `cmd`.

Valores que sao apenas caminhos sao tratados como caminhos para evitar falso positivo com pastas como `python/plugins`.

## 26. Logs e auditoria

Logs internos registram:

- start/stop da Bridge;
- origem da requisicao;
- comando recebido;
- sucesso/falha;
- erros recentes.

Comandos relacionados:

- `get_logs`;
- `get_recent_errors`;
- `collect_plugin_logs`.

Relatorios sao gerados em:

```text
diagnostics/
```

Saidas de teste e pacotes:

```text
test_outputs/
```

## 27. Relatorios importantes existentes

- `RELATORIO_COMPLETO_SIGMAI.md`;
- `RELATORIO_EXPANSAO_SIGMAI.md`;
- `RELATORIO_ANALISE_QGIS_PYQGIS_PROCESSING.md`;
- `RELATORIO_AUTOINSTALL_AUTOTEST_SIGMAI.md`;
- `RELATORIO_DIRECT_CONNECTION_SIGMAI.md`;
- `RELATORIO_CONEXAO_DIRETA_IAS_SIGMAI.md`;
- `RELATORIO_PLUGIN_MANAGEMENT_SELF_MANAGEMENT.md`.

Este documento mestre consolida esses relatorios e deve ser atualizado daqui para frente.

## 28. Limitacoes atuais

Limitacoes tecnicas:

- MCP ainda e wrapper JSON-lines, nao SDK formal;
- VS Code extension ainda nao foi implementada;
- comandos GIS avancados de primeira linha ja foram implementados; ainda faltam simbologia, mapas compostos e raster;
- Processing ja possui allowlist inicial, mas ainda precisa de perfis mais maduros;
- operacoes longas ainda sao sincronas;
- nao ha job queue;
- hot reload da propria Bridge e bloqueado por seguranca;
- menu/toolbar actions de plugins sao inspecionadas parcialmente;
- AST de imports nao garante disponibilidade real de todos os pacotes.

Limitacoes operacionais:

- QGIS precisa estar aberto para comandos PyQGIS reais;
- se session file estiver desativado, o usuario precisa passar token;
- atualizar arquivos do plugin carregado pode exigir reiniciar QGIS;
- instalar diretamente na pasta do perfil pode falhar por permissao/lock.

## 29. Proximos passos recomendados

Prioridade 1:

- reinstalar ZIP atualizado no QGIS;
- reiniciar QGIS;
- validar `self_health_check` via Bridge real;
- rodar autoteste completo.

Prioridade 2:

- adicionar comandos GIS de alto nivel:
  - `diagnose_crs`;
  - `validate_geometries`;
  - `buffer`;
  - `clip`;
  - `dissolve`;
  - `reproject_layer`.

Prioridade 3:

- fortalecer MCP com SDK formal;
- integrar mais comandos de plugin management ao MCP;
- criar configuracoes prontas para Claude/VS Code/Cursor.

Prioridade 4:

- criar checklist automatizado para QGIS Plugin Repository;
- criar smoke tests reais de plugin;
- criar gerador de skeleton de plugin.

Prioridade 5:

- iniciar VS Code Extension.

## 30. Politica de atualizacao deste documento

Este arquivo deve ser atualizado quando:

- novo comando for criado;
- comando for removido ou desativado;
- permissao mudar;
- configuracao mudar;
- arquitetura mudar;
- fluxo de instalacao mudar;
- autoteste mudar;
- relatorio importante for gerado;
- limitacao for resolvida;
- risco novo for descoberto.

Ao final de cada fase, atualizar:

1. estado atual;
2. comandos implementados;
3. configuracoes;
4. seguranca;
5. testes executados;
6. limitacoes;
7. proximos passos.

## 31. Checklist rapido de manutencao

Antes de encerrar uma nova fase:

- atualizar este documento;
- rodar unit tests;
- rodar compileall;
- gerar ou atualizar relatorio da fase;
- atualizar ZIP do plugin se arquivos do QGIS plugin mudaram;
- documentar se QGIS precisa reiniciar;
- nunca prometer que arquivos foram instalados no perfil real se a copia falhou por permissao.

## 32. Comandos uteis para a proxima sessao

Com QGIS aberto e Bridge online:

```powershell
python tools\sigmai.py status
python tools\sigmai.py capabilities
python tools\sigmai.py qgis-info
python tools\sigmai.py layers
python tools\sigmai.py plugins
python tools\sigmai.py self-health-check
python tools\sigmai.py plugin-report sigmai
python tools\sigmai.py test
```

Para testar localmente sem QGIS:

```powershell
python -m unittest discover tests
python -m compileall -q sigmai codex_plugin tools mcp_server tests
```

Para gerar ZIP do plugin:

```powershell
python tools\package_qgis_plugin_zip.py
```

## 33. Estado final desta revisao

Nesta revisao, o SIGMAI esta em um estado de plataforma em expansao:

- Bridge QGIS funcional;
- protocolo estruturado funcional;
- cliente Codex funcional;
- session discovery funcional;
- pairing code funcional;
- CLI simples funcional;
- autoteste funcional;
- plugin management implementado;
- self-management implementado com abordagem conservadora;
- identidade publica SIGMAI aplicada;
- comandos GIS de alto nivel implementados;
- migracao tecnica iniciada para pacote QGIS `sigmai`;
- documentacao consolidada neste documento.

O projeto ainda nao e produto final, mas ja tem base arquitetural solida para evoluir como plataforma profissional IA/QGIS.
## Fase 2.1 — Cartografia Atômica

O SIGMAI agora possui base de comandos cartográficos atômicos para montar mapas passo a passo:

- `add_layout_map`
- `set_layout_extent`
- `add_layout_label`
- `add_layout_legend`
- `add_layout_scale_bar`
- `add_layout_north_arrow`
- `set_layer_style`
- `generate_basic_map`
- `generate_workflow_report`

Decisão técnica: `create_layout` continua sendo apenas a criação da página/base. Um mapa cartograficamente completo exige item de mapa, extent, estilo, título, legenda, escala, norte, fonte/créditos e exportação.

Limitações restantes: grade cartográfica, ordem de camadas e destaque por feição ainda estão planejados.
## Fase 2.2 - Cartografia segura por CRS validada

Data de validacao: 2026-05-22.

A falha de mapas brancos foi causada por uso direto de extents de camadas projetadas em layouts/projetos com CRS diferente. O caso critico era projeto em `EPSG:4674` com camadas em `EPSG:31983`.

Regra implementada e validada:

- `add_layout_map` transforma o extent da camada para o CRS do projeto antes de aplicar ao item de mapa;
- `set_layout_extent` tambem usa extent transformado quando recebe `layer_id`;
- o item de mapa usa o CRS do projeto;
- `evaluate_layout_cartographic_completeness` inclui avaliacao visual do PNG exportado.

Resultados depois de reiniciar o QGIS e carregar o codigo corrigido:

- bateria reduzida: 30/30 mapas renderizados, 0 brancos;
- bateria completa: 200/200 comandos OK, 200/200 mapas renderizados, 0 brancos;
- `EPSG:4674`: 80/80 renderizados;
- `EPSG:31983`: 120/120 renderizados;
- modos `basic_auto`, `atomic_auto` e `atomic_manual`: todos sem falha visual.

Classificacao atual: `LEVEL 5 - Cartographic Map Generation Capable`.

Melhorias visuais restantes:

- escala grafica ainda pode aparecer como `0 km` em projetos CRS geograficos;
- legenda ainda pode incluir camadas irrelevantes do projeto;
- seta norte pode colidir com mapa/legenda em alguns layouts;
- templates cientificos mais sofisticados ainda estao planejados.

## 25. Atualizacao 2026-05-22 - Consolidacao Level 5 e inicio Level 6

Esta fase consolidou o nivel cartografico ja validado e iniciou `LEVEL 6 - Vector Analysis and Attribute Capable`.

Refinamentos cartograficos:

- `add_layout_legend` passou a aceitar `legend_layers`, `linked_layer_ids` e `filter_to_map_layers`;
- `generate_basic_map` passou a aceitar `legend_layers`, `layout_template`, `scale_strategy` e `prefer_projected_scale`;
- `generate_basic_map` agora usa legenda focada na camada principal por padrao;
- `add_layout_scale_bar` retorna warning quando a escala metrica pode ser aproximada por CRS geografico;
- o posicionamento padrao da seta norte foi ajustado para reduzir colisao com mapa/legenda.

Novos comandos de layer tree:

- `list_layer_tree`;
- `set_layer_visibility`;
- `move_layer_order`;
- `create_layer_group`;
- `move_layer_to_group`.

Novos comandos de atributos:

- `list_fields`;
- `sample_features`;
- `inspect_attribute_table`;
- `field_statistics`;
- `unique_values`.

Novos comandos de expressoes QGIS:

- `validate_expression`;
- `evaluate_expression`;
- `query_features`.

Novos comandos de selecao e extracao:

- `select_by_expression`;
- `select_by_attribute`;
- `select_by_location`;
- `extract_by_expression`;
- `extract_by_attribute`;
- `extract_by_location`.

Novos comandos vetoriais complementares:

- `intersection`;
- `union`;
- `difference`;
- `centroids`;
- `multipart_to_singleparts`;
- `count_points_in_polygon`.

Ferramenta de teste criada:

- `tools/run_sigmai_vector_attribute_regression.py`.

Estado de implantacao:

- arquivos aplicados ao plugin instalado por self-management;
- backup criado automaticamente antes da aplicacao;
- `restart_required=true`, portanto a validacao runtime exige reiniciar o QGIS ou desativar/ativar o plugin SIGMAI.

## 26. Atualizacao 2026-05-22 - Cartografia profissional e orquestracao QGIS

Depois de abrir o QGIS novamente, o Level 6 foi validado em runtime:

- Bridge online;
- `registered_command_count=91`;
- `get_capabilities` mostrou grupos `layer_tree`, `attribute_table`, `expressions`, `selection` e `vector_analysis`;
- `tools/run_sigmai_vector_attribute_regression.py` passou 19/19.

Em seguida, foi implementada a primeira camada de cartografia profissional e orquestracao QGIS:

- `list_layout_templates`;
- `generate_professional_map`;
- `evaluate_map_quality`;
- `choose_style_profile`;
- `apply_cartographic_palette`;
- `validate_map_readability`;
- `detect_visual_collisions`;
- `suggest_layout_improvements`;
- `list_processing_providers`;
- `list_processing_algorithms`;
- `get_processing_algorithm_info`;
- `recommend_qgis_tool`;
- `list_qgis_plugins_extended`;
- `inspect_plugin_capabilities`;
- `list_plugin_processing_algorithms`;
- `get_plugin_algorithm_info`;
- `run_plugin_algorithm_safe`;
- `generate_plugin_adapter_report`.

Templates cartograficos iniciais: `scientific_basic`, `scientific_publication`, `environmental_report`, `minimal_clean`, `technical_dark`, `atlas_page`.

Perfis de estilo iniciais: `scientific_soft`, `environmental_green`, `technical_blue`, `monochrome_publication`, `contrast_highlight`, `terrain_context`, `biodiversity_report`, `protected_area_map`.

Foi criado o runner `tools/run_sigmai_professional_map_regression.py`.

Estado de implantacao:

- codigo aplicado ao plugin instalado por self-management;
- backup criado antes da aplicacao;
- `restart_required=true`;
- validacao runtime dos comandos Level 7 exige reiniciar o QGIS ou desativar/ativar o plugin SIGMAI.


