"""Tabelas do LEIAME a partir de ``resultados/``. Python puro, sem QGIS.

    python tabelar.py [--resultados resultados]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def ler(pasta: Path) -> list[dict]:
    return [json.loads(linha) for linha in (pasta / "resultados.jsonl").read_text(encoding="utf-8").splitlines() if linha]


def mil(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def dec(x: float, casas: int | None = None) -> str:
    return (f"{x:g}" if casas is None else f"{x:.{casas}f}").replace(".", ",")


def pct(x: float) -> str:
    return f"{round(x * 100)} %"


def nota(r: dict) -> str:
    falhas = ", ".join(sorted(r["reprovadas"]))
    return f"{r['nota']}" + (f" ({falhas})" if falhas else "")


def simbolo(tamanho: float, opacidade: float) -> str:
    return f"{dec(tamanho)} mm, {pct(opacidade)}"


def fase1(res: Path) -> None:
    antes = {(r["tipo"], r["n"], r["figura"]): r for r in ler(res / "1.2.0_qgis4" / "fase1")}
    depois = {(r["tipo"], r["n"], r["figura"]): r for r in ler(res / "1.3.0_qgis4" / "fase1")}
    qgis3 = {(r["tipo"], r["n"], r["figura"]): r for r in ler(res / "1.3.0_qgis3" / "fase1")}
    for figura in ("A5", "col88"):
        print(f"\n### Fase 1, {figura}\n")
        print("| Conjunto | Pontos | 1.2.0: nota | 1.2.0: ocultos | 1.3.0: símbolo | 1.3.0: nota | 1.3.0: ocultos "
              "| Assunto à vista, 1.2.0 → 1.3.0 |")
        print("|---|---:|---|---:|---|---|---:|---|")
        for chave in sorted(depois, key=lambda k: (k[0], k[1])):
            if chave[2] != figura:
                continue
            a, d = antes[chave], depois[chave]
            print(f"| {chave[0]} | {mil(chave[1])} | {nota(a)} | {pct(a['medida']['ocultos'])} | "
                  f"{simbolo(d['simbolo_mm'], d['opacidade'])} | {nota(d)} | {pct(d['medida']['ocultos'])} | "
                  f"{pct(a['assunto_visivel'])} → {pct(d['assunto_visivel'])} |")
    diferentes = [k for k in depois if (depois[k]["nota"], sorted(depois[k]["reprovadas"]), depois[k]["simbolo_mm"])
                  != (qgis3[k]["nota"], sorted(qgis3[k]["reprovadas"]), qgis3[k]["simbolo_mm"])]
    print(f"\nQGIS 3.40 × 4.0, 1.3.0: {len(depois) - len(diferentes)} de {len(depois)} mapas com a mesma nota, "
          f"as mesmas reprovações e o mesmo símbolo.")
    for k in diferentes:
        d, q = depois[k], qgis3[k]
        print(f"- {k[0]} {mil(k[1])} {k[2]}: QGIS 4 {simbolo(d['simbolo_mm'], d['opacidade'])}, nota {nota(d)}, quadro "
              f"{dec(d['quadro_mm'][1])} mm de altura; QGIS 3 {simbolo(q['simbolo_mm'], q['opacidade'])}, nota {nota(q)}, "
              f"quadro {dec(q['quadro_mm'][1])} mm de altura.")


def fase2(res: Path) -> None:
    linhas = ler(res / "1.3.0_qgis4" / "fase2")
    print("\n### Fase 2, A5: símbolo fixado à mão (nota; ocultos; assunto à vista)\n")
    conjuntos = sorted({(r["tipo"], r["n"]) for r in linhas})
    print("| Variante | " + " | ".join(f"{t} {mil(n)}" for t, n in conjuntos) + " |")
    print("|---|" + "---|" * len(conjuntos))
    variantes = []
    for r in linhas:
        v = json.dumps(r["variante"], sort_keys=True)
        if v not in variantes:
            variantes.append(v)
    for v in variantes:
        var = json.loads(v)
        if var["tipo"] == "pontos":
            rotulo = simbolo(var["tamanho"], var["opacidade"])
        elif var["tipo"] == "calor":
            rotulo = f"calor, raio {dec(var['raio'])} mm"
        else:
            rotulo = "um símbolo por local"
        celulas = []
        for t, n in conjuntos:
            r = next(x for x in linhas if (x["tipo"], x["n"]) == (t, n) and json.dumps(x["variante"], sort_keys=True) == v)
            ocultos = pct(r["medida"]["ocultos"]) if var["tipo"] == "pontos" else "—"
            celulas.append(f"{nota(r)}; {ocultos}; {pct(r['assunto_visivel'])}")
        print(f"| {rotulo} | " + " | ".join(celulas) + " |")


def fase3(res: Path) -> None:
    linhas = ler(res / "1.3.0_qgis4" / "fase3")
    rotulos = {"padrao": "compositor (símbolo adaptado)", "locais_sigmai": "count_points_by_site + proporcional",
               "locais_escala": "idem, locais agrupados na escala do mapa", "calor": "apply_heatmap_style, raio 3 mm"}
    print("\n### Fase 3, A5: comandos da 1.3.0, assunto só os pontos (nota)\n")
    conjuntos = sorted({(r["tipo"], r["n"]) for r in linhas})
    print("| Forma | " + " | ".join(f"{t} {mil(n)}" for t, n in conjuntos) + " |")
    print("|---|" + "---|" * len(conjuntos))
    for tipo, rotulo in rotulos.items():
        celulas = [nota(next(x for x in linhas if (x["tipo"], x["n"]) == c and x["variante"]["tipo"] == tipo)) for c in conjuntos]
        print(f"| {rotulo} | " + " | ".join(celulas) + " |")
    locais = [x for x in linhas if x["variante"]["tipo"] in ("locais_sigmai", "locais_escala") and x.get("locais")]
    if locais:
        print("\n| Conjunto | Pontos | Locais (coordenada exata) | Locais (na escala) | Escala | CART076, coordenada exata |")
        print("|---|---:|---:|---:|---|---|")
        for t, n in conjuntos:
            exata = next((x for x in locais if (x["tipo"], x["n"]) == (t, n) and x["variante"]["tipo"] == "locais_sigmai"), None)
            escala = next((x for x in locais if (x["tipo"], x["n"]) == (t, n) and x["variante"]["tipo"] == "locais_escala"), None)
            if exata and escala:
                print(f"| {t} | {mil(n)} | {mil(exata['locais'])} | {mil(escala['locais'])} | "
                      f"1:{mil(escala['escala_dos_locais'])} | {exata.get('cart076')} |")


def calibracao(res: Path) -> None:
    medida = json.loads((res / "1.3.0_qgis4" / "calibracao" / "medida_x_auditoria.json").read_text(encoding="utf-8"))
    print("\n### Calibração: cobertura geométrica × parque à vista na auditoria renderizada\n")
    for rotulo, grupo in (("≤ 0,25", [m for m in medida if m["cobertura"] <= 0.25]),
                          ("> 0,25", [m for m in medida if m["cobertura"] > 0.25])):
        if not grupo:
            continue
        print(f"- {len(grupo)} mapas com cobertura {rotulo} (de {dec(min(m['cobertura'] for m in grupo), 2)} a "
              f"{dec(max(m['cobertura'] for m in grupo), 2)}): parque à vista de {pct(min(m['parque_visivel'] for m in grupo))} "
              f"a {pct(max(m['parque_visivel'] for m in grupo))}; CART075 reprovada em {sum(m['cart075'] == 'fail' for m in grupo)}.")
    escolhas = json.loads((res / "1.3.0_qgis4" / "calibracao" / "escolhas_do_compositor.json").read_text(encoding="utf-8"))
    print("\n### Símbolo que choose_point_symbol escolhe\n")
    print("| Conjunto | Pontos | A5 | ocultos; cobertura | coluna de 88 mm | ocultos; cobertura |")
    print("|---|---:|---|---|---|---|")
    por = {(e["tipo"], e["n"], e["figura"]): e for e in escolhas}
    for tipo, n in sorted({(e["tipo"], e["n"]) for e in escolhas}):
        celulas = []
        for fig in ("A5", "col88"):
            e = por[(tipo, n, fig)]
            alvo = "" if e["atingiu"] else " (fora do alvo)"
            celulas.append(f"{simbolo(e['tamanho'], e['opacidade'])}{alvo} | {pct(e['ocultos'])}; {dec(e['cobertura'], 2)}")
        print(f"| {tipo} | {mil(n)} | " + " | ".join(celulas) + " |")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resultados", default=str(Path(__file__).resolve().parent / "resultados"))
    res = Path(parser.parse_args().resultados)
    sys.stdout.reconfigure(encoding="utf-8")
    fase1(res)
    fase2(res)
    fase3(res)
    calibracao(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
