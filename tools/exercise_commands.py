#!/usr/bin/env python3
"""Exercita o catálogo de comandos contra um QGIS real, pela ponte HTTP.

A suíte de testes cobre a lógica que não precisa de QGIS. Este script cobre o
resto: sobe a ponte, carrega dados de verdade e chama os comandos como um
agente de IA chamaria — passando pela validação, pelo consentimento, pela fila
e pelos manipuladores. É onde aparecem os erros que só existem quando há um
projeto QGIS do outro lado.

Uso:
    python tools/exercise_commands.py --data /caminho/para/vetores
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TOKEN = "exercitador-" + "x" * 32


class Runner:
    def __init__(self, host: str, port: int):
        self.url = f"http://{host}:{port}/command"
        self.results: list[dict[str, Any]] = []

    def call(self, action: str, params: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
        body = json.dumps({"action": action, "params": params or {}, "dry_run": dry_run}).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            return {"ok": False, "errors": [{"code": "TRANSPORT", "message": f"{type(exc).__name__}: {exc}"}]}

    def check(self, label: str, action: str, params: dict[str, Any] | None = None,
              dry_run: bool = False, expect_ok: bool = True) -> dict[str, Any]:
        response = self.call(action, params, dry_run)
        ok = bool(response.get("ok"))
        passed = ok == expect_ok
        error = (response.get("errors") or [{}])[0]
        self.results.append({
            "label": label, "action": action, "passed": passed, "ok": ok,
            "code": error.get("code", ""), "message": error.get("message", "")[:200],
        })
        mark = "OK   " if passed else "FALHA"
        detail = "" if passed else f"  {error.get('code','')}: {error.get('message','')[:150]}"
        print(f"  {mark} {label}{detail}")
        return response.get("data") or {}

    def summary(self) -> int:
        failed = [r for r in self.results if not r["passed"]]
        print(f"\n{len(self.results) - len(failed)}/{len(self.results)} comandos como esperado.")
        if failed:
            print("\nFalhas:")
            for item in failed:
                print(f"  {item['action']:34} {item['code']:26} {item['message'][:110]}")
        return 1 if failed else 0


def load_layers(data_dir: Path) -> dict[str, Any]:
    from qgis.core import QgsProject, QgsVectorLayer

    project = QgsProject.instance()
    project.clear()
    layers = {}
    for path in sorted(data_dir.glob("*.shp")) + sorted(data_dir.glob("*.kml")) + sorted(data_dir.glob("*.gpkg")):
        layer = QgsVectorLayer(str(path), path.stem, "ogr")
        if layer.isValid():
            layers[path.stem] = layer
    if not layers:
        raise SystemExit(f"Nenhuma camada vetorial válida em {data_dir}")
    project.addMapLayers(list(layers.values()))
    first = next(iter(layers.values()))
    project.setCrs(first.crs())
    return layers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="pasta com vetores de teste")
    args = parser.parse_args()

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    from tools.qgis_lifecycle import shutdown_qgis
    try:
        layers = load_layers(Path(args.data))
        print(f"Camadas carregadas: {', '.join(layers)}")

        from sigmai.bridge_server import SIGMAIServer
        from sigmai.consent import MODE_ALLOW_SESSION

        server = SIGMAIServer(token=TOKEN, log_dir=Path(tempfile.mkdtemp()) / "logs")
        server.start()
        # A fila do QTimer fica ativa: é ela que executa os comandos na thread
        # principal do Qt. Renderizar layout em thread de trabalho devolve
        # sucesso e grava um arquivo vazio, então o exercitador precisa do
        # arranjo real — chamadas numa thread, laço de eventos na principal.
        server.consent.set_mode(MODE_ALLOW_SESSION)
        server.consent.set_limit("exports_per_session", 500)
        server.consent.set_limit("processing_runs_per_session", 500)
        server.consent.set_limit("writes_per_session", 500)

        runner = Runner(server.host, server.port)
        outcome: dict[str, Any] = {}

        def worker() -> None:
            try:
                exercise(runner, layers)
            except Exception:
                traceback.print_exc()
                outcome["error"] = True
            finally:
                outcome["done"] = True

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        while not outcome.get("done"):
            app.processEvents()
            thread.join(0.02)
        server.stop()
        return runner.summary() or (1 if outcome.get("error") else 0)
    finally:
        shutdown_qgis(app)


def exercise(runner: Runner, layers: dict[str, Any]) -> None:
    names = list(layers)
    polygon = next((layer for layer in layers.values() if layer.geometryType() == 2), None)
    any_layer = next(iter(layers.values()))
    scratch = Path(tempfile.mkdtemp())

    print("\n-- inspeção --")
    runner.check("status", "status")
    overview = runner.check("panorama do projeto", "get_project_overview")
    runner.check("capacidades", "get_capabilities")
    runner.check("ambiente do QGIS", "get_qgis_environment")
    runner.check("listar camadas", "list_layers")
    runner.check("CRS do projeto", "get_project_crs")
    runner.check("info da camada", "get_layer_info", {"layer_id": any_layer.id()})
    runner.check("listar campos", "list_fields", {"layer_id": any_layer.id()})
    runner.check("amostrar feições", "sample_features", {"layer_id": any_layer.id(), "limit": 3})
    runner.check("diagnosticar CRS", "diagnose_crs")
    runner.check("validar geometrias", "validate_geometries", {"layer_id": any_layer.id()})
    runner.check("inspecionar estilo", "inspect_layer_style", {"layer_id": any_layer.id()})
    runner.check("árvore de camadas", "list_layer_tree")
    runner.check("listar layouts", "list_layouts")
    runner.check("regulamento cartográfico", "get_cartographic_rulebook")
    runner.check("provedores do Processing", "list_processing_providers")

    field = None
    for layer in layers.values():
        for candidate in layer.fields():
            if candidate.typeName().lower().startswith(("string", "text")):
                field = (layer, candidate.name())
                break
        if field:
            break

    print("\n-- expressões e seleção --")
    runner.check("validar expressão", "validate_expression", {"layer_id": any_layer.id(), "expression": "1 = 1"})
    runner.check("contar por expressão", "query_features", {"layer_id": any_layer.id(), "expression": "1 = 1", "limit": 5})
    if field:
        layer, name = field
        runner.check("valores únicos", "unique_values", {"layer_id": layer.id(), "field_name": name, "limit": 10})
        runner.check("selecionar por expressão", "select_by_expression",
                     {"layer_id": layer.id(), "expression": f'"{name}" IS NOT NULL'})

    print("\n-- simbologia --")
    runner.check("símbolo único", "apply_single_symbol",
                 {"layer_id": any_layer.id(), "fill_color": "#CFE3EF", "stroke_color": "#0B4F6C"})
    runner.check("recomendar estilo", "recommend_style_for_layer", {"layer_id": any_layer.id()})
    runner.check("opacidade", "set_layer_opacity", {"layer_id": any_layer.id(), "opacity": 0.8})
    if field:
        layer, name = field
        runner.check("estilo categorizado", "apply_categorized_style", {"layer_id": layer.id(), "field_name": name})
        runner.check("rótulos", "create_labels", {"layer_id": layer.id(), "field_name": name})
        runner.check("desligar rótulos", "disable_labels", {"layer_id": layer.id()})
    numeric = None
    for layer in layers.values():
        for candidate in layer.fields():
            if candidate.typeName().lower() in {"integer", "integer64", "real", "double"}:
                numeric = (layer, candidate.name())
                break
        if numeric:
            break
    if numeric:
        layer, name = numeric
        runner.check("estilo graduado", "apply_graduated_style",
                     {"layer_id": layer.id(), "field_name": name, "classes": 4})

    print("\n-- geoprocessamento --")
    # Nenhum algoritmo pode fazer camadas sumirem do projeto. Já aconteceu:
    # uma transferência de camadas na direção errada esvaziava o projeto do
    # usuário no primeiro buffer.
    before = len((runner.call("get_project_overview").get("data") or {}).get("layers", []))
    if polygon is not None:
        runner.check("centroides", "centroids", {"layer_id": polygon.id(), "output_path": str(scratch / "centroides.gpkg")})
        runner.check("buffer", "buffer", {"layer_id": polygon.id(), "distance": 0.01, "output_path": str(scratch / "buffer.gpkg")})
        runner.check("dissolver", "dissolve", {"layer_id": polygon.id(), "output_path": str(scratch / "dissolve.gpkg")})
        runner.check("reprojetar", "reproject_layer",
                     {"layer_id": polygon.id(), "target_crs": "EPSG:31983", "output_path": str(scratch / "reproj.gpkg")})

    after = len((runner.call("get_project_overview").get("data") or {}).get("layers", []))
    runner.results.append({
        "label": "o projeto não perdeu camadas", "action": "invariante:camadas_preservadas",
        "passed": after >= before, "ok": after >= before, "code": "" if after >= before else "LAYERS_LOST",
        "message": "" if after >= before else f"o projeto tinha {before} camadas e ficou com {after}",
    })
    print(("  OK    " if after >= before else "  FALHA ") + f"o projeto não perdeu camadas ({before} -> {after})")

    print("\n-- cartografia --")
    runner.check("planejar layout", "plan_map_layout", {"page": "A3 landscape", "template": "cientifico"})
    runner.check("simular composição", "compose_map",
                 {"layer_ids": [layer.id() for layer in layers.values()], "title": "Simulação"}, dry_run=True)
    composed = runner.check("compor mapa", "compose_map", {
        "layer_ids": [layer.id() for layer in layers.values()],
        "title": "Exercitador do SIGMAI",
        "subtitle": "Todas as camadas do projeto",
        "output_path": str(scratch / "mapa.png"), "format": "png",
        "data_source": "Dados de teste", "map_author": "Exercitador",
        "confirm_overwrite": True,
    })
    if composed.get("layout_name"):
        runner.check("auditar layout", "audit_map_layout", {"layout_name": composed["layout_name"]})
        runner.check("exportar layout em PDF", "export_layout",
                     {"layout_name": composed["layout_name"], "format": "pdf",
                      "path": str(scratch / "mapa.pdf"), "confirm_overwrite": True})

    print("\n-- recusas esperadas --")
    runner.check("camada inexistente é recusada", "get_layer_info", {"layer_id": "nao_existe"}, expect_ok=False)
    runner.check("ação fora do catálogo é recusada", "acao_inventada", expect_ok=False)
    runner.check("travessia de diretório é recusada", "export_layout",
                 {"layout_name": "x", "path": "/tmp/../etc/x.pdf"}, expect_ok=False)
    runner.check("Python sem Modo DEV é recusado", "dev_execute_qgis_python",
                 {"code": "1+1", "confirm_dev_python": "SIM"}, expect_ok=False)


if __name__ == "__main__":
    raise SystemExit(main())
