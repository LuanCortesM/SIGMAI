# Experimento: o mesmo mapa pelo SIGMAI e em PyQGIS puro (2026-09-06)

Pergunta: que diferença faz o SIGMAI, se uma IA com acesso ao computador pode escrever PyQGIS direto?

Dois agentes, o mesmo modelo, o mesmo pedido informal de uma pesquisadora ("mapa do Parque Estadual das Carnaúbas em A4, com os municípios em volta e um mapinha de localização no Piauí; IBGE 2024 e CEUC/SEMA-PI; autora Maria Silva; me diz se ficou bom pra publicar") e os mesmos dados (`PI_Municipios_2024.shp`, `PI_UF_2024.shp`, `PE Carnaubas.kml`).

- **Agente A — pelo SIGMAI, sem acesso ao computador.** Só podia chamar as ferramentas MCP (`tools/mcp_call.py`), num QGIS sem interface com a ponte ligada (`tools/remote_ai_lab.py`). Resultado: `mapa_sigmai.png`, 17–18 chamadas, 5,5 min, nota A (100/100). Rodadas registradas no CHANGELOG 1.0.2.
- **Agente B — PyQGIS puro, acesso total ao computador**, proibido de importar ou ler o `sigmai`. Resultado: `mapa_pyqgis_direto.png`, gerado por `mapa_pyqgis_direto.py` (353 linhas, 5 iterações), 15 execuções, 19 min, 12 armadilhas da API resolvidas por tentativa e erro — tudo no `relatorio_agente_direto.md`, escrito por ele.

O layout do agente B foi então auditado pelo `sigmai_audit_layout`. A primeira nota foi **D (50/100)** — falsa: o inspetor descartava itens sem `id` e não via título, fonte, legenda nem norte. Corrigido em 1.0.3 (ver CHANGELOG), o mesmo layout recebe **B (90/100)** com dois avisos legítimos; o laudo final está em `auditoria_sigmai_do_mapa_direto.json`, com os papéis inferidos de cada item.

Os dois agentes descobriram, pelos atributos do KML, que a UC fica no Ceará e não no Piauí, e corrigiram o pedido em vez de desenhar o que foi pedido errado.
