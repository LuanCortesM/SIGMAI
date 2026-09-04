# -*- coding: utf-8 -*-
"""Mapas de base e gerência de plugins: as duas promessas que eram esqueleto.

Antes desta rodada, ``load_wms_layer``, ``load_wfs_layer``,
``load_xyz_tile_layer`` e ``load_arcgis_rest_layer`` validavam a URL e
levantavam ``NETWORK_LOAD_NOT_ENABLED`` — "requires an explicit future
network-enabled workflow". A capacidade aparecia no catálogo e no
``sigmai_capabilities``, e não existia.
"""

from __future__ import annotations

import unittest

from sigmai.cartography.compose import (
    _basemap_attributions,
    _basemap_zoom_advice,
    _required_tile_zoom,
)
from sigmai.qgis_actions.data_sources import KNOWN_TILE_ATTRIBUTION, _tile_source_kind


class _CamadaFalsa:
    """Dublê com a superfície que os ajudantes tocam, sem exigir PyQGIS."""

    def __init__(self, source: str = "", nome: str = "Base", credito: str = "") -> None:
        self._source, self._nome, self._credito = source, nome, credito

    def source(self) -> str:
        return self._source

    def name(self) -> str:
        return self._nome

    def attribution(self) -> str:
        return self._credito


class _ExtensaoFalsa:
    xmin, xmax, ymin, ymax = 490_000.0, 498_000.0, 7_510_000.0, 7_515_000.0

    def __init__(self, escala: int) -> None:
        self.scale_denominator = escala


class _CrsInvalido:
    def isValid(self) -> bool:
        return False

    def authid(self) -> str:
        return ""


class NivelDeZoomExigido(unittest.TestCase):
    """A escala impressa determina o nível de tile necessário."""

    def test_escalas_conhecidas(self) -> None:
        # Referências do esquema Web Mercator na latitude do sudeste brasileiro.
        for escala, esperado in ((1_000, 19), (32_000, 14), (150_000, 12), (5_000_000, 7)):
            with self.subTest(escala=escala):
                self.assertEqual(_required_tile_zoom(escala, -23.0), esperado)

    def test_latitude_alta_exige_menos_zoom(self) -> None:
        # O metro por pixel encolhe com o cosseno da latitude.
        self.assertLess(_required_tile_zoom(32_000, 70.0), _required_tile_zoom(32_000, 0.0))

    def test_valores_degenerados_nao_estouram(self) -> None:
        for escala in (0, -1):
            with self.subTest(escala=escala):
                self.assertEqual(_required_tile_zoom(escala, -23.0), 0)
        # Latitude fora do domínio do Web Mercator é presa nos polos úteis.
        self.assertGreaterEqual(_required_tile_zoom(32_000, 200.0), 0)


class MapaDeBaseSemTileNaEscala(unittest.TestCase):
    """Base com zmax baixo desenha nada, entra na legenda e passava com nota A."""

    def test_zmax_insuficiente_gera_aviso(self) -> None:
        camada = _CamadaFalsa("type=xyz&url=x&zmin=0&zmax=7", "Base de campo")
        notas = _basemap_zoom_advice([camada], _ExtensaoFalsa(32_000), _CrsInvalido(), {})
        self.assertEqual(len(notas), 1)
        self.assertIn("zoom 7", notas[0])
        self.assertIn("zoom 14", notas[0])
        self.assertIn("Base de campo", notas[0])

    def test_zmax_suficiente_fica_calado(self) -> None:
        camada = _CamadaFalsa("type=xyz&url=x&zmin=0&zmax=19", "OSM")
        self.assertEqual(_basemap_zoom_advice([camada], _ExtensaoFalsa(32_000), _CrsInvalido(), {}), [])

    def test_camada_que_nao_e_xyz_e_ignorada(self) -> None:
        for fonte in ("/dados/trilha.shp", "crs=EPSG:4326&layers=OSM&url=https://x/wms", ""):
            with self.subTest(fonte=fonte):
                camada = _CamadaFalsa(fonte, "Outra")
                self.assertEqual(
                    _basemap_zoom_advice([camada], _ExtensaoFalsa(32_000), _CrsInvalido(), {}), []
                )

    def test_xyz_sem_zmax_nao_estoura(self) -> None:
        camada = _CamadaFalsa("type=xyz&url=x", "Sem zmax")
        self.assertEqual(_basemap_zoom_advice([camada], _ExtensaoFalsa(32_000), _CrsInvalido(), {}), [])


class CreditoDoMapaDeBase(unittest.TestCase):
    """A licença do mapa de base exige o crédito na peça publicada."""

    def test_recolhe_o_credito_da_camada(self) -> None:
        camadas = [
            _CamadaFalsa(nome="OSM", credito="© OpenStreetMap contributors (ODbL)"),
            _CamadaFalsa(nome="Trilha", credito=""),
        ]
        self.assertEqual(_basemap_attributions(camadas), ["© OpenStreetMap contributors (ODbL)"])

    def test_nao_repete_o_mesmo_credito(self) -> None:
        credito = "© OpenStreetMap contributors (ODbL)"
        camadas = [_CamadaFalsa(nome=f"c{i}", credito=credito) for i in range(3)]
        self.assertEqual(_basemap_attributions(camadas), [credito])

    def test_marcador_de_fonte_local_nao_vira_credito(self) -> None:
        # Um cache local sem atribuição declarada não é crédito de licença.
        camadas = [_CamadaFalsa(nome="cache", credito="Fonte local (sem atribuição declarada)")]
        self.assertEqual(_basemap_attributions(camadas), [])

    def test_camada_sem_o_metodo_nao_estoura(self) -> None:
        class SemAtribuicao:
            def name(self) -> str:
                return "x"

        self.assertEqual(_basemap_attributions([SemAtribuicao()]), [])


class OrigemDoTile(unittest.TestCase):
    """Cache no disco é o caso de campo sem sinal e não é acesso de rede."""

    def test_file_e_local(self) -> None:
        self.assertEqual(_tile_source_kind("file:///dados/tiles/{z}/{x}/{y}.png"), "local")

    def test_https_e_rede(self) -> None:
        self.assertEqual(_tile_source_kind("https://tile.openstreetmap.org/{z}/{x}/{y}.png"), "rede")

    def test_atribuicao_conhecida_do_osm(self) -> None:
        for host in ("tile.openstreetmap.org", "a.tile.openstreetmap.org"):
            with self.subTest(host=host):
                self.assertIn("OpenStreetMap", KNOWN_TILE_ATTRIBUTION[host])
                self.assertIn("ODbL", KNOWN_TILE_ATTRIBUTION[host])


if __name__ == "__main__":
    unittest.main()
