"""O laço da conversa: pedido ao modelo, chamadas às ferramentas do SIGMAI, de novo, até o fim da vez.

Sem Qt e sem rede própria: o provedor e o executor de ferramentas chegam
prontos. No plugin, o executor é :func:`sigmai.mcp.sigmai_mcp.run_tool`, o
mesmo que atende um cliente MCP externo; nos testes, um executor falso.
"""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .pricing import cost_usd
from .providers import ProviderError, ToolCall, ToolResult, Usage

RunTool = Callable[[str, dict[str, Any]], tuple[Any, bool]]
#: (nome da ferramenta, resposta) -> PNG da prévia, ou None
Preview = Callable[[str, Any], "bytes | None"]

CHAT_PREAMBLE = """Você está no painel de chat do SIGMAI, dentro do QGIS do usuário. Suas únicas
ferramentas são as do SIGMAI: você não lê arquivos, não roda código e não
acessa a internet. A pessoa está na conversa: quando as instruções abaixo
mandarem perguntar algo ao usuário (autoria, fontes, onde vão título e
créditos), pergunte e espere a resposta. Responda na língua da pessoa, curto:
o que fez, a nota da auditoria e onde ficou cada arquivo."""

SCRIPTED_PREAMBLE = """Você está no painel de chat do SIGMAI, dentro do QGIS do usuário. Suas únicas
ferramentas são as do SIGMAI: você não lê arquivos, não roda código e não
acessa a internet. Nesta sessão ninguém responde perguntas: quando as
instruções abaixo mandarem perguntar algo ao usuário, faça a escolha razoável
para o pedido e diga no fim o que escolheu. Responda na língua do pedido."""

PREVIEW_NOTE = """Depois de cada mapa exportado você recebe uma prévia dele em baixa resolução,
para conferir à vista. A auditoria continua sendo a conferência principal."""

PREVIEW_TOOLS = ("sigmai_compose_map", "sigmai_recompose_from_recipe", "sigmai_campaign_map")


def system_prompt(instructions: str, scripted: bool = False, preview: bool = True) -> str:
    parts = [SCRIPTED_PREAMBLE if scripted else CHAT_PREAMBLE]
    if preview:
        parts.append(PREVIEW_NOTE)
    parts.append(instructions)
    return "\n\n".join(parts)


@dataclass
class TurnResult:
    stop: str
    tool_calls: int
    error: str = ""


