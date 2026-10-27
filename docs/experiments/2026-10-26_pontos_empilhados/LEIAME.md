# Pontos empilhados: o símbolo de ponto do compositor e a regra CART076

Experimento de 26/10/2026, feito para a 1.3.0. Os números das tabelas saem de `resultados/`; o que é julgamento visual está dito como tal.

## Por que

A base B5 do experimento E1 do artigo usa os 362.210 registros do GBIF dentro do Parque Nacional do Itatiaia. Na 1.2.0 ela saiu do compositor com nota C:
- os pontos de 2,2 mm, opacos e com contorno, deixavam só 29 % do parque à vista (`CART075`);
- o QGIS exportou o mapa sem erro e sem nenhuma mensagem.

Olhando os dados, o problema era maior:
- **Repetição:** os 362.210 registros estão em 11.742 coordenadas distintas, e uma delas tem 54.009 registros, quase todos de listas de aves do eBird.
- **O que o leitor via:** num mapa de pontos, esse local aparecia igual a um local com um registro só.
- **O que a auditoria via:** com 10.000 desses registros, o mapa tirava A, embora 98 % deles caíssem sobre outros.

## Dados

| Dado | Fonte | Licença |
|---|---|---|
| Registros de ocorrência | GBIF.org (26 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.kee8xx — todos os registros com coordenada e sem problema geoespacial dentro do polígono do parque | CC BY-NC 4.0 |
| Limite do parque | CNUC/MMA, polígonos de 2025_08, `cd_cnuc = '0000.00.0184'` | CC BY |

Os registros não são redistribuídos aqui. `preparar_dados.sh` refaz as duas camadas a partir dos downloads oficiais.

Dois tipos de conjunto de pontos, de 10 a 362.210 pontos:
- **`gbif`:** amostras aleatórias, com semente fixa, dos registros reais, aglomerados em trilhas, estradas e pontos de observação;
- **`uniforme`:** pontos sorteados, com semente fixa, dentro do polígono do parque.

## Como foi feito

`explorar_pontos.py` compõe cada mapa pelo próprio SIGMAI (`compose_map`) e guarda a auditoria e a medida de pontos ocultos de `sigmai/cartography/pointdensity.py`:

- **Fase 1:** o compositor sozinho (simbologia da paleta), em A5 deitado e numa coluna de 88 mm, para todos os tamanhos de conjunto. Assunto: os pontos e o parque.
- **Fase 2:** o símbolo fixado à mão, 4 tamanhos × 3 opacidades, mais mapa de calor (raios de 3 e 6 mm) e um protótipo de símbolo proporcional por local.
- **Fase 3:** os comandos da 1.3.0 (`count_points_by_site`, `apply_proportional_symbol_style`, `apply_heatmap_style`) e o compositor novo. Assunto: só os pontos, com o parque como contexto, como num mapa de registros de uma unidade de conservação. O símbolo por local entra de duas formas: um local por coordenada exata, e os locais agrupados na escala do mapa, que o script obtém simulando o mapa dos registros, como faria um assistente.

`calibrar.py` recalcula, para os mapas da fase 2, a fração de pontos oculta e a cobertura de tinta e as põe ao lado da fração do parque que a auditoria mediu como visível, renderizando o mapa. Depois mostra o símbolo que `choose_point_symbol` escolhe para cada conjunto da fase 1.

```
bash preparar_dados.sh <originais> <dados>
python explorar_pontos.py --fase 1 --dados <dados> --saida <pasta>   # e --fase 2, --fase 3
python calibrar.py --dados <dados> --saida <pasta>
```

Rodar com o Python do QGIS.

## A medida

- **Pontos ocultos:** os pontos, em mm do quadro, são agrupados em células do tamanho do símbolo. Numa célula com *k* pontos, só os primeiros mudam a imagem: um, para símbolo opaco; com opacidade *a*, tantos quantos levam a tinta a 95 % (`saturation_depth`: 5 a 50 %, 7 a 35 %, 11 a 25 %). Os demais são ocultos.
- **Cobertura:** o disco de cada célula, com a opacidade acumulada dos seus pontos, somado e dividido pela área ocupada pelos pontos, medida em células de 5 mm.

As duas medidas são geométricas e não leem a imagem. A comparação com a medida renderizada da auditoria está nos resultados.

## Resultados

As rodadas estão em `resultados/`, uma pasta por versão e QGIS:

| Pasta | Compositor | QGIS | Fases |
|---|---|---|---|
| `1.2.0_qgis4` | 1.2.0, antes da mudança | 4.0.2 | 1 |
| `1.3.0_qgis4` | 1.3.0 | 4.0.2 | 1, 2, 3 e calibração |
| `1.3.0_qgis3` | 1.3.0 | 3.40.7 | 1 |

Na rodada da 1.2.0, o script ainda gravava `simbolo_fixado` no lugar de `variante`, e a regra `CART076` não existia. Numa das rodadas de verificação da 1.3.0, o processo do QGIS da fase 2 terminou sem mensagem, e sem falha registrada pelo Windows, depois de exportar o mapa 51 (`gbif_362210_A5_pontos_1.4mm_0.25`); retomada, a fase refez esse mapa e terminou os 120 com as mesmas notas, e a rodada seguinte, inteira, não parou. As tabelas abaixo saem de `tabelar.py`:

```
python tabelar.py
```

### Fase 1, A5

| Conjunto | Pontos | 1.2.0: nota | 1.2.0: ocultos | 1.3.0: símbolo | 1.3.0: nota | 1.3.0: ocultos | Assunto à vista, 1.2.0 → 1.3.0 |
|---|---:|---|---:|---|---|---:|---|
| gbif | 10 | A | 40 % | 2,2 mm, 95 % | A | 40 % | 99 % → 99 % |
| gbif | 30 | A | 50 % | 2,2 mm, 95 % | A | 50 % | 98 % → 98 % |
| gbif | 100 | A | 73 % | 0,9 mm, 50 % | A | 36 % | 96 % → 100 % |
| gbif | 300 | A | 81 % | 0,9 mm, 50 % | A | 49 % | 93 % → 99 % |
| gbif | 1.000 | A | 90 % | 0,9 mm, 50 % | A (CART076) | 69 % | 87 % → 98 % |
| gbif | 3.000 | A | 95 % | 0,9 mm, 50 % | A (CART076) | 80 % | 82 % → 97 % |
| gbif | 10.000 | A | 98 % | 0,9 mm, 50 % | A (CART076) | 89 % | 72 % → 94 % |
| gbif | 30.000 | A | 99 % | 0,9 mm, 50 % | A (CART076) | 94 % | 62 % → 90 % |
| gbif | 100.000 | C (CART075) | 100 % | 0,9 mm, 50 % | A (CART076) | 97 % | 48 % → 85 % |
| gbif | 362.210 | C (CART075) | 100 % | 0,9 mm, 50 % | A (CART076) | 99 % | 29 % → 77 % |
| uniforme | 10 | A | 0 % | 2,2 mm, 95 % | A | 0 % | 99 % → 99 % |
| uniforme | 30 | A | 0 % | 2,2 mm, 95 % | A | 0 % | 96 % → 96 % |
| uniforme | 100 | A | 5 % | 2,2 mm, 95 % | A | 5 % | 88 % → 88 % |
| uniforme | 300 | A | 21 % | 1,6 mm, 80 % | A | 0 % | 68 % → 83 % |
| uniforme | 1.000 | C (CART075) | 50 % | 1,2 mm, 65 % | A | 1 % | 29 % → 80 % |
| uniforme | 3.000 | C (CART021, CART075) | 78 % | 0,9 mm, 50 % | A | 0 % | 3 % → 76 % |
| uniforme | 10.000 | C (CART021, CART075) | 93 % | 0,6 mm, 35 % | A | 0 % | 0 % → 74 % |
| uniforme | 30.000 | C (CART021, CART075) | 98 % | 0,45 mm, 25 % | A | 0 % | 0 % → 69 % |
| uniforme | 100.000 | C (CART021, CART075) | 99 % | 0,45 mm, 25 % | C (CART075) | 1 % | 0 % → 30 % |
| uniforme | 362.210 | C (CART021, CART075) | 100 % | 0,45 mm, 25 % | C (CART021, CART075, CART076) | 53 % | 0 % → 3 % |

### Fase 1, col88

| Conjunto | Pontos | 1.2.0: nota | 1.2.0: ocultos | 1.3.0: símbolo | 1.3.0: nota | 1.3.0: ocultos | Assunto à vista, 1.2.0 → 1.3.0 |
|---|---:|---|---:|---|---|---:|---|
| gbif | 10 | A | 30 % | 2,2 mm, 95 % | A | 30 % | 99 % → 99 % |
| gbif | 30 | A | 53 % | 2,2 mm, 95 % | A | 53 % | 97 % → 97 % |
| gbif | 100 | A | 75 % | 0,9 mm, 50 % | A | 40 % | 94 % → 99 % |
| gbif | 300 | A | 85 % | 0,9 mm, 50 % | A | 50 % | 89 % → 98 % |
| gbif | 1.000 | A | 92 % | 0,9 mm, 50 % | A (CART076) | 70 % | 81 % → 97 % |
| gbif | 3.000 | A | 96 % | 0,9 mm, 50 % | A (CART076) | 82 % | 74 % → 95 % |
| gbif | 10.000 | A | 98 % | 0,9 mm, 50 % | A (CART076) | 90 % | 62 % → 91 % |
| gbif | 30.000 | A | 99 % | 0,9 mm, 50 % | A (CART076) | 95 % | 51 % → 86 % |
| gbif | 100.000 | C (CART075) | 100 % | 0,9 mm, 50 % | A (CART076) | 98 % | 34 % → 79 % |
| gbif | 362.210 | C (CART075) | 100 % | 0,9 mm, 50 % | A (CART076) | 99 % | 16 % → 68 % |
| uniforme | 10 | A | 10 % | 2,2 mm, 95 % | A | 10 % | 98 % → 98 % |
| uniforme | 30 | A | 10 % | 2,2 mm, 95 % | A | 10 % | 93 % → 93 % |
| uniforme | 100 | A | 14 % | 2,2 mm, 95 % | A | 14 % | 79 % → 79 % |
| uniforme | 300 | A | 33 % | 1,6 mm, 80 % | A | 2 % | 50 % → 71 % |
| uniforme | 1.000 | C (CART075) | 64 % | 0,9 mm, 50 % | A | 0 % | 12 % → 84 % |
| uniforme | 3.000 | C (CART021, CART075) | 86 % | 0,6 mm, 35 % | A | 0 % | 0 % → 85 % |
| uniforme | 10.000 | C (CART021, CART075) | 96 % | 0,45 mm, 25 % | A | 0 % | 0 % → 82 % |
| uniforme | 30.000 | C (CART021, CART075) | 99 % | 0,45 mm, 25 % | A | 0 % | 0 % → 55 % |
| uniforme | 100.000 | C (CART021, CART075) | 100 % | 0,45 mm, 25 % | C (CART075) | 14 % | 0 % → 15 % |
| uniforme | 362.210 | C (CART021, CART075) | 100 % | 0,45 mm, 25 % | C (CART021, CART075, CART076) | 73 % | 0 % → 2 % |

QGIS 3.40 × 4.0, 1.3.0: 39 de 40 mapas com a mesma nota, as mesmas reprovações e o mesmo símbolo.
- uniforme 1.000 col88: QGIS 4 0,9 mm, 50 %, nota A, quadro 70,7 mm de altura; QGIS 3 1,2 mm, 65 %, nota A, quadro 71 mm de altura.

### Fase 2, A5: símbolo fixado à mão (nota; ocultos; assunto à vista)

| Variante | gbif 300 | gbif 3.000 | gbif 30.000 | gbif 362.210 | uniforme 300 | uniforme 3.000 | uniforme 30.000 | uniforme 362.210 |
|---|---|---|---|---|---|---|---|---|
| 2,2 mm, 95 % | A (CART076); 81 %; 94 % | A (CART076); 95 %; 84 % | A (CART076); 99 %; 66 % | C (CART075, CART076); 100 %; 33 % | A; 21 %; 73 % | C (CART021, CART075, CART076); 78 %; 5 % | C (CART021, CART075, CART076); 98 %; 0 % | C (CART021, CART075, CART076); 100 %; 0 % |
| 2,2 mm, 50 % | A (CART076); 54 %; 95 % | A (CART076); 86 %; 87 % | A (CART076); 97 %; 72 % | C (CART075, CART076); 99 %; 43 % | A; 0 %; 84 % | C (CART075); 15 %; 19 % | C (CART021, CART075, CART076); 88 %; 0 % | C (CART021, CART075, CART076); 99 %; 0 % |
| 2,2 mm, 25 % | A; 39 %; 97 % | A (CART076); 78 %; 91 % | A (CART076); 94 %; 78 % | A (CART076); 99 %; 52 % | A; 0 %; 92 % | C (CART075); 0 %; 43 % | C (CART021, CART075, CART076); 74 %; 1 % | C (CART021, CART075, CART076); 98 %; 1 % |
| 1,4 mm, 95 % | A (CART076); 77 %; 97 % | A (CART076); 93 %; 91 % | A (CART076); 99 %; 79 % | A (CART076); 100 %; 53 % | A; 10 %; 88 % | C (CART075, CART076); 55 %; 27 % | C (CART021, CART075, CART076); 94 %; 0 % | C (CART021, CART075, CART076); 100 %; 0 % |
| 1,4 mm, 50 % | A; 49 %; 98 % | A (CART076); 83 %; 93 % | A (CART076); 95 %; 83 % | A (CART076); 99 %; 61 % | A; 0 %; 93 % | C (CART075); 1 %; 50 % | C (CART021, CART075, CART076); 72 %; 0 % | C (CART021, CART075, CART076); 98 %; 0 % |
| 1,4 mm, 25 % | A; 32 %; 99 % | A (CART076); 75 %; 95 % | A (CART076); 93 %; 87 % | A (CART076); 98 %; 69 % | A; 0 %; 97 % | A; 0 %; 70 % | C (CART021, CART075); 40 %; 4 % | C (CART021, CART075, CART076); 95 %; 1 % |
| 0,9 mm, 95 % | A (CART076); 74 %; 99 % | A (CART076); 92 %; 95 % | A (CART076); 98 %; 88 % | A (CART076); 100 %; 71 % | A; 4 %; 95 % | A; 30 %; 60 % | C (CART021, CART075, CART076); 87 %; 2 % | C (CART021, CART075, CART076); 99 %; 0 % |
| 0,9 mm, 50 % | A; 49 %; 99 % | A (CART076); 80 %; 97 % | A (CART076); 94 %; 90 % | A (CART076); 99 %; 77 % | A; 0 %; 97 % | A; 0 %; 76 % | C (CART021, CART075); 37 %; 8 % | C (CART021, CART075, CART076); 94 %; 0 % |
| 0,9 mm, 25 % | A; 32 %; 99 % | A (CART076); 73 %; 98 % | A (CART076); 90 %; 93 % | A (CART076); 98 %; 82 % | A; 0 %; 99 % | A; 0 %; 87 % | C (CART075); 3 %; 27 % | C (CART021, CART075, CART076); 88 %; 1 % |
| 0,5 mm, 95 % | A (CART076); 71 %; 99 % | A (CART076); 89 %; 98 % | A (CART076); 97 %; 94 % | A (CART076); 99 %; 84 % | A; 0 %; 98 % | A; 11 %; 84 % | C (CART075, CART076); 62 %; 19 % | C (CART021, CART075, CART076); 96 %; 1 % |
| 0,5 mm, 50 % | A; 45 %; 100 % | A (CART076); 77 %; 98 % | A (CART076); 92 %; 95 % | A (CART076); 98 %; 87 % | A; 0 %; 99 % | A; 0 %; 91 % | C (CART075); 2 %; 40 % | C (CART021, CART075, CART076); 82 %; 1 % |
| 0,5 mm, 25 % | A; 30 %; 100 % | A (CART076); 70 %; 99 % | A (CART076); 87 %; 96 % | A (CART076); 97 %; 90 % | A; 0 %; 100 % | A; 0 %; 96 % | A; 0 %; 63 % | C (CART021, CART075, CART076); 62 %; 3 % |
| calor, raio 3 mm | A; —; 96 % | A (CART080); —; 96 % | A (CART080); —; 96 % | A (CART080); —; 96 % | A; —; 96 % | A; —; 95 % | A; —; 95 % | A; —; 95 % |
| calor, raio 6 mm | A; —; 97 % | A; —; 97 % | A (CART080); —; 97 % | A (CART080); —; 97 % | A; —; 95 % | A; —; 96 % | A; —; 96 % | A; —; 96 % |
| um símbolo por local | A (CART072); —; 93 % | A (CART072); —; 91 % | A (CART072); —; 85 % | A (CART072); —; 72 % | A; —; 95 % | A; —; 63 % | C (CART021, CART075); —; 2 % | C (CART021, CART075); —; 0 % |

### Fase 3, A5: comandos da 1.3.0, assunto só os pontos (nota)

| Forma | gbif 300 | gbif 3.000 | gbif 30.000 | gbif 362.210 | uniforme 300 | uniforme 3.000 | uniforme 30.000 | uniforme 362.210 |
|---|---|---|---|---|---|---|---|---|
| compositor (símbolo adaptado) | A | A (CART076) | A (CART076) | A (CART076) | A | A | A | B (CART021, CART076) |
| count_points_by_site + proporcional | A | A | A (CART076) | A (CART076) | A | A | B (CART021, CART076) | B (CART021, CART076) |
| idem, locais agrupados na escala do mapa | A | A | A | A | A | A (CART021) | A (CART021) | A (CART021) |
| apply_heatmap_style, raio 3 mm | A | A | A (CART080) | A (CART080) | A | A | A | A |

| Conjunto | Pontos | Locais (coordenada exata) | Locais (na escala) | Escala | CART076, coordenada exata |
|---|---:|---:|---:|---|---|
| gbif | 300 | 98 | 69 | 1:250.000 | pass |
| gbif | 3.000 | 486 | 198 | 1:250.000 | pass |
| gbif | 30.000 | 2.319 | 436 | 1:250.000 | fail |
| gbif | 362.210 | 11.224 | 863 | 1:300.000 | fail |
| uniforme | 300 | 300 | 276 | 1:250.000 | pass |
| uniforme | 3.000 | 3.000 | 1.539 | 1:250.000 | pass |
| uniforme | 30.000 | 29.999 | 3.256 | 1:250.000 | fail |
| uniforme | 362.210 | 361.938 | 4.124 | 1:250.000 | fail |

### Calibração: cobertura geométrica × parque à vista na auditoria renderizada

- 57 mapas com cobertura ≤ 0,25 (de 0,01 a 0,25): parque à vista de 69 % a 100 %; CART075 reprovada em 0.
- 39 mapas com cobertura > 0,25 (de 0,27 a 0,68): parque à vista de 0 % a 84 %; CART075 reprovada em 30.

### Símbolo que choose_point_symbol escolhe

| Conjunto | Pontos | A5 | ocultos; cobertura | coluna de 88 mm | ocultos; cobertura |
|---|---:|---|---|---|---|
| gbif | 10 | 2,2 mm, 95 % | 40 %; 0,15 | 2,2 mm, 95 % | 40 %; 0,30 |
| gbif | 30 | 2,2 mm, 95 % | 50 %; 0,18 | 2,2 mm, 95 % | 50 %; 0,22 |
| gbif | 100 | 0,9 mm, 50 % (fora do alvo) | 36 %; 0,03 | 0,9 mm, 50 % (fora do alvo) | 36 %; 0,04 |
| gbif | 300 | 0,9 mm, 50 % (fora do alvo) | 49 %; 0,04 | 0,9 mm, 50 % (fora do alvo) | 49 %; 0,05 |
| gbif | 1.000 | 0,9 mm, 50 % (fora do alvo) | 69 %; 0,05 | 0,9 mm, 50 % (fora do alvo) | 70 %; 0,06 |
| gbif | 3.000 | 0,9 mm, 50 % (fora do alvo) | 80 %; 0,06 | 0,9 mm, 50 % (fora do alvo) | 82 %; 0,07 |
| gbif | 10.000 | 0,9 mm, 50 % (fora do alvo) | 89 %; 0,08 | 0,9 mm, 50 % (fora do alvo) | 90 %; 0,10 |
| gbif | 30.000 | 0,9 mm, 50 % (fora do alvo) | 94 %; 0,10 | 0,9 mm, 50 % (fora do alvo) | 95 %; 0,13 |
| gbif | 100.000 | 0,9 mm, 50 % (fora do alvo) | 97 %; 0,12 | 0,9 mm, 50 % (fora do alvo) | 98 %; 0,15 |
| gbif | 362.210 | 0,9 mm, 50 % (fora do alvo) | 99 %; 0,17 | 0,9 mm, 50 % (fora do alvo) | 99 %; 0,22 |
| uniforme | 10 | 2,2 mm, 95 % | 0 %; 0,16 | 2,2 mm, 95 % | 10 %; 0,13 |
| uniforme | 30 | 2,2 mm, 95 % | 0 %; 0,17 | 2,2 mm, 95 % | 10 %; 0,16 |
| uniforme | 100 | 2,2 mm, 95 % | 5 %; 0,20 | 2,2 mm, 95 % | 14 %; 0,22 |
| uniforme | 300 | 1,6 mm, 80 % | 0 %; 0,15 | 1,6 mm, 80 % | 2 %; 0,20 |
| uniforme | 1.000 | 1,2 mm, 65 % | 1 %; 0,17 | 0,9 mm, 50 % | 0 %; 0,13 |
| uniforme | 3.000 | 0,9 mm, 50 % | 0 %; 0,20 | 0,6 mm, 35 % | 0 %; 0,11 |
| uniforme | 10.000 | 0,6 mm, 35 % | 0 %; 0,20 | 0,45 mm, 25 % | 0 %; 0,14 |
| uniforme | 30.000 | 0,45 mm, 25 % | 0 %; 0,23 | 0,45 mm, 25 % (fora do alvo) | 0 %; 0,32 |
| uniforme | 100.000 | 0,45 mm, 25 % (fora do alvo) | 1 %; 0,48 | 0,45 mm, 25 % (fora do alvo) | 14 %; 0,52 |
| uniforme | 362.210 | 0,45 mm, 25 % (fora do alvo) | 53 %; 0,60 | 0,45 mm, 25 % (fora do alvo) | 73 %; 0,55 |

### O que as tabelas mostram

- **1.2.0, pontos uniformes:** o símbolo era sempre de 2,2 mm, quase opaco. A partir de 1.000 pontos a nota caía para C, e de 3.000 em diante o parque sumia (0 a 3 % à vista).
- **1.2.0, registros do GBIF:** nota A até 30.000 registros, embora de 100 registros em diante 73 a 99 % deles ficassem ocultos. O mapa errava sem que a auditoria acusasse.
- **1.3.0, pontos uniformes:** nota A até 30.000 pontos; o símbolo desce até 0,45 mm a 25 %. Com 100.000 pontos ou mais, nem o menor símbolo deixa o parque à vista (cobertura de 0,48 a 0,60): a nota C é a resposta certa, e a `CART075` indica mapa de calor ou símbolo por local.
- **1.3.0, registros do GBIF:** nota A em todos os tamanhos. A partir de 1.000 registros, a `CART076` avisa que a maior parte deles cai sobre outros: são as coordenadas repetidas, que nenhum tamanho de símbolo separa.
- **QGIS 3.40 × 4.0:** 39 dos 40 mapas da fase 1 saem iguais. No outro, o quadro do QGIS 3 é 0,3 mm mais alto, a cobertura do símbolo de 1,2 mm fica em 0,245, abaixo do alvo de 0,25, e o compositor para nele; no QGIS 4 passa do alvo e desce para 0,9 mm. Os dois têm nota A.
- **Fase 2:** nenhum símbolo fixo serve para todos os tamanhos. Nos registros do GBIF, de 3.000 registros em diante, 70 % ou mais ficam ocultos em qualquer tamanho e opacidade. O mapa de calor, com o parque também como assunto, deixa 95 a 97 % do assunto à vista.
- **Fase 3:** com um local por coordenada exata, o símbolo por local dos registros do GBIF parecia certo, mas não estava. A partir de 30.000 registros os círculos mínimos se amontoavam: com os 362.210, eram 11.224 locais a 1:300.000, onde 1 mm são 300 m, e 79 % dos círculos caíam sobre outros. No sul do parque, onde há mais registros, os contornos brancos formavam uma mancha clara, e o lugar mais cheio parecia o mais vazio (julgamento visual, sobre o PNG). A `CART076` não media círculos proporcionais e dava A; agora mede, e acusa. Com os locais agrupados na escala do mapa, os 11.224 viram 863, nenhum círculo fica escondido, e a nota é A sem aviso em todos os tamanhos. Com pontos uniformes, cada ponto é um local, e a forma não serve em nenhum dos dois casos: os círculos cobrem o parque, e a `CART021` acusa uma camada da legenda que não aparece no mapa. O mapa de calor tira A; com 30.000 registros ou mais, a `CART080` avisa que o local mais cheio apaga os demais.
- **Calibração:** em 57 mapas com cobertura até 0,25, o parque ficou de 69 a 100 % à vista, e a `CART075` não reprovou nenhum. Acima de 0,25, de 0 a 84 %, com 30 reprovações em 39 mapas.

## Decisões

1. **O compositor ajusta o símbolo da paleta ao quadro.** Os alvos são no máximo 25 % de pontos ocultos e cobertura de no máximo 0,25. O limite de cobertura vem da calibração: nenhum mapa até 0,25 reprovou a `CART075`, cujo limite é metade do assunto à vista.
2. **Os dois menores símbolos (0,6 e 0,45 mm) só entram quando os outros não alcançam a cobertura.** Na primeira calibração, 100 registros do GBIF ganhavam 0,45 mm a 25 %, que no PNG quase some (julgamento visual). Ali o que esconde pontos é a repetição de coordenadas, que um símbolo menor não resolve.
3. **Com menos de 50 pontos fica o símbolo padrão**, e a `CART076` não se aplica.
4. **A `CART076` é um aviso, não um erro.** Um mapa de pontos de registros do GBIF mostra onde há registros, e isso é legítimo; o aviso diz que ele não mostra quantos.
5. **O símbolo por local virou comando.** Na fase 3, com os locais agrupados na escala do mapa (decisão 7), foi a única forma que mostrou onde e quantos sem nenhum aviso, em todos os tamanhos de conjunto do GBIF.
6. **O mapa de calor é tratado como uma superfície.** Os polígonos que o cobririam viram contorno por cima. Na primeira rodada da 1.3.0 isso valia só para o contexto: o parque, declarado também como assunto, era desenhado preenchido sobre o mapa de calor, e os 16 mapas de calor da fase 2 saíram com nota C, com 23 a 42 % do assunto à vista. Com a correção, saem com nota A e 95 a 97 % à vista; o resto da rodada não mudou.
7. **Os locais são agrupados na escala do mapa.** `count_points_by_site` com `scale` junta os locais a menos de 1 mm no papel, o menor círculo de `apply_proportional_symbol_style`. Do local com mais registros para o com menos, cada um vira a sede de um grupo ou entra no da primeira sede próxima; a sede guarda a coordenada real, e as sedes ficam a pelo menos 1 mm umas das outras. `compose_map` com `dense_points: "sites"` faz isso numa chamada, com a escala do próprio mapa.
8. **A `CART076` mede também os círculos proporcionais**, com o menor círculo e a opacidade da camada, e o mesmo limite de metade oculta. Reprovada, diz a escala em que os locais devem ser agrupados. O contorno dos círculos passou de branco a um tom mais escuro da cor: onde ainda houver sobreposição, o lugar mais cheio fica mais escuro, e não mais claro.

## Limites

- Um parque, duas figuras (A5 e 88 mm) e dois tipos de conjunto. O GBIF de outras regiões pode ter outra repetição.
- Nenhum limiar foi medido com leitores. 95 %, 25 %, 50 % e 50 pontos são decisões de projeto, escolhidas com folga sobre a medida renderizada da auditoria.
- O julgamento de que um ponto de 0,5 mm a 25 % "some" é visual, de quem fez o experimento, sobre os PNGs a 110 dpi.
- A medida de células é uma estimativa: discos de células vizinhas que se tocam não contam como sobrepostos, e os que caem na mesma célula sem se tocar contam.
