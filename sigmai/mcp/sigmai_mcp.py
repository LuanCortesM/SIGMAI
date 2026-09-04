#!/usr/bin/env python3
"""Servidor MCP do SIGMAI — JSON-RPC 2.0 sobre stdio, sem dependências.

O que existia antes em ``sigmai_mcp_server.py`` não era MCP: era um laço que
lia ``{"tool": ..., "arguments": ...}`` de stdin. Nenhum cliente MCP fala esse
formato, então o Claude Desktop, o Cursor e o Codex simplesmente não
conectavam — o servidor subia, ficava em silêncio e o cliente marcava a
conexão como falha.

Este arquivo implementa o protocolo de verdade:

* enquadramento JSON-Lines em stdio (a spec do MCP não usa ``Content-Length``);
* ``initialize`` / ``notifications/initialized`` / ``ping`` / ``tools/list`` /
  ``tools/call``, mais ``server/discover`` para a era sem handshake;
* negociação de versão tolerante — versão desconhecida devolve a nossa, nunca
  um erro, que é o que derruba clientes mais novos que o servidor;
* separação correta entre erro de protocolo (JSON-RPC ``error``) e erro de
  execução (``result.isError = true``), que é o que permite ao modelo se
  corrigir sozinho em vez de ver uma falha opaca;
* nada além de mensagens MCP em stdout; todo log vai para stderr.

Não há dependência externa: o servidor roda no Python que acompanha o
QGIS/OSGeo4W, que é justamente o interpretador que o usuário já tem.

Referências: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
             https://modelcontextprotocol.io/specification/2025-06-18/server/tools
"""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SERVER_NAME = "sigmai"
SERVER_TITLE = "SIGMAI — Interface Segura GIS-IA"

#: Versões da era com handshake. Todas são aceitas e devolvidas como pedidas.
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28")
FALLBACK_PROTOCOL_VERSION = "2025-06-18"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Descoberta de sessão (embutida)
# ---------------------------------------------------------------------------
# O servidor é lançado pelo cliente de IA como um processo independente, sem
# QGIS e sem o repositório por perto. Por isso a descoberta de sessão vive
# aqui dentro em vez de ser importada: o plugin instalado precisa ser
# autossuficiente para que a configuração seja um único caminho de arquivo.

APP_NAME = "SIGMAI"
SESSION_FILE = "current_bridge_session.json"


def _sessions_dirs() -> list[Path]:
    dirs: list[Path] = []
    if os.name == "nt":
        for variable in ("LOCALAPPDATA", "TEMP"):
            base = os.environ.get(variable)
            if base:
                dirs.append(Path(base) / APP_NAME / "sessions")
    elif sys.platform == "darwin":
        dirs.append(Path.home() / "Library" / "Application Support" / APP_NAME / "sessions")
    else:
        dirs.append(Path.home() / ".local" / "share" / "sigmai" / "sessions")
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
    dirs.append(Path(temp) / APP_NAME / "sessions")
    return dirs


def _session_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("SIGMAI_SESSION_FILE")
    if explicit:
        candidates.append(Path(explicit))
    for directory in _sessions_dirs():
        candidates.append(directory / SESSION_FILE)
        if directory.exists():
            try:
                candidates.extend(sorted(directory.glob("SG-*.json"), key=lambda item: item.stat().st_mtime, reverse=True))
            except OSError:
                pass
    return candidates


def resolve_connection(**overrides: Any) -> dict[str, Any]:
    """Host, porta e token da bridge ativa.

    Variáveis de ambiente têm precedência sobre o arquivo de sessão, para
    permitir apontar o servidor a uma instância específica do QGIS.
    """
    session: dict[str, Any] = {}
    wanted_code = (overrides.get("pairing_code") or os.environ.get("SIGMAI_PAIRING_CODE") or "").upper()
    for path in _session_candidates():
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data["_session_path"] = str(path)
        if wanted_code:
            if str(data.get("pairing_code", "")).upper() == wanted_code or path.stem.upper() == wanted_code:
                session = data
                break
            continue
        if data.get("active", data.get("running", True)):
            session = data
            break

    return {
        "host": overrides.get("host") or os.environ.get("SIGMAI_HOST") or session.get("host", "127.0.0.1"),
        "port": int(overrides.get("port") or os.environ.get("SIGMAI_PORT") or session.get("port", 8765)),
        "token": overrides.get("token") or os.environ.get("SIGMAI_TOKEN") or session.get("token", ""),
        "session": session,
        "session_path": session.get("_session_path", ""),
    }


# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------

class StdioTransport:
    """Enquadramento JSON-Lines com stdout protegido.

    Qualquer ``print`` acidental — do plugin, de uma biblioteca, de um warning
    do Python — corromperia o stream e derrubaria a conexão. Por isso o
    ``sys.stdout`` global é redirecionado para stderr assim que o transporte é
    criado, e o descritor real fica guardado aqui.
    """

    def __init__(self) -> None:
        self._out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="", write_through=True)
        sys.stdout = sys.stderr  # tudo que não for protocolo vai para o log
        self._in = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace", newline="")

    def read(self):
        for line in self._in:
            stripped = line.strip()
            if stripped:
                yield stripped

    def write(self, message: dict[str, Any]) -> None:
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if "\n" in data:  # defesa: uma mensagem com newline quebra o cliente
            data = data.replace("\n", "\\n")
        self._out.write(data + "\n")
        self._out.flush()


def log(message: str) -> None:
    """Log para stderr — canal oficial de log de um servidor MCP stdio."""
    sys.stderr.write(f"[sigmai-mcp] {message}\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Ponte com o QGIS
# ---------------------------------------------------------------------------

class BridgeError(RuntimeError):
    """Falha ao falar com a bridge do SIGMAI dentro do QGIS."""


def bridge_call(action: str, params: dict[str, Any] | None = None, dry_run: bool = False, timeout: float = 180.0) -> dict[str, Any]:
    connection = resolve_connection()
    token = connection.get("token") or ""
    if not token:
        raise BridgeError(
            "Nenhuma sessão do SIGMAI encontrada. No QGIS, abra o painel do SIGMAI e clique em "
            "Iniciar bridge. Se a bridge já estiver rodando, confirme que a opção de gravar o "
            "arquivo de sessão está ligada."
        )
    host = connection.get("host")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise BridgeError(f"A bridge do SIGMAI só aceita host local; a sessão aponta para {host}.")

    payload = {"schema_version": "0.3", "action": action, "params": params or {}, "dry_run": bool(dry_run)}
    request = urllib.request.Request(
        f"http://{host}:{connection['port']}/command",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise BridgeError(f"A bridge respondeu HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise BridgeError(
            f"Não foi possível falar com a bridge em {host}:{connection['port']} ({exc.reason}). "
            "Verifique se o QGIS está aberto e a bridge do SIGMAI iniciada."
        ) from exc


# ---------------------------------------------------------------------------
# Ferramentas
# ---------------------------------------------------------------------------

def _obj(properties: dict[str, Any], required: list[str] | None = None, additional: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": additional}
    if required:
        schema["required"] = required
    return schema


_S = {"type": "string"}
_B = {"type": "boolean"}
_N = {"type": "number"}
_SA = {"type": "array", "items": {"type": "string"}}

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITES = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}

#: Ordem fixa: a spec pede lista determinística para o cliente poder cachear.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "sigmai_status",
        "title": "Estado da conexão com o QGIS",
        "description": (
            "Estado da bridge do SIGMAI dentro do QGIS: versão do QGIS, versão do plugin, modo de acesso "
            "vigente (somente leitura, perguntar sempre ou liberado nesta sessão), limites de sessão já "
            "consumidos e se há projeto carregado. Chame isto primeiro, sempre: sem saber o modo de acesso "
            "você não sabe se pode executar ou apenas simular."
        ),
        "inputSchema": _obj({}),
        "annotations": {"title": "Estado da conexão", **READ_ONLY},
        "handler": lambda args: bridge_call("status"),
    },
    {
        "name": "sigmai_project_overview",
        "title": "Panorama do projeto",
        "description": (
            "Panorama completo do projeto QGIS aberto numa única chamada: caminho, CRS do projeto, e para "
            "cada camada o id, nome, tipo de geometria, CRS, contagem de feições, extensão e campos. "
            "Use antes de compor qualquer mapa ou análise — os ids de camada vêm daqui, e inventar um id "
            "é a causa mais comum de mapa vazio."
        ),
        "inputSchema": _obj({"include_fields": {**_B, "description": "Incluir a lista de campos de cada camada."}}),
        "annotations": {"title": "Panorama do projeto", **READ_ONLY},
        "handler": lambda args: bridge_call("get_project_overview", {"include_fields": bool(args.get("include_fields", True))}),
    },
    {
        "name": "sigmai_layer_details",
        "title": "Detalhes de uma camada",
        "description": (
            "Metadados detalhados de uma camada: campos e tipos, extensão, CRS, simbologia atual, "
            "validade das geometrias e uma amostra de feições. Use quando precisar decidir simbologia, "
            "expressões de rótulo ou classificação temática."
        ),
        "inputSchema": _obj({
            "layer_id": {**_S, "description": "Id da camada, obtido em sigmai_project_overview."},
            "sample_size": {**_N, "description": "Quantas feições amostrar (0 a 50)."},
        }, ["layer_id"]),
        "annotations": {"title": "Detalhes da camada", **READ_ONLY},
        "handler": lambda args: bridge_call("get_layer_info", {"layer_id": args.get("layer_id", ""), "sample_size": args.get("sample_size", 5)}),
    },
    {
        "name": "sigmai_cartographic_rulebook",
        "title": "Regras cartográficas do SIGMAI",
        "description": (
            "O regulamento cartográfico que o SIGMAI aplica a todo mapa gerado: as regras, a severidade de "
            "cada uma, o motivo de existirem, a referência que as sustenta e o comando que as satisfaz. "
            "Leia antes de compor um mapa pela primeira vez numa conversa — é o que evita produzir um mapa "
            "que será reprovado na auditoria e ter de refazê-lo."
        ),
        "inputSchema": _obj({"category": {**_S, "description": "Filtrar por categoria (elementos, escala, grade, geometria, tipografia, projecao, dados, procedencia, orientacao)."}}),
        "annotations": {"title": "Regras cartográficas", **READ_ONLY},
        "handler": lambda args: bridge_call("get_cartographic_rulebook", {"category": args.get("category", "")}),
    },
    {
        "name": "sigmai_plan_map",
        "title": "Planejar um mapa (simulação)",
        "description": (
            "Simula a composição de um mapa sem tocar no projeto nem gravar arquivo: devolve a página "
            "escolhida, a posição calculada de cada elemento, a extensão ajustada, a escala arredondada "
            "para a série cartográfica e as camadas que entrariam. Funciona em qualquer modo de acesso, "
            "inclusive somente leitura. Use para mostrar ao usuário o que será feito antes de pedir "
            "autorização para executar."
        ),
        "inputSchema": _obj({
            "layer_ids": {**_SA, "description": "Camadas a exibir, na ordem de desenho (a última fica por cima)."},
            "subject_layer_id": {**_S, "description": "Camada que define o recorte. As demais entram como contexto. Use para 'mapa DO parque MOSTRANDO os municípios'."},
            "title": _S,
            "subtitle": _S,
            "page": {**_S, "description": "Ex.: 'A4 landscape', 'A3 retrato', 'A5 portrait'. Padrão A4 paisagem."},
            "template": {**_S, "description": "cientifico, publicacao, relatorio_ambiental ou minimalista."},
            "margin_percent": _N,
            "map_crs": {**_S, "description": "CRS do mapa, ex.: EPSG:31983. Se omitido e o projeto for geográfico, o SIGMAI escolhe UTM ou Policônica conforme a extensão."},
            "include_inset": {**_B, "description": "Inserto de localização com o recorte principal marcado."},
            "label_field": {**_S, "description": "Campo cujos valores viram rótulos das feições."},
        }, ["layer_ids"]),
        "annotations": {"title": "Planejar mapa", **READ_ONLY},
        "handler": lambda args: bridge_call("compose_map", dict(args), dry_run=True),
    },
    {
        "name": "sigmai_compose_map",
        "title": "Compor e exportar um mapa",
        "description": (
            "Compõe um mapa completo e o exporta em PDF, PNG ou SVG. O SIGMAI escolhe a extensão ajustada "
            "ao quadro, arredonda a escala para a série cartográfica, dimensiona a barra de escala, "
            "calcula o intervalo da grade de coordenadas, monta a legenda com TODAS as camadas visíveis, "
            "insere rosa dos ventos ligada ao norte da grade e declara CRS, fonte, autoria e data. "
            "Ao final roda a auditoria cartográfica e devolve o laudo. "
            "ESTA AÇÃO GRAVA ARQUIVO: exige que o usuário tenha liberado escrita no painel do SIGMAI. "
            "Se vier recusada, use sigmai_plan_map para mostrar o plano e peça a liberação."
        ),
        "inputSchema": _obj({
            "layer_ids": {**_SA, "description": "Camadas a exibir, na ordem de desenho."},
            "title": {**_S, "description": "Título do mapa."},
            "subtitle": _S,
            "map_language": {**_S, "description": (
                "Língua dos textos que o PRÓPRIO compositor escreve na moldura — 'Fonte:'/"
                "'Elaboração:', título padrão quando 'title' é omitido, 'Legenda', 'Painel A/B' e o "
                "crédito da ferramenta. NÃO afeta title/subtitle/legend_title/data_source/map_author, "
                "que já saem na língua em que você os escreveu. Padrão 'pt-BR'. Aceita 'pt-BR', 'en', "
                "'es', 'fr', 'de', 'it', 'ja', 'zh-Hans', 'zh-Hant', 'ko', 'ru', 'ar', 'he', 'el', 'th' "
                "(e variantes tolerantes como 'pt', 'zh-CN', 'PT-br'). Uma língua desconhecida cai em "
                "pt-BR sem recusar. Use a mesma língua em que o usuário está conversando — não pergunte, "
                "escolha pela língua da conversa; um mapa não deve sair com metade do texto em "
                "português quando o pedido foi feito noutra língua."
            )},
            "output_path": {**_S, "description": (
                "Caminho absoluto do ARQUIVO de saída, com nome e extensão — não a pasta. "
                "A extensão define o formato quando 'format' não é informado."
            )},
            "format": {"type": "string", "enum": ["pdf", "png", "svg"]},
            "page": {**_S, "description": (
                "Formato e orientação, ex.: 'A4 landscape', 'A3 retrato', 'A2 portrait'. "
                "Formatos: A0-A5, B4, B5, LETTER, LEGAL, TABLOID. Um formato desconhecido é recusado."
            )},
            "template": {"type": "string", "enum": ["cientifico", "publicacao", "relatorio_ambiental", "minimalista"]},
            "map_crs": _S,
            "margin_percent": _N,
            "scale": {**_N, "description": (
                "Denominador da escala impressa, quando ela é imposta (norma da dissertação, "
                "folha de uma série). Ex.: 25000 para 1:25.000. Omita para o SIGMAI escolher na "
                "série cartográfica. Uma escala que cortaria os dados é recusada, dizendo qual é "
                "a maior que ainda os contém."
            )},
            "dpi": {**_N, "description": "Entre 50 e 1200. Padrão 300."},
            "data_source": {**_S, "description": "Fonte dos dados, obrigatória para o mapa ser citável."},
            "map_author": {**_S, "description": "Autoria do mapa. NÃO é o autor do plugin."},
            "organization": _S,
            "legend_title": _S,
            "grid_style": {"type": "string", "enum": ["solid", "cross", "markers", "frame"]},
            "apply_style": {"type": "string", "enum": ["missing", "all", "none"], "description": "'missing' (padrão) só estiliza camadas sem simbologia temática definida."},
            "subject_layer_id": {**_S, "description": (
                "Camada que define o recorte; as demais entram como contexto. É assim que se pede "
                "'mapa DO parque MOSTRANDO os municípios em volta' — sem isso o recorte vira a união "
                "de todas as camadas e o assunto some."
            )},
            "include_inset": {**_B, "description": (
                "Acrescenta um inserto de localização com o retângulo do recorte principal desenhado "
                "por cima. É o elemento que responde 'onde fica' — indispensável em escala grande para "
                "quem não conhece a região."
            )},
            "inset_layer_ids": {**_SA, "description": "Camadas do inserto. Use um limite municipal, estadual ou de bacia; sem contexto o inserto não localiza nada."},
            "inset_zoom_factor": {**_N, "description": "Quantas vezes mais largo que o recorte principal, quando não há camada de contexto. Padrão 12."},
            "label_field": {**_S, "description": (
                "Campo cujos valores viram rótulos das feições, com halo branco. Um campo que não "
                "existe é recusado com a lista dos campos disponíveis — consulte layer_info antes."
            )},
            "label_layer_id": {**_S, "description": "Camada a rotular. Se omitido, a primeira que tiver o campo."},
            "label_font_size": _N,
            "second_map": {
                "type": "object",
                "description": (
                    "Segundo quadro de mapa na mesma folha, para comparação. Os dois painéis são "
                    "igualados na escala mais aberta por padrão, porque comparar tamanhos entre "
                    "painéis de escalas diferentes é falso."
                ),
                "properties": {
                    "layer_ids": _SA,
                    "subject_layer_id": _S,
                    "panel_title": {**_S, "description": "Legenda do painel direito/inferior."},
                    "margin_percent": _N,
                },
                "required": ["layer_ids"],
                "additionalProperties": False,
            },
            "comparison_same_scale": {**_B, "description": "Padrão true. Se false, cada painel anuncia a própria escala e a barra única é removida."},
            "panel_title": {**_S, "description": "Legenda do painel esquerdo/superior num mapa duplo."},
            "include_legend": _B,
            "include_scale_bar": _B,
            "include_north_arrow": _B,
            "include_grid": _B,
            "confirm_overwrite": {**_B, "description": "Necessário para substituir um arquivo existente."},
        }, ["layer_ids", "title", "output_path"]),
        "annotations": {"title": "Compor mapa", **WRITES},
        "handler": lambda args: bridge_call("compose_map", dict(args), dry_run=False),
    },
    {
        "name": "sigmai_audit_layout",
        "title": "Auditar um layout existente",
        "description": (
            "Roda o regulamento cartográfico contra um layout já existente no projeto — inclusive um feito "
            "à mão pelo usuário — e devolve nota, pontuação e, para cada regra reprovada, o problema "
            "observado, o motivo da regra e o comando que a corrige. Use para revisar o mapa de alguém ou "
            "para verificar um mapa depois de editá-lo."
        ),
        "inputSchema": _obj({
            "layout_name": {**_S, "description": "Nome do layout no gerenciador de layouts do QGIS."},
            "output_path": {**_S, "description": "PNG exportado, se houver, para checar se o quadro do mapa não saiu em branco."},
        }, ["layout_name"]),
        "annotations": {"title": "Auditar layout", **READ_ONLY},
        "handler": lambda args: bridge_call("audit_map_layout", dict(args)),
    },
    {
        "name": "sigmai_list_layouts",
        "title": "Listar layouts do projeto",
        "description": "Layouts de impressão existentes no projeto, com tamanho de página e itens de cada um.",
        "inputSchema": _obj({}),
        "annotations": {"title": "Listar layouts", **READ_ONLY},
        "handler": lambda args: bridge_call("list_layouts"),
    },
    {
        "name": "sigmai_brief_plugin",
        "title": "Briefing de outro plugin do QGIS",
        "description": (
            "Tudo que você precisa para dirigir OUTRO plugin do QGIS, numa chamada — o caso de "
            "quem está desenvolvendo um plugin e quer que você o exercite. Devolve: identidade e "
            "estado (instalado, carregado, ativo); a saúde do provedor de Processing, com "
            "diagnóstico quando ele está mal registrado; a lista do que é DIRIGÍVEL por programa, "
            "com o contrato completo de cada algoritmo (parâmetros, tipos, obrigatoriedade, "
            "padrões, saídas e classificação de risco); a superfície de interface que NÃO é "
            "dirigível (menus, botões, janelas) e por quê; e um plano de teste em ordem segura. "
            "Chame isto ANTES de propor qualquer coisa ao usuário sobre outro plugin: sem o "
            "briefing você não sabe o que aquele plugin expõe, e prometer uma ação que ele não "
            "tem é o erro mais caro aqui. Não é resumo gerado nem índice: é o contrato que o "
            "próprio plugin declara ao QGIS. Nenhum código-fonte sai da máquina do usuário."
        ),
        "inputSchema": _obj({
            "plugin_name": {**_S, "description": "Nome do pacote do plugin, como aparece em sigmai_run_command list_installed_plugins."},
            "full_contract_limit": {**_N, "description": "Quantos algoritmos vêm com o contrato inteiro. Padrão 12; o resto vem só com id e nome."},
        }, ["plugin_name"]),
        "annotations": {"title": "Briefing de plugin", **READ_ONLY},
        "handler": lambda args: bridge_call("brief_plugin", dict(args)),
    },
    {
        "name": "sigmai_capabilities",
        "title": "Comandos disponíveis",
        "description": (
            "Catálogo completo dos comandos que a instalação do SIGMAI expõe, com grupo, nível de permissão, "
            "se aceita simulação e se exige confirmação. Use quando precisar de uma operação que não tem "
            "ferramenta MCP dedicada — depois execute-a por sigmai_run_command."
        ),
        "inputSchema": _obj({}),
        "annotations": {"title": "Comandos disponíveis", **READ_ONLY},
        "handler": lambda args: bridge_call("get_capabilities"),
    },
    {
        "name": "sigmai_run_command",
        "title": "Executar um comando do SIGMAI",
        "description": (
            "Executa qualquer comando do catálogo do SIGMAI (veja sigmai_capabilities). Comandos de leitura "
            "rodam sempre; comandos de escrita passam pelo controle de acesso configurado no painel. "
            "Prefira as ferramentas dedicadas quando existirem — elas têm esquema de entrada validado. "
            "Use esta para operações de vetor, raster, Processing, simbologia e fluxos de trabalho."
        ),
        "inputSchema": _obj({
            "action": {**_S, "description": "Nome do comando, ex.: 'buffer', 'apply_graduated_style', 'run_processing'."},
            "params": {"type": "object", "description": "Parâmetros do comando.", "additionalProperties": True},
            "dry_run": {**_B, "description": "Simular em vez de executar. Sempre permitido."},
        }, ["action"]),
        "annotations": {"title": "Executar comando", **WRITES},
        "handler": lambda args: bridge_call(
            str(args.get("action", "")),
            dict(args.get("params") or {}),
            dry_run=bool(args.get("dry_run", False)),
        ),
    },
]

TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}

INSTRUCTIONS = """O SIGMAI conecta você ao QGIS que o usuário tem aberto na máquina dele.

Ordem de trabalho que evita a maioria dos erros:
1. sigmai_status — confirme que a bridge está online e veja o MODO DE ACESSO.
2. sigmai_project_overview — pegue os ids reais das camadas. Nunca invente um id.
3. Para mapas: leia sigmai_cartographic_rulebook uma vez, depois use
   sigmai_plan_map para simular e sigmai_compose_map para executar.
4. Leia o campo `audit` da resposta. Ele traz nota, problemas e o comando que
   corrige cada um. Se a nota não for A, corrija e refaça em vez de entregar.

Sobre o modo de acesso: em "Somente leitura" (padrão) nenhuma ação de escrita
executa — simule com dry_run, mostre o resultado e peça ao usuário que libere no
painel do SIGMAI dentro do QGIS. Uma recusa não é motivo para tentar de novo com
os mesmos parâmetros.

Autoria: o autor do plugin não é o autor do mapa. Pergunte ao usuário o que deve
constar em map_author e data_source; sem fonte declarada o mapa não é citável.

Três parâmetros resolvem a maioria dos pedidos de quem não conhece QGIS:

- subject_layer_id — "mapa DO parque MOSTRANDO os municípios" enquadra o parque
  e desenha os municípios em volta. Sem ele o recorte vira a união de todas as
  camadas e o assunto vira um ponto invisível.
- include_inset — responde "onde fica isso?". Em escala grande, é o elemento
  que falta com mais frequência. Passe inset_layer_ids com um limite estadual
  ou municipal, senão o inserto fica vazio.
- second_map — dois recortes na mesma folha. Por padrão os painéis são
  igualados na escala mais aberta; comparar tamanhos entre escalas diferentes
  é enganoso, e o SIGMAI recusa fazer isso em silêncio.

Auditar e exercitar OUTRO plugin — o caso de quem está desenvolvendo um:
comece por sigmai_brief_plugin, que numa chamada diz o que aquele plugin expõe,
o contrato de cada algoritmo e o que NÃO é acionável por programa. Depois dele,
sigmai_run_command dá acesso ao catálogo inteiro:
inspect_plugin e check_plugin_structure para ver como ele está montado,
list_plugin_processing_algorithms para descobrir o que ele expõe,
get_plugin_algorithm_info para os parâmetros de um algoritmo,
dry_run_plugin_algorithm_generic para simular e ver a classificação de risco,
e run_plugin_algorithm_generic_safe para executar de verdade. Esse último
serve qualquer plugin; run_plugin_algorithm_safe é só para os poucos com
adaptador dedicado. Só é alcançável assim o que o plugin registrar como
algoritmo de Processing: botão de barra e janela de diálogo não são chamáveis
por programa, e para esses o SIGMAI audita a estrutura mas não aperta o botão.

compose_map recusa em vez de improvisar. Toda recusa vem com a lista do que é
aceito — leia a lista em vez de tentar variações do nome. Ele recusa:

- parâmetro que não conheça (inclusive erro de digitação);
- formato de página ou template que não exista;
- label_field que não exista nas camadas do mapa (chame sigmai_layer_info
  antes para ver os campos);
- output_path que seja uma pasta, ou sem extensão reconhecida;
- exportação que não gerou arquivo no disco.

Isso é deliberado: um mapa entregue com um parâmetro ignorado é um mapa
diferente do que você descreveu ao usuário."""


