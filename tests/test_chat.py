"""Chat do SIGMAI sem QGIS: os dois provedores contra um servidor falso local, o laço e o resumo das respostas.

O servidor falso fala o SSE da API de Mensagens da Anthropic e o do formato de
chat da OpenAI, com respostas roteirizadas, e guarda cada pedido para os
testes conferirem cabeçalhos e corpo. Nenhum teste toca a rede de verdade.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.chat.providers import (  # noqa: E402
    AnthropicProvider, OpenAICompatibleProvider, ProviderError, check_url,
)
from sigmai.chat.session import ChatSession, system_prompt  # noqa: E402
from sigmai.mcp import sigmai_mcp  # noqa: E402

CHAVE = "sk-ant-teste-0000-chave-que-nao-pode-vazar"
TOOLS = [{"name": "sigmai_status", "description": "Estado.", "inputSchema": {"type": "object", "properties": {}}},
         {"name": "sigmai_compose_map", "description": "Compõe.", "inputSchema": {"type": "object", "properties": {}}}]


def sse(*events: dict) -> bytes:
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


def anthropic_reply(text: str = "", tool: tuple | None = None, thinking: str | None = None,
                    stop: str = "end_turn", usage: tuple = (1000, 50, 0, 0)) -> bytes:
    entrada, saida, escrita, leitura = usage
    events = [{"type": "message_start", "message": {"model": "claude-opus-5-5", "usage": {
        "input_tokens": entrada, "cache_creation_input_tokens": escrita, "cache_read_input_tokens": leitura, "output_tokens": 1}}}]
    index = 0
    if thinking is not None:
        events += [{"type": "content_block_start", "index": index, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
                   {"type": "content_block_delta", "index": index, "delta": {"type": "thinking_delta", "thinking": thinking}},
                   {"type": "content_block_delta", "index": index, "delta": {"type": "signature_delta", "signature": "assinatura-xyz"}},
                   {"type": "content_block_stop", "index": index}]
        index += 1
    if text:
        events += [{"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}},
                   {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}},
                   {"type": "content_block_stop", "index": index}]
        index += 1
    if tool:
        call_id, name, arguments = tool
        raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
        events += [{"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": call_id, "name": name, "input": {}}},
                   {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": raw[: len(raw) // 2]}},
                   {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": raw[len(raw) // 2:]}},
                   {"type": "content_block_stop", "index": index}]
    events += [{"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": saida}},
               {"type": "message_stop"}]
    return sse(*events)


def openai_reply(text: str = "", tool: tuple | None = None, finish: str = "stop", usage: tuple = (900, 40, 300)) -> bytes:
    chunks = []
    if text:
        chunks.append({"choices": [{"index": 0, "delta": {"content": text}}]})
    if tool:
        call_id, name, arguments = tool
        raw = json.dumps(arguments)
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": raw[:5]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": raw[5:]}}]}}]})
    chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    prompt, completion, cached = usage
    chunks.append({"choices": [], "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "prompt_tokens_details": {"cached_tokens": cached}}})
    return b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"


class FakeProvider:
    """Servidor HTTP local com respostas roteirizadas: (status, corpo)."""

    def __init__(self, replies: list[tuple[int, bytes]]):
        self.replies = list(replies)
        self.requests: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - API do http.server
                length = int(self.headers.get("content-length", 0))
                owner.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                       "body": json.loads(self.rfile.read(length) or b"{}")})
                status, body = owner.replies.pop(0) if owner.replies else (500, b'{"error":{"message":"sem roteiro"}}')
                self.send_response(status)
                self.send_header("content-type", "text/event-stream" if status == 200 else "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Recorder:
    def __init__(self):
        self.events: list[tuple[str, object]] = []

    def __call__(self, kind, payload):
        self.events.append((kind, payload))

    def kinds(self):
        return [kind for kind, _ in self.events]


def tools_ok(name, arguments):
    if name == "sigmai_compose_map":
        return {"ok": True, "data": {"output_path": "C:/saida/mapa.pdf", "layout_name": "Mapa",
                                     "audit": {"grade": "A", "score": 95.0, "next_actions": [{"rule": "CART076"}]}}}, False
    return {"ok": True, "data": {"bridge": "online"}}, False


class AnthropicTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: getattr(self, "fake", None) and self.fake.close())

    def provider(self, replies, **kwargs):
        self.fake = FakeProvider(replies)
        return AnthropicProvider(CHAVE, transport=None, url=self.fake.url + "/v1/messages", **kwargs)

    def test_laco_de_ferramenta_ate_o_fim_da_vez(self):
        provider = self.provider([(200, anthropic_reply("Vou ver.", ("toolu_1", "sigmai_status", {}), stop="tool_use")),
                                  (200, anthropic_reply("Ponte online."))])
        calls = []
        session = ChatSession(provider, lambda n, a: (calls.append(n), tools_ok(n, a))[1], TOOLS, "sistema")
        events = Recorder()
        result = session.send("Como está o QGIS?", events, lambda: False)
        self.assertEqual(result.stop, "end_turn")
        self.assertEqual(calls, ["sigmai_status"])
        segundo = self.fake.requests[1]["body"]["messages"]
        self.assertEqual([m["role"] for m in segundo], ["user", "assistant", "user"])
        self.assertEqual(segundo[2]["content"][0]["type"], "tool_result")
        self.assertEqual(segundo[2]["content"][0]["tool_use_id"], "toolu_1")
        self.assertIn("tool_start", events.kinds())
        self.assertEqual(session.usage.input, 2000)
        self.assertGreater(session.cost, 0)

    def test_pedido_tem_cache_raciocinio_esforco_e_cabecalhos(self):
        provider = self.provider([(200, anthropic_reply("ok"))])
        ChatSession(provider, tools_ok, TOOLS, "sistema").send("oi", Recorder(), lambda: False)
        pedido = self.fake.requests[0]
        corpo, cabecalhos = pedido["body"], pedido["headers"]
        self.assertEqual(cabecalhos["x-api-key"], CHAVE)
        self.assertEqual(cabecalhos["anthropic-version"], "2026-10-21")
        self.assertIn("thinking-display-updates-2026-08-18", cabecalhos["anthropic-beta"])
        self.assertIn("server-side-fallback-2026-07-01", cabecalhos["anthropic-beta"])
        self.assertEqual(corpo["model"], "claude-opus-5-5")
        self.assertEqual(corpo["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(corpo["cache_control"], {"type": "ephemeral"})
        self.assertEqual(corpo["thinking"], {"type": "adaptive", "display": "updates"})
        self.assertEqual(corpo["output_config"], {"effort": "medium"})
        self.assertEqual(corpo["fallbacks"], "default")
        self.assertTrue(corpo["stream"])
        self.assertEqual(corpo["tools"][0]["input_schema"], TOOLS[0]["inputSchema"])
        self.assertNotIn("temperature", corpo)

    def test_haiku_vai_sem_os_recursos_que_nao_aceita(self):
        provider = self.provider([(200, anthropic_reply("ok"))], model="claude-haiku-5-5")
        ChatSession(provider, tools_ok, TOOLS, "sistema").send("oi", Recorder(), lambda: False)
        corpo, cabecalhos = self.fake.requests[0]["body"], self.fake.requests[0]["headers"]
        self.assertNotIn("fallbacks", corpo)
        self.assertEqual(corpo["thinking"], {"type": "adaptive"})
        self.assertNotIn("anthropic-beta", cabecalhos)

    def test_bloco_de_raciocinio_volta_identico(self):
        provider = self.provider([(200, anthropic_reply("", ("toolu_1", "sigmai_status", {}), thinking="Vou checar a ponte.", stop="tool_use")),
                                  (200, anthropic_reply("pronto"))])
        events = Recorder()
        ChatSession(provider, tools_ok, TOOLS, "sistema").send("oi", events, lambda: False)
        assistente = self.fake.requests[1]["body"]["messages"][1]
        self.assertEqual(assistente["content"][0], {"type": "thinking", "thinking": "Vou checar a ponte.", "signature": "assinatura-xyz"})
        self.assertIn(("note", "Vou checar a ponte."), events.events)

    def test_erros_da_api_sao_classificados_e_nao_mostram_a_chave(self):
        for status, tipo in ((401, "auth"), (429, "rate_limit"), (529, "overloaded"), (500, "server")):
            with self.subTest(status=status):
                provider = self.provider([(status, b'{"type":"error","error":{"type":"x","message":"falhou"}}')])
                events = Recorder()
                session = ChatSession(provider, tools_ok, TOOLS, "s")
                session.retry_waits = ()  # aqui interessa a classificação, não a nova tentativa
                result = session.send("oi", events, lambda: False)
                self.assertEqual(result.stop, "error")
                erro = dict(events.events)["error"]
                self.assertEqual(erro.kind, tipo)
                self.assertNotIn(CHAVE, str(erro))
                self.fake.close()

    def test_recurso_beta_recusado_segue_sem_ele(self):
        provider = self.provider([(400, b'{"error":{"type":"invalid_request_error","message":"unknown beta"}}'),
                                  (200, anthropic_reply("ok"))])
        events = Recorder()
        result = ChatSession(provider, tools_ok, TOOLS, "s").send("oi", events, lambda: False)
        self.assertEqual(result.stop, "end_turn")
        self.assertIn("notice", events.kinds())
        self.assertNotIn("fallbacks", self.fake.requests[1]["body"])
        self.assertNotIn("anthropic-beta", self.fake.requests[1]["headers"])

    def test_limite_de_chamadas_por_vez(self):
        replies = [(200, anthropic_reply("", (f"toolu_{i}", "sigmai_status", {}), stop="tool_use")) for i in range(3)]
        provider = self.provider(replies + [(200, anthropic_reply("Parei no limite."))])
        executadas = []
        session = ChatSession(provider, lambda n, a: (executadas.append(n), tools_ok(n, a))[1], TOOLS, "s", max_tool_calls=2)
        result = session.send("faça", Recorder(), lambda: False)
        self.assertEqual(len(executadas), 2)
        terceira = self.fake.requests[3]["body"]["messages"][-1]["content"][0]
        self.assertTrue(terceira["is_error"])
        self.assertIn("limite de 2 chamadas", terceira["content"][0]["text"])
        self.assertEqual(result.tool_calls, 2)

    def test_ferramenta_inexistente_e_json_cortado_sao_recusados_sem_executar(self):
        provider = self.provider([(200, anthropic_reply("", ("toolu_1", "rm_rf", {}), stop="tool_use")),
                                  (200, anthropic_reply("", ("toolu_2", "sigmai_status", '{"a": '), stop="tool_use")),
                                  (200, anthropic_reply("ok"))])
        executadas = []
        ChatSession(provider, lambda n, a: (executadas.append(n), tools_ok(n, a))[1], TOOLS, "s").send("x", Recorder(), lambda: False)
        self.assertEqual(executadas, [])
        recusas = [self.fake.requests[i]["body"]["messages"][-1]["content"][0] for i in (1, 2)]
        self.assertTrue(all(r["is_error"] for r in recusas))
        self.assertIn("inexistente", recusas[0]["content"][0]["text"])
        self.assertIn("cortada", recusas[1]["content"][0]["text"])

    def test_teto_de_custo_para_a_conversa(self):
        provider = self.provider([(200, anthropic_reply("", ("toolu_1", "sigmai_status", {}), stop="tool_use", usage=(400000, 1000, 0, 0)))])
        events = Recorder()
        result = ChatSession(provider, tools_ok, TOOLS, "s", cost_cap_usd=1.0).send("x", events, lambda: False)
        self.assertEqual(result.stop, "cap")
        self.assertEqual(len(self.fake.requests), 1)

    def test_previa_do_mapa_vai_no_resultado_da_ferramenta(self):
        provider = self.provider([(200, anthropic_reply("", ("toolu_1", "sigmai_compose_map", {}), stop="tool_use")),
                                  (200, anthropic_reply("Nota A."))])
        session = ChatSession(provider, tools_ok, TOOLS, "s", preview=lambda nome, resposta: b"\x89PNG-falso")
        session.send("mapa", Recorder(), lambda: False)
        blocos = self.fake.requests[1]["body"]["messages"][-1]["content"][0]["content"]
        self.assertEqual([b["type"] for b in blocos], ["text", "image"])
        self.assertEqual(blocos[1]["source"]["media_type"], "image/png")

    def test_parar_interrompe_antes_da_proxima_chamada(self):
        provider = self.provider([(200, anthropic_reply("", ("toolu_1", "sigmai_status", {}), stop="tool_use"))])
        parar = threading.Event()
        executadas = []

        def executar(nome, argumentos):
            executadas.append(nome)
            parar.set()
            return tools_ok(nome, argumentos)

        result = ChatSession(provider, executar, TOOLS, "s").send("x", Recorder(), parar.is_set)
        self.assertEqual(result.stop, "stopped")
        self.assertEqual(len(self.fake.requests), 1)

    def test_registro_da_conversa_sem_a_chave(self):
        provider = self.provider([(200, anthropic_reply("", ("toolu_1", "sigmai_status", {}), stop="tool_use")),
                                  (200, anthropic_reply("ok"))])
        with tempfile.TemporaryDirectory() as pasta:
            registro = Path(pasta) / "conversa.jsonl"
            ChatSession(provider, tools_ok, TOOLS, "s", log_path=registro).send("oi", Recorder(), lambda: False)
            texto = registro.read_text(encoding="utf-8")
        self.assertIn("sigmai_status", texto)
        self.assertNotIn(CHAVE, texto)

    def test_mensagem_nova_depois_de_parar_entra_na_mesma_vez_do_usuario(self):
        historico = [AnthropicProvider.user_message("a"), {"role": "assistant", "content": []},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": []}]}]
        AnthropicProvider.append_user_text(historico, "continue")
        self.assertEqual(len(historico), 3)
        self.assertEqual(historico[-1]["content"][-1], {"type": "text", "text": "continue"})


class OpenAICompatibleTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: getattr(self, "fake", None) and self.fake.close())

    def provider(self, replies, **kwargs):
        self.fake = FakeProvider(replies)
        return OpenAICompatibleProvider("sk-openai-teste", self.fake.url + "/v1", "modelo-x", **kwargs)

    def test_laco_com_argumentos_em_pedacos_e_cache(self):
        provider = self.provider([(200, openai_reply("", ("call_1", "sigmai_status", {"x": 1}), finish="tool_calls")),
                                  (200, openai_reply("Pronto."))])
        recebidos = []
        session = ChatSession(provider, lambda n, a: (recebidos.append(a), tools_ok(n, a))[1], TOOLS, "sistema")
        result = session.send("oi", Recorder(), lambda: False)
        self.assertEqual(result.stop, "end_turn")
        self.assertEqual(recebidos, [{"x": 1}])
        pedido = self.fake.requests[1]
        self.assertEqual(pedido["path"], "/v1/chat/completions")
        self.assertEqual(pedido["headers"]["authorization"], "Bearer sk-openai-teste")
        mensagens = pedido["body"]["messages"]
        self.assertEqual([m["role"] for m in mensagens], ["system", "user", "assistant", "tool"])
        self.assertEqual(mensagens[3]["tool_call_id"], "call_1")
        self.assertEqual(pedido["body"]["tools"][0]["function"]["parameters"], TOOLS[0]["inputSchema"])
        self.assertEqual((session.usage.input, session.usage.cache_read), (1200, 600))
        self.assertFalse(session.priced)

    def test_previa_vai_numa_mensagem_do_usuario(self):
        provider = self.provider([(200, openai_reply("", ("call_1", "sigmai_compose_map", {}), finish="tool_calls")),
                                  (200, openai_reply("ok"))])
        ChatSession(provider, tools_ok, TOOLS, "s", preview=lambda n, r: b"png").send("mapa", Recorder(), lambda: False)
        ultima = self.fake.requests[1]["body"]["messages"][-1]
        self.assertEqual(ultima["role"], "user")
        self.assertTrue(ultima["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_gemini_recebe_o_esquema_sem_additional_properties(self):
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"a": {"type": "object", "additionalProperties": True}}}
        ferramentas = [{"name": "x", "description": "d", "inputSchema": schema}]
        gemini = OpenAICompatibleProvider("k", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash")
        openai = OpenAICompatibleProvider("k", "https://api.openai.com/v1", "m")
        self.assertNotIn("additionalProperties", json.dumps(gemini.tool_specs(ferramentas)))
        self.assertIn("additionalProperties", json.dumps(openai.tool_specs(ferramentas)))

    def test_limite_de_uso_espera_e_tenta_de_novo(self):
        corpo_429 = b'{"error":{"code":429,"message":"quota","details":[{"retryDelay":"1s"}]}}'
        provider = self.provider([(429, corpo_429), (200, openai_reply("ok"))])
        session = ChatSession(provider, tools_ok, TOOLS, "s")
        session.retry_waits = (0.5,)
        events = Recorder()
        result = session.send("oi", events, lambda: False)
        self.assertEqual(result.stop, "end_turn")
        espera = dict(events.events)["retry"]
        self.assertEqual(espera["seconds"], 1.0)
        self.assertEqual(len(self.fake.requests), 2)

    def test_limite_de_uso_persistente_vira_erro(self):
        provider = self.provider([(429, b'{"error":{"message":"quota"}}')] * 2)
        session = ChatSession(provider, tools_ok, TOOLS, "s")
        session.retry_waits = (0.5,)
        events = Recorder()
        self.assertEqual(session.send("oi", events, lambda: False).stop, "error")
        self.assertEqual(dict(events.events)["error"].kind, "rate_limit")

    def test_gemini_sobrecarregado_503_espera_e_tenta_de_novo(self):
        corpo = b'[{"error":{"code":503,"message":"This model is currently experiencing high demand.","status":"UNAVAILABLE"}}]'
        provider = self.provider([(503, corpo), (200, openai_reply("ok"))])
        session = ChatSession(provider, tools_ok, TOOLS, "s")
        session.retry_waits = (0.5,)
        events = Recorder()
        self.assertEqual(session.send("oi", events, lambda: False).stop, "end_turn")
        self.assertEqual(dict(events.events)["retry"]["kind"], "overloaded")

    def test_gemini_sobrecarregado_segue_com_outro_modelo_gratuito(self):
        corpo = b'[{"error":{"code":503,"message":"high demand","status":"UNAVAILABLE"}}]'
        provider = self.provider([(503, corpo), (503, corpo), (200, openai_reply("ok"))])
        provider.fallback_models = ["gemini-3.6-flash"]
        session = ChatSession(provider, tools_ok, TOOLS, "s")
        session.retry_waits = (0.5,)
        events = Recorder()
        self.assertEqual(session.send("oi", events, lambda: False).stop, "end_turn")
        self.assertEqual(dict(events.events)["fallback"], {"from": "modelo-x", "to": "gemini-3.6-flash"})
        self.assertEqual(self.fake.requests[2]["body"]["model"], "gemini-3.6-flash")

    def test_lista_de_modelos_gratuitos_so_no_gemini(self):
        gemini = OpenAICompatibleProvider("k", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash")
        self.assertEqual(gemini.fallback_models, ["gemini-3.6-flash", "gemini-3.5-flash-lite"])
        self.assertEqual(OpenAICompatibleProvider("k", "https://api.openai.com/v1", "m").fallback_models, [])

    def test_assinatura_do_raciocinio_do_gemini_volta_na_chamada(self):
        chunks = [{"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                   "function": {"name": "sigmai_status", "arguments": "{}"},
                   "extra_content": {"google": {"thought_signature": "assinatura-gemini"}}}]}}]},
                  {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}]
        primeira = b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"
        provider = self.provider([(200, primeira), (200, openai_reply("ok"))])
        ChatSession(provider, tools_ok, TOOLS, "s").send("oi", Recorder(), lambda: False)
        chamada = self.fake.requests[1]["body"]["messages"][2]["tool_calls"][0]
        self.assertEqual(chamada["extra_content"], {"google": {"thought_signature": "assinatura-gemini"}})
        self.assertEqual(chamada["function"]["name"], "sigmai_status")

    def test_so_https_ou_maquina_local(self):
        check_url("https://api.openai.com/v1")
        check_url("http://localhost:11434/v1")
        with self.assertRaises(ProviderError):
            OpenAICompatibleProvider("k", "http://exemplo.com/v1", "m")


class ResumoDasRespostasTests(unittest.TestCase):
    """Laudo e receita resumidos para o modelo, por padrão; detail='full' devolve tudo."""

    LAUDO = {"score": 95.0, "grade": "A", "label": "Mapa publicável", "counts": {"errors": 0, "warnings": 1},
             "blocking_issues": [], "next_actions": [],
             "results": [{"id": "CART001", "status": "pass", "severity": "error", "detail_pt": "ok"},
                         {"id": "CART076", "status": "fail", "severity": "warning", "detail_pt": "99% escondidos",
                          "fix_pt": "dense_points='sites'", "evidence": {"grade": [1] * 500}}],
             "observation": {"items": ["muita coisa"] * 200}}

    def test_compose_map_devolve_o_laudo_resumido_e_nao_repassa_detail(self):
        resposta = {"ok": True, "data": {"audit": json.loads(json.dumps(self.LAUDO)), "output_path": "x.pdf"}}
        with mock.patch.object(sigmai_mcp, "bridge_call", return_value=resposta) as ponte:
            payload, erro = sigmai_mcp.run_tool("sigmai_compose_map", {"layer_ids": ["a"], "map_language": "en"})
        self.assertFalse(erro)
        self.assertNotIn("detail", ponte.call_args.args[1])
        laudo = payload["data"]["audit"]
        # Só as reprovadas, com as mesmas chaves do laudo completo e sem a evidência.
        self.assertEqual(laudo["results"], [{"id": "CART076", "severity": "warning", "status": "fail", "title_pt": None}])
        self.assertNotIn("observation", laudo)
        self.assertEqual(laudo["next_actions"], [{"rule": "CART076", "severity": "warning", "problem": "99% escondidos",
                                                  "fix": "dense_points='sites'"}])
        self.assertEqual(laudo["grade"], "A")

    def test_detail_full_devolve_tudo(self):
        resposta = {"ok": True, "data": {"audit": json.loads(json.dumps(self.LAUDO))}}
        with mock.patch.object(sigmai_mcp, "bridge_call", return_value=resposta) as ponte:
            payload, _ = sigmai_mcp.run_tool("sigmai_compose_map", {"layer_ids": ["a"], "detail": "full"})
        self.assertNotIn("detail", ponte.call_args.args[1])
        self.assertEqual(len(payload["data"]["audit"]["results"]), 2)

    def test_receita_sem_o_qml(self):
        resposta = {"ok": True, "data": {"recipe": {"layers": [{"name": "Parque", "style_qml": "<qgis>" + "x" * 5000}]}}}
        with mock.patch.object(sigmai_mcp, "bridge_call", return_value=resposta):
            payload, _ = sigmai_mcp.run_tool("sigmai_map_recipe", {"layout_name": "L"})
        self.assertTrue(payload["data"]["recipe"]["layers"][0]["style_qml"].startswith("(estilo QML guardado"))

    def test_so_as_ferramentas_de_laudo_e_receita_aceitam_detail(self):
        for nome, ferramenta in sigmai_mcp.TOOLS_BY_NAME.items():
            with self.subTest(nome=nome):
                self.assertEqual("detail" in ferramenta["inputSchema"]["properties"], nome in sigmai_mcp.DETAIL_TOOLS)

    def test_prompt_do_chat_leva_as_instrucoes_do_servidor(self):
        texto = system_prompt(sigmai_mcp.INSTRUCTIONS)
        self.assertIn("sigmai_briefing", texto)
        self.assertIn("pergunte e espere", texto)
        self.assertIn("ninguém responde", system_prompt("x", scripted=True))


if __name__ == "__main__":
    unittest.main()
