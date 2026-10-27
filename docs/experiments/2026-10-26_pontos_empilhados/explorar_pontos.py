"""Mapas de pontos com muitos registros: o que o SIGMAI faz e o que a auditoria vê.

Experimento para a 1.3.0, feito depois de a base B5 do E1 (362.210 registros
do GBIF no PARNA do Itatiaia) sair com nota C: os pontos de 2,2 mm, opacos,
cobriam o parque. Aqui o número de pontos varia de 10 a 362.210, em dois
tipos de conjunto:

* ``gbif``: amostras aleatórias (semente fixa) do download 10.15468/dl.kee8xx,
  que é aglomerado (trilhas, estradas, pontos de observação do eBird);
* ``uniforme``: pontos sorteados (semente fixa) dentro do polígono do parque.

Fase 1: o comportamento atual do compositor (simbologia padrão), em dois
tamanhos de figura: A5 deitado e uma coluna de 88 mm (Biodiversity
Informatics). Fase 2: o mesmo mapa com o símbolo de ponto fixado à mão
(tamanho × opacidade), para escolher o que o compositor deve fazer.

Para cada mapa registra a auditoria do SIGMAI (nota, regras reprovadas,
fração visível de cada camada) e a medida candidata à regra nova:

* ``ocultos``: fração dos pontos do quadro cujo símbolo não acrescenta nada
  visível. Os pontos são levados para milímetros do quadro e agrupados em
  células do tamanho do símbolo; numa célula com k pontos, só os primeiros
  k_max mudam a imagem, onde k_max é quantas camadas da opacidade do símbolo
  levam a tinta a 95 % (1 para símbolo opaco).

Rodar com o Python do QGIS (ferramentas/qpy4.bat ou qpy3.bat)::

    python explorar_pontos.py --fase 1 --dados <dados> --saida <pasta>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

CONTAGENS = (10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000, 362210)
CONTAGENS_FASE2 = (300, 3000, 30000, 362210)
TAMANHOS_MM = (2.2, 1.4, 0.9, 0.5)
OPACIDADES = (0.95, 0.5, 0.25)
#: Fase 2: pontos (tamanho × opacidade), mapa de calor (raio em mm) e um
#: símbolo por local com área proporcional ao número de registros.
VARIANTES = ([{"tipo": "pontos", "tamanho": t, "opacidade": o} for t in TAMANHOS_MM for o in OPACIDADES]
             + [{"tipo": "calor", "raio": r} for r in (3.0, 6.0)]
             + [{"tipo": "locais"}])
FIGURAS = {
    "A5": {"page": "A5", "orientation": "landscape"},
    "col88": {"figure_width_mm": 88},
}
SEMENTE = 20261026
SATURACAO = 0.95


def k_max(opacidade: float) -> int:
    """Quantos símbolos empilhados ainda mudam a imagem antes de a tinta chegar a 95 %."""
    if opacidade >= SATURACAO:
        return 1
    return max(1, math.ceil(math.log(1.0 - SATURACAO) / math.log(1.0 - opacidade)))


def ocultos(pontos_mm: list[tuple[float, float]], diametro_mm: float, opacidade: float) -> dict:
    celulas: dict[tuple[int, int], int] = {}
    for x, y in pontos_mm:
        chave = (int(x // diametro_mm), int(y // diametro_mm))
        celulas[chave] = celulas.get(chave, 0) + 1
    n = len(pontos_mm)
    limite = k_max(opacidade)
    escondidos = sum(max(0, k - limite) for k in celulas.values())
    return {"n_quadro": n, "celulas": len(celulas), "k_max": limite,
            "ocultos": round(escondidos / n, 4) if n else 0.0,
            "max_por_celula": max(celulas.values()) if celulas else 0}


# ---------------------------------------------------------------------------
# Conjuntos de pontos
# ---------------------------------------------------------------------------

def gravar_pontos(destino: Path, nome_camada: str, coordenadas: list[tuple[float, float]]) -> None:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature, QgsField,
                           QgsFields, QgsGeometry, QgsPointXY, QgsVectorFileWriter, QgsWkbTypes)
    try:
        from qgis.PyQt.QtCore import QMetaType
        campo = QgsField("id", QMetaType.Type.Int)
    except Exception:
        from qgis.PyQt.QtCore import QVariant
        campo = QgsField("id", QVariant.Int)
    campos = QgsFields()
    campos.append(campo)
    opcoes = QgsVectorFileWriter.SaveVectorOptions()
    opcoes.driverName = "GPKG"
    opcoes.layerName = nome_camada
    from qgis.core import Qgis
    ponto = getattr(getattr(Qgis, "WkbType", QgsWkbTypes), "Point")
    escritor = QgsVectorFileWriter.create(str(destino), campos, ponto,
                                          QgsCoordinateReferenceSystem("EPSG:4326"),
                                          QgsCoordinateTransformContext(), opcoes)
    for i, (x, y) in enumerate(coordenadas):
        f = QgsFeature(campos)
        f.setAttribute(0, i)
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        escritor.addFeature(f)
    del escritor


def conjuntos(dados: Path, trabalho: Path, contagens) -> dict[tuple[str, int], Path]:
    """GeoPackages de pontos por (tipo, n); refeitos só se faltarem."""
    from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer

    trabalho.mkdir(parents=True, exist_ok=True)
    feitos = {}
    falta = [(t, n) for t in ("gbif", "uniforme") for n in contagens
             if not (trabalho / f"{t}_{n}.gpkg").exists()]
    if falta:
        registros = QgsVectorLayer(str(dados / "gbif_registros.gpkg"), "r", "ogr")
        todos = [(f.geometry().asPoint().x(), f.geometry().asPoint().y()) for f in registros.getFeatures()]
        parque = QgsVectorLayer(str(dados / "parna_itatiaia.gpkg"), "p", "ogr")
        poligono = QgsGeometry.unaryUnion([f.geometry() for f in parque.getFeatures()])
        motor = QgsGeometry.createGeometryEngine(poligono.constGet())
        motor.prepareGeometry()
        caixa = poligono.boundingBox()
        sorteio = random.Random(SEMENTE)
        uniformes: list[tuple[float, float]] = []
        alvo = max(contagens)
        while len(uniformes) < alvo:
            x = sorteio.uniform(caixa.xMinimum(), caixa.xMaximum())
            y = sorteio.uniform(caixa.yMinimum(), caixa.yMaximum())
            candidato = QgsGeometry.fromPointXY(QgsPointXY(x, y))  # vivo durante o teste: o motor guarda o ponteiro
            if motor.contains(candidato.constGet()):
                uniformes.append((x, y))
        for tipo, n in falta:
            if tipo == "gbif":
                escolha = todos if n >= len(todos) else random.Random(SEMENTE + n).sample(todos, n)
            else:
                escolha = uniformes[:n]
            gravar_pontos(trabalho / f"{tipo}_{n}.gpkg", "pontos", escolha)
    for tipo in ("gbif", "uniforme"):
        for n in contagens:
            feitos[(tipo, n)] = trabalho / f"{tipo}_{n}.gpkg"
    return feitos


# ---------------------------------------------------------------------------
# Composição, auditoria e medidas
# ---------------------------------------------------------------------------

def mapa_principal(layout):
    from qgis.core import QgsLayoutItemMap

    mapas = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
    return max(mapas, key=lambda m: m.rect().width() * m.rect().height()) if mapas else None


def pontos_no_quadro(map_item, camada) -> list[tuple[float, float]]:
    from qgis.core import QgsCoordinateTransform, QgsFeatureRequest, QgsProject

    ext = map_item.extent()
    largura, altura = map_item.rect().width(), map_item.rect().height()
    transf = QgsCoordinateTransform(camada.crs(), map_item.crs(), QgsProject.instance())
    pedido = QgsFeatureRequest().setNoAttributes()
    saida = []
    for f in camada.getFeatures(pedido):
        p = transf.transform(f.geometry().asPoint())
        if ext.xMinimum() <= p.x() <= ext.xMaximum() and ext.yMinimum() <= p.y() <= ext.yMaximum():
            saida.append(((p.x() - ext.xMinimum()) / ext.width() * largura,
                          (ext.yMaximum() - p.y()) / ext.height() * altura))
    return saida


def simbolo_de(camada) -> tuple[float, float]:
    try:
        simbolo = camada.renderer().symbol()
        return float(simbolo.size()), float(simbolo.opacity()) * float(camada.opacity())
    except Exception:
        return float("nan"), float("nan")


def gravar_locais(pontos_gpkg: Path, destino: Path) -> int:
    """Um ponto por coordenada distinta (6 casas decimais), com o número de registros."""
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeature, QgsField,
                           QgsFields, QgsGeometry, QgsPointXY, QgsVectorFileWriter, QgsVectorLayer, Qgis, QgsWkbTypes)
    try:
        from qgis.PyQt.QtCore import QMetaType
        campo = QgsField("registros", QMetaType.Type.Int)
    except Exception:
        from qgis.PyQt.QtCore import QVariant
        campo = QgsField("registros", QVariant.Int)
    contagem: dict[tuple[float, float], int] = {}
    for f in QgsVectorLayer(f"{pontos_gpkg}|layername=pontos", "p", "ogr").getFeatures():
        q = f.geometry().asPoint()
        chave = (round(q.x(), 6), round(q.y(), 6))
        contagem[chave] = contagem.get(chave, 0) + 1
    campos = QgsFields()
    campos.append(campo)
    opcoes = QgsVectorFileWriter.SaveVectorOptions()
    opcoes.driverName = "GPKG"
    opcoes.layerName = "locais"
    escritor = QgsVectorFileWriter.create(str(destino), campos, getattr(getattr(Qgis, "WkbType", QgsWkbTypes), "Point"),
                                          QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateTransformContext(), opcoes)
    # Os maiores primeiro: desenhados antes, ficam por baixo dos pequenos.
    for (x, y), k in sorted(contagem.items(), key=lambda item: -item[1]):
        f = QgsFeature(campos)
        f.setAttribute(0, k)
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        escritor.addFeature(f)
    del escritor
    return max(contagem.values())


def estilo_locais(camada, maximo: int) -> None:
    from qgis.core import (QgsDataDefinedSizeLegend, QgsMarkerSymbol, QgsProperty, QgsSingleSymbolRenderer,
                           QgsSymbolLayer)

    from sigmai.cartography.symbology import STYLE_ORIGIN_USER, mark_style_origin

    simbolo = QgsMarkerSymbol.createSimple({"name": "circle", "color": "#D55E00", "outline_color": "#FFFFFF",
                                            "outline_width": "0.15", "size": "1"})
    simbolo.setOpacity(0.75)
    # Área proporcional à contagem (expoente 0,5 no diâmetro), de 0,8 mm a 9 mm.
    expressao = f'scale_exp("registros", 1, {max(2, maximo)}, 0.8, 9, 0.5)'
    simbolo.setDataDefinedSize(QgsProperty.fromExpression(expressao))
    renderizador = QgsSingleSymbolRenderer(simbolo)
    legenda = QgsDataDefinedSizeLegend()
    legenda.setLegendType(QgsDataDefinedSizeLegend.LegendCollapsed)
    classes = [c for c in (1, 10, 100, 1000, 10000) if c < maximo] + [maximo]
    legenda.setClasses([QgsDataDefinedSizeLegend.SizeClass(c, f"{c:,}") for c in classes])
    legenda.setTitle("Records per site")
    renderizador.setDataDefinedSizeLegend(legenda)
    camada.setRenderer(renderizador)
    mark_style_origin(camada, STYLE_ORIGIN_USER)


def fixar_simbolo(camada, tamanho: float, opacidade: float) -> None:
    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer

    from sigmai.cartography.symbology import STYLE_ORIGIN_USER, mark_style_origin

    simbolo = QgsMarkerSymbol.createSimple({"name": "circle", "color": "#D55E00", "outline_style": "no",
                                            "size": str(tamanho)})
    simbolo.setOpacity(opacidade)
    camada.setRenderer(QgsSingleSymbolRenderer(simbolo))
    mark_style_origin(camada, STYLE_ORIGIN_USER)


def um_mapa(rotulo: str, pontos_gpkg: Path, dados: Path, figura: dict, png: Path, variante: dict | None) -> dict:
    from qgis.core import QgsProject, QgsVectorLayer

    from sigmai.cartography.compose import compose_map

    projeto = QgsProject.instance()
    projeto.clear()
    nome = "GBIF occurrence records" if rotulo.startswith("gbif") else "Random points"
    maximo = 0
    escala_dos_locais = None
    if variante and variante["tipo"] in ("locais_sigmai", "locais_escala"):
        from sigmai.qgis_actions.gis_tools import count_points_by_site
        bruto = QgsVectorLayer(f"{pontos_gpkg}|layername=pontos", nome, "ogr")
        projeto.addMapLayer(bruto)
        destino = png.with_suffix(".locais.gpkg")
        if destino.exists():
            destino.unlink()
        pedido = {"layer_id": bruto.id(), "output_path": str(destino),
                  "layer_name": "Sites with GBIF records" if rotulo.startswith("gbif") else "Sites with random points"}
        if variante["tipo"] == "locais_escala":
            # Como faria um assistente: simula o mapa dos registros para saber a
            # escala e agrupa os locais nela (count_points_by_site com scale).
            parque_simulado = QgsVectorLayer(str(dados / "parna_itatiaia.gpkg"), "Itatiaia National Park", "ogr")
            projeto.addMapLayer(parque_simulado)
            projeto.setCrs(parque_simulado.crs())
            simulado = compose_map({"title": "Itatiaia National Park", "map_author": "Point density experiment",
                                    "map_language": "en", "data_source": "GBIF.org", "include_grid": True,
                                    "layer_ids": [bruto.id(), parque_simulado.id()], "subject_layer_id": [bruto.id()],
                                    "layout_name": f"simulado {rotulo}", **figura}, {"dry_run": True})
            escala_dos_locais = int(simulado["scale_denominator"])
            pedido["scale"] = escala_dos_locais
            projeto.removeMapLayer(parque_simulado.id())
        saida = count_points_by_site(pedido, {"dry_run": False})
        pontos = projeto.mapLayer(saida["layer_id"])
        projeto.removeMapLayer(bruto.id())
        nome = pontos.name()
    elif variante and variante["tipo"] == "locais":
        locais = pontos_gpkg.with_name(pontos_gpkg.stem + "_locais.gpkg")
        maximo = gravar_locais(pontos_gpkg, locais)
        nome = "Sites with GBIF records" if rotulo.startswith("gbif") else "Sites with random points"
        pontos = QgsVectorLayer(f"{locais}|layername=locais", nome, "ogr")
    else:
        pontos = QgsVectorLayer(f"{pontos_gpkg}|layername=pontos", nome, "ogr")
    parque = QgsVectorLayer(str(dados / "parna_itatiaia.gpkg"), "Itatiaia National Park", "ogr")
    if variante and variante["tipo"] in ("locais_sigmai", "locais_escala"):
        projeto.addMapLayer(parque)
    else:
        projeto.addMapLayers([pontos, parque])
    projeto.setCrs(parque.crs())
    if variante and variante["tipo"] in ("locais_sigmai", "locais_escala"):
        from sigmai.qgis_actions.symbology import apply_proportional_symbol_style
        apply_proportional_symbol_style({"layer_id": pontos.id(), "field_name": "records",
                                         "legend_title": "Records per site", "map_language": "en"}, {"dry_run": False})
    if variante and variante["tipo"] == "pontos":
        fixar_simbolo(pontos, variante["tamanho"], variante["opacidade"])
    elif variante and variante["tipo"] == "calor":
        from sigmai.qgis_actions.symbology import apply_heatmap_style
        apply_heatmap_style({"layer_id": pontos.id(), "radius": variante["raio"], "radius_unit": "mm",
                             "map_language": "en"}, {"dry_run": False})
    elif variante and variante["tipo"] == "locais":
        estilo_locais(pontos, maximo)
    params = {
        "title": "Itatiaia National Park", "subtitle": f"{nome} (n = {pontos.featureCount():,})",
        "map_author": "Point density experiment", "map_language": "en", "format": "png", "dpi": 110,
        "data_source": "GBIF.org (26 October 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.kee8xx; CNUC/MMA (2025)",
        "include_grid": True, "layer_ids": [pontos.id(), parque.id()],
        "subject_layer_id": [pontos.id()] if (variante or {}).get("assunto") == "pontos" else [pontos.id(), parque.id()],
        "layout_name": f"pontos {rotulo}", "output_path": str(png), "confirm_overwrite": True,
        **figura,
    }
    inicio = time.time()
    resultado = compose_map(params, {"dry_run": False})
    duracao = round(time.time() - inicio, 1)
    auditoria = resultado.get("audit") or {}
    obs = (auditoria.get("observation") or {}).get("map") or {}
    regras = {r["id"]: r for r in auditoria.get("results") or []}
    layout = projeto.layoutManager().layoutByName(params["layout_name"])
    mapa = mapa_principal(layout)
    tamanho, opacidade = simbolo_de(pontos)
    no_quadro = pontos_no_quadro(mapa, pontos)
    return {
        "nota": auditoria.get("grade"), "pontos": auditoria.get("score"),
        "reprovadas": [i for i, r in regras.items() if r.get("status") == "fail"],
        "cart075": (regras.get("CART075") or {}).get("status"),
        "cart021": (regras.get("CART021") or {}).get("status"),
        "visivel_por_camada": obs.get("layer_visible_fraction"),
        "assunto_visivel": obs.get("subject_visible_fraction"),
        "escala": resultado.get("scale"), "quadro_mm": [round(mapa.rect().width(), 1), round(mapa.rect().height(), 1)],
        "simbolo_mm": tamanho, "opacidade": opacidade,
        "estilo": [s for s in resultado.get("styling") or [] if s.get("layer") == nome],
        "medida": ocultos(no_quadro, tamanho, opacidade) if tamanho == tamanho and (not variante or (variante or {}).get("tipo") in ("pontos", "padrao")) else None,
        "cart076": (regras.get("CART076") or {}).get("status"),
        "cart072": (regras.get("CART072") or {}).get("status"),
        "notas": resultado.get("notes"),
        "renderizador": type(pontos.renderer()).__name__,
        "locais": pontos.featureCount() if variante and variante["tipo"] in ("locais_sigmai", "locais_escala") else None,
        "escala_dos_locais": escala_dos_locais,
        "cart076_detalhe": (regras.get("CART076") or {}).get("detail_pt"),
        "segundos": duracao,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fase", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--dados", required=True)
    parser.add_argument("--saida", required=True)
    args = parser.parse_args()

    from qgis.core import Qgis, QgsApplication

    app = QgsApplication([], False)
    app.initQgis()
    dados, saida = Path(args.dados), Path(args.saida)
    pasta = saida / f"fase{args.fase}"
    pasta.mkdir(parents=True, exist_ok=True)
    contagens = CONTAGENS if args.fase == 1 else CONTAGENS_FASE2
    gpkgs = conjuntos(dados, saida / "conjuntos", CONTAGENS)
    resultados = pasta / "resultados.jsonl"
    feitos = set()
    if resultados.exists():
        feitos = {json.loads(l)["caso"] for l in resultados.read_text(encoding="utf-8").splitlines() if l.strip()}
    from sigmai.bridge_server import plugin_version
    (pasta / "ambiente.json").write_text(json.dumps({
        "sigmai": plugin_version(), "qgis": Qgis.version(), "python": sys.version.split()[0],
        "inicio": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1), encoding="utf-8")
    casos = []
    for tipo in ("gbif", "uniforme"):
        for n in contagens:
            if args.fase == 1:
                for fig in FIGURAS:
                    casos.append((f"{tipo}_{n}_{fig}", tipo, n, fig, None))
            elif args.fase == 3:
                # Fase 3 (1.3.0): os comandos do próprio SIGMAI, com o parque como contexto.
                for v in ({"tipo": "padrao", "assunto": "pontos"}, {"tipo": "calor", "raio": 3.0, "assunto": "pontos"},
                          {"tipo": "locais_sigmai", "assunto": "pontos"}, {"tipo": "locais_escala", "assunto": "pontos"}):
                    casos.append((f"{tipo}_{n}_A5_{v['tipo']}", tipo, n, "A5", v))
            else:
                for v in VARIANTES:
                    sufixo = {"pontos": lambda v: f"pontos_{v['tamanho']}mm_{v['opacidade']}",
                              "calor": lambda v: f"calor_{v['raio']:g}mm", "locais": lambda v: "locais"}[v["tipo"]](v)
                    casos.append((f"{tipo}_{n}_A5_{sufixo}", tipo, n, "A5", v))
    with resultados.open("a", encoding="utf-8") as saida_jsonl:
        for caso, tipo, n, fig, simbolo in casos:
            if caso in feitos:
                continue
            linha = {"caso": caso, "tipo": tipo, "n": n, "figura": fig, "variante": simbolo}
            try:
                linha.update(um_mapa(caso, gpkgs[(tipo, n)], dados, FIGURAS[fig], pasta / f"{caso}.png", simbolo))
            except Exception as exc:
                import traceback
                linha["erro"] = f"{type(exc).__name__}: {exc}"
                linha["traceback"] = traceback.format_exc()[-1200:]
            saida_jsonl.write(json.dumps(linha, ensure_ascii=False) + "\n")
            saida_jsonl.flush()
            med = linha.get("medida") or {}
            print(caso, linha.get("nota"), linha.get("reprovadas"), med.get("ocultos"), linha.get("erro", ""), flush=True)
    app.exitQgis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
