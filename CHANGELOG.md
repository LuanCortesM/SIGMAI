# Changelog

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o versionamento é [semântico](https://semver.org/lang/pt-BR/).

## [1.3.1] — 2026-10-28

Achados de um assistente de IA que fez as figuras do artigo do SIGMAI só pelas ferramentas do plugin, num QGIS limpo.

### Adicionado
- `rename_layer`: muda o nome da camada, que é o que a legenda mostra. Sem ele, o assistente recarregou os arquivos com outro nome para trocar a legenda (a taxonomia de comandos já o dava como implementado). 237 comandos no catálogo, 224 habilitados.

### Corrigido
- Numa figura de comparação, `CART076` (pontos que escondem a contagem), `CART077` (rampa de raster) e `CART080` (mapa de calor) mediam só o primeiro painel; agora medem todos, e a mensagem diz o painel.
- `recompose_from_recipe` herdava da receita o `recipe_path` e o `confirm_overwrite` do mapa original: regravava a receita de origem por cima e, sem um `output_path` novo, sobrescrevia o mapa. Agora só valem se vierem em `overrides`.
- Figura de periódico com dados em graus: a altura da página era escolhida pela proporção do recorte em graus, antes de o mapa ser reprojetado, e o mapa ganhava uma faixa de sobra (a 22° de latitude, um grau de longitude mede 0,92 de um de latitude). A altura passa a sair do recorte projetado, a mesma de quando map_crs é passado.
- `recompose_from_recipe` mantém o sistema de referência projetado da receita: escolhido de novo, ele dependia do projeto em que se recompunha, e um mapa em SIRGAS 2000 / UTM 23S voltava em WGS 84 / UTM 23S.
- Parágrafo de Métodos (`describe_map_for_methods`): dizia que a receita estava "nos metadados do arquivo exportado" também em PDF e SVG, onde ela fica no layout e no JSON; citava "(MACIEL, 2026)" em inglês e espanhol, que agora citam "(Maciel 2026)"; a referência do software dá o DOI do Zenodo em vez do GitHub; a mesma fonte de duas camadas sai uma vez; em PDF, o dpi só aparece se houver raster.
- `load_qml_style` e `save_qml_style` liam o resultado do QGIS na ordem inversa: o estilo carregado saía como não carregado e não era marcado como do usuário, e a composição podia trocá-lo pela paleta.
- `apply_single_symbol` em pontos e linhas: a opacidade ia para a camada inteira, o que pode levar o QGIS a rasterizar o mapa no PDF; agora vai para o símbolo. `fill_opacity` e `stroke_opacity` passam a valer para pontos.
- Legenda de círculos proporcionais: os valores eram potências de 10, e com área proporcional os círculos de 1 e 100 registros tinham 1,0 e 1,3 mm, com os rótulos sobrepostos; agora são valores redondos com círculos a pelo menos 2,5 mm um do outro. `legend_title` vazio deixa a legenda sem título, em vez de pôr o nome do campo. Uma legenda com círculos não se divide mais entre colunas, que separavam o título dos círculos.

## [1.3.0] — 2026-10-27

### Adicionado
- Regra `CART076` (aviso): os pontos não escondem a contagem. Os pontos de cada camada de símbolo de tamanho fixo são levados para mm do quadro e contados em células do tamanho do símbolo; reprova com 50 pontos ou mais e mais da metade oculta. No símbolo proporcional, mede os locais com o menor círculo e, quando se amontoam, diz o `scale` para agrupá-los. Mapa de calor e agrupamento ficam de fora.
- `count_points_by_site`: um ponto por local (coordenadas repetidas juntas, com casas decimais configuráveis), com o número de registros, gravado em GeoPackage e marcado como derivado da camada de origem. Com `scale` (o denominador da escala do mapa), junta os locais a menos de `min_spacing_mm` (padrão 1 mm) no papel, do mais cheio para o mais vazio, mantendo a coordenada real do mais cheio: a 1:300.000, os 11.224 locais dos registros do GBIF no Itatiaia viram 863, e os círculos sobrepostos caem de 79 % para nenhum.
- `apply_proportional_symbol_style`: área do símbolo proporcional a um campo numérico, os maiores desenhados primeiro, legenda de círculos aninhados, contorno num tom mais escuro da cor (um contorno branco formava uma mancha clara onde havia mais círculos).
- `compose_map` com `dense_points`: `"sites"` troca as camadas de pontos de assunto por um símbolo por local, agrupado na escala do próprio mapa (GeoPackage ao lado de `output_path`); `"heatmap"` as desenha como mapa de calor. O padrão continua `"points"`.
- `compose_map` com `title_placement`: `"caption"` faz a figura de artigo — título, fontes (com DOI), sistema de referência e crédito da ferramenta saem da imagem e voltam em `caption`, prontos para a legenda no texto, como pedem as revistas (a *Evolution*, que a *Biodiversity Informatics* adota: "Figure titles and legends should be included in the main text file"); `"none"` faz o mapa sem título, com os créditos no mapa; `"map"` continua o padrão. A página não reserva as faixas que ficam vazias, e o mapa ganha a altura. `CART001`, `CART007` e `CART008` leem a legenda guardada no layout; na figura de artigo a autoria é a do artigo, e a fonte continua obrigatória. Numa figura de periódico com título na imagem, uma nota sugere a legenda.
- `add_context_annotations` com `boundary_name`: o nome da divisa na legenda ("State boundary" em vez de "Border — States"); e com `label_within_layer_id`, os nomes das regiões vão na parte de cada uma que fica em volta da área do mapa e fora dela — no centro de Minas Gerais, o nome caía fora do quadro de um mapa do Itatiaia.
- `compose_map` com `map_crs="auto"`: a projeção sai do recorte também num continente (Lambert azimutal de áreas iguais centrada nos dados) e no mundo (Equal Earth), com a grade em graus e sem rosa dos ventos; o mapa-múndi sai também sem barra de escala e com a grade sem rótulos. Sem `"auto"`, esses mapas continuam em graus, e a nota diz como pedir a projeção.
- `apply_single_symbol` aceita `size_mm` para pontos.
- `sigmai.cartography.pointdensity`: a medida de pontos ocultos e de cobertura, em Python puro, e a escolha do símbolo de ponto.
- Regra `CART077` (aviso): a rampa de cores de um raster contínuo mostra os dados (percentis 2 a 98 dos pixels do quadro usam ao menos 40 % dela).
- Regra `CART078` (erro): coordenadas cabem no sistema de referência declarado — área de uso do EPSG com 3° de folga, graus declarados como UTM, pontos em 0,0.
- Regra `CART079` (aviso): o recorte não é aberto por poucos pontos isolados (diagonal acima de 5 vezes a do núcleo, no máximo 0,5 % ou 3 pontos isolados).
- Regra `CART080` (aviso): o mapa de calor mostra os lugares que têm pontos (no máximo 80 % deles abaixo de 2 % da densidade máxima).
- Regra `CART081` (aviso): painéis comparáveis usam a mesma régua de cor e de tamanho. A mesma variável em dois painéis — mapa de calor, classes graduadas ou símbolo proporcional — com réguas diferentes reprova; o mapa de calor com o máximo automático estica cada painel até o próprio pico.
- `apply_proportional_symbol_style` com `min_value` e `max_value`: a mesma régua de tamanhos em mais de uma camada ou painel.
- A receita refaz o mapa num QGIS que não tem o projeto: guarda o estilo de cada camada (QML), a reamostragem do relevo e, para divisas e nomes, o comando que os fez. `recompose_from_recipe` recarrega as camadas que faltam pela fonte gravada, ou, com `data_dir`, pelo nome do arquivo noutra pasta (de preferência com o mesmo SHA-256); refaz as de `add_context_annotations`; e reaplica o estilo da receita na camada achada pelo nome, que pode vir de outro mapa. Antes, só o PNG não bastava: a recomposição recusava com `LAYER_NOT_FOUND`. O inserto, a camada rotulada e a camada de onde saíram as divisas também entram na receita.

### Alterado
- O símbolo de ponto da paleta se ajusta ao quadro: de 2,2 mm quase opaco desce até 0,45 mm a 25 % de opacidade, até que no máximo um quarto dos pontos fique oculto e os símbolos cubram no máximo um quarto da área ocupada pelos pontos. Registros repetidos nas mesmas coordenadas ficam para a `CART076`. A composição informa o símbolo escolhido em `styling` e numa nota.
- Mapa de calor é tratado como um raster: fica embaixo, e os polígonos que o cobririam, de contexto ou também assunto, viram contorno por cima.
- `apply_raster_style` sem `min`/`max`: valores de preenchimento conhecidos (-32.768, -9.999 e outros) ficam fora da rampa e passam a sem dado na camada (o arquivo não muda); um pico isolado fica fora da rampa. As duas coisas são informadas.
- Mapa em coordenadas geográficas sai sem barra de escala métrica, que não valia para a folha; fica a escala numérica.
- Grade em graus: casas decimais conforme o intervalo (eram sempre três, e "90.000" se lia como noventa mil), símbolo de grau, separador decimal da língua do mapa e nenhum rótulo além de ±180° e ±90°, que o quadro de um mapa-múndi alcançava.
- Contorno da paleta afinado (ou retirado) em polígonos pequenos no papel, que o traço padrão fundia num bloco.
- `compose_map` recusa `label_field` numa camada com mais de 5.000 feições: o motor descartava quase todos os rótulos (98 % com 20.000 pontos) e a composição levava minutos.
- Amostra da legenda legível (ao menos 1,6 mm e 70 % de opacidade) para o ponto que o compositor reduziu.
- `apply_categorized_style` acima de `limit`: ficam as classes com mais feições, e não as primeiras em ordem alfabética; as demais vão para "Outros". `CART070` e `CART072` sugerem `limit=8` quando são classes demais.
- Grade em graus: latitude só nas laterais e longitude só em cima e embaixo; numa projeção cônica ou azimutal os meridianos curvos também cruzavam as laterais.
- Rodapé de um mapa numa Lambert azimutal criada pelo compositor (recorte regional fora do Brasil) declara o sistema de referência: a projeção não tem código nem nome, e o rodapé saía sem ele. `CART008` passa a vê-la.
- Contagens nas mensagens das regras novas com ponto de milhar ("362.210").
- Relevo e sombreamento com reamostragem bilinear na leitura do dado: o vizinho mais próximo repetia linhas de pixels antes do sombreamento, e as encostas saíam quadriculadas de riscas num mapa a 300 dpi.
- Figura de periódico (`figure_width_mm`, `journal_column`): barra de escala a partir do zero, sem o segmento à esquerda, que é convenção das folhas topográficas.
- Preenchimento de contexto da paleta em cinza quase branco, e não mais azul-claro, que fazia os municípios em volta de um parque parecerem mar; o terceiro preenchimento passa a âmbar um pouco mais firme, para os cinco primeiros continuarem distinguíveis nas três simulações de daltonismo.
- Rótulos quebrados das classes de um raster (cobertura do solo, declividade) caíam na classe vizinha: a legenda esconde "Band 1" reordenando as entradas, e o rótulo era escrito pela posição nova, mas o QGIS o lê pela original. A área urbana saía como "Bare or sparse vegetation".
- Rampas comuns ("Spectral", "Viridis" e as do ColorBrewer) funcionam mesmo sem a biblioteca de estilos do QGIS, que falta num QGIS sem interface em Linux.
- Exportação em TIFF pelo GDAL quando o Qt da instalação não tem o plugin de TIFF (QGIS 4 das imagens oficiais em Linux), com a resolução nas tags do arquivo.
- A camada de `count_points_by_site` é dado, e não anotação: com a marca das divisas e nomes, ela saía da linha de crédito, e a fonte do GBIF, com o DOI, sumia do rodapé.
- `apply_graduated_style` e `apply_raster_style` avisam quando os quantis coincidem e saem menos classes que as pedidas (contagens com muitos zeros).
- `CART075` indica pontos menores, mapa de calor ou símbolo por local quando quem cobre o assunto são pontos amontoados.
- A terceira simulação de `CART070` passa a se chamar `tritanomaly`: é a linha de tritanomalia de severidade 1,0 da tabela de Machado et al. (2009), cujo modelo não se destina à tritanopia.
- Referências das regras: `CART024` passa a citar Snyder (1987), e não o art. 20 do Decreto 89.817/1984, que trata de unidades do SI; `CART006` deixa de citar o art. 15, que pede valores de convergência e declinação, e declara a exigência de indicar o norte como decisão de projeto; `CART064` corrige a justificativa (o erro de escala cresce com a distância ao meridiano central) e declara a faixa de E como decisão de projeto; `CART070` deixa de afirmar que revistas exigem figuras para daltônicos.

## [1.2.0] — 2026-10-25

### Adicionado
- `colour_mode: "greyscale"` (ou `grayscale`, `grey`, `cinza`, `black_and_white`; padrão `"colour"`) em `compose_map`, `sigmai_plan_map`, `sigmai_compose_map` e `sigmai_campaign_map`.
- Em cinza: quatro preenchimentos a ΔL* ≥ 18, hachuras da quinta camada em diante, traços e pontos em preto e cinza, recorte do inserto em preto; camada com estilo próprio convertida mantendo as classes (graduado, categorizado, por regras, raster paletado).
- Regras `CART073` (erro: figura pedida em cinza com tinta colorida), `CART074` (números da barra legíveis, par a par) e `CART075` (erro: assunto do mapa coberto por outras camadas; `SUBJECT_VISIBLE_MIN`).
- `apply_graduated_style` aceita `method` (`equal_interval`, `quantile`, `jenks`, `pretty`), `color_ramp` e `unit`; rótulos na língua do mapa (`map_language`) e cores em passos iguais de claridade.
- `apply_raster_style`: rampa contínua ou em classes, valores únicos com nomes, relevo sombreado e cinza; `preset: "declividade_embrapa"`, `blend_mode`, rampas `hypsometric` e `slope`.
- `apply_heatmap_style`: mapa de calor para camada de pontos, com peso por campo.
- `load_vector_layer` abre KMZ, OSM/PBF, FlatGeobuf, GML e shapefile zipado, e escolhe a subcamada com `layer_name`.
- `native:joinattributestable` e `native:fieldcalculator` no Processing; `raster_slope` aceita `as_percent`.
- `sigmai_audit_layout` aceita `colour_mode` e `subject_layer_id`; num layout do SIGMAI, ambos vêm da receita.

### Alterado
- Ordem de desenho cartográfica (raster, polígonos, linhas, pontos; assunto sobre contexto); polígono que contém outra camada, ou que fica sobre um raster assunto do mapa, vira contorno por cima.
- `CART021` reprova camada da legenda coberta (menos de 10 % visível e menos de 1 % do quadro), medida pela composição dos canais alfa de cada camada renderizada como o quadro a desenha; camada sem feição na extensão tem mensagem própria.
- `CART070` compara polígono sem preenchimento com as linhas, pela cor do contorno, e cada hachura como família própria.
- Polígono preenchido que esconderia outra camada vira contorno: sobre um raster temático, sobre parte de outra camada (o imóvel sobre a sua APP) ou sobre outra camada que também forra o quadro; contornos de camadas diferentes em cores diferentes.
- `apply_categorized_style`: cor pelo nome da classe (água, floresta, área urbana...), paleta qualitativa sem par confundível por daltônicos, sem repetir cor, classes em ordem, categoria "Outros"; em linhas a cor vai no traço.
- Legenda em colunas quando sobra largura, nomes de classe quebrados, uma entrada só para camadas com as mesmas classes; relevo sombreado e mapa de base fora da legenda.
- Rótulo de linha acompanha a linha, com os trechos de mesmo nome fundidos; hidrônimos em itálico azul.
- Série de escalas com 1:300.000, 1:400.000 e degraus equivalentes; `raster_slope` e `raster_hillshade` aplicam a escala de 111.120 m por grau a raster em graus.
- `sigmai_campaign_map` enquadra também a área de estudo; `raster_clip_by_extent` limita o recorte à extensão do raster.
- `CART069` conta raster e a tinta de linhas e pontos como ocupação do quadro.
- Orientação omitida é escolhida pela forma do recorte, como `orientation: "auto"`.
- Faixa inferior na altura da legenda; seta de norte limitada a 8 % do lado menor da folha.
- Legenda de raster sem o nome da banda e com os extremos da rampa arredondados, no separador da língua do mapa.
- `map_language` obrigatório no esquema MCP de plan, compose e campaign; a resposta avisa quando falta.
- Coordenadas da grade em `#1F1F1F`.

### Corrigido
- `CART003` não reprovava mapa sem barra de escala; `CART061` não era avaliada na auditoria de layout; `CART062` não via quadro em branco sob moldura e grade.
- A primeira camada pedida era desenhada por cima e cobria as demais; descrição de `layer_ids` corrigida.
- Números da barra de escala se sobrepunham em figura de coluna.
- Com pasta de saída definida no painel, carregar dado de outra pasta era recusado: o caminho de leitura contava como gravação.
- Busca e instalação de plugin pelo repositório oficial falhavam (o `plugins.xml` passou a exigir a versão do QGIS; o nome do pacote não casava com o nome de exibição).
- A instalação de plugin gravava no perfil `default` do QGIS 3, e não no perfil em uso (QGIS 4 ou outro perfil).
- Mapa de base XYZ, WMS e ArcGIS REST saía em branco no QGIS 3.x: o endereço era codificado à mão e o provedor não o decodificava. A composição agora avisa quando um mapa de base não desenha nada.

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
