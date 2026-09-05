# -*- coding: utf-8 -*-
"""Catálogo igual à realidade: as 24 ações que a auditoria pré-1.0 achou
anunciando capacidade inexistente.

Cada ação teve exatamente um dos dois desfechos: implementada de verdade, ou
desabilitada em permissions.py com uma razão em capabilities_payload()
["limitations"]. Este arquivo prova o efeito de cada implementação e traz o
teste-guarda que impede o esqueleto de voltar: nenhuma ação HABILITADA pode
ter, no corpo da própria função registrada, as marcas "planned", "future" ou
"NOT_ENABLED" incondicional — os três jeitos como o catálogo mentia antes.

Os testes que tocam PyQGIS usam objetos QGIS reais (QgsVectorLayer em
memória, QgsSettings, QgsDistanceArea) em vez de dublês: neste ambiente eles
funcionam sem display e sem QgsApplication.initQgis() — só a pintura de
verdade (QgsPrintLayout/QgsLayoutItemMap do compose_map real e o
QTextDocument/QPdfWriter do export_report_pdf real) exige um display (xvfb),
e por isso aqueles dois caminhos são provados só em scripts separados fora
deste pacote, no mesmo espírito de test_dry_run_contract.py e
test_data_source_privacy.py — só os ramos de dry_run desses dois, que não
tocam nenhuma classe de pintura, são exercitados aqui.
"""

from __future__ import annotations

import inspect
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sigmai.command_registry import CommandRegistry  # noqa: E402
from sigmai.permissions import allowed_actions, capabilities_payload, permission_for  # noqa: E402
from sigmai.validators import ValidationError, validate_command  # noqa: E402
from sigmai import qgis_actions  # noqa: E402
from sigmai.qgis_actions import atlas_reports, cartography, data_sources, workflows  # noqa: E402


#: As 13 ações que a auditoria mandou desabilitar nesta rodada, com o motivo
#: resumido que também precisa aparecer em capabilities_payload()["limitations"].
DISABLED_ACTIONS = (
    "create_map_hierarchy",
    "create_atlas",
    "configure_atlas_coverage_layer",
    "set_atlas_filter_expression",
    "set_atlas_sort_expression",
    "export_atlas_pdf",
    "export_atlas_images",
    "generate_map_book",
    "inspect_database_connection",
    "test_postgis_connection",
    "list_postgis_tables",
    "load_postgis_layer",
    "inspect_postgis_layer",
)


def _pyqgis_disponivel() -> bool:
    """PyQGIS só existe dentro de uma instalação do QGIS. As classes abaixo que
    criam QgsVectorLayer/QgsSettings/QgsDistanceArea de verdade são puladas
    — não reprovadas — numa máquina sem QGIS, para que a suíte não acuse
    defeito onde só há ausência de ambiente."""
    import importlib.util

    return importlib.util.find_spec("qgis") is not None


def _fresh_registry() -> CommandRegistry:
    """Um CommandRegistry de verdade, com todas as ~221 ações registradas,
    exatamente como a ponte monta o dela — sem precisar de um QGIS rodando
    de fato, porque nenhum handler toca QGIS só por ser registrado."""
    registry = CommandRegistry({"registered_actions": [], "host": "127.0.0.1", "port": 8765})
    qgis_actions.register_actions(registry)
    return registry


def _wait_job(registry: CommandRegistry, job_id: str, timeout_s: float = 5.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = registry.execute({"action": "get_job_status", "params": {"job_id": job_id}})
        if status["data"]["status"] in ("completed", "failed", "cancelled"):
            return status["data"]
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} não terminou em {timeout_s}s")


