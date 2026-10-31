"""A página do chat no painel do SIGMAI, sem tela: uma conversa com o provedor falso pela rede do QGIS.

Roda num subprocesso com a plataforma offscreen: os outros testes criam o
QgsApplication sem interface, e uma janela precisa dele com interface. Foi
assim que apareceu o sinal chamado "event", que escondia QObject.event() e
derrubava o QGIS na primeira mensagem.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = textwrap.dedent(r"""
    import json, os, sys, tempfile, threading, traceback
    sys.path.insert(0, sys.argv[1]); sys.path.insert(0, os.path.join(sys.argv[1], "tests"))
    erros = []
    sys.excepthook = lambda t, v, tb: erros.append("".join(traceback.format_exception(t, v, tb)))
    from qgis.core import QgsApplication
    app = QgsApplication([], True); app.initQgis()
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from test_chat import FakeProvider, anthropic_reply
    fake = FakeProvider([(200, anthropic_reply("", ("toolu_1", "sigmai_status", {}), stop="tool_use")),
                         (200, anthropic_reply("Tudo certo."))])
    os.environ["SIGMAI_CHAT_TEST_URL"] = fake.url + "/v1/messages"
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-teste-widget"
    class Ponte: running = True; host = "127.0.0.1"; port = 9;
    class Controle:
        language = "pt-BR"; server = Ponte(); token = "t"; ajustes = {"chat_privacy_ok": True}
        def settings_get(self, k, d=None): return self.ajustes.get(k, d)
        def settings_set(self, k, v): self.ajustes[k] = v
        def start_bridge(self): pass
        def log_dir(self): return tempfile.mkdtemp()
    from sigmai.ui.chat_view import ChatView
    janela = ChatView(Controle())
    enviou = janela._send("Como está o QGIS?")
    laco = QEventLoop(); QTimer.singleShot(8000, laco.quit)
    janela._worker.finished.connect(lambda r: QTimer.singleShot(300, laco.quit))
    laco.exec()
    resultado = {"enviou": enviou, "entradas": janela.entries, "pedidos": len(fake.requests), "erros": erros,
                 "status": janela.cost_label.text(), "configuracao_aberta": janela.setup_card.isVisibleTo(janela)}
    janela.shutdown(); fake.close()
    print("RESULTADO " + json.dumps(resultado, ensure_ascii=False))
""")


@unittest.skipUnless(importlib.util.find_spec("qgis") is not None, "precisa do QGIS")
class PaginaDoChat(unittest.TestCase):
    def test_conversa_com_uma_ferramenta_pela_rede_do_qgis(self):
        with tempfile.TemporaryDirectory() as pasta:
            script = Path(pasta) / "janela.py"
            script.write_text(SCRIPT, encoding="utf-8")
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
            feito = subprocess.run([sys.executable, str(script), str(ROOT)], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", env=env, timeout=120)
        linha = next((l for l in feito.stdout.splitlines() if l.startswith("RESULTADO ")), "")
        self.assertTrue(linha, feito.stdout[-2000:] + feito.stderr[-2000:])
        resultado = json.loads(linha[len("RESULTADO "):])
        self.assertEqual(resultado["erros"], [])
        self.assertTrue(resultado["enviou"])
        self.assertEqual(resultado["pedidos"], 2)
        tipos = [entrada[0] for entrada in resultado["entradas"]]
        self.assertIn("tool", tipos)
        self.assertEqual(resultado["entradas"][-1], ["assistant", "Tudo certo."])
        # A ponte do teste não existe: a ferramenta volta com erro, e a conversa segue.
        self.assertTrue(any(e[0] == "tool" and "✗" in e[1] for e in resultado["entradas"]))
        self.assertIn("US$", resultado["status"])
        # Com chave, a página abre na conversa, e não no cartão de configuração.
        self.assertFalse(resultado["configuracao_aberta"])


if __name__ == "__main__":
    unittest.main()
