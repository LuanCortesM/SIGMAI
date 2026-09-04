
### Corrigido — mapas de base e serviços OGC eram esqueleto

`load_wms_layer`, `load_wfs_layer`, `load_xyz_tile_layer` e `load_arcgis_rest_layer` apareciam no catálogo de comandos e no `sigmai_capabilities`, validavam a URL e então recusavam com `NETWORK_LOAD_NOT_ENABLED` — *"requires an explicit future network-enabled workflow"*. A capacidade era anunciada e não existia: nenhum mapa de base, nenhum serviço público de dados, nenhum WMS de órgão ambiental podia ser carregado. É o mesmo defeito de fundo desta versão inteira — o que a ferramenta diz que faz precisa ser o que ela faz.

Os quatro passam a carregar de verdade, com quatro guardas:

- **A camada inválida não entra no projeto.** Antes o padrão da casa seria devolver sucesso e deixar uma entrada morta na árvore de camadas; agora a recusa nomeia as três causas usuais em ordem de probabilidade — servidor sem resposta, nome de camada inexistente no serviço, CRS não oferecido por ele — e aponta `inspect_ogc_service`.
- **Atribuição é obrigatória.** Um mapa de base é dado de terceiro sob licença, e quase toda licença de tiles exige o crédito na peça publicada. Fontes conhecidas (OpenStreetMap, OpenTopoMap) já trazem o crédito correto; qualquer outra exige `attribution`, com recusa explicando o porquê. O crédito então **entra sozinho na linha de fonte do mapa** — depender de o usuário lembrar de repeti-lo em `data_source` é como perder a procedência.
- **Saída de rede é consentida.** Carregar de servidor externo exige `confirm_network=true`, do mesmo jeito que o acesso ao repositório de plugins.
- **Cache de tiles no disco não é rede.** Um XYZ apontando para `file://` é o caso de campo sem sinal, funciona sem confirmação, e é como esta correção foi testada de ponta a ponta.

### Novo — o mapa de base que não desenha nada

Uma camada XYZ com `zmax` 7 num mapa a 1:32.000 desenha um quadro em branco, aparece na legenda e passava com nota A. É o defeito "está na legenda e não no mapa", só que por resolução em vez de por recorte. O compositor converte a escala impressa em nível de tile pelo esquema Web Mercator, na latitude do mapa, e avisa quando a base não alcança: *"só tem tiles até o zoom 7, e a escala 1:32.000 exige o zoom 14"*.

### Corrigido — a recusa por confirmação não dizia o que passar

`CONFIRMATION_REQUIRED` respondia *"pass a confirmation flag"* sem nunca nomear quais. São cinco nomes aceitos, e quem chama tinha de adivinhar — o mesmo defeito que o compositor já não comete. A mensagem passa a listar as flags válidas para aquela ação e a avisar que algumas exigem uma segunda, específica (`confirm_network`).

### Corrigido — o guarda de extração de ZIP comparava caminhos por prefixo

Com destino `/x/plugins`, o caminho `/x/plugins_maligno` também "começa com" `/x/plugins` e passava na verificação. Nenhum arquivo escapou de fato — quem continha a extração era o `extractall` do CPython, que neutraliza os `..` —, mas depender de um detalhe de implementação do interpretador para não gravar fora da pasta do usuário não é garantia. A verificação passa a ser por relação de caminho.

### O que foi verificado, e o que não pôde ser

Nova bancada `tools/exercise_plugins_and_basemaps.py`, 31 verificações pela ponte HTTP de verdade — mesmo caminho que um assistente usa. Cobre carregamento de tiles do disco, recusas de URL, atribuição, consentimento de rede, catálogo de plugins, instalação a partir de ZIP, os bloqueios de repositório de terceiro e de HTTP, e a auto-proteção do SIGMAI.

Fica registrado o que **não** foi possível verificar neste ambiente: a rede para `plugins.qgis.org` e para servidores de tiles está bloqueada no contêiner de desenvolvimento. O que se provou foi que a falha de rede vira recusa explicada e não quebra; o download real do repositório oficial e o consumo de tiles online continuam por confirmar numa máquina com saída de rede.

Também por desenho, e não por defeito: **toda ação de plugin exige aprovação humana no painel do SIGMAI**, mesmo no modo "liberar nesta sessão". A IA busca, inspeciona, simula e propõe; quem instala, habilita ou desinstala é a pessoa, um clique por vez.
