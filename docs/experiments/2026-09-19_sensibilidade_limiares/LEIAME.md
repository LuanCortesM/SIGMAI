# Sensibilidade dos limiares do regulamento e do compositor

Gerado por `tools/threshold_sensitivity.py` em 2026-09-19 18:36:42 sobre **138 mapas** compostos com os dados de teste (`_teste_sigmai`: malha municipal e limite do Piauí, PE das Carnaúbas, trilha do Itaguaré): a matriz de composição da bateria de liberação (4 templates × 4 páginas × 2 orientações × 4 variações) e os casos da matriz de dados.

Cada limiar foi variado sozinho, com os demais no valor atual, re-pontuando a **mesma observação** que o inspetor entregou ao regulamento (nenhum mapa foi recomposto). As colunas dizem em quantos mapas a regra reprova e em quantos a **nota** (A–E) muda em relação ao laudo atual. Um limiar é estável quando a coluna "mudam de nota" fica em zero numa vizinhança do valor atual; onde ela sobe, o valor escolhido está de fato decidindo algo, e a escolha precisa ser defendida por outro meio (leitores, norma, periódico).

Distribuição das notas no laudo atual: A = 93, B = 13, C = 32, D = 0, E = 0.

## Limiares do regulamento

### `vision.CONFUSABLE_DELTA_E` — CART070 (atual: 15)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 5 | 0 | 0 |
| 8 | 0 | 0 |
| 10 | 0 | 0 |
| 12 | 0 | 0 |
| **15** | 0 | 0 |
| 18 | 0 | 0 |
| 20 | 0 | 0 |
| 25 | 0 | 0 |
| 30 | 0 | 0 |

### `FRAME_BAND_EMPTY_MAX` — CART069 (atual: 0.05)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 0.01 | 3 | 13 |
| 0.02 | 3 | 13 |
| **0.05** | 40 | 0 |
| 0.08 | 80 | 7 |
| 0.1 | 104 | 10 |
| 0.15 | 138 | 21 |
| 0.2 | 138 | 21 |

### `MIN_PRINT_FONT_PT` — CART044 (atual: 6)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 4 | 0 | 0 |
| 5 | 0 | 0 |
| **6** | 0 | 0 |
| 7 | 72 | 17 |
| 8 | 106 | 28 |
| 9 | 130 | 39 |
| 10 | 138 | 41 |

### `SCALEBAR_MIN_FRACTION` — CART022 (atual: 0.15)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 0.05 | 0 | 0 |
| 0.1 | 0 | 0 |
| **0.15** | 0 | 0 |
| 0.2 | 25 | 8 |
| 0.25 | 53 | 17 |
| 0.3 | 59 | 17 |

### `SCALEBAR_MAX_FRACTION` — CART022 (atual: 0.45)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 0.3 | 4 | 0 |
| 0.35 | 0 | 0 |
| 0.4 | 0 | 0 |
| **0.45** | 0 | 0 |
| 0.5 | 0 | 0 |
| 0.6 | 0 | 0 |

### `MAP_DOMINANCE_MIN` — CART043 (atual: 0.35)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 0.2 | 0 | 0 |
| 0.25 | 0 | 0 |
| 0.3 | 0 | 0 |
| **0.35** | 0 | 0 |
| 0.4 | 0 | 0 |
| 0.45 | 0 | 0 |
| 0.5 | 3 | 0 |
| 0.6 | 70 | 0 |

### `OVERLAY_MAX_SURROUNDINGS_INK` — CART042 (atual: 0.03)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 0.005 | 0 | 0 |
| 0.01 | 0 | 0 |
| 0.02 | 0 | 0 |
| **0.03** | 0 | 0 |
| 0.05 | 0 | 0 |
| 0.08 | 0 | 0 |
| 0.1 | 0 | 0 |

### `LEGEND_OVERFLOW_TOLERANCE_MM` — CART072 (atual: 0.5)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 0 | 0 | 0 |
| 0.1 | 0 | 0 |
| 0.25 | 0 | 0 |
| **0.5** | 0 | 0 |
| 1 | 0 | 0 |
| 2 | 0 | 0 |

### `INSET_MIN_COVERAGE` — CART067 (atual: 0.95)

| valor | mapas com a regra reprovada | mapas que mudam de nota |
|---|---|---|
| 0.8 | 0 | 0 |
| 0.85 | 0 | 0 |
| 0.9 | 0 | 0 |
| **0.95** | 0 | 0 |
| 0.98 | 0 | 0 |
| 1 | 0 | 0 |

### O limiar ΔE*ab < 15 lido nas cores

Nenhum mapa de teste reprova em CART070 em limiar algum — a paleta foi desenhada para passar. A sensibilidade do limiar está nas cores: ΔE*ab mínimo entre as três simulações de dicromacia (Machado et al. 2009, severidade 1,0) para cada par, e quantos pares cada limiar marcaria como confundíveis.

