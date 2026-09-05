# -*- coding: utf-8 -*-
"""O que um assistente remoto encontrou ao usar o SIGMAI só pelo MCP.

Um agente emulando um assistente de IA sem acesso ao computador — só o
cliente MCP, nenhum arquivo, nenhum código — produziu um mapa nota A e
devolveu uma lista de coisas que o obrigaram a adivinhar. Cada classe aqui
fixa uma delas. Todos os testes rodam sem PyQGIS.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mcp_module():
    spec = importlib.util.spec_from_file_location("sigmai_mcp_under_test", ROOT / "sigmai" / "mcp" / "sigmai_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class EsquemaDoComposeMapEIgualAoCompositor(unittest.TestCase):
    """additionalProperties=false + parâmetro fora do esquema = parâmetro
    inalcançável. production_date e auto_projected_crs, que o regulamento
    manda usar, não passavam pelo esquema."""

    ALIASES = {"layer_id", "layers", "layout_template"}

    def test_toda_chave_de_compose_esta_no_esquema_mcp(self) -> None:
        from sigmai.cartography.compose import KNOWN_PARAMETERS

        mcp = _mcp_module()
        tools = {tool["name"]: tool for tool in mcp.TOOLS}
        schema = set(tools["sigmai_compose_map"]["inputSchema"]["properties"])
        self.assertEqual(set(KNOWN_PARAMETERS) - self.ALIASES - schema, set())
        self.assertEqual(schema - set(KNOWN_PARAMETERS), set())
        for chave in ("production_date", "auto_projected_crs", "round_scale", "margin_mm", "include_logo", "logo_path"):
            self.assertIn(chave, schema)

    def test_plan_map_aceita_exatamente_o_mesmo_que_compose_map(self) -> None:
        mcp = _mcp_module()
        tools = {tool["name"]: tool for tool in mcp.TOOLS}
        self.assertEqual(
            tools["sigmai_plan_map"]["inputSchema"]["properties"],
            tools["sigmai_compose_map"]["inputSchema"]["properties"],
        )
        self.assertEqual(tools["sigmai_plan_map"]["inputSchema"]["required"], ["layer_ids"])

    def test_descricoes_de_inserto_dizem_a_verdade(self) -> None:
        mcp = _mcp_module()
        props = {tool["name"]: tool for tool in mcp.TOOLS}["sigmai_compose_map"]["inputSchema"]["properties"]
        self.assertIn("EXTENSÃO INTEIRA", props["inset_layer_ids"]["description"])
        self.assertIn("SEM inset_layer_ids", props["inset_zoom_factor"]["description"])


class CapacidadesFiltraveis(unittest.TestCase):
    """70 KB de catálogo sem filtro não cabem num cliente pequeno; foi por
    isso que o assistente chutou get_features e get_attribute_table."""

    def _resposta(self):
        from sigmai.permissions import capabilities_payload

        return {"ok": True, "data": capabilities_payload()}

    def test_sem_filtro_devolve_a_resposta_da_ponte_intacta(self) -> None:
        mcp = _mcp_module()
        resposta = self._resposta()
        self.assertIs(mcp.filter_capabilities(resposta, {}), resposta)

    def test_filtro_por_grupo_e_por_texto(self) -> None:
        mcp = _mcp_module()
        por_grupo = mcp.filter_capabilities(self._resposta(), {"group": "attribute_table"})["data"]
        self.assertIn("sample_features", por_grupo["commands"])
        self.assertTrue(all(meta["group"] == "attribute_table" for meta in por_grupo["commands"].values()))
        por_texto = mcp.filter_capabilities(self._resposta(), {"search": "feature"})["data"]
        self.assertIn("sample_features", por_texto["commands"])
        self.assertIn("query_features", por_texto["commands"])
        self.assertNotIn("buffer", por_texto["commands"])

    def test_names_only_cabe_em_qualquer_contexto(self) -> None:
        import json

        mcp = _mcp_module()
        compacto = mcp.filter_capabilities(self._resposta(), {"names_only": True})["data"]
        self.assertNotIn("commands", compacto)
        self.assertIn("attribute_table", compacto["groups"])
        self.assertLess(len(json.dumps(compacto)), 12_000)

    def test_grupo_inexistente_lista_os_grupos(self) -> None:
        mcp = _mcp_module()
        vazio = mcp.filter_capabilities(self._resposta(), {"group": "nao_existe"})["data"]
        self.assertEqual(vazio["command_count"], 0)
        self.assertIn("attribute_table", vazio["hint"])


class AcaoDesconhecidaNaoEAcaoProibida(unittest.TestCase):
    def test_chute_de_nome_recebe_sugestoes(self) -> None:
        from sigmai.validators import ValidationError, validate_command

        with self.assertRaises(ValidationError) as ctx:
            validate_command({"action": "get_features", "params": {}})
        self.assertEqual(ctx.exception.code, "UNKNOWN_ACTION")
        self.assertIn("sample_features", ctx.exception.details["suggestions"])
        with self.assertRaises(ValidationError) as ctx:
            validate_command({"action": "get_attribute_table", "params": {}})
        self.assertIn("inspect_attribute_table", ctx.exception.details["suggestions"])

    def test_acao_desabilitada_continua_not_allowed_com_motivo(self) -> None:
        from sigmai.validators import ValidationError, validate_command

        with self.assertRaises(ValidationError) as ctx:
            validate_command({"action": "create_atlas", "params": {}})
        self.assertEqual(ctx.exception.code, "ACTION_NOT_ALLOWED")
        self.assertTrue(ctx.exception.details.get("disabled"))
        self.assertIn("limitations", str(ctx.exception))


class InsertoAuditado(unittest.TestCase):
    """A auditoria não olhava o inserto: um localizador cortando o estado ao
    meio passava com nota A."""

    def _observacao(self, coverage: dict, shows_main: bool = True) -> dict:
        return {
            "page": {"width_mm": 297.0, "height_mm": 210.0},
            "map": {"item_id": "main_map", "visible_layer_names": ["Parque"]},
            "items": [{"id": "title", "role": "title", "type": "label", "text": "T"}],
            "inset": {"item_id": "inset_map", "layer_coverage": coverage, "shows_main_frame": shows_main},
        }

    def test_regra_existe_e_e_aviso(self) -> None:
        from sigmai.cartography.rulebook import RULES, SEVERITY_WARNING

        regra = next(r for r in RULES if r.id == "CART067")
        self.assertEqual(regra.severity, SEVERITY_WARNING)
        self.assertIn("inset_layer_ids", regra.fix_pt)

    def test_inserto_que_corta_o_estado_reprova(self) -> None:
        from sigmai.cartography.rulebook import _check_inset_locates

        self.assertEqual(_check_inset_locates(self._observacao({"Limite estadual": 0.41})).status, "fail")
        self.assertEqual(_check_inset_locates(self._observacao({"Limite estadual": 1.0})).status, "pass")
        self.assertEqual(_check_inset_locates(self._observacao({"Limite estadual": 1.0}, shows_main=False)).status, "fail")
        self.assertEqual(_check_inset_locates({"inset": None}).status, "skip")

    def test_a_nota_do_compositor_distingue_contexto_de_fator(self) -> None:
        import inspect

        from sigmai.cartography import compose

        fonte = inspect.getsource(compose._add_inset_map)
        self.assertIn("ajustado à extensão inteira de", fonte)
        self.assertIn("inset_zoom_factor não se aplica", fonte)


class RotuloDoCrsNaLinguaDoMapa(unittest.TestCase):
    def test_zona_e_policonica_em_portugues_e_espanhol(self) -> None:
        from sigmai.cartography.compose import _localised_crs_label

        class Crs:
            def __init__(self, description, authid):
                self._d, self._a = description, authid

            def description(self):
                return self._d

            def authid(self):
                return self._a

        utm = Crs("SIRGAS 2000 / UTM zone 24S", "EPSG:31984")
        self.assertEqual(_localised_crs_label(utm, "pt-BR"), "SIRGAS 2000 / UTM zona 24S (EPSG:31984)")
        self.assertEqual(_localised_crs_label(utm, "en"), "SIRGAS 2000 / UTM zone 24S (EPSG:31984)")
        self.assertEqual(_localised_crs_label(utm, "es"), "SIRGAS 2000 / UTM zona 24S (EPSG:31984)")
        poli = Crs("SIRGAS 2000 / Brazil Polyconic", "EPSG:5880")
        self.assertEqual(_localised_crs_label(poli, "pt-BR"), "SIRGAS 2000 / Policônica do Brasil (EPSG:5880)")
        self.assertEqual(_localised_crs_label(poli, "ja"), "SIRGAS 2000 / Brazil Polyconic (EPSG:5880)")


class DetalhesDeCamadaEntregamOQuePrometem(unittest.TestCase):
    def test_layer_details_compoe_quatro_leituras(self) -> None:
        mcp = _mcp_module()
        chamadas = []

        def falso_bridge_call(action, params=None, dry_run=False, timeout=180.0):
            chamadas.append(action)
            if action == "get_layer_info":
                return {"ok": True, "data": {"layer_id": "x", "layer_type": "vector", "geometry_type": "Polygon"}, "warnings": []}
            if action == "sample_features":
                self.assertEqual(params["max_features"], 3)
                return {"ok": True, "data": {"features": [{"Nome_UC": "PE das Carnaúbas"}]}}
            if action == "inspect_layer_style":
                return {"ok": True, "data": {"renderer_type": "singleSymbol"}}
            if action == "validate_geometries":
                return {"ok": True, "data": {"invalid_count": 0}}
            raise AssertionError(action)

        mcp.bridge_call = falso_bridge_call
        resposta = mcp.layer_details({"layer_id": "x", "sample_size": 3})
        self.assertEqual(chamadas, ["get_layer_info", "sample_features", "inspect_layer_style", "validate_geometries"])
        self.assertEqual(resposta["data"]["sample"]["features"][0]["Nome_UC"], "PE das Carnaúbas")
        self.assertIn("style", resposta["data"])
        self.assertIn("geometry_validity", resposta["data"])


if __name__ == "__main__":
    unittest.main()


class ParametrosNaoLidosSaoAvisados(unittest.TestCase):
    """sample_features com filter=... devolvia as dez primeiras feições como se
    tivesse filtrado. O parâmetro que o comando não lê agora volta em warnings."""

    def test_extracao_fechada_e_aberta(self) -> None:
        from sigmai.parameter_introspection import declared_parameters

        def fechado(params, context):
            a = params.get("alpha")
            b = params["beta"]
            return a, b, ("gamma" in params)

        def aberto(params, context):
            return outra(params)

        def outra(params):
            return params

        nomes, closed = declared_parameters(fechado)
        self.assertEqual(set(nomes), {"alpha", "beta", "gamma"})
        self.assertTrue(closed)
        self.assertFalse(declared_parameters(aberto)[1])

    def test_registro_avisa_sem_recusar(self) -> None:
        from sigmai.command_registry import CommandRegistry

        registry = CommandRegistry({})

        def handler(params, context):
            return {"echo": params.get("layer_id")}

        registry.register("sample_features", handler)
        resposta = registry.execute({"action": "sample_features", "params": {"layer_id": "x", "filter": "a", "fields": ["b"]}})
        self.assertTrue(resposta["ok"])
        self.assertEqual(len(resposta["warnings"]), 1)
        self.assertIn("fields, filter", resposta["warnings"][0])
        self.assertIn("layer_id", resposta["warnings"][0])
        limpa = registry.execute({"action": "sample_features", "params": {"layer_id": "x"}})
        self.assertEqual(limpa["warnings"], [])

    def test_catalogo_de_parametros_das_acoes_reais(self) -> None:
        from sigmai.command_registry import CommandRegistry
        from sigmai.qgis_actions import register_actions

        registry = CommandRegistry({})
        register_actions(registry)
        catalogue = registry.parameter_catalogue()
        self.assertIn("max_features", catalogue["sample_features"]["reads"])
        self.assertTrue(catalogue["sample_features"]["complete"])
        self.assertIn("expression", catalogue["query_features"]["reads"])
        # compose_map repassa params ao compositor: aberto, sem avisos falsos.
        self.assertFalse(catalogue["compose_map"]["complete"])
        fechados = sum(1 for entry in catalogue.values() if entry["complete"])
        self.assertGreater(fechados, 100)


class OrigemDoEstiloEPreservada(unittest.TestCase):
    """apply_single_symbol seguido de compose_map(apply_style='missing')
    reestilizava a camada recém-estilizada e o relatório dizia 'estilizada'."""

    def test_camada_marcada_pelo_usuario_nao_e_padrao(self) -> None:
        from sigmai.cartography.symbology import (
            STYLE_ORIGIN_PALETTE, STYLE_ORIGIN_USER, has_default_symbology, mark_style_origin, style_origin,
        )

        class Renderer:
            pass

        Renderer.__name__ = "QgsSingleSymbolRenderer"

        class Layer:
            def __init__(self):
                self.props = {}

            def renderer(self):
                return Renderer()

            def setCustomProperty(self, key, value):  # noqa: N802
                self.props[key] = value

            def customProperty(self, key, default=""):  # noqa: N802
                return self.props.get(key, default)

        layer = Layer()
        self.assertTrue(has_default_symbology(layer))
        mark_style_origin(layer, STYLE_ORIGIN_USER)
        self.assertFalse(has_default_symbology(layer))
        self.assertEqual(style_origin(layer), STYLE_ORIGIN_USER)
        mark_style_origin(layer, STYLE_ORIGIN_PALETTE)
        self.assertFalse(has_default_symbology(layer))

    def test_camada_sem_customproperty_continua_funcionando(self) -> None:
        from sigmai.cartography.symbology import has_default_symbology, style_origin

        class Renderer:
            pass

        Renderer.__name__ = "QgsSingleSymbolRenderer"

        class LayerSemProps:
            def renderer(self):
                return Renderer()

        self.assertEqual(style_origin(LayerSemProps()), "")
        self.assertTrue(has_default_symbology(LayerSemProps()))


class LayoutSubstituidoPeloNome(unittest.TestCase):
    def test_compose_substitui_layout_existente_e_avisa_sobre_acumulo(self) -> None:
        import inspect

        from sigmai.cartography import compose

        fonte = inspect.getsource(compose._compose_map)
        self.assertIn("replace_layout", fonte)
        self.assertIn("removeLayout", fonte)
        self.assertIn("layout_name para substituir", fonte)
