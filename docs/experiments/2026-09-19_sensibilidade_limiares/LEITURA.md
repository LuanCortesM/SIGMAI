# O que a análise de sensibilidade diz — e o que não diz

`LEIAME.md` e `sensibilidade.json` são gerados por `tools/threshold_sensitivity.py`
(fase 1 com PyQGIS: 138 mapas compostos com os dados de teste, observações do
inspetor em `observacoes.json`; fase 2 em Python puro: re-pontuação variando um
limiar de cada vez). Esta leitura é feita à mão e muda junto com os números.

## A pergunta

Os limiares do regulamento e do compositor são parâmetros declarados: ninguém
os mediu com leitores. A análise não os valida — só separa os que **decidem
alguma coisa** nos mapas de teste dos que **não decidem nada** numa vizinhança
larga do valor atual. Um limiar do segundo grupo pode ficar como está sem
prejuízo; um do primeiro precisa de justificativa externa (norma, periódico,
experimento perceptual), e é isso que a dissertação declara.

## Limiares que não decidem nada nos mapas de teste

Nenhum mapa muda de nota em toda a faixa varrida para: o máximo da barra de
escala (35 % a 60 % do quadro), a dominância do mapa (20 % a 45 % da área útil),
a tinta em volta de um item sobreposto (0,5 % a 10 %), a tolerância de estouro
da legenda (0 a 2 mm), a cobertura mínima do inserto (80 % a 100 %), a
penalidade de erro (10 a 25 pontos) e a de conselho (0,5 a 3 pontos). Esses
valores podem ser defendidos como "qualquer valor razoável dá o mesmo laudo".

## Limiares que decidem

- **Faixa vazia do quadro (`FRAME_BAND_EMPTY_MAX`, 5 %).** Em 5 %, 40 mapas
  reprovam em CART069; em 8 %, 80; em 2 %, 3. Os 40 são a faixa leste do
  Parque das Carnaúbas, que fica no Ceará enquanto a base só tem a malha do
  Piauí — um fato dos dados, não um defeito da composição (a bateria de
  liberação admite exatamente essa reprovação). O limiar está, portanto, na
  região em que a regra distingue "faixa realmente vazia" de "margem larga";
  acima de 8 % ela passaria a reprovar mapas de estado legítimos.
- **Fonte mínima (`MIN_PRINT_FONT_PT`, 6 pt).** Em 6 pt nada reprova; em 7 pt,
  72 mapas. Não é acaso: o compositor tem piso de 6 pt (equação das fontes),
  então regra e compositor são acoplados por construção. Levantar a regra exige
  levantar o piso. Os periódicos pedem 8 a 12 pt na largura final (PLOS ONE);
  isso é o que CART071 verifica quando a composição é uma figura de revista —
  na página inteira, 6 pt é o que cabe numa linha de crédito em A5.
- **Barra de escala mínima (`SCALEBAR_MIN_FRACTION`, 15 %).** Em 15 % nada
  reprova; em 20 %, 25 mapas. O alvo do compositor é 28 %, mas o arredondamento
  para um número "redondo" (1, 2, 2,5, 5 × 10ⁿ) deixa barras entre 15 % e 20 %
  em quadros estreitos. A regra é, na prática, "a barra não ficou menor que
  metade do alvo".
- **Penalidade de aviso (5 pontos).** Estável entre 5 e 8; em 4 ou menos, 13
  mapas mudam de nota (avisos ficam baratos demais para separar A de B); em
  10, 41 mudam.
- **Cortes de nota.** As pontuações observadas são só 80, 85, 90, 95 e 100 —
  nenhum mapa de teste reprova em regra de conselho. Logo "A ≥ 92, sem erro"
  equivale a "no máximo um aviso"; qualquer corte entre 90 e 95 dá o mesmo
  resultado, e um corte em 96 mandaria 41 mapas para B. "B ≥ 80" equivale a
  "até quatro avisos". A nota é, na prática, uma contagem de avisos com nomes.

