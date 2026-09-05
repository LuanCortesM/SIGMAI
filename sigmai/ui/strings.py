"""Textos da interface, em português do Brasil e inglês."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "window_title": "SIGMAI — Interface Segura GIS-IA",
        "subtitle": "Interface Segura GIS-IA",
        "context": "Ponte local entre assistentes de IA e o QGIS",
        "language_button": "EN",
        "online": "Conectado",
        "offline": "Desligado",

        "tab_connection": "Conexão",
        "tab_access": "Acesso",
        "tab_activity": "Atividade",
        "tab_advanced": "Avançado",
        "tab_help": "Ajuda",

        "step1_title": "Ligue a ponte com o QGIS",
        "step1_hint": "A ponte escuta apenas em 127.0.0.1 e exige um token. Nada sai da sua máquina.",
        "step1_start": "Iniciar ponte",
        "step1_stop": "Parar ponte",
        "step1_running": "Ponte ativa em {host}:{port} · QGIS {qgis}",
        "step1_stopped": "A ponte está desligada. Clique em Iniciar ponte.",

        "step2_title": "Configure seu assistente de IA",
        "step2_hint": "Escolha o programa que você usa. O SIGMAI monta a configuração com os caminhos certos.",
        "step2_client": "Programa",
        "step2_where": "Onde colar",
        "step2_copy": "Copiar configuração",
        "step2_open_folder": "Abrir pasta de configuração",
        "step2_copied": "Configuração copiada. Cole no arquivo indicado e reinicie o programa.",

        "step3_title": "Confira se está funcionando",
        "step3_hint": "O teste percorre a ponte de ponta a ponta, como um assistente de IA faria.",
        "step3_run": "Testar conexão",
        "step3_running": "Testando…",
        "step3_never": "Ainda não testado.",

        "access_title": "O que a IA pode fazer neste QGIS",
        "access_hint": "Comandos de leitura e simulações funcionam sempre. Esta escolha vale para ações que alteram o projeto ou gravam arquivos.",
        "mode_read_only": "Somente leitura",
        "mode_read_only_hint": "A IA inspeciona e simula, mas nada é alterado nem gravado. Recomendado para começar.",
        "mode_ask": "Perguntar sempre",
        "mode_ask_hint": "Cada ação que altera algo abre uma confirmação mostrando exatamente o que será feito.",
        "mode_allow": "Liberar nesta sessão",
        "mode_allow_hint": "A IA executa sem perguntar, dentro das pastas e limites definidos abaixo.",

        "folders_title": "Pastas onde a IA pode gravar",
        "folders_hint": "Vazio significa qualquer pasta. Restringir é a proteção mais eficaz contra gravação em lugar errado.",
        "folders_add": "Adicionar pasta…",
        "folders_remove": "Remover",

        "limits_title": "Limites desta sessão",
        "limits_hint": "Um teto por sessão evita que um laço de repetição do assistente gere centenas de arquivos.",
        "limit_writes": "Alterações no projeto",
        "limit_exports": "Mapas e exportações",
        "limit_processing": "Execuções de Processing",
        "limits_reset": "Zerar contadores e aprovações",

        "activity_title": "O que a IA pediu",
        "activity_hint": "Registro das decisões de acesso desta sessão. Nenhum token aparece aqui.",
        "activity_refresh": "Atualizar",
        "activity_export": "Exportar relatório…",
        "activity_empty": "Nenhuma solicitação ainda.",
        "col_time": "Quando",
        "col_event": "Decisão",
        "col_action": "Comando",
        "col_detail": "Detalhe",

        "advanced_endpoint": "Ponte local",
        "advanced_host": "Host",
        "advanced_port": "Porta",
        "advanced_token": "Token",
        "advanced_show": "Mostrar",
        "advanced_hide": "Ocultar",
        "advanced_copy_token": "Copiar",
        "advanced_regenerate": "Gerar novo token",
        "advanced_session_file": "Arquivo de sessão",
        "advanced_open_logs": "Abrir pasta de diagnóstico",
        "advanced_autostart": "Iniciar a ponte junto com o QGIS",
        "advanced_write_session": "Gravar o arquivo de sessão para os clientes de IA encontrarem a ponte",
        "advanced_persist_token": "Manter o mesmo token entre sessões do QGIS",
        "advanced_persist_hint": "Sem isso, o token muda a cada abertura do QGIS e a configuração do cliente precisa ser refeita.",
        "advanced_token_warning": "Trate o token como senha. Quem o tiver pode comandar este QGIS pela ponte local.",

        "dev_title": "Modo Desenvolvedor",
        "dev_hint": "Libera execução de Python dentro do QGIS para desenvolver plugins. Desligado por padrão.",
        "dev_warning": "Este modo pode corromper o seu QGIS: ele executa código diretamente no interpretador da ferramenta.",
        "dev_off": "Desligado",
        "dev_on": "LIGADO",
        "dev_enable": "Ativar Modo DEV",
        "dev_disable": "Desativar Modo DEV",
        "dev_dialog_title": "Ativar o Modo DEV do SIGMAI",
        "dev_dialog_prompt": "Digite SIM para confirmar:",

        "help_title": "Como o SIGMAI funciona",
        "help_what_title": "O que é isto",
        "help_what": (
            "O SIGMAI abre uma porta entre o QGIS e um assistente de IA. Você conversa com o "
            "assistente em português; ele opera o QGIS por você e devolve o mapa pronto. Você não "
            "precisa saber onde ficam os menus do QGIS, nem o que é escala, projeção ou legenda — "
            "o SIGMAI cuida disso e conta o que fez."
        ),
        "help_try_title": "Frases para começar",
        "help_try": (
            "• “Quais camadas estão abertas neste projeto?”\n"
            "• “Faça um mapa da trilha em A4, para eu imprimir.”\n"
            "• “Mapa do parque mostrando os municípios em volta, com um mapinha de localização.”\n"
            "• “Coloque os nomes das unidades no mapa.”\n"
            "• “Dois mapas na mesma folha: o parque e o estado inteiro.”\n"
            "• “Esse mapa está bom para publicar? O que falta nele?”"
        ),
        "help_ask_title": "Duas coisas que o assistente vai perguntar",
        "help_ask": (
            "De onde vieram os dados e quem assina o mapa. Sem essas duas informações o mapa não "
            "pode ser citado num trabalho, e o SIGMAI recusa dar nota máxima. A autoria do mapa é "
            "sua (ou de quem o elaborou) — não é a autoria deste plugin."
        ),
        "help_quality_title": "A nota do mapa",
        "help_quality": (
            "Todo mapa gerado recebe uma nota de A a E, com a lista do que está errado e o que "
            "corrige cada item. A nota não é opinião: é um regulamento de regras explícitas, cada "
            "uma com o motivo de existir. Peça ao assistente “me explique a nota deste mapa”."
        ),
        "help_refuse_title": "Quando o SIGMAI recusa",
        "help_refuse": (
            "Recusar é proposital. Se o assistente pedir um formato de página que não existe, um "
            "campo de rótulo vazio ou uma pasta no lugar do arquivo, o SIGMAI para e diz o que "
            "aceita — em vez de entregar, calado, um mapa diferente do que foi pedido."
        ),
        "help_privacy_title": "Onde os seus dados ficam",
        "help_privacy": (
            "A ponte escuta apenas em 127.0.0.1, que é a sua própria máquina, e exige um token. "
            "Os seus arquivos não são enviados para lugar nenhum: o assistente manda comandos, o "
            "QGIS executa aqui e devolve o resultado."
        ),
        "help_docs": "Documentação e código: github.com/LuanCortesM/SIGMAI",
        "about_title": "Sobre o SIGMAI",
        "about_plugin": "Plugin author: MACIEL, L. S. C. · herpetomantiqueira@gmail.com",
        "about_license": "SIGMAI {version} · GNU GPL v3.0 ou posterior · github.com/LuanCortesM/SIGMAI",
        "about_map_authorship": "A autoria do plugin não é a autoria dos mapas: informe map_author e data_source em cada mapa gerado.",
        "consent_dialog_title": "O assistente de IA quer executar uma ação",
        "consent_allow": "Permitir uma vez",
        "consent_allow_category": "Permitir tudo desta categoria nesta sessão",
        "consent_deny": "Negar",
        "msg_started": "Ponte do SIGMAI iniciada em {host}:{port}.",
        "msg_stopped": "Ponte do SIGMAI parada.",
        "msg_start_failed": "Não foi possível iniciar a ponte do SIGMAI",
    },
    "en": {
        "window_title": "SIGMAI — Secure GIS-AI Interface",
        "subtitle": "Secure GIS-AI Interface",
        "context": "Local bridge between AI assistants and QGIS",
        "language_button": "PT-BR",
        "online": "Connected",
        "offline": "Stopped",

        "tab_connection": "Connection",
        "tab_access": "Access",
        "tab_activity": "Activity",
        "tab_advanced": "Advanced",
        "tab_help": "Help",

        "step1_title": "Start the bridge to QGIS",
        "step1_hint": "The bridge listens on 127.0.0.1 only and requires a token. Nothing leaves your machine.",
        "step1_start": "Start bridge",
        "step1_stop": "Stop bridge",
        "step1_running": "Bridge running on {host}:{port} · QGIS {qgis}",
        "step1_stopped": "The bridge is stopped. Click Start bridge.",

        "step2_title": "Configure your AI assistant",
        "step2_hint": "Pick the program you use. SIGMAI fills in the correct paths for you.",
        "step2_client": "Program",
        "step2_where": "Where to paste it",
        "step2_copy": "Copy configuration",
        "step2_open_folder": "Open configuration folder",
        "step2_copied": "Configuration copied. Paste it into the file above and restart the program.",

        "step3_title": "Check that it works",
        "step3_hint": "The check walks the whole bridge, the way an AI assistant would.",
        "step3_run": "Test connection",
        "step3_running": "Testing…",
        "step3_never": "Not tested yet.",

        "access_title": "What the AI may do in this QGIS project",
        "access_hint": "Read commands and dry runs always work. This choice governs actions that change the project or write files.",
        "mode_read_only": "Read only",
        "mode_read_only_hint": "The AI inspects and simulates; nothing is changed or written. Recommended when you are getting started.",
        "mode_ask": "Ask every time",
        "mode_ask_hint": "Every changing action opens a confirmation showing exactly what will happen.",
        "mode_allow": "Allow for this session",
        "mode_allow_hint": "The AI acts without asking, within the folders and limits set below.",

        "folders_title": "Folders the AI may write to",
        "folders_hint": "Empty means any folder. Restricting this is the most effective guard against writing to the wrong place.",
        "folders_add": "Add folder…",
        "folders_remove": "Remove",

        "limits_title": "Limits for this session",
        "limits_hint": "A per-session ceiling stops an assistant loop from producing hundreds of files.",
        "limit_writes": "Project changes",
        "limit_exports": "Maps and exports",
        "limit_processing": "Processing runs",
        "limits_reset": "Reset counters and approvals",

        "activity_title": "What the AI asked for",
        "activity_hint": "Access decisions recorded this session. No token ever appears here.",
        "activity_refresh": "Refresh",
        "activity_export": "Export report…",
        "activity_empty": "No requests yet.",
        "col_time": "When",
        "col_event": "Decision",
        "col_action": "Command",
        "col_detail": "Detail",

        "advanced_endpoint": "Local bridge",
        "advanced_host": "Host",
        "advanced_port": "Port",
        "advanced_token": "Token",
        "advanced_show": "Show",
        "advanced_hide": "Hide",
        "advanced_copy_token": "Copy",
        "advanced_regenerate": "Generate a new token",
        "advanced_session_file": "Session file",
        "advanced_open_logs": "Open diagnostics folder",
        "advanced_autostart": "Start the bridge together with QGIS",
        "advanced_write_session": "Write the session file so AI clients can find the bridge",
        "advanced_persist_token": "Keep the same token across QGIS sessions",
        "advanced_persist_hint": "Without this the token changes every time QGIS starts and the client configuration must be redone.",
        "advanced_token_warning": "Treat the token as a password. Anyone holding it can control this QGIS instance through the local bridge.",

        "dev_title": "Developer Mode",
        "dev_hint": "Enables Python execution inside QGIS for plugin development. Off by default.",
        "dev_warning": "This mode can corrupt your QGIS: it runs code directly in the application interpreter.",
        "dev_off": "Off",
        "dev_on": "ON",
        "dev_enable": "Enable DEV mode",
        "dev_disable": "Disable DEV mode",
        "dev_dialog_title": "Enable SIGMAI DEV mode",
        "dev_dialog_prompt": "Type YES to confirm:",

        "help_title": "How SIGMAI works",
        "help_what_title": "What this is",
        "help_what": (
            "SIGMAI opens a channel between QGIS and an AI assistant. You talk to the assistant in "
            "plain language; it drives QGIS for you and hands back the finished map. You do not "
            "need to know where the QGIS menus are, nor what scale, projection or legend mean — "
            "SIGMAI handles that and tells you what it did."
        ),
        "help_try_title": "Sentences to start with",
        "help_try": (
            "• “What layers are open in this project?”\n"
            "• “Make a map of the trail on A4, for printing.”\n"
            "• “Map of the park showing the surrounding municipalities, with a locator inset.”\n"
            "• “Put the names of the units on the map.”\n"
            "• “Two maps on one sheet: the park and the whole state.”\n"
            "• “Is this map good enough to publish? What is missing?”"
        ),
        "help_ask_title": "Two things the assistant will ask you",
        "help_ask": (
            "Where the data came from and who signs the map. Without those two, the map cannot be "
            "cited in a paper, and SIGMAI will not give it a top grade. Map authorship is yours "
            "(or whoever made it) — it is not the authorship of this plugin."
        ),
        "help_quality_title": "The map grade",
        "help_quality": (
            "Every map is graded A to E, with the list of what is wrong and what fixes each item. "
            "The grade is not an opinion: it is an explicit rulebook, each rule carrying the reason "
            "it exists. Ask the assistant to “explain this map's grade”."
        ),
        "help_refuse_title": "When SIGMAI refuses",
        "help_refuse": (
            "Refusing is deliberate. If the assistant asks for a page size that does not exist, an "
            "empty label field or a folder where a file belongs, SIGMAI stops and says what it "
            "accepts — instead of quietly handing over a different map from the one requested."
        ),
        "help_privacy_title": "Where your data stays",
        "help_privacy": (
            "The bridge listens on 127.0.0.1 only — your own machine — and requires a token. Your "
            "files are not uploaded anywhere: the assistant sends commands, QGIS runs them here and "
            "returns the result."
        ),
        "help_docs": "Documentation and code: github.com/LuanCortesM/SIGMAI",
        "about_title": "About SIGMAI",
        "about_plugin": "Plugin author: MACIEL, L. S. C. · herpetomantiqueira@gmail.com",
        "about_license": "SIGMAI {version} · GNU GPL v3.0 or later · github.com/LuanCortesM/SIGMAI",
        "about_map_authorship": "Plugin authorship is not map authorship: set map_author and data_source on every map you generate.",
        "consent_dialog_title": "The AI assistant wants to run an action",
        "consent_allow": "Allow once",
        "consent_allow_category": "Allow this whole category for this session",
        "consent_deny": "Deny",
        "msg_started": "SIGMAI bridge started on {host}:{port}.",
        "msg_stopped": "SIGMAI bridge stopped.",
        "msg_start_failed": "Could not start the SIGMAI bridge",
    },
}


def translate(language: str, key: str, **kwargs: object) -> str:
    table = STRINGS.get(language) or STRINGS["en"]
    text = table.get(key) or STRINGS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