class ChatSession:
    def __init__(self, provider: Any, run_tool: RunTool, tools: list[dict[str, Any]], system: str, *,
                 max_tool_calls: int = 60, cost_cap_usd: float | None = 5.0, preview: Preview | None = None,
                 log_path: Path | None = None):
        self.provider = provider
        self.run_tool = run_tool
        self.tools = tools
        self.tool_names = {tool["name"] for tool in tools}
        self.system = system
        self.max_tool_calls = max_tool_calls
        self.cost_cap_usd = cost_cap_usd
        self.preview = preview
        self.log_path = log_path
        self.history: list[Any] = []
        self.usage = Usage()
        self.cost = 0.0
        self.priced = True
        self.over_cap_allowed = False
        self._turn_calls = 0
        self.retry_waits = (20.0, 40.0, 60.0)

    # -- contas -------------------------------------------------------------
    def _account(self, model: str, usage: Usage) -> None:
        self.usage.add(usage)
        cost = cost_usd(model, usage)
        if cost is None:
            cost = cost_usd(getattr(self.provider, "model", ""), usage)
        if cost is None:
            self.priced = False
        else:
            self.cost += cost

    def over_cap(self) -> bool:
        return bool(self.cost_cap_usd) and self.priced and self.cost >= float(self.cost_cap_usd) and not self.over_cap_allowed

    # -- registro (sem a chave: ela não passa por aqui) ----------------------
    def _log(self, kind: str, **fields: Any) -> None:
        if not self.log_path:
            return
        entry = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind, **fields}
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    # -- uma vez da conversa ---------------------------------------------------
    def send(self, text: str, on_event: Callable[[str, Any], None], should_stop: Callable[[], bool]) -> TurnResult:
        self.provider.append_user_text(self.history, text)
        self._log("user", text=text)
        self._turn_calls = 0
        retried_cut = False
        while True:
            if should_stop():
                on_event("stopped", None)
                return TurnResult("stopped", self._turn_calls)
            if self.over_cap():
                on_event("cap", self.cost)
                return TurnResult("cap", self._turn_calls)
            try:
                reply = self._complete_with_retry(on_event, should_stop)
            except ProviderError as exc:
                self._log("error", error=exc.kind, message=str(exc))
                on_event("error", exc)
                return TurnResult("error", self._turn_calls, str(exc))
            self.history.append(reply.message)
            self._account(reply.model, reply.usage)
            self._log("assistant", model=reply.model, stop=reply.stop, text=reply.text,
                      tool_calls=[{"name": c.name, "arguments": c.arguments} for c in reply.tool_calls],
                      usage=vars(reply.usage))
            on_event("usage", {"usage": self.usage, "cost": self.cost if self.priced else None, "model": reply.model})
            if reply.stop == "refusal":
                on_event("refusal", reply.text)
                return TurnResult("refusal", self._turn_calls)
            if not reply.tool_calls:
                on_event("done", reply.stop)
                return TurnResult(reply.stop, self._turn_calls)
            cut = reply.stop == "max_tokens"
            # Todo pedido de ferramenta recebe resposta, mesmo recusada: a API
            # não aceita um tool_use sem o tool_result correspondente.
            results = [self._execute(call, cut, on_event, should_stop) for call in reply.tool_calls]
            self.history.extend(self.provider.tool_results_messages(results))
            if cut:
                if retried_cut:
                    on_event("done", "max_tokens")
                    return TurnResult("max_tokens", self._turn_calls)
                retried_cut = True

    def _complete_with_retry(self, on_event: Callable[[str, Any], None], should_stop: Callable[[], bool]) -> Any:
        """Pede ao provedor; no limite de uso ou na sobrecarga, espera e tenta de novo.

        Cotas gratuitas limitam pedidos por minuto, e uma conversa que faz um
        mapa manda dezenas: parar no primeiro 429 tornava o chat inútil nelas.
        """
        attempt = 0
        while True:
            try:
                return self.provider.complete(self.system, self.tools, self.history, on_event, should_stop)
            except ProviderError as exc:
                if exc.kind not in ("rate_limit", "overloaded"):
                    raise
                if attempt >= len(self.retry_waits):
                    # Ainda sobrecarregado: se o provedor tem outro modelo
                    # gratuito equivalente (Gemini), segue com ele e avisa.
                    fallbacks = getattr(self.provider, "fallback_models", None)
                    if exc.kind != "overloaded" or not fallbacks:
                        raise
                    old, self.provider.model = self.provider.model, fallbacks.pop(0)
                    on_event("fallback", {"from": old, "to": self.provider.model})
                    self._log("fallback", source=old, target=self.provider.model)
                    attempt = 0
                    continue
                wait = min(90, exc.retry_after or self.retry_waits[attempt])
                attempt += 1
                on_event("retry", {"seconds": wait, "kind": exc.kind})
                self._log("retry", error=exc.kind, seconds=wait)
                waited = 0.0
                while waited < wait:
                    if should_stop():
                        raise ProviderError("cancelled", "Interrompido.") from exc
                    time.sleep(0.5)
                    waited += 0.5

    def _execute(self, call: ToolCall, cut: bool, on_event: Callable[[str, Any], None],
                 should_stop: Callable[[], bool]) -> ToolResult:
        def refused(message: str) -> ToolResult:
            on_event("tool_end", {"name": call.name, "error": True, "summary": message})
            return ToolResult(call.id, call.name, json.dumps({"ok": False, "message": message}, ensure_ascii=False), True)

        if should_stop():
            return refused("Interrompido pelo usuário antes desta chamada.")
        if cut or not call.valid:
            return refused("A chamada chegou cortada (limite de tokens da resposta); refaça-a.")
        if call.name not in self.tool_names:
            return refused(f"Ferramenta inexistente: {call.name}. Use só as ferramentas do SIGMAI listadas.")
        if self._turn_calls >= self.max_tool_calls:
            return refused(f"Atingido o limite de {self.max_tool_calls} chamadas nesta vez; diga ao usuário onde parou e pergunte se continua.")
        on_event("tool_start", {"name": call.name, "arguments": call.arguments})
        self._turn_calls += 1
        payload, is_error = self.run_tool(call.name, call.arguments)
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        summary = tool_summary(payload, is_error)
        on_event("tool_end", {"name": call.name, "error": is_error, "summary": summary})
        self._log("tool", name=call.name, arguments=call.arguments, error=is_error, result=text)
        image = None
        if self.preview and not is_error and call.name in PREVIEW_TOOLS and getattr(self.provider, "sends_images", False):
            image = self.preview(call.name, payload)
            if image:
                on_event("preview", {"name": call.name, "bytes": len(image)})
        return ToolResult(call.id, call.name, text, is_error, image)


def tool_summary(payload: Any, is_error: bool) -> str:
    """Uma linha para a conversa: nota da auditoria, caminho gravado ou o erro."""
    if not isinstance(payload, dict):
        return ""
    if is_error:
        errors = payload.get("errors") or []
        first = errors[0] if errors and isinstance(errors[0], dict) else {}
        return str(first.get("message") or payload.get("message") or payload.get("error") or "erro")[:160]
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    audit = data.get("audit") if isinstance(data, dict) else None
    parts = []
    if isinstance(audit, dict) and audit.get("grade"):
        failed = [str(action.get("rule")) for action in audit.get("next_actions") or [] if isinstance(action, dict)]
        parts.append(f"nota {audit.get('grade')} ({audit.get('score')})" + (f", {', '.join(failed)}" if failed else ""))
    output = data.get("output_path") if isinstance(data, dict) else None
    if output:
        parts.append(str(output))
    return " · ".join(parts)