class GuardaContraEsqueletoVoltar(unittest.TestCase):
    """O teste que impede o esqueleto de voltar: nenhuma ação habilitada pode
    devolver/levantar "planned", "future" ou um NOT_ENABLED incondicional no
    próprio corpo da função registrada — os três disfarces de sucesso falso
    que a auditoria encontrou nas 24 ações."""

    FORBIDDEN = re.compile(r"planned|future|NOT_ENABLED", re.IGNORECASE)

    def test_nenhuma_acao_habilitada_tem_marca_de_esqueleto(self) -> None:
        registry = _fresh_registry()
        enabled = allowed_actions()
        self.assertTrue(enabled, "allowed_actions() não pode voltar vazio")
        problemas = []
        for action in sorted(enabled):
            handler = registry._handlers.get(action)
            self.assertIsNotNone(handler, f"ação habilitada sem handler registrado: {action}")
            source = inspect.getsource(handler)
            if self.FORBIDDEN.search(source):
                problemas.append(action)
        self.assertEqual(problemas, [], f"ações com marca de esqueleto no corpo: {problemas}")

    def test_as_13_acoes_desabilitadas_nesta_rodada_nao_aparecem_mais(self) -> None:
        for action in DISABLED_ACTIONS:
            with self.subTest(action=action):
                self.assertNotIn(action, allowed_actions())


class AcoesDesabilitadasSaoRecusadasComoInexistentes(unittest.TestCase):
    """enabled=False precisa fechar o ciclo inteiro: fora de allowed_actions(),
    fora dos grupos/listas de capacidade, dentro de disabled_actions, e com
    uma razão específica em limitations — não só sumir do catálogo."""

    def setUp(self) -> None:
        self.payload = capabilities_payload()

    def test_ponte_recusa_como_inexistente(self) -> None:
        for action in DISABLED_ACTIONS:
            with self.subTest(action=action):
                with self.assertRaises(ValidationError) as ctx:
                    validate_command({"action": action, "params": {}})
                self.assertEqual(ctx.exception.code, "ACTION_NOT_ALLOWED")

    def test_lista_disabled_actions_contem_as_13(self) -> None:
        for action in DISABLED_ACTIONS:
            with self.subTest(action=action):
                self.assertIn(action, self.payload["disabled_actions"])

    def test_nao_sobra_em_nenhum_grupo_nem_lista_de_capacidade(self) -> None:
        capacidades_por_grupo = [
            "atlas_report_capabilities",
            "cartographic_design_capabilities",
            "database_capabilities",
            "dry_run_supported",
            "requires_confirmation",
        ]
        for action in DISABLED_ACTIONS:
            for grupo, membros in self.payload["groups"].items():
                self.assertNotIn(action, membros, f"{action} ainda aparece no grupo {grupo}")
            for nome_lista in capacidades_por_grupo:
                with self.subTest(action=action, lista=nome_lista):
                    self.assertNotIn(action, self.payload[nome_lista])

    def test_cada_desabilitada_tem_uma_razao_em_limitations(self) -> None:
        texto = " ".join(self.payload["limitations"])
        for action in DISABLED_ACTIONS:
            with self.subTest(action=action):
                self.assertIn(action, texto, f"nenhuma frase em limitations menciona {action}")

    def test_permission_metadata_bate_com_enabled_false(self) -> None:
        for action in DISABLED_ACTIONS:
            permission = permission_for(action)
            self.assertIsNotNone(permission)
            self.assertFalse(permission.enabled)


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS não instalado")
class ExecuteWorkflowExecutaDeVerdade(unittest.TestCase):
    """execute_workflow (item 10): despacha cada passo pelo command_executor
    real da ponte (o mesmo CommandRegistry.execute que qualquer chamada
    direta atravessa), para no primeiro erro e devolve o que já rodou e o
    que falta — em vez do WORKFLOW_EXECUTION_NOT_ENABLED incondicional de
    antes."""

    def setUp(self) -> None:
        self.registry = _fresh_registry()

    def test_dry_run_nao_executa_nada_so_planeja(self) -> None:
        resposta = self.registry.execute(
            {"action": "execute_workflow", "dry_run": True, "params": {"name": "teste", "steps": [{"action": "status"}]}}
        )
        self.assertTrue(resposta["ok"])
        self.assertTrue(resposta["data"]["dry_run"])
        self.assertIn("step_outputs", resposta["data"])

    def test_executa_passo_a_passo_e_para_no_primeiro_erro(self) -> None:
        resposta = self.registry.execute(
            {
                "action": "execute_workflow",
                "dry_run": False,
                "params": {
                    "name": "teste",
                    "steps": [
                        {"action": "status", "dry_run": True},
                        {"action": "get_job_status", "dry_run": True, "params": {"job_id": "nao-existe"}},
                        {"action": "status", "dry_run": True},
                    ],
                },
            }
        )
        self.assertTrue(resposta["ok"])  # a chamada em si não quebrou
        data = resposta["data"]
        self.assertFalse(data["ok"])  # o workflow parou no meio
        self.assertEqual(data["stopped_at_step"], 2)
        self.assertEqual(len(data["executed_steps"]), 2)
        self.assertTrue(data["executed_steps"][0]["ok"])
        self.assertFalse(data["executed_steps"][1]["ok"])
        self.assertEqual(data["executed_steps"][1]["errors"][0]["code"], "JOB_NOT_FOUND")
        self.assertEqual(data["pending_steps"], [{"step": 3, "action": "status"}])

    def test_workflow_completo_sem_erros(self) -> None:
        resposta = self.registry.execute(
            {
                "action": "execute_workflow",
                "dry_run": False,
                "params": {"name": "teste", "steps": [{"action": "status", "dry_run": True}, {"action": "status", "dry_run": True}]},
            }
        )
        data = resposta["data"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["pending_steps"], [])
        self.assertEqual(len(data["executed_steps"]), 2)

    def test_passo_nao_pode_chamar_execute_workflow_de_volta(self) -> None:
        resposta = self.registry.execute(
            {
                "action": "execute_workflow",
                "dry_run": False,
                "params": {"steps": [{"action": "execute_workflow", "params": {"steps": [{"action": "status"}]}}]},
            }
        )
        self.assertFalse(resposta["ok"])
        self.assertEqual(resposta["errors"][0]["code"], "WORKFLOW_UNSAFE_ACTION")

    def test_sem_command_executor_recusa_em_vez_de_fingir(self) -> None:
        plan = workflows.plan_workflow({"steps": [{"action": "status"}]}, {"registered_actions": ["status"]})
        with self.assertRaises(ValidationError) as ctx:
            workflows.execute_workflow({"steps": [{"action": "status"}]}, {"registered_actions": ["status"], "dry_run": False})
        self.assertEqual(ctx.exception.code, "WORKFLOW_EXECUTOR_UNAVAILABLE")
        self.assertGreaterEqual(plan["step_count"], 1)


