"""Os provedores do chat: a API de Mensagens da Anthropic e o formato de chat da OpenAI.

HTTP direto, sem SDK: um plugin do QGIS não instala pacotes com dependências
compiladas. O transporte é injetado. No QGIS é o gerenciador de rede do
próprio QGIS (``qgis_transport.py``), que respeita o proxy e os certificados
configurados; nos testes é :func:`urllib_transport` contra um servidor falso
local.

Cada provedor guarda o histórico no formato dele, sem conversão: a Anthropic
exige que o bloco de raciocínio volte idêntico ao que ela mandou, e uma
tradução de ida e volta perderia a assinatura.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2026-10-21"
#: Notas curtas de progresso entre uma chamada e outra (beta). Só nos modelos
#: que as aceitam; o Haiku 5.5 não.
NOTES_BETA = "thinking-display-updates-2026-08-18"
NOTES_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")
#: Recusa do filtro de segurança refeita noutro modelo pela própria API (beta).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")
ANTHROPIC_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
EFFORTS = ("low", "medium", "high")

#: Endereços prontos do formato da OpenAI. Outros servem, se falarem o mesmo formato.
OPENAI_PRESETS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "ollama": "http://localhost:11434/v1",
}
#: Modelo sugerido quando a pessoa escolhe o endereço pronto (o do Gemini é gratuito).
PRESET_MODELS = {"gemini": "gemini-3.8-flash"}
#: Modelos gratuitos do Gemini, na ordem em que o chat os tenta quando o
#: escolhido segue sobrecarregado (a cota gratuita do mais novo vive cheia).
GEMINI_FREE_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite")


def _strip_keyword(schema: Any, keyword: str) -> Any:
    if isinstance(schema, dict):
        return {key: _strip_keyword(value, keyword) for key, value in schema.items() if key != keyword}
    if isinstance(schema, list):
        return [_strip_keyword(item, keyword) for item in schema]
    return schema

Transport = Callable[[str, dict, bytes, Callable[[str], None], Callable[[], bool]], tuple]
EventSink = Callable[[str, Any], None]


class ProviderError(Exception):
    """Falha ao falar com o provedor, já classificada para a mensagem ao usuário."""

    def __init__(self, kind: str, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retry_after = retry_after


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    valid: bool = True


@dataclass
class ToolResult:
    call_id: str
    name: str
    text: str
    is_error: bool = False
    image_png: bytes | None = None


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    def add(self, other: "Usage") -> None:
        self.input += other.input
        self.output += other.output
        self.cache_write += other.cache_write
        self.cache_read += other.cache_read


@dataclass
class Reply:
    message: Any
    text: str
    tool_calls: list[ToolCall]
    stop: str
    usage: Usage
    model: str = ""
    notes: list[str] = field(default_factory=list)


def _is_loopback(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def check_url(url: str) -> None:
    """Só HTTPS; HTTP só para a própria máquina (modelo local, servidor de teste)."""
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme == "https" or (scheme == "http" and _is_loopback(url)):
        return
    raise ProviderError("bad_url", f"O endereço do provedor precisa ser HTTPS (ou http em 127.0.0.1/localhost): {url}")


def urllib_transport(url: str, headers: dict, body: bytes, on_line: Callable[[str], None],
                     should_stop: Callable[[], bool], timeout: float = 300.0) -> tuple[int, str]:
    """Transporte da biblioteca padrão: entrega o corpo linha a linha (SSE)."""
    check_url(url)
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - HTTPS do provedor ou loopback, conferido em check_url.
            for raw in response:
                if should_stop():
                    return 499, ""
                on_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        return 200, ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        raise ProviderError("network", f"Sem conexão com o provedor: {getattr(exc, 'reason', exc)}") from exc


def _error_from_status(status: int, body: str, provider: str) -> ProviderError:
    try:
        detail = json.loads(body)
        # O Gemini devolve o erro dentro de uma lista: [{"error": {...}}].
        if isinstance(detail, list) and detail:
            detail = detail[0]
        error = detail.get("error") if isinstance(detail, dict) else None
        message = (error.get("message") if isinstance(error, dict) else None) or (detail.get("message") if isinstance(detail, dict) else None) or body
        kind_hint = str(error.get("type") or error.get("status") or "") if isinstance(error, dict) else ""
    except (json.JSONDecodeError, AttributeError):
        message, kind_hint = body, ""
    message = str(message)[:600]
    if status in (401, 403):
        return ProviderError("auth", f"{provider} recusou a chave de API ({status}): {message}", status)
    if status == 429:
        delay = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)
        return ProviderError("rate_limit", f"{provider}: limite de uso atingido ({status}). Espere um pouco. {message}", status,
                             float(delay.group(1)) if delay else None)
    if status == 499:
        return ProviderError("cancelled", "Interrompido.", status)
    # Sobrecarga passageira: 529 da Anthropic, 502/503/504 (o Gemini gratuito
    # responde 503 "high demand" nos picos). O chat espera e tenta de novo.
    if status in (502, 503, 504, 529) or kind_hint in ("overloaded_error", "UNAVAILABLE"):
        return ProviderError("overloaded", f"{provider} está sobrecarregado ({status}): {message}", status)
    if status >= 500:
        return ProviderError("server", f"{provider} respondeu com erro {status}: {message}", status)
    return ProviderError("bad_request", f"{provider} recusou o pedido ({status}): {message}", status)


def _sse_data(line: str) -> str | None:
    if line.startswith("data:"):
        return line[5:].strip()
    return None


class AnthropicProvider:
    """API de Mensagens da Anthropic, com streaming, cache e raciocínio adaptativo."""

    name = "anthropic"
    label = "Anthropic"

    def __init__(self, api_key: str, model: str = "claude-opus-5-5", effort: str = "medium",
                 transport: Transport | None = None, url: str = ANTHROPIC_URL, max_tokens: int = 32000,
                 notes: bool = True, fallbacks: bool = True):
        self.api_key = api_key
        self.model = model
        self.effort = effort if effort in EFFORTS else "medium"
        self.transport = transport or urllib_transport
        self.url = url
        self.max_tokens = max_tokens
        self.notes = notes and model in NOTES_MODELS
        self.fallbacks = fallbacks and model in FALLBACK_MODELS
        self.sends_images = True

    # -- formato das mensagens ---------------------------------------------
    @staticmethod
    def tool_specs(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"name": tool["name"], "description": tool.get("description", ""), "input_schema": tool["inputSchema"]}
                for tool in tools]

    @staticmethod
    def user_message(text: str) -> dict[str, Any]:
        return {"role": "user", "content": [{"type": "text", "text": text}]}

    @staticmethod
    def append_user_text(history: list[Any], text: str) -> None:
        """Texto novo depois de resultados de ferramenta vai na mesma mensagem do usuário."""
        last = history[-1] if history else None
        if isinstance(last, dict) and last.get("role") == "user" and isinstance(last.get("content"), list):
            last["content"].append({"type": "text", "text": text})
        else:
            history.append(AnthropicProvider.user_message(text))

    @staticmethod
    def tool_results_messages(results: list[ToolResult]) -> list[dict[str, Any]]:
        content = []
        for result in results:
            blocks: list[dict[str, Any]] = [{"type": "text", "text": result.text}]
            if result.image_png:
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                            "data": base64.b64encode(result.image_png).decode("ascii")}})
            content.append({"type": "tool_result", "tool_use_id": result.call_id, "content": blocks,
                            "is_error": bool(result.is_error)})
        return [{"role": "user", "content": content}]

    # -- pedido ------------------------------------------------------------
    def _body(self, system: str, tools: list[dict[str, Any]], messages: list[Any]) -> tuple[dict[str, Any], dict[str, str]]:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "stream": True,
            # Ferramentas e instruções são o prefixo fixo de todo pedido: o
            # ponto de cache no sistema guarda os dois; o automático, no fim,
            # guarda a conversa até ali.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": self.tool_specs(tools),
            "messages": messages,
            "cache_control": {"type": "ephemeral"},
            "thinking": {"type": "adaptive", "display": "updates"} if self.notes else {"type": "adaptive"},
            "output_config": {"effort": self.effort},
        }
        betas = []
        if self.notes:
            betas.append(NOTES_BETA)
        if self.fallbacks:
            body["fallbacks"] = "default"
            betas.append(FALLBACK_BETA)
        headers = {"content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION}
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        return body, headers

    def complete(self, system: str, tools: list[dict[str, Any]], messages: list[Any], on_event: EventSink,
                 should_stop: Callable[[], bool]) -> Reply:
        try:
            return self._complete(system, tools, messages, on_event, should_stop)
        except ProviderError as exc:
            # Os recursos beta são extras: se a API recusar o pedido por causa
            # deles, o chat segue sem eles em vez de parar.
            if exc.kind == "bad_request" and (self.notes or self.fallbacks):
                self.notes = self.fallbacks = False
                on_event("notice", "O provedor recusou um recurso opcional (notas de progresso ou modelo reserva); seguindo sem ele.")
                return self._complete(system, tools, messages, on_event, should_stop)
            raise

    def _complete(self, system: str, tools: list[dict[str, Any]], messages: list[Any], on_event: EventSink,
                  should_stop: Callable[[], bool]) -> Reply:
        body, headers = self._body(system, tools, messages)
        state = _AnthropicStream(on_event)
        status, error_body = self.transport(self.url, headers, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                            state.feed, should_stop)
        if status != 200:
            raise _error_from_status(status, error_body, "Anthropic")
        if state.error:
            raise state.error
        return state.reply()


class _AnthropicStream:
    """Remonta a mensagem a partir dos eventos SSE, bloco por bloco."""

    def __init__(self, on_event: EventSink):
        self.on_event = on_event
        self.blocks: dict[int, dict[str, Any]] = {}
        self.partial: dict[int, str] = {}
        self.usage = Usage()
        self.stop = ""
        self.model = ""
        self.error: ProviderError | None = None
        self.notes: list[str] = []

    def feed(self, line: str) -> None:
        data = _sse_data(line)
        if not data:
            return
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            return
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message") or {}
            self.model = message.get("model", "")
            self._usage(message.get("usage") or {})
        elif kind == "content_block_start":
            index = int(event.get("index", len(self.blocks)))
            block = dict(event.get("content_block") or {})
            if block.get("type") == "tool_use":
                block["input"] = {}
                self.partial[index] = ""
            self.blocks[index] = block
        elif kind == "content_block_delta":
            self._delta(int(event.get("index", 0)), event.get("delta") or {})
        elif kind == "content_block_stop":
            index = int(event.get("index", 0))
            block = self.blocks.get(index) or {}
            if block.get("type") == "tool_use":
                text = self.partial.get(index, "")
                try:
                    block["input"] = json.loads(text) if text.strip() else {}
                except json.JSONDecodeError:
                    block["input"] = {}
                    block["_invalid"] = True
            if block.get("type") == "thinking" and block.get("thinking"):
                self.notes.append(block["thinking"])
        elif kind == "message_delta":
            self.stop = (event.get("delta") or {}).get("stop_reason") or self.stop
            self._usage(event.get("usage") or {})
        elif kind == "error":
            error = event.get("error") or {}
            status = 529 if error.get("type") == "overloaded_error" else 500
            self.error = _error_from_status(status, json.dumps({"error": error}), "Anthropic")

    def _delta(self, index: int, delta: dict[str, Any]) -> None:
        block = self.blocks.setdefault(index, {"type": "text", "text": ""})
        kind = delta.get("type")
        if kind == "text_delta":
            block["text"] = block.get("text", "") + delta.get("text", "")
            self.on_event("text", delta.get("text", ""))
        elif kind == "input_json_delta":
            self.partial[index] = self.partial.get(index, "") + delta.get("partial_json", "")
        elif kind == "thinking_delta":
            block["thinking"] = block.get("thinking", "") + delta.get("thinking", "")
            self.on_event("note", delta.get("thinking", ""))
        elif kind == "signature_delta":
            block["signature"] = delta.get("signature", "")

    def _usage(self, usage: dict[str, Any]) -> None:
        # message_start traz a entrada; message_delta, a saída acumulada.
        if "input_tokens" in usage:
            self.usage.input = int(usage.get("input_tokens") or 0)
        if "cache_creation_input_tokens" in usage:
            self.usage.cache_write = int(usage.get("cache_creation_input_tokens") or 0)
        if "cache_read_input_tokens" in usage:
            self.usage.cache_read = int(usage.get("cache_read_input_tokens") or 0)
        if "output_tokens" in usage:
            self.usage.output = int(usage.get("output_tokens") or 0)

    def reply(self) -> Reply:
        content = []
        calls = []
        for index in sorted(self.blocks):
            block = self.blocks[index]
            invalid = bool(block.pop("_invalid", False))
            content.append(block)
            if block.get("type") == "tool_use":
                calls.append(ToolCall(str(block.get("id", "")), str(block.get("name", "")), block.get("input") or {}, not invalid))
        text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
        return Reply({"role": "assistant", "content": content}, text, calls, self.stop or "end_turn", self.usage,
                     self.model, self.notes)


class OpenAICompatibleProvider:
    """Formato de chat da OpenAI: OpenAI, Gemini pelo endpoint compatível, Ollama e outros."""

    name = "openai_compatible"
    label = "OpenAI-compatible"

    def __init__(self, api_key: str, base_url: str, model: str, transport: Transport | None = None,
                 send_images: bool = True):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.transport = transport or urllib_transport
        self.sends_images = send_images
        # O Gemini aceita só um subconjunto do esquema OpenAPI nas funções, sem
        # additionalProperties; os outros provedores do formato aceitam tudo.
        self.strict_subset = "generativelanguage.googleapis.com" in self.base_url
        self.fallback_models = [m for m in GEMINI_FREE_MODELS if m != model and model in GEMINI_FREE_MODELS]             if self.strict_subset else []
        check_url(self.base_url)

    def tool_specs(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        specs = []
        for tool in tools:
            schema = _strip_keyword(tool["inputSchema"], "additionalProperties") if self.strict_subset else tool["inputSchema"]
            specs.append({"type": "function", "function": {"name": tool["name"], "description": tool.get("description", ""),
                                                           "parameters": schema}})
        return specs

    @staticmethod
    def user_message(text: str) -> dict[str, Any]:
        return {"role": "user", "content": text}

    @staticmethod
    def append_user_text(history: list[Any], text: str) -> None:
        history.append(OpenAICompatibleProvider.user_message(text))

    def tool_results_messages(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "tool", "tool_call_id": result.call_id, "content": result.text}
                                          for result in results]
        # Mensagem de ferramenta só leva texto nesse formato: a prévia do mapa
        # vai numa mensagem do usuário logo depois.
        images = [result for result in results if result.image_png] if self.sends_images else []
        if images:
            content: list[dict[str, Any]] = [{"type": "text", "text": "Prévia do mapa exportado, para conferir à vista."}]
            for result in images:
                url = "data:image/png;base64," + base64.b64encode(result.image_png or b"").decode("ascii")
                content.append({"type": "image_url", "image_url": {"url": url}})
            messages.append({"role": "user", "content": content})
        return messages

    def complete(self, system: str, tools: list[dict[str, Any]], messages: list[Any], on_event: EventSink,
                 should_stop: Callable[[], bool]) -> Reply:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": self.tool_specs(tools),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        state = _OpenAIStream(on_event)
        status, error_body = self.transport(f"{self.base_url}/chat/completions", headers,
                                            json.dumps(body, ensure_ascii=False).encode("utf-8"), state.feed, should_stop)
        if status != 200:
            raise _error_from_status(status, error_body, "O provedor")
        return state.reply()


def _merge(target: dict, key: str, value: Any) -> None:
    if isinstance(value, dict) and isinstance(target.get(key), dict):
        for inner_key, inner_value in value.items():
            _merge(target[key], inner_key, inner_value)
    elif isinstance(value, str) and isinstance(target.get(key), str):
        target[key] += value
    else:
        target[key] = value


class _OpenAIStream:
    STOPS = {"tool_calls": "tool_use", "stop": "end_turn", "length": "max_tokens", "content_filter": "refusal"}

    def __init__(self, on_event: EventSink):
        self.on_event = on_event
        self.text = ""
        self.calls: dict[int, dict[str, Any]] = {}
        self.finish = ""
        self.usage = Usage()
        self.model = ""

    def feed(self, line: str) -> None:
        data = _sse_data(line)
        if not data or data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return
        self.model = chunk.get("model") or self.model
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            cached = int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
            self.usage.input = int(usage.get("prompt_tokens") or 0) - cached
            self.usage.cache_read = cached
            self.usage.output = int(usage.get("completion_tokens") or 0)
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                self.text += delta["content"]
                self.on_event("text", delta["content"])
            for call in delta.get("tool_calls") or []:
                slot = self.calls.setdefault(int(call.get("index", len(self.calls))),
                                             {"id": "", "name": "", "arguments": "", "extra": {}})
                slot["id"] = call.get("id") or slot["id"]
                function = call.get("function") or {}
                slot["name"] = function.get("name") or slot["name"]
                slot["arguments"] += function.get("arguments") or ""
                # Campos que o provedor acrescenta à chamada voltam como vieram:
                # o Gemini 3 manda a assinatura do raciocínio em
                # extra_content.google.thought_signature e recusa (400) o pedido
                # seguinte se ela não voltar.
                for key, value in call.items():
                    if key not in ("index", "id", "type", "function"):
                        _merge(slot["extra"], key, value)
            if choice.get("finish_reason"):
                self.finish = choice["finish_reason"]

    def reply(self) -> Reply:
        calls = []
        native_calls = []
        for index in sorted(self.calls):
            slot = self.calls[index]
            call_id = slot["id"] or f"call_{index}"
            try:
                arguments = json.loads(slot["arguments"]) if slot["arguments"].strip() else {}
                valid = isinstance(arguments, dict)
            except json.JSONDecodeError:
                arguments, valid = {}, False
            calls.append(ToolCall(call_id, slot["name"], arguments if isinstance(arguments, dict) else {}, valid))
            native_calls.append({"id": call_id, "type": "function", **slot.get("extra", {}),
                                 "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"}})
        message: dict[str, Any] = {"role": "assistant", "content": self.text or None}
        if native_calls:
            message["tool_calls"] = native_calls
        stop = self.STOPS.get(self.finish, "tool_use" if calls else "end_turn")
        return Reply(message, self.text, calls, stop, self.usage, self.model)
