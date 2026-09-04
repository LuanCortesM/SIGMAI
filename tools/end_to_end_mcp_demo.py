#!/usr/bin/env python3
"""Produz um mapa complexo pelo caminho completo, como um assistente de IA faria.

Nada aqui chama o PyQGIS diretamente. Tudo passa por onde passaria de verdade:

    cliente MCP  →  servidor MCP (subprocesso, JSON-RPC 2.0 por stdio)
                 →  ponte HTTP local (token, validação, consentimento, fila)
                 →  manipuladores de comando  →  QGIS

Serve como demonstração e como teste de integração do encadeamento inteiro.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOKEN = "demo-mcp-" + "z" * 32


class MCPClient:
    """Cliente MCP mínimo, do tipo que o Claude Desktop implementa."""

    def __init__(self, server: Path, env: dict[str, str]):
        self.process = subprocess.Popen(
            [sys.executable, str(server)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, env=env,
        )
        self.counter = 0

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        payload = {"jsonrpc": "2.0", "id": self.counter, "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def initialize(self) -> dict[str, Any]:
        result = self._request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "SIGMAI demo client", "version": "1.0.0"},
        })
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.process.stdin.flush()
        return result["result"]

    def list_tools(self) -> list[dict[str, Any]]:
        return self._request("tools/list")["result"]["tools"]

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> tuple[bool, Any]:
        response = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        result = response.get("result")
        if result is None:
            return False, response.get("error")
        payload = result.get("structuredContent")
        if payload is None:
            payload = json.loads(result["content"][0]["text"])
        return not result.get("isError", False), payload

    def close(self) -> None:
        try:
            self.process.stdin.close()
            self.process.wait(timeout=10)
        except Exception:
            self.process.kill()


def unwrap(label: str, ok: bool, payload: Any) -> Any:
    """Desembrulha a resposta da ponte, que vem no envelope padrão do SIGMAI."""
    if not ok:
        raise SystemExit(f"[{label}] falhou: {json.dumps(payload, ensure_ascii=False)[:400]}")
    if isinstance(payload, dict) and "ok" in payload:
        if not payload["ok"]:
            errors = payload.get("errors") or [{}]
            raise SystemExit(f"[{label}] recusado: {errors[0].get('code')} {errors[0].get('message', '')[:300]}")
        return payload.get("data")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", default=str(Path(tempfile.mkdtemp()) / "mapa_complexo.png"))
    args = parser.parse_args()

    from qgis.core import QgsApplication, QgsProject, QgsVectorLayer

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()

    from sigmai.bridge_server import SIGMAIServer
    from sigmai.consent import MODE_ALLOW_SESSION

    data = Path(args.data)
    project = QgsProject.instance()
    project.clear()
    sources = {
        "Municípios do Piauí": data / "PI_Municipios_2024.shp",
        "Limite estadual": data / "PI_UF_2024.shp",
        "Parque Estadual das Carnaúbas": data / "PE Carnaubas.kml",
    }
    loaded = {}
    for name, path in sources.items():
        layer = QgsVectorLayer(str(path), name, "ogr")
        if not layer.isValid():
            raise SystemExit(f"camada inválida: {path}")
        loaded[name] = layer
    project.addMapLayers(list(loaded.values()))
    project.setCrs(loaded["Limite estadual"].crs())

    server = SIGMAIServer(token=TOKEN, log_dir=Path(tempfile.mkdtemp()) / "logs")
    server.start()
    # A fila do QTimer permanece ativa de propósito: é ela que leva os comandos
    # para a thread principal do Qt. Renderizar layout fora dela produz imagem
    # vazia em silêncio, então a demonstração precisa exercitar o caminho real.
    server.consent.set_mode(MODE_ALLOW_SESSION)
    for limit in ("exports_per_session", "processing_runs_per_session", "writes_per_session"):
        server.consent.set_limit(limit, 500)

    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        "SIGMAI_HOST": server.host,
        "SIGMAI_PORT": str(server.port),
        "SIGMAI_TOKEN": TOKEN,
    }
    client = MCPClient(ROOT / "sigmai" / "mcp" / "sigmai_mcp.py", env)

    # A conversa MCP roda numa thread de trabalho enquanto a thread principal
    # gira o laço de eventos do Qt — exatamente o arranjo do QGIS, onde a
    # interface é a thread principal e o servidor HTTP são threads de trabalho.
    import threading

    outcome: dict[str, Any] = {}

    def conversation() -> None:
        try:
            outcome["code"] = converse(client, ids_holder, args)
        except SystemExit as exc:
            outcome["error"] = str(exc)
            outcome["code"] = 1
        except Exception as exc:  # noqa: BLE001
            import traceback
            outcome["error"] = traceback.format_exc()
            outcome["code"] = 1
        finally:
            outcome["done"] = True

    ids_holder: dict[str, Any] = {}
    worker = threading.Thread(target=conversation, daemon=True)
    try:
        worker.start()
        while not outcome.get("done"):
            app.processEvents()
            worker.join(0.02)
        if outcome.get("error"):
            print(outcome["error"])
        return int(outcome.get("code", 1))
    finally:
        client.close()
        server.stop()
        app.exitQgis()


def converse(client: "MCPClient", ids_holder: dict[str, Any], args: Any) -> int:
    if True:
        print("== 1. handshake MCP ==")
        info = client.initialize()
        print(f"   servidor: {info['serverInfo']['name']} {info['serverInfo']['version']} "
              f"| protocolo {info['protocolVersion']}")
        tools = client.list_tools()
        print(f"   {len(tools)} ferramentas publicadas")

        print("\n== 2. o assistente descobre o estado ==")
        status = unwrap("status", *client.call("sigmai_status"))
        print(f"   QGIS {status['qgis_version']} | modo de acesso: {status['consent']['mode_label']}")

        overview = unwrap("panorama", *client.call("sigmai_project_overview"))
        print(f"   projeto em {overview['project_crs']} ({overview['project_crs_description']}), "
              f"{overview['layer_count']} camadas:")
        ids = {}
        for layer in overview["layers"]:
            ids[layer["name"]] = layer["id"]
            print(f"     - {layer['name']:32} {layer['geometry']:8} {layer.get('feature_count', '?'):>5} feições")

        rulebook = unwrap("regulamento", *client.call("sigmai_cartographic_rulebook"))
        print(f"   regulamento: {rulebook['rule_count']} regras em {len(rulebook['categories'])} categorias")

        print("\n== 3. análise: entorno de 10 km do parque ==")
        buffer_path = str(Path(args.out).parent / "entorno_parque.gpkg")
        unwrap("buffer", *client.call("sigmai_run_command", {
            "action": "buffer",
            "params": {
                "layer_id": ids["Parque Estadual das Carnaúbas"],
                "distance": 0.09,  # ~10 km em graus na latitude do Piauí
                "output_path": buffer_path,
                "confirm_overwrite": True,
            },
        }))
        print("   camada de entorno criada")

        print("\n== 4. simbologia temática ==")
        unwrap("graduado", *client.call("sigmai_run_command", {
            "action": "apply_graduated_style",
            "params": {"layer_id": ids["Municípios do Piauí"], "field_name": "AREA_KM2", "classes": 5},
        }))
        print("   municípios graduados por área")
        unwrap("contorno", *client.call("sigmai_run_command", {
            "action": "apply_single_symbol",
            "params": {"layer_id": ids["Limite estadual"], "fill_color": "#00000000",
                       "stroke_color": "#16232B", "stroke_width": 0.8, "outline_only": True},
        }))
        unwrap("destaque", *client.call("sigmai_run_command", {
            "action": "apply_single_symbol",
            "params": {"layer_id": ids["Parque Estadual das Carnaúbas"], "fill_color": "#009E73",
                       "stroke_color": "#00402E", "stroke_width": 0.6},
        }))
        print("   limite estadual em contorno; parque destacado")

        print("\n== 5. o assistente planeja antes de executar ==")
        after = unwrap("panorama 2", *client.call("sigmai_project_overview"))
        order = ["Municípios do Piauí", "Limite estadual", "Parque Estadual das Carnaúbas"]
        layer_ids = [ids[name] for name in order]
        plan = unwrap("plano", *client.call("sigmai_plan_map", {
            "layer_ids": layer_ids,
            "title": "Parque Estadual das Carnaúbas e a malha municipal do Piauí",
            "page": "A3 landscape",
            "template": "relatorio_ambiental",
        }))
        print(f"   página {plan['plan']['page']['name']} {plan['plan']['page']['orientation']}, "
              f"arranjo {plan['plan']['arrangement']}, escala prevista {plan['scale']}, CRS {plan['map_crs']}")

        print("\n== 6. composição real ==")
        result = unwrap("composição", *client.call("sigmai_compose_map", {
            "layer_ids": layer_ids,
            "title": "Parque Estadual das Carnaúbas e a malha municipal do Piauí",
            "subtitle": "Municípios classificados por área — malha IBGE 2024",
            "page": "A3 landscape",
            "template": "relatorio_ambiental",
            "output_path": args.out,
            "format": "png",
            "dpi": 200,
            "data_source": "IBGE, Malha Municipal 2024; CEUC/SEMA-PI",
            "map_author": "MACIEL, L. S. C.",
            "organization": "Herpeto Mantiqueira",
            "legend_title": "Legenda",
            "apply_style": "none",
            "confirm_overwrite": True,
        }))
        audit = result["audit"]
        print(f"   escala {result['scale']} | CRS {result['map_crs']}")
        print(f"   barra: {result['scale_bar']['segments_left']}+{result['scale_bar']['segments_right']} x "
              f"{result['scale_bar']['units_per_segment']:g} {result['scale_bar']['unit_label']} "
              f"({result['scale_bar']['frame_fraction']:.0%} do quadro)")
        for note in result["notes"]:
            print(f"   nota: {note}")
        print(f"\n   AUDITORIA: {audit['grade']} — {audit['label']} ({audit['score']}/100)")
        print(f"   {audit['counts']}")
        for action in audit["next_actions"]:
            print(f"     [{action['severity']}] {action['rule']} {action['problem'][:120]}")

        print("\n== 7. o assistente audita de novo, do zero ==")
        again = unwrap("auditoria", *client.call("sigmai_audit_layout", {
            "layout_name": result["layout_name"], "output_path": args.out,
        }))
        print(f"   {again['grade']} {again['score']}/100 — {again['counts']['passed']} regras aprovadas")

        print(f"\nArquivo: {args.out}")
        return 0 if audit["counts"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
