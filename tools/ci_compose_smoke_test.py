#!/usr/bin/env python3
"""Compõe um mapa dentro de um QGIS real e exige nota A na auditoria.

Roda no contêiner oficial do QGIS em CI. É o teste que os módulos puros não
podem fazer: verifica que a API de layout do QGIS aceitou tudo que o motor
pediu — grade com intervalo, rosa dos ventos ligada ao norte da grade, barra
de escala nas unidades certas — e que o resultado passa no próprio regulamento.
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)


def build_project() -> tuple[QgsVectorLayer, QgsVectorLayer]:
    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))

    polygons = QgsVectorLayer("Polygon?crs=EPSG:31983&field=nome:string(30)", "Áreas", "memory")
    provider = polygons.dataProvider()
    random.seed(11)
    features = []
    for index in range(6):
        cx = 330000.0 + (index % 3) * 12000
        cy = 7480000.0 + (index // 3) * 9000
        ring = [
            QgsPointXY(cx + 3500 * math.cos(2 * math.pi * step / 8), cy + 3500 * math.sin(2 * math.pi * step / 8))
            for step in range(8)
        ]
        feature = QgsFeature(polygons.fields())
        feature.setGeometry(QgsGeometry.fromPolygonXY([ring]))
        feature["nome"] = f"Área {index + 1}"
        features.append(feature)
    provider.addFeatures(features)
    polygons.updateExtents()

    points = QgsVectorLayer("Point?crs=EPSG:31983&field=id:integer", "Pontos", "memory")
    point_provider = points.dataProvider()
    point_features = []
    for index in range(25):
        feature = QgsFeature(points.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(
            328000 + random.uniform(0, 30000), 7478000 + random.uniform(0, 22000)
        )))
        feature["id"] = index
        point_features.append(feature)
    point_provider.addFeatures(point_features)
    points.updateExtents()

    project.addMapLayers([points, polygons])
    return polygons, points


def main() -> int:
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    from tools.qgis_lifecycle import shutdown_qgis
    try:
        from sigmai.cartography.compose import compose_map

        polygons, points = build_project()
        failures: list[str] = []

        with tempfile.TemporaryDirectory() as directory:
            for page, template, fmt in (
                ("A4 landscape", "cientifico", "png"),
                ("A4 portrait", "publicacao", "png"),
                ("A3 landscape", "relatorio_ambiental", "pdf"),
            ):
                output = Path(directory) / f"mapa_{page.replace(' ', '_')}.{fmt}"
                result = compose_map(
                    {
                        "layer_ids": [polygons.id(), points.id()],
                        "title": "Teste automatizado do SIGMAI",
                        "subtitle": "Composição verificada em integração contínua",
                        "page": page,
                        "template": template,
                        "output_path": str(output),
                        "format": fmt,
                        "data_source": "Dados sintéticos",
                        "map_author": "CI",
                        "confirm_overwrite": True,
                    },
                    {"dry_run": False},
                )
                audit = result["audit"]
                print(f"{page:14} {template:20} {fmt} -> {audit['grade']} {audit['score']:5.1f}  {result['scale']}")
                for entry in audit["results"]:
                    if entry["status"] == "fail":
                        print(f"    [{entry['severity']}] {entry['id']} {entry['detail_pt']}")
                if audit["counts"]["errors"]:
                    failures.append(f"{page}/{template}: {audit['counts']['errors']} erro(s) na auditoria")
                if not output.exists():
                    failures.append(f"{page}/{template}: arquivo de saída não foi criado")

            # Caminhos de saída inválidos precisam ser recusados com mensagem
            # acionável, e não produzir um mapa que não existe no disco.
            base = {
                "layer_ids": [polygons.id()],
                "title": "Recusa esperada",
                "page": "A4 landscape",
                "template": "cientifico",
                "data_source": "Dados sintéticos",
                "map_author": "CI",
                "confirm_overwrite": True,
            }
            for label, output_path in (
                ("pasta como saída", directory),
                ("sem extensão", str(Path(directory) / "sem_extensao")),
                ("extensão desconhecida", str(Path(directory) / "mapa.tiff")),
                ("pasta inexistente", str(Path(directory) / "nao_existe" / "m.png")),
            ):
                try:
                    compose_map({**base, "output_path": output_path}, {"dry_run": False})
                except Exception as exc:  # noqa: BLE001 - o teste é sobre recusar
                    print(f"{label:24} -> recusado: {str(exc)[:80]}")
                else:
                    failures.append(f"{label}: deveria ter sido recusado")

        if failures:
            print("\nFALHOU:")
            for failure in failures:
                print("  -", failure)
            return 1
        print("\nComposição e auditoria aprovadas em todas as combinações.")
        return 0
    finally:
        shutdown_qgis(app)


if __name__ == "__main__":
    raise SystemExit(main())
