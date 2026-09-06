# Relatório técnico — Mapa A4 do Parque Estadual das Carnaúbas (PyQGIS puro, sem plugin)

Ambiente: QGIS 3.34.4 / PyQGIS em `python3.12`, executado com `xvfb-run -a` (sem display), sem internet.
Entregas: `/tmp/lab_direto/mapa.png` (A4 retrato, 1653×2338 px, 200 dpi, exportado de um `QgsPrintLayout`),
`/tmp/lab_direto/projeto.qgz` (8 camadas + layout "Mapa PE Carnaúbas A4" com 15 itens, caminhos relativos),
`/tmp/lab_direto/mapa.py` (script gerador), `/tmp/lab_direto/apoio_rotulos.gpkg` (camadas de apoio criadas pelo script),
`/tmp/lab_direto/inspect.py` (script de inspeção inicial).

---

## 1. Lista ordenada de execuções (13 no total)

| # | Ferramenta | O que rodou | Resultado / o que aprendi |
|---|-----------|-------------|---------------------------|
| 1 | Bash | `ls` + `ogrinfo -so -al` nos 3 arquivos | Municípios (224 feições) e UF em **EPSG:4674** (SIRGAS 2000 geográfico); KML em EPSG:4326 com campos ricos (`Nome_UC`, `Descricao`, `Dat_publ`, `a_decr_ha`, `Cod_CNUC`, `municipios`, `Fonte`). Extensão da UC: lon −41,23/−40,97, lat −3,35/−3,15. `head -60` cortou os últimos campos do KML. |
| 2 | Bash (script PyQGIS inline `inspect.py`) | Tipo de geometria, área em UTM 24S, teste `UF.contains(UC)`, municípios que intersectam, distâncias | **Surpresa central:** a UC está **100 % fora do Piauí** (9.987 ha fora, 0 dentro). Nenhum município piauiense a intersecta. O mais próximo é Cocal (~12 km), depois Luís Correia (~17 km). O KML diz `municipios = "Granja; Viçosa do Ceará"` (ambos CE), `Fonte = "CEUC - CEDIB/COBIO/SEMA"`, `Cod_CNUC = 0000.23.1933` (23 = código IBGE do Ceará) e `Descricao = "Decreto nº 28.154/2006"`. Área calculada 9.987 ha vs 10.005 ha decretados (diferença de 0,2 %, normal). Saída apareceu duplicada no terminal (peculiaridade do ambiente, sem efeito). |
| 3 | Write | Escrevi `mapa.py` (≈300 linhas) | — |
| 4 | Bash | 1ª execução de `mapa.py` | **Erro:** `QFont('DejaVu Sans', 9.5)` → `TypeError` (PyQt exige `int` no tamanho). |
| 5 | Bash (patch + rerun) | Troquei por `QFont().setPointSizeF()` e `QgsLayoutItemLabel.setTextFormat()`; rodou até o fim | PNG e QGZ gerados; projeto reaberto com 7 camadas válidas e 1 layout de 15 itens. Segfault **após** `exitQgis()` (inofensivo). Mensagem GDAL "PNG driver does not support update access" é ruído do QGIS ao tentar gravar metadados no PNG. |
| 6 | Read (PNG) | Conferência visual nº 1 | 7 problemas: barra de escala rotulada "0,005 km"; legenda invadindo a coluna de notas; `.replace(',', '.')` trocou todas as vírgulas do texto; "CEARÁ" do inset caiu fora do frame e o ponto de apoio apareceu como bolinha vermelha; "CEARÁ" do mapa principal em cima de uma cruz da grade; rótulo da UC cobrindo o polígono; espaço mal distribuído embaixo. |
| 7 | Bash (patch + rerun) | Corrigi os 7 itens (ver §3) | Rodou; mas os nomes das camadas do projeto ficaram com "\|" — `QgsLayerTreeLayer.setName()` renomeou as camadas reais. |
| 8 | Read (PNG) | Conferência nº 2 | Escala OK (0–20 km), vírgulas OK, CEARÁ no inset OK, rótulo da UC fora do polígono. Restava a 2ª linha da legenda longa demais e a divisa aparecendo na legenda como retângulo (polígono) em vez de linha. |
| 9 | Bash (patch + rerun) | Criei camada de **linha** (boundary do polígono do PI) no GPKG; encurtei o nome; usei `setUseLayerName(False)` + `setName()` | Nomes das camadas limpos, porém… |
| 10 | Read (PNG) | Conferência nº 3 | …a legenda voltou a mostrar os nomes das camadas (`limite_estadual_pi`), ignorando os nomes personalizados. |
| 11 | Bash (patch + rerun + auditoria do .qgz) | `legend/title-label` definido nos nós **antes** do clone da árvore + `refreshLayerLegend()`; `unzip -l`, contagem de `<LayoutItem>`, fontes de dados, dpi do PNG via PIL | PNG 1653×2338 @ 200 dpi; QGZ com 15 LayoutItems e caminhos relativos `./dados/...`, `./apoio_rotulos.gpkg`. |
| 12 | Read (PNG) | Conferência final | Legenda correta, nada sobreposto/cortado. Aprovado. |
| 13 | Write | Este relatório | — |

