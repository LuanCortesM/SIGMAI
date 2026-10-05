# Changelog

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o versionamento é [semântico](https://semver.org/lang/pt-BR/).

## [1.2.0] — 2026-10-05

### Adicionado
- `colour_mode: "greyscale"` (ou `grayscale`, `grey`, `cinza`, `black_and_white`; padrão `"colour"`) em `compose_map`, `sigmai_plan_map`, `sigmai_compose_map` e `sigmai_campaign_map`.
- Em cinza: quatro preenchimentos a ΔL* ≥ 18, hachuras da quinta camada em diante, traços e pontos em preto e cinza, recorte do inserto em preto.
- Regras `CART073` (erro: figura pedida em cinza com tinta colorida; `GREYSCALE_CHROMA_MIN`, `GREYSCALE_MAX_CHROMATIC_FRACTION`) e `CART074` (números da barra legíveis).
- `sigmai_audit_layout` aceita `colour_mode` e `subject_layer_id`; num layout do SIGMAI, ambos vêm da receita.

### Alterado
- Ordem de desenho cartográfica (raster, polígonos, linhas, pontos; assunto sobre contexto); polígono que contém outra camada vira contorno de 0,7 mm por cima.
- `CART021` reprova camada da legenda coberta num quadro único (menos de 10 % visível, `COVERED_VISIBLE_MAX`); coordenadas da grade em `#1F1F1F`.

### Corrigido
- `CART003` não reprovava mapa sem barra de escala; `CART061` não era avaliada na auditoria de layout; `CART062` não via quadro em branco sob moldura e grade.
- A primeira camada pedida era desenhada por cima e cobria as demais; descrição de `layer_ids` corrigida.
- Números da barra de escala se sobrepunham em figura de coluna (`scalebar_spec`, `SCALEBAR_DIGIT_EM`, `SCALEBAR_LABEL_CLEARANCE`).

## [1.1.7] — 2026-10-04

Sem mudança de comportamento.

### Alterado
- Variáveis `l` renomeadas em `cartography/compose.py`, `qgis_actions/briefing.py` e `undo.py` (Flake8 E741).
- `tools/qgis_repository_scan.py` roda as regras do Flake8 ativas no plugins.qgis.org e reprova qualquer achado.

## [1.1.6] — 2026-10-04

### Alterado
- `tools/qgis_repository_scan.py` reprova qualquer achado do Bandit ou do detect-secrets fora de `UPLOAD_SKIPPED_RULES` (B110, B112), como o plugins.qgis.org.
- O servidor MCP usa `tempfile.gettempdir()` em vez de `"/tmp"` fixo; `# nosec` com motivo nas chamadas já restritas.

### Segurança
- Código de pareamento gerado com `secrets.choice` em vez de `random.choice` (`sigmai/session.py`, `core/session_paths.py`); o formato não muda.

## [1.1.5] — 2026-10-04

Sem mudança de comportamento.

### Adicionado
- `tools/qgis_qt6_check.py`: roda o `pyqt5_to_pyqt6.py` do QGIS no pacote ou no ZIP; usado no job "Qt6 / QGIS 4 compatibility" do CI.

### Alterado
- `plugin.py` sem o ramo `box.exec_()`; `ui/theme.py` sem importar PyQt5 (`is_dark_palette` usa a classe da paleta recebida).
- `tools/qgis_repository_scan.py` inclui B323, B501, B503 e B507; `CITATION.cff` e o README citam o DOI que reúne todas as versões.

## [1.1.4] — 2026-10-04

Sem mudança de comportamento.

### Adicionado
- `tools/qgis_repository_scan.py`: varreduras do repositório de plugins do QGIS (Bandit, detect-secrets, Flake8, arquivos suspeitos) no CI.

### Alterado
- Opção `persist_token` renomeada para `persist_access_key`, com migração automática na abertura (`migrate_legacy_settings`).
- Chaves de texto `advanced_*token*` passam a `advanced_*access_key*` e `STATUS_PASS` a `STATUS_PASSED`; texto exibido e respostas da ponte não mudam.

## [1.1.3] — 2026-10-04

### Adicionado
- `add_context_annotations` aceita `map_language` e nomeia as camadas que cria nas 15 línguas do mapa.
- `paper/` (rascunho para o *Journal of Open Source Software*, workflow `draft-pdf.yml`); `CITATION.cff` com ORCID; `CONTRIBUTING.md` com governança.

### Alterado
- Camada de contexto sem feição no quadro sai do quadro e da legenda, com nota.
- Documentação reorganizada: `ARCHITECTURE.md` e `MCP_SECURITY_MODEL.md` reescritos, índice em `docs/README.md`, `docs/archive/0.1/` e `docs/dev-notes/`.

### Corrigido
- Abrir o painel congelava o QGIS 4 e derrubava o QGIS 3.40 (da 1.0.1 à 1.1.2).
- O autoteste congelava o QGIS por 15 s e aprovava servidor MCP que não subia; agora o lança como um cliente MCP e nomeia a etapa que falhou.
- No Windows, o bloco de configuração apontava para `bin\python.exe`, que não sobe; passa a `sys.base_exec_prefix\python.exe`.
- Duas instâncias do QGIS: no Windows ligavam a ponte na mesma porta (agora `SO_EXCLUSIVEADDRUSE`), e fechar uma desconectava a IA da outra.
- CSV de pontos não carregava no Windows (`load_vector_layer`); compor mapa quebrava no Python 3.9 (QGIS 3.28 e 3.30).
- O assunto saía com a cor mais apagada quando listado depois do contexto.
- `tools/mcp_call.py` e `tools/end_to_end_mcp_demo.py` não alcançavam a ponte no Windows; `tools/prepare_public_release.py` varre só o publicado.

### Removido
- `mcp_server/` (o plugin do Codex aponta para `sigmai/mcp/sigmai_mcp.py`), `vscode_extension/` e scripts de outro projeto em `tools/`.

### Segurança
- O token volta a ser regenerado a cada abertura do QGIS ("manter o mesmo token" desligado por padrão); token antigo guardado é apagado.

## [1.1.2] — 2026-09-19

### Adicionado
- `tools/threshold_sensitivity.py` e `docs/experiments/2026-09-19_sensibilidade_limiares/`; `sigmai_cartographic_rulebook` publica `thresholds_provenance` e `inset_min_coverage`.

### Alterado
- Licença MIT em todo o projeto (plugin, `pyproject.toml`, `CITATION.cff`, README, janela Sobre), no lugar de GPL-3.0-or-later.
- Cada regra cita sua fonte: normativa (Decreto nº 89.817/1984, por analogia; Resolução IBGE PR nº 1/2015), acadêmica ou "decisão de projeto do SIGMAI".
- Limiares do compositor como constantes nomeadas (`LAYOUT_SWITCH_GAIN`, `MAX_EFFECTIVE_MARGIN_PERCENT`, `FONT_SCALE_EXPONENT`…).

### Corrigido
- `CART003` e `CART008` citavam normas ABNT erradas; o apelido depreciado `QgsCoordinateTransform.ReverseTransform` saiu do código (QGIS 4).

## [1.1.1] — 2026-09-19

### Alterado
- Arranjo dos itens de apoio pela forma dos dados (troca com ganho de escala acima de 12 %); `arrangement` (`coluna_lateral`, `faixa_inferior`) força um deles.
- Grade de painéis pela célula mais próxima do quadrado (três painéis em 270 × 150 mm ficam 3 × 1).

### Corrigido
- Números da barra de escala com o separador de milhar e decimal da língua do mapa (antes "1,000 2,000 m" em português).
- Preenchimento novo podia ser confundível com o de camada preservada por `apply_style=missing`.
- `status` lia o projeto fora da thread do Qt; a ponte serve um instantâneo tirado na thread principal.

## [1.1.0] — 2026-09-19

### Adicionado
- Regras `CART068` (rótulos não colocados), `CART069` (faixa do quadro sem dados) e `CART070` (cores confundíveis por daltônicos; categoria `simbologia`).
- Regras `CART071` (corpo das fontes na largura impressa; `print_width_mm`) e `CART072` (legenda cabe na caixa).
- `orientation: "auto"`: orientação pela forma dos dados, trocando só com ganho de escala acima de 12 %.
- Figura para revista: `journal_column` (`single`, `one_and_half`, `double`) ou `figure_width_mm`/`figure_height_mm`; template `publicacao`; `tif` e `jpg`.
- `panels=[...]` para três ou mais quadros com letras (a), (b), (c); `data_source` por camada (`{camada: fonte}`), com a fonte na legenda.
- `add_context_annotations`, `compose_campaign_map` (mapa de campanha com inserto) e `export_coordinate_table` (CSV com E/N e lon/lat).
- Receita do mapa no layout e no PNG (`sigmai:recipe`): `get_map_recipe`, `recompose_from_recipe` e `describe_map_for_methods` (parágrafo de Métodos).
- `undo_last_action` e `list_undo_history` desfazem escritas no projeto; nova categoria de consentimento **Projeto**.
- `spatial_relationship`, `set_layer_encoding` (com `encoding_problem` em `get_layer_info`) e `project_briefing`.
- `load_vector_layer` aceita `.csv`, `.txt` e `.tsv` de pontos, detectando separador, decimal, codificação e colunas (`x_field`/`y_field`).
- Ferramentas MCP `sigmai_briefing`, `sigmai_spatial_relationship`, `sigmai_add_context_annotations`, `sigmai_campaign_map`, `sigmai_export_coordinate_table`, `sigmai_map_recipe`, `sigmai_recompose_from_recipe`, `sigmai_methods_paragraph` e `sigmai_undo`.

### Alterado
- `CART042` aceita item sobre o quadro com menos de 3 % de tinta em volta; rótulos de polígono ficam dentro da feição (`centroidInside`).
- A legenda quebra nomes e reduz a fonte até 6 pt para caber na caixa; camadas só-de-rótulo não entram nela.
- Paleta de polígonos nova (`POLYGON_FILLS`), distinguível por daltônicos nos quatro primeiros preenchimentos.
- A auditoria de um layout composto usa as margens e a largura impressa da receita.

### Corrigido
- A receita quebrava com camada raster; `QFont.AbsoluteSpacing` era incompatível com Qt6; `extra_labels` aceita `{text, lon, lat}`.

## [1.0.3] — 2026-09-06

### Corrigido
- Itens sem `id` (layouts feitos à mão ou por script) eram descartados pela auditoria e por `list_layouts`; recebem id sintético e papel inferido.
- `resolve_page` lia 210 × 297 sem orientação como paisagem; `audit_map_layout` media a tinta no primeiro quadro, e não no maior.
- `CART007` reconhece cabeçalhos como "FONTES DOS DADOS" em seis línguas; `CART020` dispensa camadas só-de-rótulo (`label_only_layer_names`).

## [1.0.2] — 2026-09-05

### Adicionado
- Regra `CART067` (aviso): o inserto deve mostrar as camadas de contexto inteiras e conter o recorte principal.
- `sigmai_capabilities` aceita `group`, `search` e `names_only` e lista os parâmetros de cada comando; a ponte avisa (`warnings`) dos não lidos.

### Alterado
- Comando desconhecido recebe `UNKNOWN_ACTION` com sugestões; `layout_name` existente é substituído em vez de gerar "Título (2)".
- CRS da linha de crédito na língua do mapa; a nota do inserto diz qual camada o ajustou; `apply_boundary_highlight` aceita cor e espessura.

### Corrigido
- `compose_map(apply_style="missing")` reestilizava camada recém-estilizada; a origem do estilo fica marcada (`sigmai/style_origin`).
- `sigmai_layer_details`, `inspect_layer_style` e `list_layouts` entregavam menos do que prometiam; `status.project_loaded` vinha `null`.
- `sigmai_plan_map` e `sigmai_compose_map` não publicavam todos os parâmetros do compositor (`production_date`, `margin_mm`, `round_scale`…).

## [1.0.1] — 2026-09-05

### Adicionado
- Interface em nove línguas, numa lista no cabeçalho (Português, English, Español, Français, Deutsch, Italiano, 日本語, 简体中文, 繁體中文).
- Autoteste, consentimento, trilha de atividade e instruções dos clientes de IA traduzidos; código de língua tolerante (`pt`, `en-US`, `zh-TW`).
- Tema escuro do painel, conforme o tema do QGIS; *Avançado ▸ Aparência* força claro ou escuro.

### Corrigido
- Painel ilegível no Night Mapping e em outros temas escuros do QGIS.
- Abas cortadas e largura mínima de 600 px em alemão; as abas rolam num dock estreito.

## [1.0.0] — 2026-09-05

### Adicionado
- Primeira versão estável: toda ação de `get_capabilities` executa o que o nome diz; as demais estão desabilitadas com o motivo em `capabilities.limitations`.
- `execute_workflow` executa os passos com validação, consentimento e `dry_run` por passo; `export_report_pdf` gera PDF; `create_report` descreve o projeto.
- `repair_data_source_path`, `test_service_connection`, `list_ogc_connections`, `list_database_connections`, `gpx_track_length` e `map_gpx_track` implementados.
- `tools/release_battery.py`: bateria de liberação sobre a matriz de composição (`--full`).

### Alterado
- Estilos científicos recusam camada de outra geometria (`GEOMETRY_TYPE_MISMATCH`); `apply_boundary_highlight` tem perfil próprio.
- Denominador da escala com o separador de milhar da língua do mapa; painéis sem `panel_title` recebem "Painel A"/"Painel B".
- `map_language` desconhecido e `format` inválido são recusados; `margin_percent` limitado a 0–100.

### Corrigido
- `run_workflow_job` e `run_map_export_job` ignoravam o `dry_run`; a auditoria criava uma grade-fantasma no quadro inspecionado.
- A barra de escala invadia o rodapé; `CART007` falhava em japonês, chinês e francês; `CART043` ignorava o segundo painel.
- `output_path` relativo, ou do Windows num QGIS em Linux/macOS, é recusado; uma recusa deixava a simbologia do projeto trocada.

### Removido
- Desabilitados: atlas (`create_atlas`, `export_atlas_pdf`, `generate_map_book`…) e `create_map_hierarchy`.

### Segurança
- Família PostGIS desabilitada (`load_postgis_layer`, `test_postgis_connection`…): o erro do provedor podia expor a senha da conexão.

## [0.2.2] — 2026-09-04

### Adicionado
- `second_map`: dois quadros na mesma folha, na mesma escala por padrão; regra `CART066` reprova painel duplo que não declara as escalas.
- `subject_layer_id` (assunto enquadrado, demais camadas como contexto), `include_inset` (inserto de localização) e `label_field` (rótulos com halo).
- `scale` fixa a escala impressa e recusa a que cortaria os dados; com escala comum, o compositor sugere o inserto quando um painel fica minúsculo.
- `map_language`: textos do compositor em quinze línguas, à direita em árabe e hebraico; orientação da página reconhecida nas mesmas línguas.
- `load_wms_layer`, `load_wfs_layer`, `load_xyz_tile_layer` e `load_arcgis_rest_layer` carregam de fato; `attribution` vai à linha de fonte.
- `brief_plugin` (`sigmai_brief_plugin`): contrato de outro plugin numa chamada, com diagnóstico de provedor de Processing mal registrado.
- Avisos de camada XYZ sem tiles no zoom exigido e de camada de contexto sem feição no recorte.
- Aba **Ajuda** no painel; `tools/scenario_runner.py` e bancadas de exercício de plugins de terceiros e mapas de base.

### Alterado
- `CART007` exige fonte dos dados e autoria; `CART022` considera o comprimento absoluto da barra, que desce para uma faixa sob o mapa se não couber.
- Parâmetros lidos por `sigmai/cartography/params.py`: bandeiras por `as_flag`, vírgula decimal (`"7,5"`), `dpi` de 50 a 1200.
- Título e legendas longos são reduzidos ou quebrados (`sigmai/cartography/textfit.py`); `CONFIRMATION_REQUIRED` lista as flags aceitas.
- Logs de execução no perfil do QGIS; Modo DEV confirma com `SIM` ou `YES`; termos de mapa revistos em japonês, chinês e árabe.

### Corrigido
- `label_field`, página, template, `grid_style` e `apply_style` inválidos eram aceitos em silêncio; agora são recusados com o que é aceito.
- `confirm_overwrite: "false"` autorizava sobrescrever; valores de tipo errado quebravam a composição; `format` divergente da extensão passava.
- Exportação sem arquivo dava sucesso; projeto sem CRS derrubava a composição; escala podia sair 1:0.
- Barra de escala medida sem o segmento antes do zero; projeção automática pela extensão dos dados, e não pela impressa; CRS sem EPSG relatado vazio.
- `BRAZIL_BOUNDS` excluía as ilhas oceânicas; título sem espaço era cortado; o mapa saía bilíngue.
- Mapas saíam sem rótulos (campo vazio), sem amostra de KML/KMZ na legenda, com polígonos de mesmo preenchimento, inserto em cor aleatória ou legenda sem o painel (b).
- `run_plugin_algorithm_generic_safe` falhava sem o plugin Processing; `metadata.txt` com `%` seria rejeitado pelo repositório oficial.
- No Linux e no macOS, o plugin publicado gravava o arquivo de sessão fora da pasta em que o servidor MCP procura.

### Removido
- Parâmetro `style_profile` (sem efeito), arquivos órfãos e código morto.

### Segurança
- Rede externa exige `confirm_network=true`; `run_plugin_algorithm_safe` passa pelo portão de risco; extração de ZIP verifica caminho por relação.

## [0.2.1] — 2026-09-04

### Adicionado
- Regra `CART064` (UTM além da faixa útil da zona); recortes estaduais passam à Policônica do Brasil (EPSG:5880).
- `tools/check_qt6_compat.py` e `tools/qt6_panel_check.py` (CI), `tools/exercise_commands.py` e `tools/end_to_end_mcp_demo.py`.

### Alterado
- O Processing roda pela API de núcleo sem o plugin Processing, e o erro de algoritmo sugere nomes parecidos.

### Corrigido
- O plugin não abria no QGIS 4 e a exportação quebraria (enums do Qt6 como `QSizePolicy.Fixed` e `QgsLayoutExporter.Success`).
- Rodar um algoritmo do Processing apagava as camadas do projeto.
- Exportação transparente recebia nota A, e renderizar fora da thread principal gerava arquivo vazio; ambos passam a ser acusados.

## [0.2.0] — 2026-09-04

### Adicionado
- Consentimento em três modos (somente leitura, perguntar sempre, liberar nesta sessão), com sandbox de pastas, limites por sessão e trilha de auditoria.
- Layout por página (A5 a A0 ou milímetros), escala na série cartográfica, barra com 15–45 % do quadro e grade com intervalo calculado.
- Legenda com todas as camadas, rosa dos ventos como símbolo, reprojeção automática para UTM e simbologia segura para daltônicos.
- Regulamento de 26 regras (`sigmai_cartographic_rulebook`) e `audit_map_layout`, que audita qualquer layout e detecta quadro em branco.
- Painel acoplável: conexão em três passos, configuração por cliente de IA, autoteste e abas Acesso, Atividade e Avançado.

### Alterado
- Ações de escrita deixam de ser forçadas a `dry_run`; porta com fallback a partir da 8765; HTTP/1.1 com conexão persistente.
- Token mantido entre sessões no perfil do usuário, com opção de desligar e botão para gerar outro; oculto por padrão.

### Corrigido
- Clientes MCP não conectavam: o servidor segue a especificação (JSON-RPC 2.0, handshake) e vai dentro do plugin (`sigmai/mcp/sigmai_mcp.py`).
- Grade sem intervalo não era desenhada; o arquivo de sessão gravava a porta errada; validava-se um comando e executava-se outro.
- Varredura de tokens bloqueados recusava campos inócuos; versão divergente entre arquivos; `IndexError` ao instalar plugin sem perfil.

### Segurança
- Instalar, remover e recarregar plugins e executar Python ficam fora do consentimento, exigindo o painel e o Modo DEV.

## [0.1.1] — 2026-05-27

### Adicionado
- Compatibilidade com Qt6 e diálogo responsivo.

## [0.1.0] — 2026-05-25

### Adicionado
- Primeira versão pública: ponte local com token, registro de comandos, permissões, dry-run e fundações de cartografia, vetor, raster e diagnóstico de plugins.

[0.2.1]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.2.1
[0.2.0]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.2.0
[0.1.1]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.1.1
[0.1.0]: https://github.com/LuanCortesM/SIGMAI/releases/tag/v0.1.0
