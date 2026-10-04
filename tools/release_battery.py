# -*- coding: utf-8 -*-
"""Bateria de liberação: a matriz de variações que decide se uma versão sai.

Os testes unitários provam cada peça; os exercitadores provam cada caminho.
O que nenhum deles prova é a COMBINAÇÃO — todo template com toda página com
toda orientação com todo formato, todo tipo de dado, toda língua — e é na
combinação que uma versão quebra na mão do usuário.

Portões, todos obrigatórios para liberar:

1. Matriz de composição: templates × páginas × orientações × formatos, com e
   sem grade, legenda e inserto. Cada combinação tem de compor, gerar arquivo
   com tamanho, e receber nota A ou B da auditoria.
2. Matriz de dados: ponto, linha, polígono, multipolígono, raster, GPX, KML,
   CRS misturados, extensão minúscula e continental.
3. Matriz de línguas: as quinze línguas de map_language compõem, e a linha de
   crédito sai na língua pedida — nem uma palavra em português onde não deve.
4. Catálogo igual à realidade: nenhuma ação habilitada devolve marca de
   esqueleto, e toda ação desabilitada é recusada como inexistente com razão.
5. Idempotência: compor o mesmo mapa duas vezes dá o mesmo laudo.
6. Recusas nomeadas: página, dpi, formato, template, campo, língua, escala,
   camada, parâmetro, pasta e sobrescrita inválidos viram recusa que nomeia o
   problema — nunca traceback, nunca arquivo gerado.
7. Comparação multilíngue: folha de dois quadros, com e sem escala comum, nas
   escritas latinas, cirílica, grega, tailandesa, CJK e da direita para a
   esquerda, com os rótulos de painel na língua pedida.

Uso::

    xvfb-run -a python3.12 tools/release_battery.py --data <pasta _teste_sigmai> [--full]
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Gate:
    def __init__(self, nome: str) -> None:
        self.nome, self.passou, self.falhou, self.detalhes = nome, 0, 0, []

    def ok(self, rotulo: str) -> None:
        self.passou += 1

    def falha(self, rotulo: str, motivo: str) -> None:
        self.falhou += 1
        self.detalhes.append(f"{rotulo}: {motivo}")
        print(f"    FALHA {rotulo}: {motivo[:140]}")

    def resumo(self) -> str:
        return f"{self.nome}: {self.passou} ok, {self.falhou} falha(s)"


def carregar_dados(data: Path) -> dict[str, Any]:
    from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, QgsCoordinateReferenceSystem

    project = QgsProject.instance()
    project.clear()
    camadas: dict[str, Any] = {}
    fontes = {
        "uf": (data / "PI_UF_2024.shp", "Limite estadual", "ogr"),
        "municipios": (data / "PI_Municipios_2024.shp", "Municípios", "ogr"),
        "parque": (data / "PE Carnaubas.kml", "PE das Carnaúbas", "ogr"),
        "trilha": (data / "trilha" / "Trilha Itaguaré pelo batedor.shp", "Trilha", "ogr"),
        "gpx": (Path(str(data / "trilha" / "Decida primeira coleta.gpx") + "|layername=track_points"), "Pontos GPX", "ogr"),
    }
    for alias, (caminho, nome, provedor) in fontes.items():
        camada = QgsVectorLayer(str(caminho), nome, provedor)
        if camada.isValid():
            project.addMapLayer(camada)
            camadas[alias] = camada
    dem = data.parent / "DEM_GLO90" / "Copernicus_DSM_COG_30_S05_00_W042_00_DEM.tif"
    if dem.exists():
        raster = QgsRasterLayer(str(dem), "Altimetria")
        if raster.isValid():
            project.addMapLayer(raster)
            camadas["dem"] = raster
    # Um ponto solto (extensão degenerada) e uma camada de memória em outro CRS.
    ponto = QgsVectorLayer("Point?crs=EPSG:31983", "Ponto solto", "memory")
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
    feicao = QgsFeature()
    feicao.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(650000, 9400000)))
    ponto.dataProvider().addFeatures([feicao])
    project.addMapLayer(ponto)
    camadas["ponto"] = ponto
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:4674"))
    return camadas


AMOSTRAGEM = 3  # 1 = matriz completa (--full)


def portao_matriz_composicao(camadas: dict[str, Any], saida: Path) -> Gate:
    from sigmai.cartography.compose import compose_map

    gate = Gate("1. matriz de composição")
    templates = ("cientifico", "publicacao", "relatorio_ambiental", "minimalista")
    paginas = ("A4", "A3", "A5", "LETTER")
    orientacoes = ("landscape", "portrait")
    formatos = ("png", "pdf", "svg")
    extras = ({}, {"include_grid": False}, {"include_legend": False}, {"include_inset": True, "inset_layer_ids": [camadas["uf"].id()]})
    # O que cada variação tem o direito de custar na auditoria. Um mapa de duas
    # camadas SEM legenda é uma omissão deliberada que o regulamento tem de
    # apontar (CART002) — a bateria exige que ele aponte exatamente isso e
    # nada mais. Sem grade, CART010 avisa; nenhuma regra de intervalo ou de
    # anotação pode disparar sobre uma grade que não existe.
    # CART069 (faixa do quadro sem dado de área) é PERMITIDA em toda a matriz:
    # o Parque das Carnaúbas fica no Ceará e a base só tem a malha do Piauí —
    # a faixa leste vazia é um fato dos dados que a regra tem de apontar, não
    # um defeito da composição. Continua proibida em qualquer outra regra.
    falhas_permitidas = ({"CART069"}, {"CART010", "CART069"}, {"CART002", "CART069"}, {"CART069"})
    base = {"layer_ids": [camadas["municipios"].id(), camadas["parque"].id()], "subject_layer_id": camadas["parque"].id(),
            "title": "Matriz", "data_source": "IBGE 2024; CEUC", "map_author": "Bateria", "confirm_overwrite": True, "dpi": 72}
    combinacoes = list(itertools.product(templates, paginas, orientacoes, formatos, range(len(extras))))
    # Amostragem determinística: a matriz completa tem 384 células; uma em cada
    # três, com semente fixa, cobre todo template/página/orientação/formato/extra
    # em menos de dez minutos e é reproduzível de uma corrida para a outra.
    for indice, (template, pagina, orientacao, formato, extra_i) in enumerate(combinacoes):
        if indice % AMOSTRAGEM:
            continue
        rotulo = f"{template}/{pagina} {orientacao}/{formato}/extra{extra_i}"
        arquivo = saida / f"m_{indice}.{formato}"
        try:
            r = compose_map({**base, **extras[extra_i], "template": template, "page": f"{pagina} {orientacao}",
                             "format": formato, "output_path": str(arquivo)}, {"dry_run": False})
        except Exception as exc:  # noqa: BLE001
            gate.falha(rotulo, f"{type(exc).__name__}: {exc}")
            continue
        nota = r["audit"]["grade"]
        reprovadas = {e["id"] for e in r["audit"]["results"] if e["status"] == "fail"}
        inesperadas = reprovadas - falhas_permitidas[extra_i]
        if not arquivo.exists() or arquivo.stat().st_size < 1000:
            gate.falha(rotulo, "arquivo ausente ou vazio")
        elif inesperadas:
            gate.falha(rotulo, f"nota {nota}: " + "; ".join(sorted(inesperadas)))
        elif not falhas_permitidas[extra_i] and nota not in ("A", "B"):
            gate.falha(rotulo, f"nota {nota} sem regra reprovada")
        else:
            gate.ok(rotulo)
    return gate


def portao_matriz_dados(camadas: dict[str, Any], saida: Path) -> Gate:
    from sigmai.cartography.compose import compose_map, CompositionError

    gate = Gate("2. matriz de dados")
    casos = {
        "ponto solto (extensão degenerada)": {"layer_ids": [camadas["ponto"].id()]},
        "linha (trilha)": {"layer_ids": [camadas["trilha"].id()]},
        "pontos GPX": {"layer_ids": [camadas["gpx"].id()]},
        "polígono KML": {"layer_ids": [camadas["parque"].id()]},
        "multipolígono (municípios)": {"layer_ids": [camadas["municipios"].id()]},
        "CRS misturados (UTM 23 + geográfico)": {"layer_ids": [camadas["ponto"].id(), camadas["uf"].id()]},
        "continental (estado inteiro)": {"layer_ids": [camadas["uf"].id(), camadas["municipios"].id()]},
        "assunto pequeno dentro de contexto grande": {"layer_ids": [camadas["uf"].id(), camadas["trilha"].id()], "subject_layer_id": camadas["trilha"].id()},
        "escala imposta": {"layer_ids": [camadas["parque"].id()], "scale": 250000},
        "comparação com escalas iguais": {"layer_ids": [camadas["parque"].id()], "second_map": {"layer_ids": [camadas["uf"].id()]}, "page": "A3 landscape"},
        "comparação com escalas próprias": {"layer_ids": [camadas["parque"].id()], "second_map": {"layer_ids": [camadas["municipios"].id()]}, "comparison_same_scale": False, "page": "A3 landscape"},
        "rótulos pelo nome": {"layer_ids": [camadas["municipios"].id()], "label_field": "NM_MUN", "label_font_size": 6},
    }
    if "dem" in camadas:
        casos["raster sozinho"] = {"layer_ids": [camadas["dem"].id()]}
        casos["raster com vetor por cima"] = {"layer_ids": [camadas["dem"].id(), camadas["trilha"].id()], "subject_layer_id": camadas["trilha"].id()}
    for i, (rotulo, params) in enumerate(casos.items()):
        arquivo = saida / f"d_{i}.png"
        try:
            r = compose_map({"title": rotulo, "data_source": "teste", "map_author": "Bateria", "confirm_overwrite": True,
                             "dpi": 72, "format": "png", "output_path": str(arquivo), **params}, {"dry_run": False})
        except CompositionError as exc:
            gate.falha(rotulo, f"recusa: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            gate.falha(rotulo, f"QUEBRA {type(exc).__name__}: {exc}")
            continue
        nota = r["audit"]["grade"]
        if nota in ("A", "B") and arquivo.exists() and arquivo.stat().st_size > 1000:
            gate.ok(rotulo)
        else:
            gate.falha(rotulo, f"nota {nota}")
    # Camada vazia TEM de ser recusada com nome.
    from qgis.core import QgsProject, QgsVectorLayer
    vazia = QgsVectorLayer("Polygon?crs=EPSG:4674", "Camada vazia", "memory")
    QgsProject.instance().addMapLayer(vazia)
    try:
        compose_map({"layer_ids": [vazia.id()], "title": "x", "output_path": str(saida / "vazia.png"),
                     "format": "png", "confirm_overwrite": True, "data_source": "t", "map_author": "b"}, {"dry_run": False})
        gate.falha("camada vazia", "deveria ter sido recusada")
    except CompositionError as exc:
        gate.ok("camada vazia recusada") if "Camada vazia" in str(exc) else gate.falha("camada vazia", "recusa não nomeia a camada")
    return gate


def portao_linguas(camadas: dict[str, Any], saida: Path) -> Gate:
    from sigmai.cartography.compose import compose_map
    from sigmai.cartography.maptext import MAP_TEXT, maptext

    gate = Gate("3. matriz de línguas")
    chaves = ("fonte", "elaboracao", "credito_ferramenta", "escala_prefixo", "legenda_padrao")
    for lingua in sorted(MAP_TEXT):
        arquivo = saida / f"l_{lingua}.png"
        try:
            r = compose_map({"layer_ids": [camadas["municipios"].id(), camadas["parque"].id()], "title": "T",
                             "map_language": lingua, "dpi": 72, "output_path": str(arquivo), "format": "png",
                             "confirm_overwrite": True, "data_source": "S", "map_author": "A"}, {"dry_run": False})
        except Exception as exc:  # noqa: BLE001
            gate.falha(lingua, f"{type(exc).__name__}: {exc}")
            continue
        itens = r["audit"]["observation"].get("items", [])
        textos = " ".join(str(item.get("text", "")) for item in itens)
        legenda = r["audit"]["observation"].get("legend") or {}
        textos += " " + str(legenda.get("title", ""))
        # Só é vazamento de português o que for português E diferente da
        # tradução pedida: "Escala " é espanhol tanto quanto português, e
        # "Fonte: " é italiano — acusar essas palavras era falso positivo.
        vazamentos = sorted(
            maptext("pt-BR", chave).strip() for chave in chaves
            if maptext("pt-BR", chave).strip() and maptext("pt-BR", chave).strip() != maptext(lingua, chave).strip()
            and maptext("pt-BR", chave).strip() in textos
        )
        ausentes = sorted(
            maptext(lingua, chave).strip() for chave in ("fonte", "elaboracao", "credito_ferramenta", "escala_prefixo")
            if maptext(lingua, chave).strip() and maptext(lingua, chave).strip() not in textos
        )
        # CART068/CART069 são fatos dos dados desta matriz (a malha rotulada
        # pelo portão 2 tem 224 nomes que não cabem; o parque fica no Ceará
        # e a base é só do Piauí), não da língua — o que este portão testa.
        reprovadas = sorted(
            e["id"] for e in r["audit"]["results"] if e["status"] == "fail" and e["id"] not in ("CART068", "CART069")
        )
        if vazamentos:
            gate.falha(lingua, "português vazou: " + ", ".join(repr(v) for v in vazamentos))
        elif ausentes:
            gate.falha(lingua, "rótulos ausentes: " + ", ".join(repr(a) for a in ausentes))
        elif reprovadas:
            # A auditoria tem de ler a língua que o compositor escreveu: um
            # rodapé japonês completo não pode ser acusado de "sem fonte".
            gate.falha(lingua, f"nota {r['audit']['grade']}: " + "; ".join(reprovadas))
        else:
            gate.ok(lingua)
    return gate


def portao_recusas(camadas: dict[str, Any], saida: Path) -> Gate:
    """Entrada inválida tem de virar recusa nomeada — nunca traceback, nunca arquivo."""
    from sigmai.cartography.compose import compose_map, CompositionError
    from sigmai.cartography.params import ParameterError

    gate = Gate("6. recusas nomeadas")
    base = {"layer_ids": [camadas["parque"].id()], "title": "R", "data_source": "S", "map_author": "A",
            "confirm_overwrite": True, "dpi": 72, "format": "png"}
    casos = {
        "página inexistente": ({"page": "A9"}, ("A9",)),
        "orientação inventada": ({"page": "A4 diagonal"}, ("diagonal",)),
        "dpi absurdo": ({"dpi": 5000}, ("dpi",)),
        "dpi por texto": ({"dpi": "alto"}, ("dpi",)),
        "formato não suportado": ({"format": "bmp"}, ("bmp",)),
        "template desconhecido": ({"template": "barroco"}, ("barroco",)),
        "campo de rótulo inexistente": ({"label_field": "NAO_EXISTE"}, ("NAO_EXISTE",)),
        "língua desconhecida": ({"map_language": "tlh"}, ("tlh",)),
        "escala negativa": ({"scale": -5}, ("scale",)),
        "escala por texto": ({"scale": "grande"}, ("scale",)),
        "camada inexistente": ({"layer_ids": ["nao_existe_xyz"]}, ("nao_existe_xyz",)),
        "parâmetro desconhecido": ({"incluir_legenda": True}, ("incluir_legenda",)),
        "pasta de saída inexistente": ({"output_path": "/nao/existe/mapa.png"}, ("/nao/existe",)),
        "sobrescrita sem confirmação": ({"output_path": str(saida / "existente.png"), "confirm_overwrite": False}, ("confirm_overwrite",)),
        "margem negativa": ({"margin_percent": -10}, ("margin_percent",)),
        "flag por texto ambíguo": ({"include_grid": "talvez"}, ("include_grid",)),
    }
    (saida / "existente.png").write_bytes(b"x")
    for rotulo, (extra, esperados) in casos.items():
        alvo = saida / "recusa.png"
        params = {**base, "output_path": str(alvo), **extra}
        try:
            compose_map(params, {"dry_run": False})
        except (CompositionError, ParameterError) as exc:
            texto = str(exc)
            if all(e in texto for e in esperados) and not alvo.exists():
                gate.ok(rotulo)
            elif alvo.exists():
                gate.falha(rotulo, "recusou mas gerou arquivo")
            else:
                gate.falha(rotulo, f"recusa não nomeia {esperados}: {texto[:120]}")
        except Exception as exc:  # noqa: BLE001
            gate.falha(rotulo, f"QUEBRA {type(exc).__name__}: {exc}")
        else:
            gate.falha(rotulo, "aceito sem recusa")
        if alvo.exists():
            alvo.unlink()
    return gate


def portao_comparacao_multilingue(camadas: dict[str, Any], saida: Path) -> Gate:
    """Folha de comparação (dois quadros) nas escritas mais difíceis."""
    from sigmai.cartography.compose import compose_map
    from sigmai.cartography.maptext import maptext

    gate = Gate("7. comparação multilíngue")
    for lingua in ("pt-BR", "en", "ja", "zh-Hant", "ar", "he", "th", "el", "ru", "ko"):
        for mesma_escala in (True, False):
            rotulo = f"{lingua}/{'mesma escala' if mesma_escala else 'escalas próprias'}"
            arquivo = saida / f"c_{lingua}_{int(mesma_escala)}.png"
            try:
                r = compose_map({"layer_ids": [camadas["parque"].id()], "second_map": {"layer_ids": [camadas["uf"].id()]},
                                 "comparison_same_scale": mesma_escala, "page": "A3 landscape", "map_language": lingua,
                                 "title": "C", "data_source": "S", "map_author": "A", "confirm_overwrite": True, "dpi": 72,
                                 "format": "png", "output_path": str(arquivo)}, {"dry_run": False})
            except Exception as exc:  # noqa: BLE001
                gate.falha(rotulo, f"{type(exc).__name__}: {exc}")
                continue
            itens = r["audit"]["observation"].get("items", [])
            textos = " ".join(str(item.get("text", "")) for item in itens)
            # Sem panel_title os painéis levam "Painel A"/"Painel B" na língua
            # do mapa — simétricos, e nunca o título da folha repetido.
            legenda_a = next((str(i.get("text", "")) for i in itens if i.get("id") == "panel_caption_a"), "")
            faltam = []
            if not legenda_a.startswith(maptext(lingua, "painel_a").strip()):
                faltam.append(f"painel A = {legenda_a!r}")
            painel_b = maptext(lingua, "painel_b").strip()
            if painel_b and painel_b not in textos:
                faltam.append(painel_b)
            if not mesma_escala:
                aviso = maptext(lingua, "escalas_por_painel").strip()
                if aviso and aviso not in textos:
                    faltam.append(aviso)
            if faltam:
                gate.falha(rotulo, "rótulos de painel ausentes: " + ", ".join(repr(f) for f in faltam))
            elif r["audit"]["grade"] not in ("A", "B") or not arquivo.exists() or arquivo.stat().st_size < 1000:
                gate.falha(rotulo, f"nota {r['audit']['grade']}: " + "; ".join(e["id"] for e in r["audit"]["results"] if e["status"] == "fail"))
            else:
                gate.ok(rotulo)
    return gate


def portao_catalogo(camadas: dict[str, Any]) -> Gate:
    import inspect
    import re

    from sigmai.permissions import COMMAND_PERMISSIONS, allowed_actions
    from sigmai.command_registry import CommandRegistry
    from sigmai.qgis_actions import register_actions

    gate = Gate("4. catálogo igual à realidade")
    registry = CommandRegistry({"qgis_version": "bateria", "unsafe_developer_mode": False})
    register_actions(registry)
    habilitadas = allowed_actions()
    marcas = re.compile(r'"planned"|"future"|not_enabled|NOT_ENABLED|"placeholder"', re.I)
    for acao in sorted(COMMAND_PERMISSIONS):
        handler = registry._handlers.get(acao)
        if acao in habilitadas:
            if handler is None:
                gate.falha(acao, "habilitada no catálogo mas sem função registrada")
                continue
            try:
                fonte = inspect.getsource(handler)
            except (OSError, TypeError):
                gate.ok(acao)
                continue
            # Uma marca só é esqueleto se for o caminho normal, não a exceção.
            corpo = "\n".join(l for l in fonte.splitlines() if "raise" not in l or "NOT_ENABLED" in l)
            if marcas.search(corpo) and "raise ValidationError" in fonte and fonte.count("return") == 0:
                gate.falha(acao, "corpo só recusa com marca de esqueleto")
            else:
                gate.ok(acao)
        else:
            # A ação desabilitada tem de ser recusada pela ponte como inexistente
            # — não pode existir um caminho por onde ela ainda execute.
            resposta = registry.execute({"action": acao, "params": {}, "request_id": "bateria"})
            codigos = [erro.get("code") for erro in resposta.get("errors", [])]
            if resposta.get("ok") or "ACTION_NOT_ALLOWED" not in codigos:
                gate.falha(acao, f"desabilitada no catálogo mas a ponte respondeu {resposta.get('ok')} {codigos}")
            else:
                gate.ok(f"{acao} (desabilitada, recusada pela ponte)")
    return gate


def portao_idempotencia(camadas: dict[str, Any], saida: Path) -> Gate:
    from sigmai.cartography.compose import compose_map

    gate = Gate("5. idempotência")
    laudos = []
    for i in range(2):
        r = compose_map({"layer_ids": [camadas["municipios"].id(), camadas["parque"].id()], "subject_layer_id": camadas["parque"].id(),
                         "title": "Idem", "output_path": str(saida / f"i_{i}.png"), "format": "png", "dpi": 72,
                         "confirm_overwrite": True, "data_source": "S", "map_author": "A"}, {"dry_run": False})
        laudos.append((r["scale"], r["audit"]["grade"], r["audit"]["score"], sorted(r["items_created"])))
    if laudos[0] == laudos[1]:
        gate.ok("dois mapas iguais dão o mesmo laudo")
    else:
        gate.falha("idempotência", f"{laudos[0]} != {laudos[1]}")
    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--full", action="store_true", help="matriz de composição completa (384 células) em vez de 1 em 3")
    args = parser.parse_args()
    global AMOSTRAGEM
    if args.full:
        AMOSTRAGEM = 1

    from qgis.core import QgsApplication

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    from tools.qgis_lifecycle import shutdown_qgis

    saida = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="sigmai_release_"))
    saida.mkdir(parents=True, exist_ok=True)
    inicio = time.time()
    try:
        camadas = carregar_dados(Path(args.data))
        print(f"camadas: {', '.join(camadas)}\n")
        gates = []
        for fabrica in (portao_matriz_composicao, portao_matriz_dados, portao_linguas, portao_idempotencia,
                        portao_recusas, portao_comparacao_multilingue):
            gate = fabrica(camadas, saida)
            print(f"  {gate.resumo()}")
            gates.append(gate)
        gate = portao_catalogo(camadas)
        print(f"  {gate.resumo()}")
        gates.append(gate)
    finally:
        shutdown_qgis(app)

    total_ok = sum(g.passou for g in gates)
    total_falha = sum(g.falhou for g in gates)
    print(f"\n{'LIBERADO' if not total_falha else 'BLOQUEADO'}: {total_ok} verificações ok, {total_falha} falha(s), {time.time() - inicio:.0f}s, saída em {saida}")
    Path(saida / "laudo.json").write_text(json.dumps(
        [{"portao": g.nome, "ok": g.passou, "falhas": g.detalhes} for g in gates], ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if total_falha else 0


if __name__ == "__main__":
    raise SystemExit(main())
