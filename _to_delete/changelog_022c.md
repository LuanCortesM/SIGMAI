
### Novo — a aba Ajuda

O painel tinha quatro abas voltadas a quem já entende de SIG: ligar a ponte, definir permissões, ver a auditoria, mexer em token e porta. Nenhuma dizia *o que fazer depois de conectar*. As chaves de texto da Ajuda existiam no código desde a 0.2.0 e a aba nunca havia sido construída.

A aba responde, sem jargão, às seis perguntas de quem nunca abriu um SIG: o que é isto; que frases dizer ao assistente (seis exemplos copiáveis, do "quais camadas estão abertas?" ao "dois mapas na mesma folha"); as duas coisas que o assistente vai perguntar de volta (fonte dos dados e autoria); o que significa a nota do mapa; por que o SIGMAI às vezes recusa; e onde os dados ficam. Em português e inglês, com troca de idioma.

### Corrigido — o pedido mais simples possível quebrava

Foram encontrados fazendo o pedido mínimo que uma IA faria sem saber nada do projeto: só o id da camada e um título.

- **Projeto sem sistema de coordenadas definido derrubava a composição.** Um CRS inválido não é geográfico nem projetado, então a reprojeção automática não disparava, os graus da camada eram tomados por metros, a escala saía 1:0 e a barra de escala estourava com um `ValueError` cru — a 300 linhas da causa. Agora o compositor herda o CRS da primeira camada válida e diz isso na resposta, ou recusa explicando como definir o CRS.
- **`choose_publication_scale` podia devolver zero.** Um denominador arredondado a zero significa escala abaixo de 1:1, ou seja, unidades erradas. O piso passa a ser 1, e o diagnóstico fica com quem tem contexto para dá-lo.
- **CART007 conferia presença de rodapé, não procedência.** O compositor sempre escreve o sistema de referência, a data e "Produzido com SIGMAI/QGIS"; com isso, um mapa sem nenhuma fonte e sem nenhuma autoria declaradas passava com nota A e chegava ao usuário parecendo citável. A regra agora exige que a linha de crédito diga de onde vieram os dados **e** quem assina o mapa, nomeando qual dos dois falta. É o mecanismo que faz o assistente perguntar ao usuário em vez de assinar sozinho.