class JobsHonramODryRunDoChamador(unittest.TestCase):
    """run_workflow_job e run_map_export_job (itens 1-2): honram o dry_run
    que o chamador passou em vez de sempre responder "completed" sem ter
    executado nada — e, sem dry_run, recusam explicando por que (o runner de
    jobs só aceita leitura/dry-run) em vez de fingir sucesso."""

    def setUp(self) -> None:
        self.registry = _fresh_registry()

    def test_run_workflow_job_dry_run_true_completa_via_execute_workflow(self) -> None:
        started = self.registry.execute(
            {"action": "run_workflow_job", "dry_run": True, "params": {"dry_run": True, "steps": [{"action": "status"}]}}
        )
        job = _wait_job(self.registry, started["data"]["job_id"])
        self.assertEqual(job["status"], "completed")
        result = self.registry.execute({"action": "get_job_result", "params": {"job_id": started["data"]["job_id"]}})
        self.assertEqual(result["data"]["result"]["action"], "execute_workflow")

    def test_run_workflow_job_dry_run_false_recusa_sem_fingir_sucesso(self) -> None:
        resposta = self.registry.execute(
            {"action": "run_workflow_job", "dry_run": True, "params": {"dry_run": False, "steps": [{"action": "status"}]}}
        )
        self.assertFalse(resposta["ok"])
        self.assertEqual(resposta["errors"][0]["code"], "JOB_UNSAFE_ACTION_USE_DRY_RUN")

    def test_run_map_export_job_honra_dry_run_true_do_chamador(self) -> None:
        started = self.registry.execute(
            {"action": "run_map_export_job", "dry_run": True, "params": {"dry_run": True, "map_action": "list_layout_templates"}}
        )
        self.assertTrue(started["ok"])
        job = _wait_job(self.registry, started["data"]["job_id"])
        self.assertEqual(job["status"], "completed")

    def test_run_map_export_job_dry_run_false_recusa_em_vez_de_forcar_dry_run(self) -> None:
        resposta = self.registry.execute(
            {"action": "run_map_export_job", "dry_run": True, "params": {"dry_run": False, "map_action": "generate_professional_map"}}
        )
        self.assertFalse(resposta["ok"])
        self.assertEqual(resposta["errors"][0]["code"], "JOB_UNSAFE_ACTION_USE_DRY_RUN")


