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
import tempfile
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
    temp = os.environ.get("TEMP") or tempfile.gettempdir()
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
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - http://<loopback>:<port>, host checked just above.
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


def filter_capabilities(response: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Recorta o catálogo antes de devolvê-lo ao cliente.

    A resposta inteira tem ~70 KB: num cliente pequeno ela não cabe no
    contexto e o assistente acaba adivinhando nomes de comando — foi assim
    que um assistente tentou get_features e get_attribute_table, que não
    existem, em vez de sample_features. Filtrar aqui, e não na ponte, mantém
    a ação get_capabilities inalterada para os clientes que a chamam direto.
    """
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or "commands" not in data:
        return response
    group = str(args.get("group") or "").strip().lower()
    search = str(args.get("search") or "").strip().lower()
    names_only = bool(args.get("names_only"))
    commands = {
        name: meta for name, meta in data["commands"].items()
        if (not group or str(meta.get("group", "")).lower() == group) and (not search or search in name.lower())
    }
    groups = {}
    for name, meta in commands.items():
        groups.setdefault(str(meta.get("group", "")), []).append(name)
    filtered = {
        "schema_version": data.get("schema_version"),
        "groups": {key: sorted(value) for key, value in sorted(groups.items())},
        "command_count": len(commands),
        "disabled_actions": [name for name in data.get("disabled_actions", []) if name in commands or not (group or search)],
    }
    if not names_only:
        filtered["commands"] = commands
        filtered["requires_confirmation"] = [name for name in data.get("requires_confirmation", []) if name in commands]
        filtered["dry_run_supported"] = [name for name in data.get("dry_run_supported", []) if name in commands]
    if not (group or search or names_only):
        # Sem filtro, a resposta completa continua igual à da ponte.
        return response
    if group and not commands:
        filtered["hint"] = "Nenhum comando neste grupo. Grupos existentes: " + ", ".join(sorted({str(m.get("group", "")) for m in data["commands"].values()}))
    return {**response, "data": filtered}


def layer_details(args: dict[str, Any]) -> dict[str, Any]:
    """Uma chamada, quatro leituras: metadados, amostra, estilo e validade.

    A versão anterior só chamava get_layer_info e descartava sample_size — a
    descrição prometia amostra, simbologia e validade e não entregava nenhum
    dos três. O assistente que precisava ler o atributo 'Nome_UC' de um KML
    para saber em que estado o parque fica não tinha como.
    """
    layer_id = str(args.get("layer_id", ""))
    sample_size = int(args.get("sample_size", 5) or 0)
    sample_size = max(0, min(50, sample_size))
    info = bridge_call("get_layer_info", {"layer_id": layer_id})
    if not info.get("ok"):
        return info
    data = dict(info.get("data") or {})
    warnings = list(info.get("warnings") or [])
    is_vector = str(data.get("layer_type", data.get("type", ""))).lower() == "vector" or "geometry_type" in data
    if is_vector and sample_size > 0:
        sample = bridge_call("sample_features", {"layer_id": layer_id, "max_features": sample_size})
        if sample.get("ok"):
            data["sample"] = sample.get("data")
        else:
            warnings.append("amostra indisponível: " + str((sample.get("errors") or [{}])[0].get("message", "")))
    style = bridge_call("inspect_layer_style", {"layer_id": layer_id})
    if style.get("ok"):
        data["style"] = style.get("data")
    if is_vector:
        validity = bridge_call("validate_geometries", {"layer_id": layer_id})
        if validity.get("ok"):
            data["geometry_validity"] = validity.get("data")
        else:
            warnings.append("validade das geometrias indisponível: " + str((validity.get("errors") or [{}])[0].get("message", "")))
    return {**info, "data": data, "warnings": warnings}


def _obj(properties: dict[str, Any], required: list[str] | None = None, additional: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": additional}
    if required:
        schema["required"] = required
    return schema


_S = {"type": "string"}
_B = {"type": "boolean"}
_N = {"type": "number"}
_SA = {"type": "array", "items": {"type": "string"}}

#: Parâmetros de compose_map, publicados UMA vez para sigmai_plan_map e
#: sigmai_compose_map. O esquema tem additionalProperties=false: um parâmetro
#: que o compositor aceita mas não estiver aqui é INALCANÇÁVEL pelo cliente —
#: e foi o que aconteceu com production_date e auto_projected_crs, que o
#: regulamento manda usar e o esquema não deixava passar. Um teste confere esta
#: tabela contra compose.KNOWN_PARAMETERS.
COMPOSE_PROPERTIES: dict[str, Any] = {
    "layer_ids": {**_SA, "description": "Camadas a exibir, na ordem de desenho (a última fica por cima)."},
    "title": {**_S, "description": "Título do mapa."},
    "subtitle": _S,
    "map_language": {**_S, "description": (
        "Língua dos textos que o PRÓPRIO compositor escreve na moldura — 'Fonte:'/"
        "'Elaboração:', título padrão quando 'title' é omitido, 'Legenda', 'Painel A/B' e o "
        "crédito da ferramenta. NÃO afeta title/subtitle/legend_title/data_source/map_author, "
        "que já saem na língua em que você os escreveu. Padrão 'pt-BR'. Aceita 'pt-BR', 'en', "
        "'es', 'fr', 'de', 'it', 'ja', 'zh-Hans', 'zh-Hant', 'ko', 'ru', 'ar', 'he', 'el', 'th' "
        "(e variantes tolerantes como 'pt', 'zh-CN', 'PT-br'). Uma língua fora dessa lista é "
        "recusada com a lista — escolha então a mais próxima (em geral 'en'). Use a mesma língua "
        "em que o usuário está conversando — não pergunte, escolha pela língua da conversa; um "
        "mapa não deve sair com metade do texto em português quando o pedido foi feito noutra língua."
    )},
    "output_path": {**_S, "description": (
        "Caminho absoluto do ARQUIVO de saída, com nome e extensão — não a pasta, não um caminho "
        "relativo, não um caminho de outro sistema operacional. A extensão define o formato quando "
        "'format' não é informado. Ignorado em sigmai_plan_map."
    )},
    "format": {"type": "string", "enum": ["pdf", "png", "svg", "tif", "tiff", "jpg", "jpeg"],
               "description": "Formato do arquivo. Revistas costumam pedir TIFF a 300-600 dpi para figuras."},
    "page": {**_S, "description": (
        "Formato e orientação, ex.: 'A4 landscape', 'A3 retrato', 'A2 portrait'. "
        "Formatos: A0-A5, B4, B5, LETTER, LEGAL, TABLOID. Um formato desconhecido é recusado."
    )},
    "orientation": {**_S, "description": (
        "'landscape'/'portrait' (ou retrato/paisagem), quando não vier junto de 'page'; ou 'auto' para o "
        "SIGMAI girar a folha se o recorte aproveitar melhor a outra orientação (recomendado quando você não sabe)."
    )},
    "arrangement": {**_S, "description": (
        "Onde ficam legenda, escala e norte: 'coluna_lateral' (quadro alto) ou 'faixa_inferior' (quadro largo). "
        "Omitido: o SIGMAI escolhe pela forma do recorte."
    )},
    "margin_mm": {"description": "Margens da página em mm: um número, ou um objeto {top, right, bottom, left}, ou uma lista [topo, direita, base, esquerda].",
                  "anyOf": [{"type": "number"}, {"type": "object"}, {"type": "array"}]},
    "template": {"type": "string", "enum": ["cientifico", "publicacao", "relatorio_ambiental", "minimalista"]},
    "map_crs": {**_S, "description": "CRS do mapa, ex.: EPSG:31983. Se omitido e o projeto for geográfico, o SIGMAI escolhe UTM ou Policônica conforme a extensão."},
    "auto_projected_crs": {**_B, "description": "Padrão true: projeto em coordenadas geográficas é reprojetado para o UTM/Policônica adequado, para que escala e barra sejam métricas. false mantém o CRS do projeto."},
    "margin_percent": {**_N, "description": "Folga em torno dos dados, em porcentagem da extensão (0 a 100). Padrão 5."},
    "round_scale": {**_B, "description": "Padrão true: fecha a escala na série cartográfica (1:250.000 em vez de 1:257.090)."},
    "scale": {**_N, "description": (
        "Denominador da escala impressa, quando ela é imposta (norma da dissertação, "
        "folha de uma série). Ex.: 25000 para 1:25.000. Omita para o SIGMAI escolher na "
        "série cartográfica. Uma escala que cortaria os dados é recusada, dizendo qual é "
        "a maior que ainda os contém."
    )},
    "dpi": {**_N, "description": "Entre 50 e 1200. Padrão 300."},
    "data_source": {
        "description": (
            "Fonte dos dados, obrigatória para o mapa ser citável (CART007). Texto único para o mapa inteiro, "
            "OU um objeto {camada: fonte} (id ou nome da camada) para procedência POR CAMADA — nesse caso a "
            "legenda mostra 'Municípios (IBGE, 2024)' e a linha de crédito lista cada fonte com as camadas que "
            "cobre. Camada sem fonte declarada herda a dos metadados dela, se houver."
        ),
        "anyOf": [{"type": "string"}, {"type": "object", "additionalProperties": {"type": "string"}}],
    },
    "map_author": {**_S, "description": "Autoria do mapa, obrigatória para o mapa ser citável (CART007). NÃO é o autor do plugin."},
    "map_author_email": _S,
    "organization": _S,
    "production_date": {**_S, "description": "Data de elaboração, como texto (ex.: '2026-09-05' ou 'setembro de 2026'). Padrão: a data de hoje."},
    "notes_text": {**_S, "description": "Observação livre acrescentada à linha de crédito."},
    "legend_title": _S,
    "grid_style": {"type": "string", "enum": ["solid", "cross", "markers", "frame"]},
    "apply_style": {"type": "string", "enum": ["missing", "all", "none"], "description": (
        "'missing' (padrão): reestiliza com a paleta segura só as camadas que ainda têm o símbolo único "
        "padrão do QGIS (sorteado ao carregar) ou um estilo embutido de KML sem amostra de legenda; uma "
        "camada com estilo temático (graduado, categorizado) ou um símbolo único que VOCÊ acabou de "
        "aplicar por apply_single_symbol é preservada. 'all' força a paleta em todas; 'none' não toca "
        "em nenhuma. A resposta lista camada a camada o que foi feito e por quê."
    )},
    "subject_layer_id": {
        "description": (
            "Camada que define o recorte; as demais entram como contexto. É assim que se pede "
            "'mapa DO parque MOSTRANDO os municípios em volta' — sem isso o recorte vira a união "
            "de todas as camadas e o assunto some. Aceita uma lista quando o assunto são várias camadas "
            "(pontos de coleta E a trilha)."
        ),
        "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
    },
    "include_inset": {**_B, "description": (
        "Acrescenta um inserto de localização com o retângulo do recorte principal desenhado "
        "por cima. É o elemento que responde 'onde fica' — indispensável em escala grande para "
        "quem não conhece a região."
    )},
    "inset_layer_ids": {**_SA, "description": (
        "Camadas do inserto. Use um limite municipal, estadual ou de bacia: o inserto passa a mostrar a "
        "EXTENSÃO INTEIRA dessa camada (o estado inteiro, não um recorte dele), e inset_zoom_factor é "
        "ignorado. Com mais de uma camada, manda a de extensão mais larga. Sem contexto o inserto não "
        "localiza nada."
    )},
    "inset_zoom_factor": {**_N, "description": "Só vale SEM inset_layer_ids: quantas vezes mais largo que o recorte principal. Padrão 12."},
    "label_field": {**_S, "description": (
        "Campo cujos valores viram rótulos das feições, com halo branco. Um campo que não "
        "existe é recusado com a lista dos campos disponíveis — consulte sigmai_layer_details antes."
    )},
    "label_layer_id": {**_S, "description": "Camada a rotular. Se omitido, a primeira que tiver o campo."},
    "label_font_size": {**_N, "description": "Corpo dos rótulos em pontos (3 a 72)."},
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
    "panels": {
        "type": "array",
        "description": (
            "Painéis EXTRAS além do principal, para uma figura (a), (b), (c)… — cada um como second_map "
            "({layer_ids, subject_layer_id?, panel_title?, margin_percent?}). Até 7 extras. Os quadros ficam "
            "em grade e recebem letras; igualados na escala mais aberta salvo comparison_same_scale=false. "
            "Não combine com second_map."
        ),
        "items": {
            "type": "object",
            "properties": {"layer_ids": _SA, "subject_layer_id": _S, "panel_title": _S, "margin_percent": _N},
            "required": ["layer_ids"],
            "additionalProperties": False,
        },
    },
    "figure_width_mm": {**_N, "description": (
        "Figura para periódico: a página passa a ter esta largura (a largura final impressa) e a altura é "
        "escolhida para o quadro casar com o recorte. As fontes são julgadas nessa largura (CART071)."
    )},
    "figure_height_mm": {**_N, "description": "Altura da figura, se a revista a impõe; senão o SIGMAI escolhe."},
    "figure_max_height_mm": {**_N, "description": "Altura máxima quando o SIGMAI escolhe (padrão 230 mm)."},
    "journal_column": {**_S, "description": (
        "Atalho para figure_width_mm: 'single' (85 mm), 'one_and_half' (120 mm) ou 'double' (175 mm). "
        "Cada revista tem a sua medida — se a instrução aos autores der outra, passe figure_width_mm."
    )},
    "recipe_path": {**_S, "description": (
        "Caminho absoluto de um .json para gravar a receita reproduzível do mapa (parâmetros, camadas, hashes "
        "dos dados, versões). A receita vai SEMPRE para o layout e para os metadados do PNG; este arquivo é extra."
    )},
    "comparison_same_scale": {**_B, "description": "Padrão true. Se false, cada painel anuncia a própria escala e a barra única é removida."},
    "panel_title": {**_S, "description": "Legenda do painel esquerdo/superior num mapa duplo. Sem ela, 'Painel A' na língua do mapa."},
    "include_legend": {**_B, "description": "Padrão true. Sem legenda num mapa de mais de uma camada, CART002 reprova — é uma omissão deliberada que a auditoria aponta."},
    "include_scale_bar": _B,
    "include_scale_text": _B,
    "include_north_arrow": _B,
    "include_grid": {**_B, "description": "Padrão true. Sem grade, CART010 avisa."},
    "include_logo": _B,
    "logo_path": {**_S, "description": "Caminho absoluto de uma imagem (PNG/SVG) para o canto da folha, quando include_logo=true."},
    "layout_name": {**_S, "description": (
        "Nome do layout no projeto do QGIS. Se já existir um com esse nome, ele é SUBSTITUÍDO — use o "
        "mesmo layout_name ao refazer um mapa, senão cada composição acumula 'Título (2)', 'Título (3)'… "
        "no projeto do usuário. Padrão: derivado do título."
    )},
    "confirm_overwrite": {**_B, "description": "Necessário para substituir um ARQUIVO existente (o layout no projeto é regido por layout_name)."},
}

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
            "Metadados detalhados de uma camada numa chamada: campos e tipos, extensão, CRS, simbologia "
            "atual, validade das geometrias e uma amostra de feições com os valores dos atributos. Use "
            "para decidir simbologia, expressões de rótulo, classificação temática — ou para ler o que "
            "uma camada diz de si mesma (nome da unidade, fonte, municípios) antes de responder ao usuário."
        ),
        "inputSchema": _obj({
            "layer_id": {**_S, "description": "Id da camada, obtido em sigmai_project_overview."},
            "sample_size": {**_N, "description": "Quantas feições amostrar (0 a 50)."},
        }, ["layer_id"]),
        "annotations": {"title": "Detalhes da camada", **READ_ONLY},
        "handler": lambda args: layer_details(args),
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
            "para a série cartográfica, as camadas que entrariam e o que a simbologia faria. Aceita "
            "EXATAMENTE os mesmos parâmetros de sigmai_compose_map — o que você simular aqui é o que "
            "será composto lá. Funciona em qualquer modo de acesso, inclusive somente leitura. Use para "
            "mostrar ao usuário o que será feito antes de pedir autorização para executar."
        ),
        "inputSchema": _obj(dict(COMPOSE_PROPERTIES), ["layer_ids"]),
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
        "inputSchema": _obj(dict(COMPOSE_PROPERTIES), ["layer_ids", "title", "output_path"]),
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
        "name": "sigmai_briefing",
        "title": "Briefing do projeto em uma chamada",
        "description": (
            "COMECE POR AQUI. Numa chamada: versões, projeto (caminho, CRS), cada camada com id, geometria, "
            "contagem, CRS, campo de nome provável com exemplos, rótulos ligados, problema de codificação; "
            "layouts (e quais foram compostos pelo SIGMAI); o modo de acesso e as pastas liberadas; o "
            "regulamento resumido; os templates; e o caminho recomendado para os pedidos mais comuns. "
            "Substitui a sequência status → panorama → detalhes → regulamento → capacidades."
        ),
        "inputSchema": _obj({}),
        "annotations": {"title": "Briefing", **READ_ONLY},
        "handler": lambda args: bridge_call("project_briefing", {}),
    },
    {
        "name": "sigmai_spatial_relationship",
        "title": "Onde fica o quê: contenção, interseção e vizinho mais próximo",
        "description": (
            "Responde, em número e em texto, a relação entre duas camadas: quanto de cada feição de A está "
            "dentro de B (fração de área), quais feições de B tocam A, e a feição de B mais próxima com a "
            "distância geodésica em metros. Use ANTES de assumir em que estado/município uma área está — foi "
            "assim que se descobriu que um parque pedido 'no Piauí' fica no Ceará. Nomes vêm do campo de "
            "nome da camada (display_field para escolher)."
        ),
        "inputSchema": _obj({
            "layer_id": {**_S, "description": "Camada A (o assunto: a UC, os pontos)."},
            "other_layer_id": {**_S, "description": "Camada B (o contexto: estados, municípios)."},
            "feature_id": {**_N, "description": "Só esta feição de A (id numérico)."},
            "display_field": {**_S, "description": "Campo de B usado como nome nas respostas."},
            "max_results": {**_N, "description": "Vizinhos/interseções listados por feição (padrão 10, máx. 100)."},
            "radius_m": {**_N, "description": "Só vizinhos até esta distância em metros."},
        }, ["layer_id", "other_layer_id"]),
        "annotations": {"title": "Relação espacial", **READ_ONLY},
        "handler": lambda args: bridge_call("spatial_relationship", dict(args)),
    },
    {
        "name": "sigmai_add_context_annotations",
        "title": "Divisa como linha e nomes de região a partir de uma camada",
        "description": (
            "Cria, a partir de uma camada de polígonos já carregada, o contexto que um cartógrafo desenha à "
            "mão: a divisa (fronteira) como linha tracejada, os nomes das regiões (por campo, ou um texto "
            "único para a união) posicionados pelo polo de inacessibilidade, e rótulos avulsos (o estado "
            "vizinho, 'Oceano Atlântico') em coordenadas dadas. Devolve os ids criados para incluir em "
            "layer_ids. Camadas de memória por padrão; output_gpkg as persiste. ESTA AÇÃO ALTERA O PROJETO."
        ),
        "inputSchema": _obj({
            "boundary_layer_id": {**_S, "description": "Camada de polígonos de origem (UF, municípios, bacia)."},
            "dissolve": {**_B, "description": "Padrão true: uma divisa da união; false: a fronteira de cada feição."},
            "label_field": {**_S, "description": "Campo com o nome de cada feição (um rótulo por feição; exige dissolve=false para várias)."},
            "label_text": {**_S, "description": "Um nome só, para a união (ex.: 'Piauí')."},
            "extra_labels": {"type": "array", "items": {"type": "object",
                                                        "properties": {"text": _S, "x": _N, "y": _N, "crs": _S, "lon": _N, "lat": _N},
                                                        "required": ["text"], "additionalProperties": False},
                             "description": "Rótulos avulsos: {text, x, y, crs?} (crs padrão: o da camada) ou {text, lon, lat} em graus (EPSG:4326)."},
            "include_boundary": _B,
            "boundary_color": _S, "boundary_width_mm": _N,
            "boundary_style": {"type": "string", "enum": ["solid", "dash", "dot", "dash dot"]},
            "label_font_size": _N, "label_color": _S, "letter_spacing": _N, "uppercase": _B,
            "output_gpkg": {**_S, "description": "Caminho absoluto de um .gpkg para persistir as camadas (pasta liberada)."},
            "map_language": {**_S, "description": "Língua dos nomes das camadas criadas, que aparecem na legenda — use a mesma de map_language do compose_map (padrão pt-BR)."},
        }, ["boundary_layer_id"]),
        "annotations": {"title": "Anotações de contexto", **WRITES},
        "handler": lambda args: bridge_call("add_context_annotations", dict(args)),
    },
    {
        "name": "sigmai_campaign_map",
        "title": "Mapa de campanha de campo",
        "description": (
            "A figura 1 de uma dissertação de campo numa chamada: pontos de coleta rotulados, trilha, área de "
            "estudo em destaque, entorno como contexto e inserto de localização, com o template 'campanha'. "
            "Opcionalmente grava a tabela de coordenadas dos pontos (CSV com atributos, E/N no CRS pedido e "
            "lat/lon). Aceita os demais parâmetros de sigmai_compose_map (output_path, dpi, page, "
            "data_source por camada…). ESTA AÇÃO GRAVA ARQUIVO."
        ),
        "inputSchema": _obj({
            "points_layer_id": {**_S, "description": "Camada de PONTOS dos sítios/coletas (waypoints, não a trilha). Sítios numa planilha? Antes, sigmai_run_command load_vector_layer com o .csv (lon/lat detectados; x_field/y_field/crs para E/N)."},
            "track_layer_id": {**_S, "description": "Camada de LINHA da trilha percorrida."},
            "area_layer_ids": {**_SA, "description": "Polígonos da área de estudo (UC, fazenda, bacia)."},
            "context_layer_ids": {**_SA, "description": "Camadas de contexto (municípios, hidrografia)."},
            "inset_layer_ids": {**_SA, "description": "Limite para o inserto de localização (estado)."},
            "label_field": {**_S, "description": "Campo de nome dos pontos (padrão: detectado; acima de 60 pontos só rotula se pedido)."},
            "subject_layer_id": {"anyOf": [{"type": "string"}, _SA], "description": "Padrão: pontos + trilha."},
            "title": _S, "subtitle": _S,
            "campaign_dates": {**_S, "description": "Datas da campanha, viram o subtítulo ('Campanha de campo: …')."},
            "map_author": _S,
            "data_source": {"anyOf": [{"type": "string"}, {"type": "object", "additionalProperties": {"type": "string"}}]},
            "coordinate_table_path": {**_S, "description": "Caminho absoluto de um .csv com as coordenadas dos pontos."},
            "table_crs": {**_S, "description": "CRS das colunas E/N da tabela (padrão: o da camada); lat/lon saem sempre."},
            "table_delimiter": {"type": "string", "enum": [",", ";"]},
            "output_path": _S, "format": _S, "dpi": _N, "page": _S, "orientation": _S, "map_language": _S,
            "margin_percent": _N, "include_grid": _B, "confirm_overwrite": _B, "layout_name": _S, "recipe_path": _S,
            "journal_column": _S, "figure_width_mm": _N,
        }, ["points_layer_id"]),
        "annotations": {"title": "Mapa de campanha", **WRITES},
        "handler": lambda args: bridge_call("compose_campaign_map", dict(args)),
    },
    {
        "name": "sigmai_export_coordinate_table",
        "title": "Tabela de coordenadas (CSV)",
        "description": (
            "Grava um CSV com os atributos e as coordenadas de cada feição — E/N no CRS pedido e longitude/"
            "latitude (EPSG:4326) sempre — para a seção de material examinado ou o apêndice de sítios. "
            "Feições não pontuais usam o ponto representativo. ESTA AÇÃO GRAVA ARQUIVO."
        ),
        "inputSchema": _obj({
            "layer_id": _S,
            "output_path": {**_S, "description": "Caminho absoluto do .csv (pasta liberada)."},
            "crs": {**_S, "description": "CRS das colunas E/N (ex.: 'EPSG:31984'); padrão: o da camada."},
            "fields": {**_SA, "description": "Campos a incluir (padrão: todos)."},
            "delimiter": {"type": "string", "enum": [",", ";"]},
            "decimals": _N, "confirm_overwrite": _B,
        }, ["layer_id", "output_path"]),
        "annotations": {"title": "Tabela de coordenadas", **WRITES},
        "handler": lambda args: bridge_call("export_coordinate_table", dict(args)),
    },
    {
        "name": "sigmai_map_recipe",
        "title": "Receita reproduzível de um mapa",
        "description": (
            "Devolve a receita gravada num layout composto pelo SIGMAI (parâmetros como pedidos, camadas com "
            "fonte e hash SHA-256 dos arquivos, versões do QGIS/SIGMAI, página, escala, laudo) e diz se os "
            "dados mudaram desde então. Lê de layout_name, de um .json ou do PNG exportado (a receita vai nos "
            "metadados dele). Com output_path grava um .json."
        ),
        "inputSchema": _obj({
            "layout_name": _S,
            "recipe_path": {**_S, "description": "Um .json de receita ou o .png exportado."},
            "output_path": {**_S, "description": "Grava a receita neste .json (pasta liberada)."},
            "confirm_overwrite": _B,
        }),
        "annotations": {"title": "Receita do mapa", **WRITES},
        "handler": lambda args: bridge_call("get_map_recipe", dict(args)),
    },
    {
        "name": "sigmai_recompose_from_recipe",
        "title": "Refazer um mapa a partir da receita",
        "description": (
            "Recompõe o mapa com os mesmos parâmetros da receita — quando o dado foi atualizado, quando o "
            "projeto foi reaberto (camadas localizadas pelo nome se o id mudou) ou noutra máquina — e diz o "
            "que mudou nos dados desde a receita. 'overrides' sobrescreve parâmetros (novo output_path, "
            "confirm_overwrite…). ESTA AÇÃO GRAVA ARQUIVO."
        ),
        "inputSchema": _obj({
            "layout_name": _S,
            "recipe_path": {**_S, "description": "Um .json de receita ou o .png exportado."},
            "overrides": {"type": "object", "additionalProperties": True, "description": "Parâmetros de compose_map a substituir."},
        }),
        "annotations": {"title": "Recompor da receita", **WRITES},
        "handler": lambda args: bridge_call("recompose_from_recipe", dict(args), dry_run=False),
    },
    {
        "name": "sigmai_methods_paragraph",
        "title": "Parágrafo de Métodos e referência do software",
        "description": (
            "Texto pronto para a seção de Métodos de uma dissertação ou artigo descrevendo como o mapa foi "
            "feito (software e versões, camadas e fontes, CRS, escala, página, exportação, auditoria), mais a "
            "referência bibliográfica do SIGMAI. Em pt-BR, en ou es (outras línguas caem no inglês, com nota)."
        ),
        "inputSchema": _obj({
            "layout_name": _S,
            "recipe_path": _S,
            "language": {**_S, "description": "'pt-BR' (padrão: a língua do mapa), 'en' ou 'es'."},
        }),
        "annotations": {"title": "Parágrafo de Métodos", **READ_ONLY},
        "handler": lambda args: bridge_call("describe_map_for_methods", dict(args)),
    },
    {
        "name": "sigmai_undo",
        "title": "Desfazer a última ação no projeto",
        "description": (
            "Desfaz a última escrita do SIGMAI no projeto do QGIS nesta sessão: restaura estilos, nomes e "
            "rótulos das camadas tocadas, restaura layouts substituídos e remove layouts e camadas criados. "
            "Arquivos gravados em disco NÃO são apagados (a resposta lista quais ficaram). Sem argumentos "
            "desfaz; com list=true só lista o histórico."
        ),
        "inputSchema": _obj({"list": {**_B, "description": "true: só listar o que pode ser desfeito."}}),
        "annotations": {"title": "Desfazer", **WRITES},
        "handler": lambda args: bridge_call("list_undo_history" if args.get("list") else "undo_last_action", {}),
    },
    {
        "name": "sigmai_list_layouts",
        "title": "Listar layouts do projeto",
        "description": "Layouts de impressão existentes no projeto: tamanho e orientação da página, os itens de cada um (mapa, legenda, barra de escala, inserto…) e o CRS/escala de cada quadro de mapa.",
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
            "Catálogo dos comandos que a instalação do SIGMAI expõe (mais de duzentos), com grupo, nível de "
            "permissão, se aceita simulação e se exige confirmação. O catálogo inteiro é grande: comece por "
            "names_only=true para ver os grupos e os nomes, ou filtre com group/search. Para ler feições e "
            "atributos: grupo attribute_table (sample_features, inspect_attribute_table, unique_values, "
            "field_statistics) e expressions (query_features). Depois execute por sigmai_run_command."
        ),
        "inputSchema": _obj({
            "group": {**_S, "description": "Só os comandos deste grupo (ex.: attribute_table, symbology, processing, cartography, raster, layers)."},
            "search": {**_S, "description": "Só os comandos cujo nome contém este texto (ex.: 'feature', 'style', 'buffer')."},
            "names_only": {**_B, "description": "Devolve só a lista de grupos com os nomes dos comandos, sem os metadados de cada um — cabe em qualquer contexto."},
        }),
        "annotations": {"title": "Comandos disponíveis", **READ_ONLY},
        "handler": lambda args: filter_capabilities(bridge_call("get_capabilities"), args),
    },
    {
        "name": "sigmai_run_command",
        "title": "Executar um comando do SIGMAI",
        "description": (
            "Executa qualquer comando do catálogo do SIGMAI. Descubra o nome e os PARÂMETROS em "
            "sigmai_capabilities (cada comando lista os parâmetros que lê; 'parameters_complete' diz se a "
            "lista é exata). Um parâmetro que o comando não lê volta em 'warnings' — nunca é aplicado em "
            "silêncio. Comandos de leitura rodam sempre; comandos de escrita passam pelo controle de acesso "
            "configurado no painel. Prefira as ferramentas dedicadas quando existirem — elas têm esquema de "
            "entrada validado. Use esta para operações de vetor, raster, Processing, simbologia e fluxos."
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
1. sigmai_briefing — numa chamada: modo de acesso, ids reais das camadas (nunca
   invente um id), campo de nome de cada uma, regulamento resumido e o caminho
   recomendado para o pedido. (sigmai_status/sigmai_project_overview/
   sigmai_cartographic_rulebook continuam existindo para o detalhe.)
2. Antes de assumir ONDE algo fica, sigmai_spatial_relationship.
3. Para mapas: sigmai_plan_map para simular, sigmai_compose_map para executar
   (orientation 'auto', data_source por camada, include_inset). Para campo,
   sigmai_campaign_map (sítios em planilha: sigmai_run_command load_vector_layer
   com o .csv — lon/lat, separador e decimal são detectados); para revista,
   journal_column/figure_width_mm e format tif; para (a)(b)(c), panels.
4. Leia o campo `audit` da resposta. Ele traz nota, problemas e o comando que
   corrige cada um. Se a nota não for A, corrija e refaça em vez de entregar.
5. Errou? sigmai_undo. Vai citar? sigmai_methods_paragraph e sigmai_map_recipe.

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
    """Versão do plugin. Este servidor roda como processo separado, então tenta
    o leitor único do pacote e, se o pacote não estiver importável, lê o
    metadata.txt direto — a mesma regra, num só lugar de reserva."""
    try:
        from sigmai.bridge_server import plugin_version  # type: ignore

        return plugin_version()
    except Exception:
        pass
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