## O limiar ΔE*ab < 15, lido nas cores

Os mapas de teste não reprovam em CART070 em limiar algum — a paleta foi
desenhada para passar. A sensibilidade está nas cores:

- Os pares em que o limiar foi calibrado (`tests/test_rules_from_experiment.py`)
  ficam a ΔE 12,1 (vermelho #FF0000 × verde #00A000, deuteranopia), 4,3
  (vermelho-escuro × verde-escuro) e 6,6 (laranja × lima); todos têm de ser
  acusados, e qualquer limiar entre 12,2 e 16,0 acusa os três sem acusar o
  menor par da paleta de Okabe & Ito (16,1, verde × azul-claro, tritanopia).
  A janela real do limiar é, portanto, **(12,1; 16,1)** — 15 está dentro dela
  e 10 ou 20 não.
- A sequência atual de preenchimentos tem 28 pares, dos quais 10 ficam abaixo
  de 15. Os quatro primeiros são mutuamente distinguíveis (ΔE ≥ 19,8); a partir
  da quinta cor o compositor não encontra preenchimento que não se confunda
  com algum já usado, e é a própria auditoria que acusa. **O SIGMAI tem, por
  construção, quatro preenchimentos de polígono seguros para daltônicos** —
  compatível com a recomendação de manter paletas categóricas pequenas —, e a
  paleta anterior (Okabe & Ito clareada 82 %) tinha 23 pares confundíveis em 28.

## Compositor

- **Ganho de troca (`LAYOUT_SWITCH_GAIN`, 1,12).** As razões de ganho observadas
  nos 256 casos formam dois grupos: um entre 1,055 e 1,094 (dez razões distintas, páginas
  em que trocar a orientação rende menos de 10 %) e outro de 1,116 para cima.
  O limiar de 1,12 cai na lacuna entre os grupos: entre 1,117 e 1,128 as
  decisões são as atuais; entre 1,094 e 1,116, dois casos-limite (razão
  1,1163) passam a trocar; a partir de 1,129, dezenas deixam de trocar. Acima
  de 1,15 a orientação quase nunca troca (12 casos; zero a 1,20), o que mostra
  que o ganho típico da troca em páginas da série A é de 13 % a 19 %: um
  limiar de 20 % desligaria a orientação automática na prática. Para o arranjo (coluna
  lateral × faixa inferior) a decisão é estável de 1,00 a 1,15.
- **Margem efetiva máxima (25 %).** Estável entre 25 % e 30 % (4 séries
  abandonadas, nenhuma escala diferente); em 20 %, 11 abandonos e 7 escalas
  mudam; em 40 %, 3 mapas ganham escala mais redonda e margem mais larga.
- **Expoente das fontes (0,62).** Decide pouco abaixo de A3: em A4 nada muda
  (é a página de referência), em A5 a legenda fica no piso de 6 pt para qualquer
  expoente ≥ 0,5 e o título varia 2,4 pt entre os extremos; em A0 o título vai
  de 27,9 pt (expoente 0,4) a 37,8 pt (0,62) e ao teto de 41,6 pt (≥ 0,8). O
  valor é editorial e o capítulo o declara como tal.
- **Custo por célula vazia (0,35).** Estável entre 0,35 e 0,5. Abaixo de 0,2,
  quatro painéis em A4 paisagem vão para 3 × 2 com duas células vazias; acima
  de 0,75, três painéis em página retrato vão para uma coluna 1 × 3.

## O que a análise não faz

Não diz se um leitor distingue duas cores a ΔE 15, se uma barra com 15 % do
quadro é legível ou se 12 % de escala compensam virar a folha. Isso exige
leitores, e é a validação perceptual listada como desdobramento. O que ela
garante é que os limiares não estão em regiões instáveis por acidente, e que os
que decidem têm a decisão nomeada.