---

## 2. Decisões cartográficas e justificativas

**Tratamento da surpresa (UC fora do Piauí).** Em vez de esconder, o mapa assume o fato: subtítulo "Municípios de Granja e Viçosa do Ceará (CE), junto à divisa com o Piauí"; divisa estadual em linha preta tracejada grossa; nomes de estado "PIAUÍ" e "CEARÁ" em cinza espaçado; aviso em itálico sob "CEARÁ" ("malha municipal cearense não disponível nesta base"); nota explícita no rodapé com a distância medida (12 km) e os municípios cearenses do KML. O inset foi intitulado "Localização em relação ao Piauí" (e não "no Piauí").

**CRS.** Projeto, mapa principal e inset em **SIRGAS 2000 / UTM fuso 24 S (EPSG:31984)** — a UC (lon −41,2 a −41,0) e todo o entorno estão no fuso 24; datum idêntico ao do IBGE. O inset usa o mesmo CRS embora o oeste do Piauí caia no fuso 23 (distorção irrelevante num localizador de 1:14 M). O KML (WGS 84) é reprojetado em tempo real (WGS 84 ≈ SIRGAS 2000 na escala usada).

**Escala e extensão.** Mapa principal 175 × 161 mm a **1:450.000** (escala redonda, fixada com `setScale`), extensão E 212,6–291,4 km / N 9.600,8–9.673,2 km. Escolhida para: (a) a UC (29 × 22 km) ocupar ~65 mm de largura, em destaque à direita do centro; (b) mostrar uma faixa de ~27 km do Piauí à esquerda com 5 municípios inteiros ou parciais (Cocal, Luís Correia, Cajueiro da Praia, Bom Princípio do Piauí, Cocal dos Alves); (c) o topo ficar ao sul da linha de costa (lat −2,96), evitando mostrar "oceano" sem camada de costa no lado cearense.