| conjunto | pares | 5 | 8 | 10 | 12 | **15** | 18 | 20 | 25 | 30 |
|---|---|---|---|---|---|---|---|---|---|---|
| preenchimentos atuais (POLYGON_FILLS) | 28 | 2 | 3 | 4 | 7 | 10 | 14 | 15 | 21 | 22 |
| paleta anterior (Okabe & Ito clareada 82 %) | 28 | 8 | 13 | 16 | 17 | 23 | 27 | 28 | 28 | 28 |
| Okabe & Ito (2008) pura | 28 | 0 | 0 | 0 | 0 | 0 | 5 | 6 | 9 | 9 |
| pares clássicos | 8 | 2 | 3 | 4 | 4 | 5 | 5 | 5 | 6 | 7 |

Pares de menor ΔE em *preenchimentos atuais (POLYGON_FILLS)*: cor 3 × cor 7 (#F9E7BF × #F6EF8E) ΔE 4.1 sob tritanopia (normal 28.2); cor 6 × cor 8 (#EBC9DC × #CCCCCC) ΔE 4.7 sob deuteranopia (normal 16); cor 2 × cor 6 (#D9EAF3 × #EBC9DC) ΔE 7.1 sob deuteranopia (normal 20.4); cor 3 × cor 6 (#F9E7BF × #EBC9DC) ΔE 9.5 sob tritanopia (normal 31.7).

Pares de menor ΔE em *paleta anterior (Okabe & Ito clareada 82 %)*: cor 3 × cor 4 (#D1EEE6 × #F6E7EF) ΔE 2.3 sob deuteranopia (normal 17.7); cor 1 × cor 3 (#D1E6F1 × #D1EEE6) ΔE 2.9 sob tritanopia (normal 10.6); cor 4 × cor 5 (#F6E7EF × #FAEED1) ΔE 3.6 sob tritanopia (normal 19); cor 4 × cor 6 (#F6E7EF × #E1F2FB) ΔE 3.6 sob protanopia (normal 11.2).

Pares de menor ΔE em *Okabe & Ito (2008) pura*: cor 3 × cor 6 (#009E73 × #56B4E9) ΔE 16.1 sob tritanopia (normal 59.5); cor 1 × cor 3 (#0072B2 × #009E73) ΔE 17 sob tritanopia (normal 70.1); cor 5 × cor 7 (#E69F00 × #F0E442) ΔE 17 sob deuteranopia (normal 35.1); cor 4 × cor 5 (#CC79A7 × #E69F00) ΔE 17.2 sob tritanopia (normal 88.6).

Pares de menor ΔE em *pares clássicos*: amarelo × verde-limão (#FFFF00 × #BFFF00) ΔE 3.9 sob protanopia (normal 26.2); vermelho-escuro × verde-escuro (#8B0000 × #006400) ΔE 4.3 sob deuteranopia (normal 94.7); laranja × lima (#FF6600 × #66CC00) ΔE 6.6 sob deuteranopia (normal 112.6); azul-claro × rosa (#ADD8E6 × #FFC0CB) ΔE 9.6 sob protanopia (normal 38).

## Penalidades por severidade

### `error`

| penalidade | mapas que mudam de nota |
|---|---|
| 10 | 0 |
| 12 | 0 |
| **15** | 0 |
| 18 | 0 |
| 20 | 0 |
| 25 | 0 |

### `warning`

| penalidade | mapas que mudam de nota |
|---|---|
| 2 | 13 |
| 3 | 13 |
| 4 | 13 |
| **5** | 0 |
| 6 | 0 |
| 8 | 0 |
| 10 | 41 |

### `advice`

| penalidade | mapas que mudam de nota |
|---|---|
| 0.5 | 0 |
| 1 | 0 |
| **1.5** | 0 |
| 2 | 0 |
| 3 | 0 |

## Cortes de nota

Mapas sem regra de erro reprovada que receberiam A para cada corte: ≥85: 106, ≥88: 106, ≥90: 106, ≥92: 93, ≥94: 93, ≥96: 52, ≥98: 52.

Mapas sem erro que receberiam pelo menos B para cada corte: ≥70: 106, ≥75: 106, ≥80: 106, ≥85: 106.

Pontuações observadas: 80, 85, 90, 95, 100.

## Compositor

### Ganho mínimo para trocar orientação ou arranjo (`LAYOUT_SWITCH_GAIN`, atual 1,12)

256 combinações de conjunto de dados × template × página × orientação × inserto, com as extensões reais dos dados no CRS escolhido pelo compositor. Trocas que cada limiar autorizaria:

| limiar | trocas de arranjo | trocas de orientação |
|---|---|---|
| 1 | 96 | 128 |
| 1.05 | 96 | 94 |
| 1.08 | 96 | 82 |
| 1.1 | 96 | 70 |
| **1.12** | 96 | 68 |
| 1.15 | 94 | 12 |
| 1.2 | 46 | 0 |
| 1.25 | 34 | 0 |
| 1.3 | 14 | 0 |

Razões de ganho observadas entre 1,05 e 1,30 (onde um limiar diferente mudaria a decisão): 1.0555, 1.0571, 1.0594, 1.0624, 1.0715, 1.0823, 1.0828, 1.0873, 1.0933, 1.0934, 1.1163, 1.1289, 1.1292, 1.1302, 1.1306, 1.1311, 1.1313, 1.1315, 1.1323, 1.1324, 1.1331, 1.1338, 1.1342, 1.1353, 1.1388, 1.1426, 1.1445, 1.1483, 1.1507, 1.1524, 1.1536, 1.154, 1.1563, 1.1606, 1.1622, 1.1629, 1.1651, 1.1658, 1.1678, 1.1686, 1.1711, 1.1722, 1.1725, 1.1733, 1.1741, 1.1775, 1.1785, 1.1792, 1.1801, 1.1805, 1.1808, 1.1812, 1.1846, 1.1869, 1.1875, 1.1896, 1.1899, 1.1984, 1.2072, 1.2149, 1.231, 1.2358, 1.237, 1.2427, 1.2641, 1.2701, 1.2715, 1.2722, 1.2742, 1.2832, 1.2901, 1.2942, 1.295, 1.2992.

### Margem efetiva máxima (`MAX_EFFECTIVE_MARGIN_PERCENT`, atual 25 %) — 137 mapas

| tolerância (%) | séries abandonadas | escalas diferentes da atual |
|---|---|---|
| 10 | 74 | 70 |
| 15 | 35 | 31 |
| 20 | 11 | 7 |
| **25** | 4 | 0 |
| 30 | 4 | 0 |
| 40 | 1 | 3 |
| 50 | 0 | 4 |

### Expoente da escala das fontes (`FONT_SCALE_EXPONENT`, atual 0,62)

Corpo da legenda (7 pt em A4 paisagem) e do título (16 pt) por página:

| expoente | A5 | A4 | A3 | A2 | A0 | legenda < 6 pt em A5 |
|---|---|---|---|---|---|---|
| 0.4 | 6.1 / 13.9 | 7 / 16 | 8 / 18.4 | 9.2 / 21.1 | 12.2 / 27.9 | não |
| 0.5 | 6 / 13.4 | 7 / 16 | 8.3 / 19 | 9.9 / 22.6 | 14 / 32 | não |
| **0.62** | 6 / 12.9 | 7 / 16 | 8.7 / 19.8 | 10.8 / 24.6 | 16.5 / 37.8 | não |
| 0.7 | 6 / 12.5 | 7 / 16 | 8.9 / 20.4 | 11.4 / 26 | 18.2 / 41.6 | não |
| 0.8 | 6 / 12.1 | 7 / 16 | 9.2 / 21.1 | 12.2 / 27.9 | 18.2 / 41.6 | não |
| 1 | 6 / 11.5 | 7 / 16 | 9.9 / 22.6 | 14 / 32 | 18.2 / 41.6 | não |

### Custo por célula vazia na grade de painéis (`EMPTY_CELL_PENALTY`, atual 0,35)

| custo | 3 painéis / A4 paisagem | 3 painéis / A4 retrato | 3 painéis / A3 paisagem | 3 painéis / A3 retrato | 4 painéis / A4 paisagem | 4 painéis / A4 retrato | 4 painéis / A3 paisagem | 4 painéis / A3 retrato | 5 painéis / A4 paisagem | 5 painéis / A4 retrato | 5 painéis / A3 paisagem | 5 painéis / A3 retrato | 6 painéis / A4 paisagem | 6 painéis / A4 retrato | 6 painéis / A3 paisagem | 6 painéis / A3 retrato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 3x1 | 2x2 | 2x2 | 2x2 | 3x2 | 2x2 | 3x2 | 2x2 | 4x2 | 2x3 | 3x2 | 2x3 | 4x2 | 2x3 | 3x2 | 2x3 |
| 0.1 | 3x1 | 2x2 | 2x2 | 2x2 | 3x2 | 2x2 | 3x2 | 2x2 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 |
| 0.2 | 3x1 | 2x2 | 3x1 | 2x2 | 3x2 | 2x2 | 3x2 | 2x2 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 |
| **0.35** | 3x1 | 2x2 | 3x1 | 2x2 | 2x2 | 2x2 | 2x2 | 2x2 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 |
| 0.5 | 3x1 | 2x2 | 3x1 | 2x2 | 2x2 | 2x2 | 2x2 | 2x2 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 |
| 0.75 | 3x1 | 1x3 | 3x1 | 1x3 | 2x2 | 2x2 | 2x2 | 2x2 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 |
| 1 | 3x1 | 1x3 | 3x1 | 1x3 | 2x2 | 2x2 | 2x2 | 2x2 | 5x1 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 | 3x2 | 2x3 |
