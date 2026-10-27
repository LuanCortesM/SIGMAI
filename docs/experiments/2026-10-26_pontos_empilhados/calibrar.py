"""Calibra o compositor: a medida geométrica de pointdensity contra a auditoria.

Para cada mapa de pontos da fase 2 (símbolo fixado à mão), recalcula, com
``sigmai.cartography.pointdensity.stacking``, a fração de pontos oculta e a
cobertura de tinta, e as põe ao lado da fração do parque que a auditoria
(renderização) mediu como visível. Depois mostra que símbolo
``choose_point_symbol`` escolheria para cada conjunto da fase 1, nas duas
figuras.

    python calibrar.py --dados <dados> --saida <pasta qpy4>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def quadro(dados: Path, pontos_gpkg: Path, figura: dict, trabalho: Path):
    """Extensão e tamanho do quadro principal que o compositor dá a esta figura."""
    from qgis.core import QgsProject, QgsVectorLayer

    from explorar_pontos import mapa_principal
    from sigmai.cartography.compose import compose_map

    projeto = QgsProject.instance()
    projeto.clear()
    pontos = QgsVectorLayer(f"{pontos_gpkg}|layername=pontos", "p", "ogr")
    parque = QgsVectorLayer(str(dados / "parna_itatiaia.gpkg"), "Itatiaia National Park", "ogr")
    projeto.addMapLayers([pontos, parque])
    projeto.setCrs(parque.crs())
    nome = "calibra " + "_".join(f"{k}{v}" for k, v in figura.items())
    compose_map({"title": "Itatiaia National Park", "subtitle": "x", "map_author": "x", "data_source": "x",
                 "map_language": "en", "format": "png", "dpi": 60, "include_grid": True,
                 "layer_ids": [pontos.id(), parque.id()], "subject_layer_id": [pontos.id(), parque.id()],
                 "layout_name": nome, "output_path": str(trabalho / f"{nome}.png"), "confirm_overwrite": True,
                 **figura}, {"dry_run": False})
    mapa = mapa_principal(projeto.layoutManager().layoutByName(nome))
    # Cópias: o próximo project.clear() apaga o layout e o item com ele.
    from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle
    from qgis.PyQt.QtCore import QRectF

    class Quadro:
        def __init__(self, extensao, retangulo, crs):
            self._e, self._r, self._c = extensao, retangulo, crs

        def extent(self):
            return self._e

        def rect(self):
            return self._r

        def crs(self):
            return self._c

    return Quadro(QgsRectangle(mapa.extent()), QRectF(mapa.rect()), QgsCoordinateReferenceSystem(mapa.crs()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dados", required=True)
    parser.add_argument("--saida", required=True)
    args = parser.parse_args()

    from qgis.core import QgsApplication, QgsVectorLayer

    from explorar_pontos import CONTAGENS, FIGURAS, pontos_no_quadro
    from sigmai.cartography.pointdensity import choose_point_symbol, stacking

    app = QgsApplication([], False)
    app.initQgis()
    dados, saida = Path(args.dados), Path(args.saida)
    trabalho = saida / "calibracao"
    trabalho.mkdir(parents=True, exist_ok=True)
    conjuntos = saida / "conjuntos"

    # 1. medida geométrica × visibilidade medida pela auditoria (fase 2, A5)
    fase2 = [json.loads(l) for l in (saida / "fase2" / "resultados.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    mapas = {fig: quadro(dados, conjuntos / "uniforme_300.gpkg", FIGURAS[fig], trabalho) for fig in FIGURAS}
    cache: dict[tuple[str, int, str], list] = {}

    def pontos_mm(tipo: str, n: int, fig: str):
        chave = (tipo, n, fig)
        if chave not in cache:
            camada = QgsVectorLayer(f"{conjuntos / f'{tipo}_{n}.gpkg'}|layername=pontos", "p", "ogr")
            cache[chave] = pontos_no_quadro(mapas[fig], camada)
        return cache[chave]

    linhas = []
    for r in fase2:
        v = r.get("variante") or {}
        if v.get("tipo") != "pontos" or r.get("erro"):
            continue
        medida = stacking(pontos_mm(r["tipo"], r["n"], "A5"), v["tamanho"], v["opacidade"])
        parque = (r.get("visivel_por_camada") or {}).get("Itatiaia National Park")
        linhas.append({"caso": r["caso"], "ocultos": medida["hidden_fraction"], "cobertura": medida["ink_coverage"],
                       "parque_visivel": parque, "cart075": r.get("cart075")})
        print(f"{r['caso']:<40} ocult={medida['hidden_fraction']:.3f} cob={medida['ink_coverage']:.3f} "
              f"parque_vis={parque:.2f} CART075={r.get('cart075')}", flush=True)
    (trabalho / "medida_x_auditoria.json").write_text(json.dumps(linhas, indent=1, ensure_ascii=False), encoding="utf-8")

    # 2. o que o compositor escolheria para os conjuntos da fase 1
    escolhas = []
    for tipo in ("gbif", "uniforme"):
        for n in CONTAGENS:
            for fig in FIGURAS:
                e = choose_point_symbol(pontos_mm(tipo, n, fig))
                escolhas.append({"tipo": tipo, "n": n, "figura": fig, "tamanho": e["size_mm"], "opacidade": e["opacity"],
                                 "contorno": e["outline"], "ocultos": e["hidden_fraction"], "cobertura": e["ink_coverage"],
                                 "atingiu": e["reached"]})
                print(f"escolha {tipo:<9} n={n:<7} {fig:<6} -> {e['size_mm']} mm, {e['opacity']}, "
                      f"ocult={e['hidden_fraction']:.3f} cob={e['ink_coverage']:.3f} atingiu={e['reached']}", flush=True)
    (trabalho / "escolhas_do_compositor.json").write_text(json.dumps(escolhas, indent=1, ensure_ascii=False), encoding="utf-8")
    app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