**Hierarquia visual e cores.** UC = verde (#4caf50, 65 % opacidade) com contorno verde-escuro 0,7 mm — único elemento saturado; municípios do PI em bege claro (#f4efe2) com contornos cinza 0,28 mm; Ceará em branco (ausência de dado, explicada); divisa estadual em preto tracejado 0,9 mm. Rótulos: municípios 7,5 pt cinza-escuro com halo branco, quebra automática (14 caracteres), centróide da parte visível (`centroidWhole=False`) para nomes de polígonos cortados pela moldura; nome da UC 10 pt negrito verde-escuro **fora** do polígono (ponto de apoio ao lado do lobo SE) para não cobri-lo; estados 10 pt negrito cinza espaçado.

**Grade e moldura.** Grade geográfica (EPSG:4674) a cada 15′ em cruzes (não linhas, para não poluir), moldura zebrada 1,6 mm, anotações graus-minutos com zero à esquerda (`DegreeMinutePadded`: 3°00′S, 41°15′W) nos 4 lados, rotacionadas nas laterais.

**Inset.** 58 × 83 mm, polígono do Piauí em cinza-bege com o retângulo vermelho da área do mapa principal (overview vinculado ao mapa) e a UC em vermelho sólido; extensão alargada 90 km a leste para caber "CEARÁ"; nomes de MARANHÃO, CEARÁ, BAHIA e Oceano Atlântico para orientação; "PIAUÍ" posicionado pelo polo de inacessibilidade do polígono.

**Elementos marginais.** Título 15 pt + subtítulo itálico; legenda com 3 itens (nomes em 2 linhas via `setWrapString('|')`); barra de escala "Single Box" 4 × 5 km; escala numérica; bloco CRS/datum/grade; autoria e data (data do sistema no dia da geração); bloco de fontes com decreto, área decretada e código CNUC lidos do próprio KML; nota metodológica; rodapé "Mapa elaborado em QGIS 3.34 (PyQGIS)". Seta de norte = SVG nativo `NorthArrow_04.svg` vinculada ao mapa (`GridNorth`), no canto superior direito onde o mapa é vazio.

---

## 3. Erros e armadilhas da API encontrados (e soluções)

1. **`QFont(family, size)` só aceita `int`** — 9,5 pt quebrou. Solução: `QFont(family).setPointSizeF()`; e nos itens de layout usar `setTextFormat(QgsTextFormat)` (API atual) em vez de `setFont`/`setFontColor` (deprecados).
2. **Barra de escala com `setUnits(km)` + `setMapUnitsPerScaleBarUnit(1000)` rotulou "0,005 km".** Em QGIS 3.x, `mapWidth()` já converte a largura do mapa para a unidade da barra; `unitsPerSegment` é em km e o rótulo é `unitsPerSegment / mapUnitsPerScaleBarUnit`. Solução: `setMapUnitsPerScaleBarUnit(1.0)`.
3. **Camadas de pontos só para rótulo desenharam marcadores** (bolinha vermelha aleatória no inset). Solução: `layer.setRenderer(QgsNullSymbolRenderer())`.
4. **Rótulo cruzando a moldura é descartado** pelo motor de rótulos (CEARÁ no inset). Solução: alargar a extensão do inset (`setXMaximum(+90 km)`) e reposicionar o ponto.
5. **`QgsLayerTreeLayer.setName()` na árvore da legenda renomeia a camada do projeto** (nomes ficaram com "|"). Solução parcial: `setUseLayerName(False)` antes.
6. **…mas o rótulo de um nó "embutido no pai" (camada de símbolo único) é fixado na criação do `QgsSymbolLegendNode`** (`symbolLabel()` lê `legend/title-label` ou `name()` uma vez). `setName()` posterior não atualiza. Solução: definir `setCustomProperty('legend/title-label', ...)` nos nós do projeto **antes** de `setAutoUpdateModel(False)` (o clone herda) e ainda `legend.model().refreshLayerLegend(node)`.
7. **`legend.rect().height()` não é recalculado antes da renderização** (voltou 40 mm = valor que eu havia setado). Solução: posicionar os itens abaixo com um valor fixo (BY + 34).
8. **Legenda mostra polígono sem preenchimento como retângulo tracejado.** Para a divisa aparecer como linha, criei uma camada de linha com `QgsGeometry(polygon.constGet().boundary())` + `convertToMultiType()` gravada no GPKG.
9. **Camadas em memória não persistem no .qgz.** Todas as camadas de apoio foram gravadas em `apoio_rotulos.gpkg` via `QgsVectorFileWriter.create()` (`CreateOrOverwriteFile` na 1ª, `CreateOrOverwriteLayer` nas seguintes).
10. **`QgsApplication([], False)` (sem GUI) costuma falhar em `QFontDatabase`**; usei `GUIenabled=True` sob xvfb. **`setExtent()` redimensiona o item** — usei `zoomToExtent()` + `setScale()`. **Segfault na saída** ao criar um 2º `QgsProject()` de verificação antes de `exitQgis()` — ocorre depois de tudo gravado; ignorado.
11. Enums novos (3.26+): `Qgis.LabelPlacement.Horizontal/OverPoint`, `Qgis.LabelMultiLineAlignment.Center`, `Qgis.DistanceUnit.Kilometers` — os aliases antigos em `QgsPalLayerSettings` podem falhar por tipo.
12. Meu próprio bug: `.replace(',', '.')` aplicado ao texto inteiro para formatar "10.005" apagou todas as vírgulas da nota. Corrigido formatando só o número.

---

## 4. O que tive de adivinhar ou decidir sem saber

- **A UC é do Ceará, não do Piauí.** Não é adivinhação: o dado prova (0 ha dentro do PI; municípios Granja e Viçosa do Ceará; CNUC com código de UF 23; Decreto 28.154/2006 é do governo cearense). Mas a Maria disse "CEUC/SEMA-PI"; o campo `Fonte` do KML diz apenas "CEUC - CEDIB/COBIO/SEMA" sem UF. Citei como **"CEUC – CEDIB/COBIO/SEMA (Ceará)"** e na legenda "CEUC/SEMA-CE". Ela deve confirmar a instituição na dissertação.
- **Nome do produto IBGE:** escrevi "Malha Municipal Digital 2024" (o `.dbf` indica atualização 2025-03-06, compatível com a malha 2024 publicada em 2025). Sem internet, não pude confirmar o título oficial.
- **Municípios cearenses do entorno não estão na base fornecida.** Preferi NÃO desenhar sedes/limites de Granja e Viçosa do Ceará de memória; mencionei-os só em texto. O lado cearense ficou em branco com aviso.
- **Sem camada de costa/oceano:** limitei o topo do mapa a −2,96° para não mostrar mar como "vazio" idêntico ao Ceará. No inset, "Oceano Atlântico" é apenas um rótulo.
- **Posições dos nomes de estados** (mapa e inset) foram escolhidas por mim em coordenadas fixas (conferidas visualmente).
- **Escala 1:450.000** e A4 retrato: escolhas minhas (a mensagem só pedia A4).
- **Data:** data do sistema no dia da geração (06/09/2026).
- **Arquivos de `trilha/`** ignorados: não fazem parte do pedido.
- **Título:** mantive "e municípios do entorno" (pedido dela) e usei o subtítulo para deixar claro que só há municípios piauienses na base.

---

## 5. Avaliação honesta: está bom para publicar?

**Sim, como mapa de localização de dissertação, com uma ressalva conceitual importante que não é do mapa, e sim do enunciado.** O mapa tem todos os elementos exigidos (título, UC em destaque, municípios rotulados, grade com coordenadas, legenda, escala gráfica e numérica, norte, inset, fontes, autoria, CRS/datum, data), nada se sobrepõe ou corta, tipografia legível a 200 dpi, hierarquia visual clara e é reproduzível pelo script e pelo projeto.

O que **faltou ou pode melhorar**:
1. **Malha municipal do Ceará (Granja e Viçosa do Ceará)** — é o "entorno" real da UC. Sem ela, metade do mapa é branco. Basta a Maria baixar a malha municipal do CE (IBGE 2024) e eu incluo em minutos; a nota de rodapé então some.
2. **Hidrografia, rodovias e sedes municipais** dariam contexto (não havia dados).
3. **Linha de costa/oceano** não está representada; evitei mostrar.
4. Se a banca exigir, a UC poderia ser hachurada em vez de preenchida, e a escala poderia ser 1:300.000 num A4 paisagem para ampliar a UC.
5. Confirmar a citação institucional da fonte do limite (SEMA-CE vs. "SEMA-PI" da mensagem).

---

## 6. Contagem e tempo

- **Execuções de ferramentas: 15** — 7 Bash (2 de inspeção, 5 rodadas/patches do script; a auditoria do .qgz foi embutida na rodada 11), 4 Read do PNG, 2 Write (script e relatório), 2 Edit (correções desta contagem no relatório). Bem abaixo do limite de ~40.
- **Tempo aproximado:** ~20 minutos de relógio (04:57 → 05:13 para o mapa final; cada execução do script leva ~2 s).
