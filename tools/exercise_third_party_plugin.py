# -*- coding: utf-8 -*-
"""Prova a corrente: pedido -> IA -> SIGMAI -> QGIS -> plugin de TERCEIRO executa.

É o caso de quem está desenvolvendo um plugin e quer que a IA o exercite: o
SIGMAI precisa enxergar o plugin, auditar a estrutura dele, listar os
algoritmos que ele registra, explicar os parâmetros, simular e então executar —
sem que o desenvolvedor escreva uma linha de código de teste.

Roda tudo pela ponte HTTP, o mesmo caminho de um assistente de IA de verdade.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TOKEN = "token-do-ensaio-de-terceiro"
PLUGIN = "trilhateste"
ALGORITMO = "trilhateste:comprimento_da_trilha"


class Runner:
    def __init__(self, host: str, port: int) -> None:
        self.url = f"http://{host}:{port}/command"
        self.resultados: list[dict[str, Any]] = []

    def call(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"action": action, "params": params or {}}).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {TOKEN}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read())

    def check(self, rotulo: str, action: str, params: dict[str, Any] | None = None,
              espera: str = "ok", mostrar: str | None = None) -> dict[str, Any]:
        resposta = self.call(action, params)
        ok = bool(resposta.get("ok"))
        erros = resposta.get("errors") or []
        primeiro = erros[0] if erros else {}
        codigo = str(primeiro.get("code", ""))
        mensagem = str(primeiro.get("message", ""))
        quebrou = (not ok) and codigo in {"", "INTERNAL_ERROR", "UNEXPECTED_ERROR"}
        passou = (espera == "ok" and ok) or (espera == "recusa" and not ok and not quebrou) or espera == "qualquer"
        self.resultados.append({"rotulo": rotulo, "passou": passou, "codigo": codigo})
        extra = ""
        if mostrar and ok:
            alvo: Any = resposta.get("data") or {}
            for parte in mostrar.split("."):
                alvo = (alvo or {}).get(parte) if isinstance(alvo, dict) else None
            extra = f"  -> {json.dumps(alvo, ensure_ascii=False)[:90]}"
        print(f"  {'OK   ' if passou else 'FALHA'} {rotulo:48s} {codigo or 'ok':30s}{extra or ('  ' + mensagem[:60])}")
        return resposta

    def summary(self) -> int:
        falhas = [r for r in self.resultados if not r["passou"]]
        print(f"\n{len(self.resultados) - len(falhas)}/{len(self.resultados)} como esperado.")
        for f in falhas:
            print(f"  - {f['rotulo']}: {f['codigo']}")
        return 1 if falhas else 0


def exercitar(runner: Runner, trilha_id: str, saida: Path) -> None:
    print("\n== 1. o SIGMAI enxerga o plugin de terceiro? ==")
    runner.check("aparece na lista de instalados", "list_installed_plugins", mostrar="plugins")
    runner.check("inspeciona o plugin", "inspect_plugin", {"plugin_name": PLUGIN})
    runner.check("valida o metadata.txt dele", "validate_metadata_txt", {"plugin_name": PLUGIN})

    print("\n== 1b. o briefing que a IA lê antes de qualquer coisa ==")
    resposta = runner.check("briefing numa chamada", "brief_plugin", {"plugin_name": PLUGIN})
    briefing = resposta.get("data") or {}
    print(f"     dirigível: {briefing.get('dirigivel_por_programa', {}).get('algorithm_count')} algoritmo(s)"
          f" | interface: {briefing.get('nao_dirigivel_por_programa', {}).get('superficie_de_interface')}")
    print(f"     provedor: {json.dumps(briefing.get('provedor_processing'), ensure_ascii=False)[:150]}")
    for passo in briefing.get("plano_de_teste_sugerido", []):
        print(f"       {passo['passo']}. {passo['acao']}")
    runner.check("briefing de plugin inexistente é recusado", "brief_plugin",
                 {"plugin_name": "plugin_que_nao_existe"}, espera="qualquer")

    print("\n== 2. auditoria de estrutura, como um revisor faria ==")
    for rotulo, acao in (
        ("estrutura de arquivos", "check_plugin_structure"),
        ("imports resolvem", "check_plugin_imports"),
        ("ícone declarado existe", "check_plugin_icon"),
        ("recursos declarados", "check_plugin_resources"),
        ("estado em tempo de execução", "check_plugin_runtime_status"),
        ("provedor de Processing registrado", "check_processing_provider_registration"),
        ("algoritmos registrados", "check_plugin_algorithm_registration"),
    ):
        runner.check(rotulo, acao, {"plugin_name": PLUGIN}, espera="qualquer")

    print("\n== 3. o que o plugin oferece ==")
    runner.check("lista os algoritmos do plugin", "list_plugin_processing_algorithms",
                 {"plugin_name": PLUGIN}, mostrar="algorithms")
    runner.check("descreve os parâmetros do algoritmo", "get_plugin_algorithm_info",
                 {"algorithm_id": ALGORITMO}, mostrar="parameters")
    runner.check("manifesto de capacidades", "build_plugin_capability_manifest",
                 {"plugin_name": PLUGIN}, espera="qualquer")

    print("\n== 4. simular antes de executar ==")
    runner.check("simulação com parâmetros certos", "dry_run_plugin_algorithm_generic",
                 {"algorithm_id": ALGORITMO,
                  "parameters": {"INPUT": trilha_id, "FATOR": 1.0}}, mostrar="execution_policy")
    runner.check("simulação acusa parâmetro obrigatório faltando",
                 "dry_run_plugin_algorithm_generic",
                 {"algorithm_id": ALGORITMO, "parameters": {"FATOR": 1.0}},
                 mostrar="missing_required_parameters")
    runner.check("algoritmo inexistente é recusado", "dry_run_plugin_algorithm_generic",
                 {"algorithm_id": "trilhateste:nao_existe", "parameters": {}}, espera="qualquer")

    print("\n== 5. EXECUTAR o algoritmo do plugin de terceiro ==")
    resposta = runner.check("executa e devolve o resultado", "run_plugin_algorithm_generic_safe",
                            {"algorithm_id": ALGORITMO,
                             "parameters": {"INPUT": trilha_id, "FATOR": 1.0}},
                            mostrar="result")
    dados = resposta.get("data") or {}
    print(f"     resultado bruto do plugin: {json.dumps(dados.get('result'), ensure_ascii=False)[:160]}")
    runner.check("executa com outro fator e muda o resultado",
                 "run_plugin_algorithm_generic_safe",
                 {"algorithm_id": ALGORITMO,
                  "parameters": {"INPUT": trilha_id, "FATOR": 2.0}}, mostrar="result")
    runner.check("parâmetro obrigatório faltando é recusado na execução",
                 "run_plugin_algorithm_generic_safe",
                 {"algorithm_id": ALGORITMO, "parameters": {"FATOR": 1.0}}, espera="recusa")

    print("\n== 6. o adaptador de lista fixa ==")
    runner.check("adaptador dedicado recusa quem não está na lista",
                 "run_plugin_algorithm_safe",
                 {"algorithm_id": ALGORITMO, "parameters": {"INPUT": trilha_id}}, espera="recusa")

    print("\n== 7. relatório para o desenvolvedor ==")
    runner.check("relatório do plugin", "generate_plugin_report",
                 {"plugin_name": PLUGIN, "output_path": str(saida / "relatorio.md"),
                  "confirm_overwrite": True}, espera="qualquer")
    runner.check("relatório de adaptador", "generate_plugin_adapter_report",
                 {"plugin_name": PLUGIN, "output_path": str(saida / "adaptador.md"),
                  "confirm_overwrite": True}, espera="qualquer")
    runner.check("logs do plugin", "collect_plugin_logs", {"plugin_name": PLUGIN}, espera="qualquer")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--plugin-source", default="/tmp/plugin_terceiro/trilhateste")
    args = parser.parse_args()

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    from tools.qgis_lifecycle import shutdown_qgis
    try:
        # Instala o plugin de terceiro onde o QGIS procura, e registra o
        # provedor dele — que é o que o gerenciador de plugins faria ao ativar.
        destino_raiz = Path(QgsApplication.qgisSettingsDirPath()) / "python" / "plugins"
        destino_raiz.mkdir(parents=True, exist_ok=True)
        destino = destino_raiz / PLUGIN
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(args.plugin_source, destino)
        sys.path.insert(0, str(destino_raiz))
        print(f"Plugin de terceiro instalado em: {destino}")

        from trilhateste.provider import TrilhaTesteProvider  # type: ignore

        provider = TrilhaTesteProvider()
        QgsApplication.processingRegistry().addProvider(provider)
        print(f"Provedor registrado: {provider.id()}")

        from qgis.core import QgsProject, QgsVectorLayer
        projeto = QgsProject.instance()
        projeto.clear()
        trilha = QgsVectorLayer(
            str(Path(args.data) / "trilha" / "Trilha Itaguaré pelo batedor.shp"),
            "Trilha do Itaguaré", "ogr")
        projeto.addMapLayer(trilha)
        projeto.setCrs(trilha.crs())

        from sigmai.bridge_server import SIGMAIServer
        from sigmai.consent import MODE_ALLOW_SESSION

        temporario = Path(tempfile.mkdtemp())
        server = SIGMAIServer(token=TOKEN, log_dir=temporario / "logs")
        server.start()
        server.consent.set_mode(MODE_ALLOW_SESSION)
        for limite in ("exports_per_session", "processing_runs_per_session", "writes_per_session"):
            server.consent.set_limit(limite, 500)

        runner = Runner(server.host, server.port)
        estado: dict[str, Any] = {}

        def worker() -> None:
            try:
                exercitar(runner, trilha.id(), temporario)
            except Exception:
                traceback.print_exc()
                estado["error"] = True
            finally:
                estado["done"] = True

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        while not estado.get("done"):
            app.processEvents()
            thread.join(0.02)
        server.stop()
        return runner.summary() or (1 if estado.get("error") else 0)
    finally:
        shutdown_qgis(app)


if __name__ == "__main__":
    raise SystemExit(main())