class MapGpxTrackComponeOMapa(unittest.TestCase):
    """map_gpx_track (item 3): o ramo de dry_run não toca PyQGIS (prova
    aqui); a composição real (load + compose_map desenhando a trilha) é
    provada com xvfb num script separado — ver o relatório final."""

    def test_dry_run_anuncia_os_dois_passos_sem_carregar_nada(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        gpx_path = tmp / "trilha.gpx"
        gpx_path.write_text(
            "<?xml version='1.0'?><gpx version='1.1'><trk><trkseg>"
            "<trkpt lat='-22.5' lon='-45.09'><ele>1339</ele></trkpt>"
            "<trkpt lat='-22.501' lon='-45.091'><ele>1338</ele></trkpt>"
            "</trkseg></trk></gpx>",
            encoding="utf-8",
        )
        resposta = data_sources.map_gpx_track({"path": str(gpx_path)}, {"dry_run": True})
        self.assertTrue(resposta["dry_run"])
        self.assertEqual(resposta["steps"], ["load_gpx", "compose_map"])

    def test_recusa_arquivo_sem_extensao_gpx(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        not_gpx = tmp / "trilha.txt"
        not_gpx.write_text("nada")
        with self.assertRaises(ValidationError) as ctx:
            data_sources.map_gpx_track({"path": str(not_gpx)}, {"dry_run": True})
        self.assertEqual(ctx.exception.code, "BAD_REQUEST")


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS não instalado")
class GpxTrackLengthCalculaDistanciaReal(unittest.TestCase):
    """gpx_track_length (item 25): QgsDistanceArea elipsoidal (WGS84) em vez
    de "length_calculation": "planned" — a métrica óbvia dos dados de
    trilha do próprio autor."""

    def _gpx_com_trilha_conhecida(self) -> Path:
        # Dois pontos ~1km a ~ (0.009 grau de latitude) de distância no
        # equador, para o resultado ter uma faixa esperada fácil de checar
        # sem depender de nenhuma calculadora externa.
        tmp = Path(tempfile.mkdtemp())
        gpx_path = tmp / "trilha.gpx"
        gpx_path.write_text(
            "<?xml version='1.0'?><gpx version='1.1'><trk><trkseg>"
            "<trkpt lat='0.0' lon='0.0'></trkpt>"
            "<trkpt lat='0.009' lon='0.0'></trkpt>"
            "</trkseg></trk></gpx>",
            encoding="utf-8",
        )
        return gpx_path

    def test_comprimento_em_metros_bate_com_a_geodesia_esperada(self) -> None:
        gpx_path = self._gpx_com_trilha_conhecida()
        resultado = data_sources.gpx_track_length({"path": str(gpx_path)}, {"dry_run": False})
        # 0.009 grau de latitude ~ 1000m (1 grau ~ 111.32 km no equador).
        self.assertAlmostEqual(resultado["length_meters"], 1000.0, delta=20.0)
        self.assertEqual(resultado["segment_count"], 1)
        self.assertEqual(resultado["method"], "QgsDistanceArea, ellipsoidal WGS84")

    def test_arquivo_inexistente_recusa_com_erro_real(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            data_sources.gpx_track_length({"path": "/tmp/sigmai_nao_existe_de_verdade.gpx"}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "FILE_NOT_FOUND")


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS não instalado")
class RepairDataSourcePathConserta(unittest.TestCase):
    """repair_data_source_path (item 11): layer.setDataSource() de verdade,
    com isValid() checado depois — fecha o ciclo com broken_data_source_report."""

    def setUp(self) -> None:
        from qgis.core import QgsProject, QgsVectorLayer

        self.project = QgsProject.instance()
        self.project.clear()
        self.tmp = Path(tempfile.mkdtemp())
        self.original = self.tmp / "original.geojson"
        self.original.write_text(
            '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},'
            '"geometry":{"type":"Point","coordinates":[1,2]}}]}'
        )
        self.layer = QgsVectorLayer(str(self.original), "camada", "ogr")
        self.assertTrue(self.layer.isValid())
        self.project.addMapLayer(self.layer)

    def tearDown(self) -> None:
        self.project.clear()

    def test_repara_apontando_para_novo_caminho_valido(self) -> None:
        novo = self.tmp / "novo.geojson"
        novo.write_text(self.original.read_text())
        resultado = data_sources.repair_data_source_path(
            {"layer_id": self.layer.id(), "new_path": str(novo)}, {"dry_run": False}
        )
        self.assertTrue(resultado["valid"])
        self.assertEqual(resultado["new_path"], str(novo))

    def test_dry_run_nao_muda_a_fonte_de_dados(self) -> None:
        novo = self.tmp / "novo.geojson"
        novo.write_text(self.original.read_text())
        resultado = data_sources.repair_data_source_path(
            {"layer_id": self.layer.id(), "new_path": str(novo)}, {"dry_run": True}
        )
        self.assertTrue(resultado["dry_run"])
        self.assertEqual(self.layer.source(), str(self.original))

    def test_recusa_caminho_novo_inexistente(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            data_sources.repair_data_source_path(
                {"layer_id": self.layer.id(), "new_path": str(self.tmp / "fantasma.geojson")}, {"dry_run": False}
            )
        self.assertEqual(ctx.exception.code, "FILE_NOT_FOUND")

    def test_recusa_layer_id_desconhecido(self) -> None:
        novo = self.tmp / "novo.geojson"
        novo.write_text(self.original.read_text())
        with self.assertRaises(ValidationError) as ctx:
            data_sources.repair_data_source_path({"layer_id": "nao-existe", "new_path": str(novo)}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "LAYER_NOT_FOUND")


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS não instalado")
class EstilosCientificosProduzemSaidasDistintas(unittest.TestCase):
    """apply_boundary_highlight e as três apply_scientific_* (itens 5-8):
    antes as quatro caíam no mesmo padrão (sem perfil próprio em
    STYLE_PROFILES) e produziam saída idêntica byte a byte. Agora cada uma
    tem comportamento próprio, e as apply_scientific_* recusam camada de
    tipo de geometria diferente do nome."""

    def setUp(self) -> None:
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        self.project = QgsProject.instance()
        self.project.clear()

        self.poly = QgsVectorLayer("Polygon?crs=EPSG:4326&field=id:integer", "poligono", "memory")
        feat = QgsFeature(self.poly.fields())
        feat.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(1, 0), QgsPointXY(1, 1), QgsPointXY(0, 1)]]))
        self.poly.dataProvider().addFeature(feat)
        self.project.addMapLayer(self.poly)

        self.line = QgsVectorLayer("LineString?crs=EPSG:4326&field=id:integer", "linha", "memory")
        feat_l = QgsFeature(self.line.fields())
        feat_l.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(1, 1)]))
        self.line.dataProvider().addFeature(feat_l)
        self.project.addMapLayer(self.line)

        self.point = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "ponto", "memory")
        feat_p = QgsFeature(self.point.fields())
        feat_p.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        self.point.dataProvider().addFeature(feat_p)
        self.project.addMapLayer(self.point)

    def tearDown(self) -> None:
        self.project.clear()

    def _estilo(self, resposta: dict[str, Any]) -> tuple:
        return (resposta["fill_color"], resposta["stroke_color"], resposta["stroke_width"], resposta["outline_only"])

    def test_boundary_highlight_e_scientific_polygon_diferem_na_mesma_camada(self) -> None:
        boundary = cartography.apply_boundary_highlight({"layer_id": self.poly.id()}, {"dry_run": False})
        scientific = cartography.apply_scientific_polygon_style({"layer_id": self.poly.id()}, {"dry_run": False})
        self.assertNotEqual(self._estilo(boundary), self._estilo(scientific))
        self.assertTrue(boundary["outline_only"])
        self.assertFalse(scientific["outline_only"])

    def test_as_quatro_saidas_sao_todas_distintas_entre_si(self) -> None:
        # As três apply_scientific_* usam o MESMO perfil de cor (scientific_soft
        # restrito ao tipo de geometria do nome — por design, não é o defeito
        # antigo) então comparar só fill/stroke não separa as três. O que
        # prova que as quatro são ações diferentes, e não a mesma saída
        # reembalada, é a combinação de (a) o perfil e a geometria exigida,
        # que não se repete em nenhuma das quatro, e (b) a classe real do
        # símbolo que cada uma manda o QGIS desenhar — marcador para ponto,
        # linha para linha, preenchimento para polígono/limite.
        boundary = cartography.apply_boundary_highlight({"layer_id": self.poly.id()}, {"dry_run": False})
        classe_boundary = type(self.poly.renderer().symbol()).__name__

        poly_style = cartography.apply_scientific_polygon_style({"layer_id": self.poly.id()}, {"dry_run": False})
        classe_poly = type(self.poly.renderer().symbol()).__name__

        line_style = cartography.apply_scientific_line_style({"layer_id": self.line.id()}, {"dry_run": False})
        classe_line = type(self.line.renderer().symbol()).__name__

        point_style = cartography.apply_scientific_point_style({"layer_id": self.point.id()}, {"dry_run": False})
        classe_point = type(self.point.renderer().symbol()).__name__

        assinaturas = [
            (r.get("style_profile"), r.get("required_geometry"), r["outline_only"])
            for r in (boundary, poly_style, line_style, point_style)
        ]
        self.assertEqual(len(set(assinaturas)), 4, f"esperava 4 assinaturas distintas, achou {assinaturas}")

        self.assertEqual(classe_boundary, "QgsFillSymbol")  # apply_boundary_highlight, polígono sem preenchimento
        self.assertEqual(classe_poly, "QgsFillSymbol")  # apply_scientific_polygon_style
        self.assertEqual(classe_line, "QgsLineSymbol")  # apply_scientific_line_style
        self.assertEqual(classe_point, "QgsMarkerSymbol")  # apply_scientific_point_style

    def test_apply_scientific_polygon_style_recusa_camada_de_linha(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            cartography.apply_scientific_polygon_style({"layer_id": self.line.id()}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "GEOMETRY_TYPE_MISMATCH")

    def test_apply_scientific_line_style_recusa_camada_de_ponto(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            cartography.apply_scientific_line_style({"layer_id": self.point.id()}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "GEOMETRY_TYPE_MISMATCH")

    def test_apply_scientific_point_style_recusa_camada_de_poligono(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            cartography.apply_scientific_point_style({"layer_id": self.poly.id()}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "GEOMETRY_TYPE_MISMATCH")

    def test_registro_aponta_para_funcoes_distintas(self) -> None:
        registry = _fresh_registry()
        handlers = {
            action: registry._handlers[action]
            for action in (
                "apply_boundary_highlight",
                "apply_scientific_polygon_style",
                "apply_scientific_line_style",
                "apply_scientific_point_style",
            )
        }
        self.assertEqual(len(set(id(h) for h in handlers.values())), 4)


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS não instalado")
class GenerateAnalysisReportInventariaOProjeto(unittest.TestCase):
    """generate_analysis_report (item 4): camadas (tipo, CRS, contagem de
    feições, extensão) e layouts existentes de verdade, mais o que o
    chamador passar em sections — em vez das duas seções fixas de sempre."""

    def setUp(self) -> None:
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        self.project = QgsProject.instance()
        self.project.clear()
        self.layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "pontos_de_coleta", "memory")
        feat = QgsFeature(self.layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        self.layer.dataProvider().addFeature(feat)
        self.project.addMapLayer(self.layer)

    def tearDown(self) -> None:
        self.project.clear()
        atlas_reports._REPORT_SECTIONS.clear()

    def test_relatorio_lista_camada_de_verdade_e_secao_do_chamador(self) -> None:
        resultado = atlas_reports.generate_analysis_report(
            {"report_name": "Relatorio X", "sections": [{"title": "Observações de campo", "body": "nota do autor"}]},
            {"dry_run": False},
        )
        self.assertEqual(resultado["layer_count"], 1)
        self.assertEqual(resultado["section_count"], 3)
        armazenado = atlas_reports._REPORT_SECTIONS["Relatorio X"]
        titulos = [s["title"] for s in armazenado["sections"]]
        self.assertIn("Camadas do projeto", titulos)
        self.assertIn("Layouts existentes", titulos)
        self.assertIn("Observações de campo", titulos)
        secao_camadas = next(s for s in armazenado["sections"] if s["title"] == "Camadas do projeto")
        self.assertIn("pontos_de_coleta", secao_camadas["body"])
        self.assertIn("vector", secao_camadas["body"])
        self.assertIn("EPSG:4326", secao_camadas["body"])
        self.assertEqual(armazenado["layers"][0]["feature_count"], 1)

    def test_dry_run_nao_grava_nada_mas_ja_conta_direito(self) -> None:
        resultado = atlas_reports.generate_analysis_report({"report_name": "Relatorio Y"}, {"dry_run": True})
        self.assertTrue(resultado["dry_run"])
        self.assertEqual(resultado["layer_count"], 1)
        self.assertNotIn("Relatorio Y", atlas_reports._REPORT_SECTIONS)


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS não instalado")
class ListOgcEDatabaseConnectionsLeemQgsSettingsDeVerdade(unittest.TestCase):
    """list_ogc_connections e list_database_connections (itens 17-18): leem
    as conexões de verdade do QgsSettings do QGIS — só nome/URL para OGC e
    nome/host/porta/banco/usuário para PostgreSQL, nunca senha nem authcfg."""

    GROUPS = (
        "qgis/connections-wms/_sigmai_teste_catalogo",
        "PostgreSQL/connections/_sigmai_teste_catalogo",
    )

    def setUp(self) -> None:
        from qgis.core import QgsSettings

        self.settings = QgsSettings()
        for group in self.GROUPS:
            self.settings.remove(group)

    def tearDown(self) -> None:
        for group in self.GROUPS:
            self.settings.remove(group)
        self.settings.sync()

    def test_list_ogc_connections_le_url_e_nunca_senha(self) -> None:
        self.settings.setValue("qgis/connections-wms/_sigmai_teste_catalogo/url", "https://exemplo.test/wms")
        self.settings.setValue("qgis/connections-wms/_sigmai_teste_catalogo/password", "senha-nao-pode-vazar")
        self.settings.sync()
        resultado = data_sources.list_ogc_connections({}, {"dry_run": False})
        entradas = [c for c in resultado["connections"] if c["name"] == "_sigmai_teste_catalogo"]
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["url"], "https://exemplo.test/wms")
        self.assertEqual(entradas[0]["service_type"], "WMS")
        self.assertNotIn("senha-nao-pode-vazar", str(resultado))
        self.assertNotIn("password", str(resultado))

    def test_list_database_connections_le_host_e_nunca_senha(self) -> None:
        self.settings.setValue("PostgreSQL/connections/_sigmai_teste_catalogo/host", "10.0.0.9")
        self.settings.setValue("PostgreSQL/connections/_sigmai_teste_catalogo/port", "5432")
        self.settings.setValue("PostgreSQL/connections/_sigmai_teste_catalogo/database", "meubanco")
        self.settings.setValue("PostgreSQL/connections/_sigmai_teste_catalogo/username", "pguser")
        self.settings.setValue("PostgreSQL/connections/_sigmai_teste_catalogo/password", "segredo-nao-pode-vazar")
        self.settings.sync()
        resultado = data_sources.list_database_connections({}, {"dry_run": False})
        entradas = [c for c in resultado["connections"] if c["name"] == "_sigmai_teste_catalogo"]
        self.assertEqual(len(entradas), 1)
        self.assertEqual(entradas[0]["host"], "10.0.0.9")
        self.assertEqual(entradas[0]["username"], "pguser")
        self.assertNotIn("segredo-nao-pode-vazar", str(resultado))


class TestServiceConnectionRecusaComOErroReal(unittest.TestCase):
    """test_service_connection (item 16): faz a chamada de rede de verdade
    (GET GetCapabilities / HEAD) com timeout curto; sem confirm_network
    recusa antes de qualquer saída de rede, e sem rede recusa com o erro
    real do urllib — nunca mais "network_test": "planned"."""

    def test_recusa_sem_confirm_network_antes_de_qualquer_rede(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            data_sources.test_service_connection({"url": "https://exemplo.test/wms"}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "NETWORK_CONFIRMATION_REQUIRED")

    def test_host_inalcancavel_recusa_com_o_erro_real_do_urllib(self) -> None:
        # .invalid é reservado pela IANA para nunca resolver — a falha é
        # garantida em qualquer ambiente de rede, não só neste contêiner.
        with self.assertRaises(ValidationError) as ctx:
            data_sources.test_service_connection(
                {"url": "https://sigmai-nao-existe.invalid", "confirm_network": True, "timeout_seconds": 5},
                {"dry_run": False},
            )
        self.assertEqual(ctx.exception.code, "NETWORK_TEST_FAILED")
        self.assertIn("sigmai-nao-existe.invalid", str(ctx.exception.details))

    def test_credenciais_na_url_continuam_bloqueadas(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            data_sources.test_service_connection(
                {"url": "https://user:pass@exemplo.test/wms", "confirm_network": True}, {"dry_run": False}
            )
        self.assertEqual(ctx.exception.code, "CREDENTIALS_IN_URL_BLOCKED")


class ExportReportPdfNaoRecusaMaisIncondicionalmente(unittest.TestCase):
    """export_report_pdf e generate_workflow_report_pdf (itens 12-13): o
    ramo de dry_run (que não toca QTextDocument/QPdfWriter) é provado aqui;
    a escrita real do PDF é provada com xvfb num script separado — ver o
    relatório final."""

    def test_dry_run_reconhece_formato_pdf_sem_escrever_nada(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        saida = tmp / "relatorio.pdf"
        resultado = atlas_reports.export_report_pdf(
            {"report_name": "Relatorio Z", "output_path": str(saida)}, {"dry_run": True}
        )
        self.assertTrue(resultado["dry_run"])
        self.assertEqual(resultado["format"], "pdf")
        self.assertFalse(saida.exists())

    def test_generate_workflow_report_pdf_e_o_mesmo_caminho(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        saida = tmp / "relatorio_workflow.pdf"
        resultado = atlas_reports.generate_workflow_report_pdf(
            {"report_name": "Relatorio Z", "output_path": str(saida)}, {"dry_run": True}
        )
        self.assertEqual(resultado["format"], "pdf")

    def test_recusa_sobrescrever_sem_confirmacao(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        saida = tmp / "existe.pdf"
        saida.write_bytes(b"conteudo antigo")
        with self.assertRaises(ValidationError) as ctx:
            atlas_reports.export_report_pdf({"report_name": "Relatorio Z", "output_path": str(saida)}, {"dry_run": False})
        self.assertEqual(ctx.exception.code, "OVERWRITE_BLOCKED")


if __name__ == "__main__":
    unittest.main()
