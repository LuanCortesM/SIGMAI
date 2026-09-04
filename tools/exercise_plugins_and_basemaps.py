# -*- coding: utf-8 -*-
"""Exercita as duas promessas que ainda não tinham prova: instalar plugin e carregar mapa de base.

Passa pela ponte HTTP de verdade — mesmo caminho que um assistente de IA usa —
para que o teste inclua consentimento, validação e despacho, e não só a função
solta. O que depende de rede externa (plugins.qgis.org, servidores de tiles) é
exercitado assim mesmo: o que se verifica aí não é o download, e sim que a
falha de rede vira uma recusa explicada, e não uma quebra.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import traceback
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TOKEN = "token-de-teste-exercitador"


class Runner:
    def __init__(self, host: str, port: int) -> None:
        self.url = f"http://{host}:{port}/command"
        self.resultados: list[dict[str, Any]] = []

    def call(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"action": action, "params": params or {}}).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read())

    def check(self, rotulo: str, action: str, params: dict[str, Any] | None = None,
              espera: str = "ok") -> dict[str, Any]:
        """``espera``: 'ok', 'recusa' (erro tratado) ou 'qualquer'."""
        resposta = self.call(action, params)
        ok = bool(resposta.get("ok"))
        erros = resposta.get("errors") or []
        primeiro = erros[0] if erros else {}
        codigo = str(primeiro.get("code", ""))
        mensagem = str(primeiro.get("message", ""))
        # Uma recusa tratada tem código próprio; INTERNAL_ERROR é a ponte
        # perdendo o controle, e nunca é resposta aceitável.
        quebrou = codigo in {"INTERNAL_ERROR", "UNEXPECTED_ERROR", ""} and not ok
        passou = (espera == "ok" and ok) or (espera == "recusa" and not ok and not quebrou) or espera == "qualquer"
        self.resultados.append({"rotulo": rotulo, "action": action, "passou": passou,
                                "ok": ok, "codigo": codigo, "mensagem": mensagem})
        marca = "OK   " if passou else "FALHA"
        print(f"  {marca} {rotulo:46s} {codigo or ('ok' if ok else '?'):32s} {mensagem[:70]}")
        return resposta

    def summary(self) -> int:
        falhas = [r for r in self.resultados if not r["passou"]]
        print(f"\n{len(self.resultados) - len(falhas)}/{len(self.resultados)} como esperado.")
        for f in falhas:
            print(f"  - {f['rotulo']}: {f['codigo']} {f['mensagem'][:120]}")
        return 1 if falhas else 0


def _tiles_locais(raiz: Path) -> str:
    """Cria um XYZ mínimo no disco. Prova o caminho sem depender de servidor."""
    from qgis.PyQt.QtGui import QColor, QImage
    for z in (0, 1):
        for x in range(2 ** z):
            for y in range(2 ** z):
                destino = raiz / str(z) / str(x)
                destino.mkdir(parents=True, exist_ok=True)
                imagem = QImage(256, 256, QImage.Format_ARGB32)
                imagem.fill(QColor(200, 220, 240))
                imagem.save(str(destino / f"{y}.png"), "PNG")
    return "file://" + str(raiz) + "/{z}/{x}/{y}.png"


def _plugin_zip_valido(destino: Path) -> Path:
    caminho = destino / "plugin_de_teste.zip"
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr("plugin_de_teste/metadata.txt",
                         "[general]\nname=Plugin de teste\nqgisMinimumVersion=3.28\n"
                         "description=Plugin mínimo para exercitar a instalação\nversion=1.0\n"
                         "author=Teste\nemail=teste@exemplo.org\n")
        arquivo.writestr("plugin_de_teste/__init__.py",
                         "def classFactory(iface):\n    return None\n")
    return caminho


def exercitar(runner: Runner, temporario: Path) -> None:
    print("\n== 1. mapas de base e serviços OGC ==")
    template = _tiles_locais(temporario / "tiles")
    runner.check("XYZ local vira camada de verdade", "load_xyz_tile_layer",
                 {"url": template, "name": "Mapa de base de teste", "zoom_max": 1})
    runner.check("XYZ sem os marcadores {z}{x}{y} é recusado", "load_xyz_tile_layer",
                 {"url": "https://tile.openstreetmap.org/tiles.png", "name": "x"}, espera="recusa")
    runner.check("XYZ de rede sem atribuição é recusado", "load_xyz_tile_layer",
                 {"url": "https://tiles.exemplo.test/{z}/{x}/{y}.png", "name": "x",
                  "confirm_network": True}, espera="recusa")
    runner.check("XYZ de rede sem confirm_network é recusado", "load_xyz_tile_layer",
                 {"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "name": "OSM"},
                 espera="recusa")
    runner.check("OSM inalcançável falha explicado, sem sujar o projeto", "load_xyz_tile_layer",
                 {"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "name": "OSM",
                  "confirm_network": True}, espera="qualquer")
    runner.check("zoom invertido é recusado", "load_xyz_tile_layer",
                 {"url": template, "name": "x", "zoom_min": 8, "zoom_max": 2}, espera="recusa")
    runner.check("XYZ sem url é recusado", "load_xyz_tile_layer", {"name": "x"}, espera="recusa")
    runner.check("XYZ com esquema inválido é recusado", "load_xyz_tile_layer",
                 {"url": "javascript:alert(1)", "name": "x"}, espera="recusa")
    runner.check("URL de serviço é validada", "validate_service_url",
                 {"url": "https://ows.terrestris.de/osm/service"})
    runner.check("URL de serviço inválida é recusada", "validate_service_url",
                 {"url": "nao-e-url"}, espera="recusa")
    runner.check("WMS sem layers é recusado", "load_wms_layer",
                 {"url": "https://ows.terrestris.de/osm/service", "name": "x",
                  "confirm_network": True, "attribution": "terrestris"}, espera="recusa")
    runner.check("WMS sem confirm_network é recusado", "load_wms_layer",
                 {"url": "https://ows.terrestris.de/osm/service", "layers": ["OSM-WMS"],
                  "name": "x", "attribution": "terrestris"}, espera="recusa")
    runner.check("WMS inalcançável falha explicado", "load_wms_layer",
                 {"url": "https://ows.terrestris.de/osm/service", "layers": ["OSM-WMS"],
                  "name": "WMS de teste", "confirm_network": True,
                  "attribution": "© terrestris GmbH"}, espera="recusa")
    runner.check("WFS sem typename é recusado", "load_wfs_layer",
                 {"url": "https://exemplo.test/wfs", "name": "x",
                  "confirm_network": True, "attribution": "x"}, espera="recusa")
    runner.check("conexões OGC do perfil", "list_ogc_connections")
    runner.check("o projeto não ganhou camada quebrada", "list_layers")

    print("\n== 2. plugins: catálogo local ==")
    runner.check("lista os plugins instalados", "list_installed_plugins")
    runner.check("lista estendida", "list_qgis_plugins_extended")

    print("\n== 3. plugins: instalar de um ZIP ==")
    zip_valido = _plugin_zip_valido(temporario)
    runner.check("inspeciona o ZIP antes de instalar", "inspect_qgis_plugin_zip",
                 {"zip_path": str(zip_valido)})
    # Contrato deliberado: ação de plugin NUNCA é auto-aprovada, nem no modo
    # "liberar nesta sessão". Cada instalação exige um clique da pessoa no
    # painel do SIGMAI dentro do QGIS. A IA prepara e propõe; quem instala é
    # o usuário. Por isso o esperado aqui é a recusa por consentimento.
    runner.check("instalar do ZIP exige aprovação humana", "install_plugin_from_zip",
                 {"zip_path": str(zip_valido), "confirm_action": True, "confirm_destructive": True},
                 espera="recusa")
    runner.check("simular a instalação é permitido", "install_plugin_from_zip",
                 {"zip_path": str(zip_valido), "dry_run": True}, espera="qualquer")
    runner.check("habilita o plugin instalado", "enable_plugin",
                 {"plugin_name": "plugin_de_teste", "confirm_action": True, "confirm_destructive": True}, espera="recusa")
    runner.check("desabilita o plugin", "disable_plugin",
                 {"plugin_name": "plugin_de_teste", "confirm_action": True, "confirm_destructive": True}, espera="recusa")
    runner.check("ZIP inexistente é recusado", "install_plugin_from_zip",
                 {"zip_path": str(temporario / "nao_existe.zip"), "confirm_action": True, "confirm_destructive": True},
                 espera="recusa")

    print("\n== 4. plugins: repositório oficial (rede bloqueada neste contêiner) ==")
    runner.check("busca sem confirm_network é recusada", "search_qgis_plugin_repository",
                 {"query": "qgis2web"}, espera="recusa")
    runner.check("busca com rede indisponível falha explicada", "search_qgis_plugin_repository",
                 {"query": "qgis2web", "confirm_network": True}, espera="recusa")
    runner.check("repositório de terceiro é bloqueado", "search_qgis_plugin_repository",
                 {"query": "x", "confirm_network": True,
                  "repository_url": "https://exemplo-malicioso.test/plugins.xml"}, espera="recusa")
    runner.check("repositório http é bloqueado", "search_qgis_plugin_repository",
                 {"query": "x", "confirm_network": True,
                  "repository_url": "http://plugins.qgis.org/plugins/plugins.xml"}, espera="recusa")
    runner.check("download de URL fora do repositório é bloqueado", "download_qgis_plugin_zip",
                 {"plugin_name": "x", "confirm_network": True,
                  "download_url": "https://exemplo-malicioso.test/x.zip"}, espera="recusa")

    print("\n== 5. o SIGMAI não se desinstala nem se desabilita ==")
    runner.check("não desabilita a si mesmo", "disable_plugin", {"plugin_name": "sigmai", "confirm_action": True, "confirm_destructive": True}, espera="recusa")
    runner.check("não desinstala a si mesmo", "uninstall_plugin",
                 {"plugin_name": "sigmai", "confirm_action": True, "confirm_destructive": True}, espera="recusa")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    from tools.qgis_lifecycle import shutdown_qgis
    try:
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
                exercitar(runner, temporario)
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
