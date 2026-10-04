#!/usr/bin/env python3
"""Laboratório do "assistente remoto": um QGIS com a ponte do SIGMAI no ar.

Emula o lado do computador do usuário — QGIS aberto, projeto carregado, ponte
ligada, acesso liberado para esta sessão numa pasta — e fica girando o laço de
eventos do Qt até aparecer o arquivo de parada. Do outro lado, um assistente
de IA que NÃO tem acesso a esta máquina fala com ela só pelo caminho real:

    assistente → cliente MCP (tools/mcp_call.py) → servidor MCP (stdio)
               → ponte HTTP em 127.0.0.1 (token, validação, consentimento)
               → QGIS

Ao parar, grava a trilha de auditoria do consentimento e o log da ponte na
pasta de saída: é com eles que se confere, depois, que cada coisa que o
assistente disse ter feito passou de fato pela ponte.

Uso::

    xvfb-run -a python3.12 tools/remote_ai_lab.py --data <_teste_sigmai> --out <pasta> &
    # ... o assistente trabalha via tools/mcp_call.py ...
    touch <pasta>/PARAR
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="pasta _teste_sigmai")
    parser.add_argument("--out", required=True, help="pasta de saída autorizada para o assistente")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    from tools.qgis_lifecycle import shutdown_qgis

    from sigmai.bridge_server import SIGMAIServer, plugin_version
    from sigmai.consent import MODE_ALLOW_SESSION
    from sigmai.security import generate_token
    from sigmai.session import build_session_payload

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = Path(args.data)

    # O projeto do usuário: o que ele teria aberto no QGIS antes de pedir ajuda.
    project = QgsProject.instance()
    project.clear()
    sources = {
        "Municípios do Piauí": (data / "PI_Municipios_2024.shp", "ogr"),
        "Limite estadual do Piauí": (data / "PI_UF_2024.shp", "ogr"),
        "PE das Carnaúbas": (data / "PE Carnaubas.kml", "ogr"),
        "Trilha do Itaguaré": (data / "trilha" / "Trilha Itaguaré pelo batedor.shp", "ogr"),
    }
    layers = []
    for name, (path, provider) in sources.items():
        layer = QgsVectorLayer(str(path), name, provider)
        if not layer.isValid():
            raise SystemExit(f"camada inválida: {path}")
        layers.append(layer)
    dem = data.parent / "DEM_GLO90" / "Copernicus_DSM_COG_30_S05_00_W042_00_DEM.tif"
    if dem.exists():
        raster = QgsRasterLayer(str(dem), "Altimetria (Copernicus DEM 30 m)")
        if raster.isValid():
            layers.append(raster)
    project.addMapLayers(layers)
    project.setCrs(layers[1].crs())

    token = generate_token()
    server = SIGMAIServer(token=token, port=args.port, log_dir=out / "_ponte" / "logs")
    server.start()
    # O que o usuário teria feito no painel: "Liberar nesta sessão", com a
    # pasta de saída autorizada. Os limites ficam nos padrões.
    server.consent.set_mode(MODE_ALLOW_SESSION)
    server.consent.set_output_roots([str(out)])

    session_path = out / "_ponte" / "current_bridge_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_session_payload(
        host=server.host, port=server.port, token=token, qgis_version=server.qgis_version,
        plugin_version=plugin_version(), running=True, source="remote_ai_lab",
    )
    session_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out / "_ponte" / "PRONTO").write_text(f"{server.host}:{server.port}\n", encoding="utf-8")
    print(f"ponte no ar em {server.host}:{server.port}; sessão em {session_path}", flush=True)

    stop = out / "PARAR"
    try:
        while not stop.exists():
            app.processEvents()
            time.sleep(0.02)
    finally:
        audit = server.consent.recent_audit(1000)
        status = server.consent.status()
        (out / "_ponte" / "auditoria.json").write_text(
            json.dumps({"status": status, "audit": audit}, ensure_ascii=False, indent=1, default=str), encoding="utf-8",
        )
        server.stop()
        layers = None
        shutdown_qgis(app)
        print("ponte encerrada; auditoria gravada", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