# ---------------------------------------------------------------------------
# Protocolo
# ---------------------------------------------------------------------------

def _tool_manifest() -> list[dict[str, Any]]:
    return [{key: value for key, value in tool.items() if key != "handler"} for tool in TOOLS]


def _text_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    """Resultado de tool: JSON serializado em texto + cópia estruturada.

    A spec recomenda emitir os dois: clientes antigos leem o texto, clientes
    novos leem o objeto.
    """
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}
    if not isinstance(payload, str):
        result["structuredContent"] = payload if isinstance(payload, dict) else {"result": payload}
    return result


class MCPServer:
    def __init__(self) -> None:
        self.transport = StdioTransport()
        self.protocol_version = FALLBACK_PROTOCOL_VERSION
        self.initialized = False

    # -- laço principal ---------------------------------------------------
    def run(self) -> int:
        log(f"iniciado (pid {os.getpid()}, python {sys.version.split()[0]})")
        for line in self.transport.read():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._send_error(None, PARSE_ERROR, "Parse error")
                continue
            try:
                self._dispatch(message)
            except Exception as exc:  # nunca deixar o laço morrer
                log(f"exceção no dispatcher: {type(exc).__name__}: {exc}")
                message_id = message.get("id") if isinstance(message, dict) else None
                if message_id is not None:
                    self._send_error(message_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        log("stdin fechado; encerrando")
        return 0

    def _dispatch(self, message: Any) -> None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            self._send_error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Invalid Request")
            return

        method = message.get("method")
        message_id = message.get("id")

        # Notificações não recebem resposta, nunca.
        if message_id is None:
            if method == "notifications/initialized":
                self.initialized = True
                log("cliente inicializado")
            return

        if not isinstance(method, str):
            self._send_error(message_id, INVALID_REQUEST, "Invalid Request: missing method")
            return

        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            self._send_error(message_id, INVALID_PARAMS, "params must be an object")
            return

        if method == "initialize":
            self._send_result(message_id, self._initialize(params))
        elif method == "ping":
            self._send_result(message_id, {})
        elif method in ("tools/list", "server/discover"):
            self._send_result(message_id, self._list_tools(method))
        elif method == "tools/call":
            self._call_tool(message_id, params)
        elif method in ("resources/list", "prompts/list"):
            # Alguns clientes sondam mesmo sem a capability declarada.
            self._send_result(message_id, {"resources": []} if method.startswith("resources") else {"prompts": []})
        else:
            self._send_error(message_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    # -- métodos ----------------------------------------------------------
    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        # Versão desconhecida NÃO é erro na era com handshake: responder com a
        # nossa é o comportamento normativo. Devolver erro derruba clientes
        # mais novos que este servidor.
        self.protocol_version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else FALLBACK_PROTOCOL_VERSION
        client = params.get("clientInfo") or {}
        log(f"initialize de {client.get('name', '?')} {client.get('version', '')} "
            f"(pediu {requested!r}, negociado {self.protocol_version})")
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": SERVER_TITLE, "version": _plugin_version()},
            "instructions": INSTRUCTIONS,
        }

    def _list_tools(self, method: str) -> dict[str, Any]:
        result: dict[str, Any] = {"tools": _tool_manifest()}
        if method == "server/discover" or self.protocol_version >= "2026-07-28":
            result["resultType"] = "complete"
            result["serverInfo"] = {"name": SERVER_NAME, "title": SERVER_TITLE, "version": _plugin_version()}
            result["instructions"] = INSTRUCTIONS
        return result

    def _call_tool(self, message_id: Any, params: dict[str, Any]) -> None:
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOLS_BY_NAME:
            # Ferramenta inexistente é erro de protocolo: o modelo não se
            # corrige inventando outro nome.
            self._send_error(message_id, INVALID_PARAMS, f"Unknown tool: {name}")
            return
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            self._send_error(message_id, INVALID_PARAMS, "arguments must be an object")
            return

        tool = TOOLS_BY_NAME[name]
        try:
            response = tool["handler"](arguments)
        except BridgeError as exc:
            # Erro de execução: vai como isError para o modelo poder reagir.
            self._send_result(message_id, _text_result({"ok": False, "error": "SIGMAI_BRIDGE_UNAVAILABLE", "message": str(exc)}, True))
            return
        except Exception as exc:
            self._send_result(message_id, _text_result({"ok": False, "error": type(exc).__name__, "message": str(exc)}, True))
            return

        failed = isinstance(response, dict) and response.get("ok") is False
        self._send_result(message_id, _text_result(response, failed))

    # -- envio ------------------------------------------------------------
    def _send_result(self, message_id: Any, result: dict[str, Any]) -> None:
        self.transport.write({"jsonrpc": "2.0", "id": message_id, "result": result})

    def _send_error(self, message_id: Any, code: int, message: str, data: Any = None) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self.transport.write({"jsonrpc": "2.0", "id": message_id, "error": error})


def _plugin_version() -> str:
    metadata = _ROOT / "metadata.txt"
    if not metadata.exists():
        metadata = _ROOT / "sigmai" / "metadata.txt"
    try:
        for line in metadata.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("version="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return "0.0.0"


def main() -> int:
    return MCPServer().run()


if __name__ == "__main__":
    raise SystemExit(main())
