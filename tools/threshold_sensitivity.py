#!/usr/bin/env python3
"""Análise de sensibilidade dos limiares do regulamento e do compositor.

O SIGMAI decide com números que ninguém mediu num experimento perceptual:
ΔE*ab < 15 para cores confundíveis, 5 % de cobertura para uma faixa vazia,
6 pt de fonte mínima, 15 % a 45 % do quadro para a barra de escala, penalidades
de 15/5/1,5 pontos, cortes de nota em 92/80/62/40, ganho de 12 % para trocar a
orientação ou o arranjo, margem efetiva de 25 %, expoente 0,62 das fontes,
custo 0,35 por célula vazia. Este script responde à pergunta que uma banca
faz — "por que 15 e não 10 ou 20?" — da única forma honesta disponível sem
leitores: mostrando em que faixa de cada limiar as decisões sobre os mapas de
teste NÃO mudam, e onde mudam.

Duas fases:

  1. ``--data <pasta _teste_sigmai> --out <dir>`` (precisa de PyQGIS): compõe a
     matriz de composição da bateria de liberação (4 templates × 4 páginas ×
     2 orientações × 4 variações, em PNG) e os casos da matriz de dados, e grava
     ``observacoes.json`` com a observação que o inspetor entregou ao regulamento
     para cada mapa, o laudo de referência e as extensões dos dados no CRS do mapa.

  2. ``--analyse <dir>`` (Python puro): re-pontua cada observação variando um
     limiar de cada vez e conta quantos mapas mudam de nota; e, para os
     parâmetros do compositor (ganho de troca, margem efetiva, expoente das
     fontes, custo por célula vazia), recalcula as decisões com as funções
     puras de ``layoutgrid`` e ``scaling``. Grava ``sensibilidade.json`` e
     ``LEIAME.md``.

Uso:
    xvfb-run -a python3.12 tools/threshold_sensitivity.py --data ../_teste_sigmai --out saida
    python3 tools/threshold_sensitivity.py --analyse saida
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEMPLATES = ("cientifico", "publicacao", "relatorio_ambiental", "minimalista")
PAGES = ("A4", "A3", "A5", "LETTER")
ORIENTATIONS = ("landscape", "portrait")


# ---------------------------------------------------------------------------
# Fase 1 — composição (PyQGIS)
# ---------------------------------------------------------------------------

def _data_extent_in(layers: list[Any], crs_id: str) -> dict[str, float]:
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRectangle

    target = QgsCoordinateReferenceSystem(crs_id)
    union: QgsRectangle | None = None
    for layer in layers:
        transform = QgsCoordinateTransform(layer.crs(), target, QgsProject.instance())
        rect = transform.transformBoundingBox(layer.extent())
        if union is None:
            union = QgsRectangle(rect)
        else:
            union.combineExtentWith(rect)
    assert union is not None
    return {"width": union.width(), "height": union.height(), "crs": crs_id}


def compose_phase(data: Path, out: Path) -> None:
    from tools.release_battery import carregar_dados
    from sigmai.cartography.compose import compose_map, CompositionError

    out.mkdir(parents=True, exist_ok=True)
    camadas = carregar_dados(data)
    registros: list[dict[str, Any]] = []
    extras = ({}, {"include_grid": False}, {"include_legend": False}, {"include_inset": True, "inset_layer_ids": [camadas["uf"].id()]})
    base = {"layer_ids": [camadas["municipios"].id(), camadas["parque"].id()], "subject_layer_id": camadas["parque"].id(),
            "title": "Matriz", "data_source": "IBGE 2024; CEUC", "map_author": "Sensibilidade", "confirm_overwrite": True, "dpi": 72}
    combinacoes = list(itertools.product(TEMPLATES, PAGES, ORIENTATIONS, range(len(extras))))
    inicio = time.time()
    for indice, (template, pagina, orientacao, extra_i) in enumerate(combinacoes):
        rotulo = f"matriz/{template}/{pagina} {orientacao}/extra{extra_i}"
        arquivo = out / f"m_{indice}.png"
        r = compose_map({**base, **extras[extra_i], "template": template, "page": f"{pagina} {orientacao}",
                         "format": "png", "output_path": str(arquivo)}, {"dry_run": False})
        registros.append(_registro(rotulo, r, base["layer_ids"], camadas))
    casos = {
        "linha (trilha)": {"layer_ids": [camadas["trilha"].id()]},
        "pontos GPX": {"layer_ids": [camadas["gpx"].id()]},
        "polígono KML": {"layer_ids": [camadas["parque"].id()]},
        "multipolígono (municípios)": {"layer_ids": [camadas["municipios"].id()]},
        "continental (estado inteiro)": {"layer_ids": [camadas["uf"].id(), camadas["municipios"].id()]},
        "assunto pequeno dentro de contexto grande": {"layer_ids": [camadas["uf"].id(), camadas["trilha"].id()], "subject_layer_id": camadas["trilha"].id()},
        "escala imposta": {"layer_ids": [camadas["parque"].id()], "scale": 250000},
        "rótulos pelo nome": {"layer_ids": [camadas["municipios"].id()], "label_field": "NM_MUN", "label_font_size": 6},
        "estado em A4 retrato (auto)": {"layer_ids": [camadas["uf"].id(), camadas["municipios"].id()], "page": "A4", "orientation": "auto"},
        "parque em A4 (auto) com inserto": {"layer_ids": [camadas["municipios"].id(), camadas["parque"].id()], "subject_layer_id": camadas["parque"].id(),
                                             "page": "A4", "orientation": "auto", "include_inset": True, "inset_layer_ids": [camadas["uf"].id()]},
    }
    for i, (rotulo, params) in enumerate(casos.items()):
        arquivo = out / f"d_{i}.png"
        try:
            r = compose_map({"title": rotulo, "data_source": "teste", "map_author": "Sensibilidade", "confirm_overwrite": True,
                             "dpi": 72, "format": "png", "output_path": str(arquivo), **params}, {"dry_run": False})
        except CompositionError as exc:
            print(f"  recusa {rotulo}: {exc}")
            continue
        registros.append(_registro("dados/" + rotulo, r, params["layer_ids"], camadas))
    # Extensões dos conjuntos de dados nos CRS que o compositor escolheu, para a
    # análise pura do ganho de troca de orientação/arranjo.
    conjuntos = {
        "estado (UF + municípios)": [camadas["uf"], camadas["municipios"]],
        "parque + municípios": [camadas["municipios"], camadas["parque"]],
        "parque": [camadas["parque"]],
        "trilha": [camadas["trilha"]],
    }
    extensoes = {}
    for nome, layers in conjuntos.items():
        crs = next((reg["map_crs"] for reg in registros if set(reg["layer_ids"]) == {l.id() for l in layers}), "EPSG:5880")
        extensoes[nome] = _data_extent_in(layers, crs)
    (out / "observacoes.json").write_text(json.dumps({
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duracao_s": round(time.time() - inicio, 1),
        "mapas": registros,
        "extensoes": extensoes,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(registros)} mapas compostos em {time.time() - inicio:.0f} s → {out / 'observacoes.json'}")


def _registro(rotulo: str, r: dict[str, Any], layer_ids: list[str], camadas: dict[str, Any]) -> dict[str, Any]:
    audit = r["audit"]
    return {
        "rotulo": rotulo,
        "layer_ids": list(layer_ids),
        "map_crs": r.get("map_crs"),
        "template": r.get("template"),
        "arrangement": r.get("arrangement"),
        "page": r.get("page"),
        "scale_denominator": r.get("scale_denominator"),
        "extent": r.get("extent"),
        "observation": audit["observation"],
        "baseline": {"score": audit["score"], "grade": audit["grade"],
                     "fails": sorted(e["id"] for e in audit["results"] if e["status"] == "fail")},
    }


# ---------------------------------------------------------------------------
# Fase 2 — análise (Python puro)
# ---------------------------------------------------------------------------

def _reevaluate(observations: list[dict[str, Any]], patches: dict[str, Any]) -> list[dict[str, Any]]:
    """Re-pontua todas as observações com os limiares alterados (e restaura)."""
    from sigmai.cartography import rulebook, vision

    saved: dict[str, Any] = {}
    try:
        for name, value in patches.items():
            module, attr = (vision, name[7:]) if name.startswith("vision.") else (rulebook, name)
            saved[name] = getattr(module, attr)
            setattr(module, attr, value)
        if "vision.CONFUSABLE_DELTA_E" in patches:
            # o valor padrão do parâmetro foi congelado na definição da função
            original = vision.confusable_pairs
            saved["vision.confusable_pairs"] = original
            limiar = patches["vision.CONFUSABLE_DELTA_E"]
            vision.confusable_pairs = lambda colours, threshold=limiar: original(colours, threshold)
        out = []
        for reg in observations:
            laudo = rulebook.evaluate(reg["observation"])
            out.append({"score": laudo["score"], "grade": laudo["grade"],
                        "fails": sorted(e["id"] for e in laudo["results"] if e["status"] == "fail")})
        return out
    finally:
        for name, value in saved.items():
            if name == "vision.confusable_pairs":
                vision.confusable_pairs = value
            else:
                module, attr = (vision, name[7:]) if name.startswith("vision.") else (rulebook, name)
                setattr(module, attr, value)


AUDIT_SWEEPS: dict[str, tuple[str, list[Any]]] = {
    # nome do limiar: (regra afetada, valores varridos — o valor atual está entre eles)
    "vision.CONFUSABLE_DELTA_E": ("CART070", [5.0, 8.0, 10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0]),
    "FRAME_BAND_EMPTY_MAX": ("CART069", [0.01, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20]),
    "MIN_PRINT_FONT_PT": ("CART044", [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]),
    "SCALEBAR_MIN_FRACTION": ("CART022", [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]),
    "SCALEBAR_MAX_FRACTION": ("CART022", [0.30, 0.35, 0.40, 0.45, 0.50, 0.60]),
    "MAP_DOMINANCE_MIN": ("CART043", [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60]),
    "OVERLAY_MAX_SURROUNDINGS_INK": ("CART042", [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]),
    "LEGEND_OVERFLOW_TOLERANCE_MM": ("CART072", [0.0, 0.1, 0.25, 0.5, 1.0, 2.0]),
    "INSET_MIN_COVERAGE": ("CART067", [0.80, 0.85, 0.90, 0.95, 0.98, 1.0]),
}

PENALTY_SWEEPS = {
    "error": [10.0, 12.0, 15.0, 18.0, 20.0, 25.0],
    "warning": [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0],
    "advice": [0.5, 1.0, 1.5, 2.0, 3.0],
}


def analyse_audit(observations: list[dict[str, Any]]) -> dict[str, Any]:
    from sigmai.cartography import rulebook, vision

    base = _reevaluate(observations, {})
    for reg, b in zip(observations, base):
        if (b["grade"], b["fails"]) != (reg["baseline"]["grade"], reg["baseline"]["fails"]):
            raise SystemExit(f"a re-pontuação não reproduz o laudo gravado em {reg['rotulo']}: {b} vs {reg['baseline']}")
    n = len(observations)
    resultado: dict[str, Any] = {"n_mapas": n, "limiares": {}, "penalidades": {}, "notas": {}}
    for name, (rule, values) in AUDIT_SWEEPS.items():
        current = getattr(vision, name[7:]) if name.startswith("vision.") else getattr(rulebook, name)
        linhas = []
        for value in values:
            novo = _reevaluate(observations, {name: value})
            mudam = sum(1 for a, b in zip(base, novo) if a["grade"] != b["grade"])
            disparos = sum(1 for b in novo if rule in b["fails"])
            linhas.append({"valor": value, "atual": math.isclose(value, current), "mapas_com_regra_reprovada": disparos,
                           "mapas_que_mudam_de_nota": mudam})
        resultado["limiares"][name] = {"regra": rule, "valor_atual": current, "varredura": linhas}
    for sev, values in PENALTY_SWEEPS.items():
        linhas = []
        for value in values:
            pen = dict(rulebook.SEVERITY_PENALTY); pen[sev] = value
            novo = _reevaluate(observations, {"SEVERITY_PENALTY": pen})
            mudam = sum(1 for a, b in zip(base, novo) if a["grade"] != b["grade"])
            linhas.append({"valor": value, "atual": math.isclose(value, rulebook.SEVERITY_PENALTY[sev]), "mapas_que_mudam_de_nota": mudam})
        resultado["penalidades"][sev] = linhas
    # Distribuição das pontuações: onde os cortes de nota cairiam.
    scores = sorted(b["score"] for b in base)
    resultado["notas"] = {
        "distribuicao": {g: sum(1 for b in base if b["grade"] == g) for g in "ABCDE"},
        "pontuacoes": scores,
        "cortes_A": {str(c): sum(1 for b in base if b["score"] >= c and not _tem_erro(b)) for c in (85, 88, 90, 92, 94, 96, 98)},
        "cortes_B": {str(c): sum(1 for b in base if b["score"] >= c and not _tem_erro(b)) for c in (70, 75, 80, 85)},
    }
    return resultado


def _tem_erro(laudo: dict[str, Any]) -> bool:
    from sigmai.cartography.rulebook import RULES_BY_ID, SEVERITY_ERROR
    return any(RULES_BY_ID[i].severity == SEVERITY_ERROR for i in laudo["fails"])


def analyse_composer(extensoes: dict[str, dict[str, float]], mapas: list[dict[str, Any]]) -> dict[str, Any]:
    from sigmai.cartography import layoutgrid, scaling
    from sigmai.cartography.pagespec import resolve_page

    out: dict[str, Any] = {}
    # 1. Ganho de troca (orientação e arranjo): razões observadas nos conjuntos de teste.
    ganhos = []
    for nome, ext in extensoes.items():
        for template in TEMPLATES:
            for pagina in PAGES:
                for orient in ORIENTATIONS:
                    for inset in (False, True):
                        page = resolve_page(pagina, orient)
                        req = dict(page=page, template=template, include_inset=inset)
                        plano = layoutgrid.solve_layout(**req)
                        frame = plano.map_frame()
                        fator = max(ext["width"] / frame.width, ext["height"] / frame.height)
                        outro = "faixa_inferior" if plano.arrangement == "coluna_lateral" else "coluna_lateral"
                        alt = layoutgrid.solve_layout(**{**req, "arrangement": outro}).map_frame()
                        fator_alt = max(ext["width"] / alt.width, ext["height"] / alt.height)
                        flipped = "portrait" if orient == "landscape" else "landscape"
                        alt_o = layoutgrid.solve_layout(**{**req, "page": resolve_page(pagina, flipped)}).map_frame()
                        fator_o = max(ext["width"] / alt_o.width, ext["height"] / alt_o.height)
                        ganhos.append({"dados": nome, "template": template, "pagina": f"{pagina} {orient}", "inserto": inset,
                                       "arranjo_atual": plano.arrangement,
                                       "ganho_arranjo": round(fator / fator_alt, 4), "ganho_orientacao": round(fator / fator_o, 4)})
    limiares = [1.00, 1.05, 1.08, 1.10, 1.12, 1.15, 1.20, 1.25, 1.30]
    decisoes = []
    for g in limiares:
        trocas_arr = sum(1 for x in ganhos if x["ganho_arranjo"] >= g)
        trocas_ori = sum(1 for x in ganhos if x["ganho_orientacao"] >= g)
        decisoes.append({"limiar": g, "atual": math.isclose(g, 1.12), "trocas_de_arranjo": trocas_arr, "trocas_de_orientacao": trocas_ori})
    valores = sorted({x["ganho_arranjo"] for x in ganhos} | {x["ganho_orientacao"] for x in ganhos})
    out["ganho_de_troca"] = {"casos": len(ganhos), "decisoes": decisoes,
                             "ganhos_entre_1_05_e_1_30": [v for v in valores if 1.05 <= v <= 1.30],
                             "detalhe": ganhos}
    # 2. Margem efetiva máxima: com que frequência a série é abandonada.
    margens = [10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]
    linhas = []
    for tol in margens:
        abandonos = 0
        escalas_mudam = 0
        for reg in mapas:
            ext = reg.get("extent") or {}
            raw = ext.get("raw_scale_denominator")
            if not raw or "escala imposta" in reg["rotulo"]:
                continue  # escala pedida pelo usuário não passa pela série
            minimo = raw / 1.10  # margem pedida de 5 %: alvo = mínimo × (1 + 2 × 0,05)
            escala, base = scaling.choose_publication_scale(minimo, raw, tol)
            if base == "dois_algarismos_significativos":
                abandonos += 1
            if escala != reg["scale_denominator"]:
                escalas_mudam += 1
        linhas.append({"valor_pct": tol, "atual": math.isclose(tol, scaling.MAX_EFFECTIVE_MARGIN_PERCENT),
                       "series_abandonadas": abandonos, "escalas_diferentes_da_atual": escalas_mudam})
    out["margem_efetiva_maxima"] = {"mapas": sum(1 for r in mapas if (r.get("extent") or {}).get("raw_scale_denominator") and "escala imposta" not in r["rotulo"]), "varredura": linhas}
    # 3. Expoente das fontes.
    fontes = {"title": 16.0, "subtitle": 10.0, "legend": 7.0, "credits": 6.0}
    expoentes = [0.4, 0.5, 0.62, 0.7, 0.8, 1.0]
    linhas = []
    saved = layoutgrid.FONT_SCALE_EXPONENT
    try:
        for e in expoentes:
            layoutgrid.FONT_SCALE_EXPONENT = e
            por_pagina = {}
            for pagina in ("A5", "A4", "A3", "A2", "A1", "A0"):
                page = resolve_page(pagina, "landscape")
                por_pagina[pagina] = layoutgrid._scale_fonts(fontes, page)
            linhas.append({"expoente": e, "atual": math.isclose(e, 0.62), "fontes_por_pagina": por_pagina,
                           "abaixo_de_6pt_em_A5": any(v < 6.0 for v in por_pagina["A5"].values())})
    finally:
        layoutgrid.FONT_SCALE_EXPONENT = saved
    out["expoente_das_fontes"] = {"fontes_de_referencia_A4_paisagem": fontes, "varredura": linhas}
    # 4. Custo por célula vazia na grade de painéis.
    custos = [0.0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0]
    quadros = {"A4 paisagem": (270.0, 150.0), "A4 retrato": (190.0, 250.0), "A3 paisagem": (390.0, 240.0), "A3 retrato": (280.0, 360.0)}
    linhas = []
    saved = layoutgrid.EMPTY_CELL_PENALTY
    try:
        for c in custos:
            layoutgrid.EMPTY_CELL_PENALTY = c
            grades = {f"{n} painéis / {nome}": "x".join(map(str, layoutgrid.panel_grid(n, w, h, 6.0)))
                      for n in (3, 4, 5, 6) for nome, (w, h) in quadros.items()}
            linhas.append({"custo": c, "atual": math.isclose(c, 0.35), "grades": grades})
    finally:
        layoutgrid.EMPTY_CELL_PENALTY = saved
    out["custo_por_celula_vazia"] = {"varredura": linhas}
    return out


CLASSIC_PAIRS = {
    # os três primeiros são os pares em que o limiar foi calibrado (tests/test_rules_from_experiment.py)
    "vermelho × verde (#FF0000 × #00A000)": ("#FF0000", "#00A000"),
    "vermelho-escuro × verde-escuro": ("#8B0000", "#006400"),
    "laranja × lima": ("#FF6600", "#66CC00"),
    "vermelho × verde puros (luminosidades distintas)": ("#FF0000", "#00FF00"),
    "azul × roxo": ("#0000FF", "#800080"),
    "verde × castanho": ("#2E8B57", "#8B4513"),
    "azul-claro × rosa": ("#ADD8E6", "#FFC0CB"),
    "amarelo × verde-limão": ("#FFFF00", "#BFFF00"),
}


def analyse_palette() -> dict[str, Any]:
    """ΔE*ab mínimo (visão normal e nas três dicromacias) para os pares da paleta.

    Os mapas de teste nunca reprovam em CART070 — a paleta foi desenhada para
    passar —, então a sensibilidade do limiar ΔE < 15 tem de ser lida nas
    próprias cores: os pares da sequência atual de preenchimentos, a paleta
    anterior (Okabe & Ito clareada em 82 %), a paleta de Okabe & Ito pura e os
    pares clássicos que a literatura de acessibilidade usa como exemplo.
    """
    from sigmai.cartography import vision
    from sigmai.cartography.symbology import POLYGON_FILLS, _tint

    conjuntos = {
        "preenchimentos atuais (POLYGON_FILLS)": [(f"cor {i + 1}", _tint(h, t)) for i, (h, t) in enumerate(POLYGON_FILLS)],
        "paleta anterior (Okabe & Ito clareada 82 %)": [(f"cor {i + 1}", _tint(h, 0.82)) for i, h in enumerate(vision.OKABE_ITO)],
        "Okabe & Ito (2008) pura": [(f"cor {i + 1}", h) for i, h in enumerate(vision.OKABE_ITO)],
        "pares clássicos": [],
    }
    saida: dict[str, Any] = {}
    for nome, cores in conjuntos.items():
        pares = []
        if nome == "pares clássicos":
            itens = [(rotulo, a, b) for rotulo, (a, b) in CLASSIC_PAIRS.items()]
        else:
            itens = [(f"{na} × {nb}", ha, hb) for (na, ha), (nb, hb) in itertools.combinations(cores, 2)]
        for rotulo, ha, hb in itens:
            ra, rb = vision.parse_hex(ha), vision.parse_hex(hb)
            normal = vision.delta_e(ra, rb)
            sims = {d: vision.delta_e(vision.simulate(ra, d), vision.simulate(rb, d)) for d in vision.CVD_MATRICES}
            pior = min(sims, key=sims.get)
            pares.append({"par": rotulo, "cores": [ha, hb], "dE_normal": round(normal, 1), "dE_min_simulado": round(sims[pior], 1), "pior": pior})
        pares.sort(key=lambda x: x["dE_min_simulado"])
        limiares = [5.0, 8.0, 10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0]
        saida[nome] = {"pares": pares, "n_pares": len(pares),
                       "marcados_por_limiar": {f"{l:g}": sum(1 for x in pares if x["dE_min_simulado"] < l) for l in limiares}}
    return saida


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    fmt = lambda v: (f"{v:g}" if isinstance(v, float) else str(v))
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(fmt(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def write_readme(out: Path, dados: dict[str, Any], audit: dict[str, Any], comp: dict[str, Any], paleta: dict[str, Any]) -> None:
    n = audit["n_mapas"]
    partes = [
        "# Sensibilidade dos limiares do regulamento e do compositor",
        "",
        f"Gerado por `tools/threshold_sensitivity.py` em {dados['gerado_em']} sobre **{n} mapas** compostos com os dados de "
        "teste (`_teste_sigmai`: malha municipal e limite do Piauí, PE das Carnaúbas, trilha do Itaguaré): a matriz de "
        "composição da bateria de liberação (4 templates × 4 páginas × 2 orientações × 4 variações) e os casos da matriz de dados.",
        "",
        "Cada limiar foi variado sozinho, com os demais no valor atual, re-pontuando a **mesma observação** que o inspetor "
        "entregou ao regulamento (nenhum mapa foi recomposto). As colunas dizem em quantos mapas a regra reprova e em quantos "
        "a **nota** (A–E) muda em relação ao laudo atual. Um limiar é estável quando a coluna \"mudam de nota\" fica em zero "
        "numa vizinhança do valor atual; onde ela sobe, o valor escolhido está de fato decidindo algo, e a escolha precisa ser "
        "defendida por outro meio (leitores, norma, periódico).",
        "",
        f"Distribuição das notas no laudo atual: " + ", ".join(f"{g} = {c}" for g, c in audit["notas"]["distribuicao"].items()) + ".",
        "",
        "## Limiares do regulamento",
        "",
    ]
    for name, info in audit["limiares"].items():
        rows = [[("**%g**" % l["valor"]) if l["atual"] else l["valor"], l["mapas_com_regra_reprovada"], l["mapas_que_mudam_de_nota"]]
                for l in info["varredura"]]
        partes += [f"### `{name}` — {info['regra']} (atual: {info['valor_atual']:g})", "",
                   _md_table(["valor", "mapas com a regra reprovada", "mapas que mudam de nota"], rows), ""]
    partes += ["### O limiar ΔE*ab < 15 lido nas cores", "",
               "Nenhum mapa de teste reprova em CART070 em limiar algum — a paleta foi desenhada para passar. A sensibilidade "
               "do limiar está nas cores: ΔE*ab mínimo entre as três simulações de dicromacia (Machado et al. 2009, severidade "
               "1,0) para cada par, e quantos pares cada limiar marcaria como confundíveis.", ""]
    limiares = list(next(iter(paleta.values()))["marcados_por_limiar"].keys())
    partes += [_md_table(["conjunto", "pares"] + [("**" + l + "**") if l == "15" else l for l in limiares],
                         [[nome, info["n_pares"]] + [info["marcados_por_limiar"][l] for l in limiares] for nome, info in paleta.items()]), ""]
    for nome, info in paleta.items():
        partes += [f"Pares de menor ΔE em *{nome}*: " + "; ".join(
            f"{x['par']} ({x['cores'][0]} × {x['cores'][1]}) ΔE {x['dE_min_simulado']:g} sob {x['pior']} (normal {x['dE_normal']:g})"
            for x in info["pares"][:4]) + ".", ""]
    partes += ["## Penalidades por severidade", ""]
    for sev, linhas in audit["penalidades"].items():
        rows = [[("**%g**" % l["valor"]) if l["atual"] else l["valor"], l["mapas_que_mudam_de_nota"]] for l in linhas]
        partes += [f"### `{sev}`", "", _md_table(["penalidade", "mapas que mudam de nota"], rows), ""]
    partes += ["## Cortes de nota", "",
               "Mapas sem regra de erro reprovada que receberiam A para cada corte: " +
               ", ".join(f"≥{c}: {v}" for c, v in audit["notas"]["cortes_A"].items()) + ".", "",
               "Mapas sem erro que receberiam pelo menos B para cada corte: " +
               ", ".join(f"≥{c}: {v}" for c, v in audit["notas"]["cortes_B"].items()) + ".", "",
               "Pontuações observadas: " + ", ".join(f"{s:g}" for s in sorted(set(audit["notas"]["pontuacoes"]))) + ".", ""]
    g = comp["ganho_de_troca"]
    partes += ["## Compositor", "",
               f"### Ganho mínimo para trocar orientação ou arranjo (`LAYOUT_SWITCH_GAIN`, atual 1,12)", "",
               f"{g['casos']} combinações de conjunto de dados × template × página × orientação × inserto, com as extensões reais "
               "dos dados no CRS escolhido pelo compositor. Trocas que cada limiar autorizaria:", "",
               _md_table(["limiar", "trocas de arranjo", "trocas de orientação"],
                         [[("**%g**" % d["limiar"]) if d["atual"] else d["limiar"], d["trocas_de_arranjo"], d["trocas_de_orientacao"]] for d in g["decisoes"]]),
               "", "Razões de ganho observadas entre 1,05 e 1,30 (onde um limiar diferente mudaria a decisão): " +
               (", ".join(f"{v:g}" for v in g["ganhos_entre_1_05_e_1_30"]) or "nenhuma") + ".", ""]
    m = comp["margem_efetiva_maxima"]
    partes += [f"### Margem efetiva máxima (`MAX_EFFECTIVE_MARGIN_PERCENT`, atual 25 %) — {m['mapas']} mapas", "",
               _md_table(["tolerância (%)", "séries abandonadas", "escalas diferentes da atual"],
                         [[("**%g**" % l["valor_pct"]) if l["atual"] else l["valor_pct"], l["series_abandonadas"], l["escalas_diferentes_da_atual"]] for l in m["varredura"]]), ""]
    e = comp["expoente_das_fontes"]
    partes += ["### Expoente da escala das fontes (`FONT_SCALE_EXPONENT`, atual 0,62)", "",
               "Corpo da legenda (7 pt em A4 paisagem) e do título (16 pt) por página:", "",
               _md_table(["expoente", "A5", "A4", "A3", "A2", "A0", "legenda < 6 pt em A5"],
                         [[("**%g**" % l["expoente"]) if l["atual"] else l["expoente"]] +
                          [f"{l['fontes_por_pagina'][p]['legend']:g} / {l['fontes_por_pagina'][p]['title']:g}" for p in ("A5", "A4", "A3", "A2", "A0")] +
                          ["sim" if l["abaixo_de_6pt_em_A5"] else "não"] for l in e["varredura"]]), ""]
    c = comp["custo_por_celula_vazia"]
    chaves = list(c["varredura"][0]["grades"].keys())
    partes += ["### Custo por célula vazia na grade de painéis (`EMPTY_CELL_PENALTY`, atual 0,35)", "",
               _md_table(["custo"] + chaves, [[("**%g**" % l["custo"]) if l["atual"] else l["custo"]] + [l["grades"][k] for k in chaves] for l in c["varredura"]]), ""]
    (out / "LEIAME.md").write_text("\n".join(partes), encoding="utf-8")


def analyse_phase(out: Path) -> None:
    dados = json.loads((out / "observacoes.json").read_text(encoding="utf-8"))
    audit = analyse_audit(dados["mapas"])
    comp = analyse_composer(dados["extensoes"], dados["mapas"])
    paleta = analyse_palette()
    (out / "sensibilidade.json").write_text(json.dumps({"auditoria": audit, "compositor": comp, "paleta": paleta}, ensure_ascii=False, indent=1), encoding="utf-8")
    write_readme(out, dados, audit, comp, paleta)
    print(f"análise gravada em {out / 'sensibilidade.json'} e {out / 'LEIAME.md'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", help="pasta _teste_sigmai (fase de composição, precisa de PyQGIS)")
    parser.add_argument("--out", help="pasta de saída da composição")
    parser.add_argument("--analyse", help="pasta com observacoes.json (fase de análise, Python puro)")
    args = parser.parse_args()
    if args.analyse:
        analyse_phase(Path(args.analyse))
        return 0
    if not (args.data and args.out):
        parser.error("informe --data e --out (composição) ou --analyse (análise)")
    from qgis.core import QgsApplication

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    from tools.qgis_lifecycle import shutdown_qgis

    try:
        compose_phase(Path(args.data), Path(args.out))
    finally:
        shutdown_qgis(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
