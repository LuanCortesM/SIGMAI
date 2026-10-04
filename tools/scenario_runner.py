# -*- coding: utf-8 -*-
"""Bancada de cenários: roda pedidos contra o compositor e classifica o desfecho.

Existe para que se possa escrever muitos pedidos — em várias línguas, com erros
de digitação, do jeito que um iniciante escreveria — num arquivo JSON, e receber
de volta um laudo dizendo, para cada um, se a ferramenta:

* ``ok``       — compôs o mapa (com nota e achados da auditoria);
* ``recusa``   — recusou de propósito, com ``CompositionError``;
* ``quebra``   — levantou qualquer outra exceção. **Sempre é defeito**: mesmo um
                 pedido absurdo tem de ser recusado com uma frase útil, e não
                 estourar com um ``KeyError`` que ninguém entende.

A distinção entre ``recusa`` e ``quebra`` é o coração da bancada. Uma recusa é
um contrato cumprido; uma quebra é a ferramenta perdendo o controle.

Além disso, mede se a mensagem de recusa é *acionável*: uma recusa que não diz
o que é aceito deixa a IA adivinhando, e adivinhar é como se produz um mapa
diferente do pedido.

Uso::

    python tools/scenario_runner.py --scenarios cenarios.json --out laudo.json \
        --data "/caminho/_teste_sigmai" [--images out/cenarios]

Formato de cada cenário::

    {
      "id": "ja-01",
      "lang": "ja",
      "intent": "legitimo",          # ou "invalido": pedido que DEVE ser recusado
      "note": "usuário japonês pede A4 paisagem em japonês",
      "params": {"layer_ids": ["@trilha"], "title": "イタグアレの登山道", "page": "A4 横"}
    }

``@apelido`` em ``layer_ids``, ``subject_layer_id``, ``inset_layer_ids`` e dentro
de ``second_map`` é trocado pelo id real da camada carregada.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


#: Apelido -> (arquivo, nome apresentado, tipo). O apelido é o que os cenários usam.
FIXTURE_LAYERS: list[tuple[str, str, str, str]] = [
    ("uf", "PI_UF_2024.shp", "Limite estadual do Piauí", "vetor"),
    ("municipios", "PI_Municipios_2024.shp", "Municípios do Piauí", "vetor"),
    ("parque", "PE Carnaubas.kml", "PE das Carnaúbas", "vetor"),
    ("trilha", "trilha/Trilha Itaguaré pelo batedor.shp", "Trilha do Itaguaré", "vetor"),
    ("gpx", "trilha/Decida primeira coleta.gpx|layername=track_points", "Pontos da coleta", "vetor"),
]
RASTER_LAYERS: list[tuple[str, str, str]] = [
    ("dem", "Copernicus_DSM_COG_30_S05_00_W042_00_DEM.tif", "Altimetria Copernicus GLO-90"),
]

#: Marcas de que a mensagem de recusa diz o que fazer em seguida. Sem alguma
#: delas, a recusa é um "não" sem porta de saída.
ACTIONABLE_MARKERS = (
    "aceito", "aceitos", "disponív", "use um", "use estes", "passe ", "informe ",
    "por exemplo", "campos ", "camadas do mapa", "formatos", "templates",
    "defina ", "omita ", "tire-a", "escolha ",
    # "X precisa ser um número; recebido 'hoch'" diz o que fazer tanto quanto
    # "use um"; sem estes dois marcadores toda recusa de tipo contava como opaca.
    "precisa ", "verifique ",
)


class ScenarioBench:
    def __init__(self, data_dir: Path, image_dir: Path | None) -> None:
        from qgis.core import QgsApplication  # type: ignore

        QgsApplication.setPrefixPath("/usr", True)
        self.app = QgsApplication([], False)
        self.app.initQgis()
        self.data_dir = data_dir
        self.image_dir = image_dir
        if image_dir:
            image_dir.mkdir(parents=True, exist_ok=True)
        self.aliases: dict[str, str] = {}
        self.layer_names: dict[str, str] = {}
        self._load_project()

    # -- projeto ----------------------------------------------------------
    def _load_project(self) -> None:
        from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer  # type: ignore

        project = QgsProject.instance()
        project.clear()
        first_crs = None
        for alias, relative, label, _kind in FIXTURE_LAYERS:
            layer = QgsVectorLayer(str(self.data_dir / relative), label, "ogr")
            if not layer.isValid():
                print(f"aviso: camada inválida ignorada: {alias}", file=sys.stderr)
                continue
            project.addMapLayer(layer)
            self.aliases[alias] = layer.id()
            self.layer_names[alias] = label
            first_crs = first_crs or layer.crs()
        raster_dir = self.data_dir.parent / "DEM_GLO90"
        for alias, filename, label in RASTER_LAYERS:
            path = raster_dir / filename
            if not path.exists():
                continue
            layer = QgsRasterLayer(str(path), label)
            if not layer.isValid():
                continue
            project.addMapLayer(layer)
            self.aliases[alias] = layer.id()
            self.layer_names[alias] = label
        if first_crs is not None:
            project.setCrs(first_crs)

    # -- substituição de apelidos ----------------------------------------
    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str):
            if value.startswith("@"):
                return self.aliases.get(value[1:], value)
            return value
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: self._resolve(item) for key, item in value.items()}
        return value

    # -- execução ---------------------------------------------------------
    def run(self, scenario: dict[str, Any]) -> dict[str, Any]:
        from sigmai.cartography.compose import CompositionError, compose_map  # type: ignore

        identifier = str(scenario.get("id") or "sem-id")
        params = self._resolve(dict(scenario.get("params") or {}))

        # Saída própria por cenário, para que um não sobrescreva o outro e para
        # que se possa abrir a imagem e olhar.
        if self.image_dir is not None and "output_path" not in params:
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in identifier)
            params["output_path"] = str(self.image_dir / f"{safe}.png")
            params.setdefault("format", "png")
            params.setdefault("dpi", 110)
            # Só a saída que o PRÓPRIO runner inventou ganha confirmação
            # automática: um cenário que traz output_path está testando o
            # comportamento de sobrescrita e precisa do padrão real do
            # compositor (sem confirmação = recusa).
            params.setdefault("confirm_overwrite", True)
        # Cenários de sobrescrita nomeiam o alvo "_preexistente_*": o arquivo
        # tem de existir antes da chamada, sem depender de uma corrida anterior.
        alvo = str(params.get("output_path") or "")
        if "_preexistente" in alvo:
            try:
                Path(alvo).parent.mkdir(parents=True, exist_ok=True)
                if not Path(alvo).exists():
                    Path(alvo).write_bytes(b"conteudo anterior")
            except OSError:
                pass

        record: dict[str, Any] = {
            "id": identifier,
            "lang": scenario.get("lang", ""),
            "intent": scenario.get("intent", "legitimo"),
            "note": scenario.get("note", ""),
            "params_sent": {k: v for k, v in params.items() if k != "output_path"},
        }

        try:
            result = compose_map(params, {"dry_run": False})
        except CompositionError as exc:
            record.update(
                outcome="recusa",
                exception="CompositionError",
                message=str(exc),
                actionable=any(marker in str(exc).lower() for marker in ACTIONABLE_MARKERS),
            )
            return record
        except Exception as exc:  # noqa: BLE001 - qualquer outra coisa é defeito
            record.update(
                outcome="quebra",
                exception=type(exc).__name__,
                message=str(exc),
                traceback=traceback.format_exc(limit=6),
            )
            return record

        audit = result.get("audit", {})
        output = params.get("output_path")
        size = 0
        try:
            size = Path(output).stat().st_size if output and Path(output).exists() else 0
        except OSError:
            size = 0
        record.update(
            outcome="ok",
            grade=audit.get("grade"),
            score=audit.get("score"),
            scale=result.get("scale"),
            map_crs=result.get("map_crs"),
            items=sorted(result.get("items_created") or {}),
            failures=[
                {"id": entry["id"], "severity": entry["severity"], "detail": entry["detail_pt"][:200]}
                for entry in audit.get("results", []) if entry.get("status") == "fail"
            ],
            notes=[note[:200] for note in (result.get("notes") or [])],
            output_path=output,
            output_bytes=size,
        )
        return record

    def close(self) -> None:
        from tools.qgis_lifecycle import shutdown_qgis  # type: ignore

        shutdown_qgis(self.app)


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    """O resumo é o que se lê primeiro: onde a ferramenta perdeu o controle."""
    quebras = [r for r in records if r["outcome"] == "quebra"]
    recusas = [r for r in records if r["outcome"] == "recusa"]
    oks = [r for r in records if r["outcome"] == "ok"]

    # Um pedido legítimo recusado é tão defeito quanto uma quebra: o usuário
    # queria algo razoável e não conseguiu.
    recusas_indevidas = [r for r in recusas if r["intent"] == "legitimo"]
    # Um pedido inválido aceito é o defeito mais perigoso: entrega calada.
    aceites_indevidos = [r for r in oks if r["intent"] == "invalido"]
    recusas_opacas = [r for r in recusas if not r.get("actionable")]
    notas_baixas = [r for r in oks if str(r.get("grade") or "") not in ("A", "B")]
    vazios = [r for r in oks if r.get("output_bytes", 0) and r["output_bytes"] < 3000]

    return {
        "total": len(records),
        "ok": len(oks),
        "recusa": len(recusas),
        "quebra": len(quebras),
        "defeitos": {
            "quebras": [r["id"] for r in quebras],
            "recusas_de_pedido_legitimo": [r["id"] for r in recusas_indevidas],
            "pedidos_invalidos_aceitos": [r["id"] for r in aceites_indevidos],
            "recusas_sem_saida": [r["id"] for r in recusas_opacas],
            "notas_abaixo_de_B": [f"{r['id']}={r.get('grade')}" for r in notas_baixas],
            "arquivos_suspeitos_de_vazio": [r["id"] for r in vazios],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", required=True, help="arquivo JSON com a lista de cenários")
    parser.add_argument("--data", required=True, help="pasta _teste_sigmai com os dados reais")
    parser.add_argument("--out", required=True, help="onde gravar o laudo JSON")
    parser.add_argument("--images", default="", help="pasta para os PNG de cada cenário")
    parser.add_argument("--only", default="", help="roda apenas os ids listados, separados por vírgula")
    args = parser.parse_args()

    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    if isinstance(scenarios, dict):
        scenarios = scenarios.get("scenarios", [])
    if args.only:
        alvo = {item.strip() for item in args.only.split(",") if item.strip()}
        scenarios = [s for s in scenarios if str(s.get("id")) in alvo]

    bench = ScenarioBench(Path(args.data), Path(args.images) if args.images else None)
    records = []
    try:
        for scenario in scenarios:
            record = bench.run(scenario)
            records.append(record)
            marca = {"ok": "ok    ", "recusa": "RECUSA", "quebra": "QUEBRA"}[record["outcome"]]
            extra = record.get("grade") or record.get("exception") or ""
            print(f"{marca} {record['id']:14s} [{record['lang']:5s}] {str(extra):18s} {record.get('message','')[:80]}")
    finally:
        bench.close()

    summary = summarise(records)
    Path(args.out).write_text(
        json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if (summary["quebra"] or summary["defeitos"]["recusas_de_pedido_legitimo"]
                 or summary["defeitos"]["pedidos_invalidos_aceitos"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
