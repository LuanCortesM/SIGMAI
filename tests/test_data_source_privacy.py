# -*- coding: utf-8 -*-
"""Vazamento de credencial e symlink de sessão achados na auditoria pré-publicação.

Defeito 1 (crítico): uma camada PostGIS, MSSQL ou Oracle guarda a senha em
texto puro na string de conexão (``layer.source()``), e ``get_layer_info``,
``raster_info``, ``broken_data_source_report``, ``list_gpx_layers`` e o
``_layer_record`` de ``layer_tree`` devolviam essa string crua — todas ações
somente-leitura, sem consentimento algum antes de responder à IA. A correção
promove a redação a um único lugar (``project_overview.redact_source`` /
``redact_layer_source``) e todas passam a usar esse ponto único.

Defeito 4: ``write_session_file``/``invalidate_session_file`` escreviam
através de um symlink pré-posicionado no caminho de sessão, sobrescrevendo o
alvo com o token em texto puro.

São todos em Python puro (sem PyQGIS), no mesmo espírito de
``test_cartography_regressions.py``: um dublê mínimo no lugar de
``QgsVectorLayer`` real. A prova contra QGIS de verdade (a que mostra a
senha saindo pelo ``get_layer_info`` real e o segfault do defeito 2) está em
scripts separados, fora deste pacote de testes.
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from sigmai.qgis_actions.project_overview import redact_layer_source, redact_source
import sigmai.session as session


ROOT = Path(__file__).resolve().parents[1]
QGIS_ACTIONS = ROOT / "sigmai" / "qgis_actions"


class _CamadaFalsa:
    """Dublê mínimo: só o método que ``redact_layer_source`` toca."""

    def __init__(self, source: str) -> None:
        self._source = source

    def source(self) -> str:
        return self._source


class _CamadaQueEstoura:
    def source(self):
        raise RuntimeError("provedor não respondeu")


class VariacoesDeEscritaDaSenha(unittest.TestCase):
    """A senha de PostGIS/MSSQL/Oracle não pode sair em texto puro, em nenhuma grafia comum."""

    def test_password_minusculo_com_aspas_simples(self) -> None:
        fonte = "dbname='sigmai' host=localhost user='postgres' password='S3cr3t-DB-Passw0rd!'"
        redigida = redact_source(fonte)
        self.assertNotIn("S3cr3t-DB-Passw0rd!", redigida)
        self.assertIn("<omitido>", redigida)
        # O resto da string de conexão continua legível — a IA ainda sabe
        # qual banco, host e usuário, só não a senha.
        self.assertIn("dbname='sigmai'", redigida)
        self.assertIn("host=localhost", redigida)
        self.assertIn("user='postgres'", redigida)

    def test_password_maiusculo(self) -> None:
        fonte = "dbname='x' PASSWORD='Outro-Segredo' host=y"
        self.assertNotIn("Outro-Segredo", redact_source(fonte))

    def test_password_capitalizado(self) -> None:
        fonte = "dbname='x' Password='Mais-Um-Segredo' host=y"
        self.assertNotIn("Mais-Um-Segredo", redact_source(fonte))

    def test_pwd_maiusculo_sem_aspas_estilo_odbc(self) -> None:
        # Connection string ODBC típica de MSSQL: chave=valor separado por ';'.
        fonte = "Driver={ODBC Driver 17 for SQL Server};Server=host;Database=db;UID=admin;PWD=Secret123;"
        redigida = redact_source(fonte)
        self.assertNotIn("Secret123", redigida)
        # Só a credencial some — o resto da connection string continua útil.
        self.assertIn("UID=admin", redigida)
        self.assertIn("Server=host", redigida)

    def test_pwd_minusculo_sem_aspas(self) -> None:
        fonte = "host=y pwd=NoQuotesHere port=1521 service=XE"
        redigida = redact_source(fonte)
        self.assertNotIn("NoQuotesHere", redigida)
        self.assertIn("port=1521", redigida)

    def test_password_com_aspas_duplas(self) -> None:
        fonte = 'host=y password="Segredo-Com-Aspas-Duplas" port=5432'
        self.assertNotIn("Segredo-Com-Aspas-Duplas", redact_source(fonte))

    def test_apikey_em_query_string_de_url(self) -> None:
        bruta = "https://example.com/wfs?service=WFS&apikey=RAWKEY999&typename=x"
        redigida = redact_source(bruta)
        self.assertNotIn("RAWKEY999", redigida)
        self.assertIn("typename=x", redigida)

    def test_key_como_parametro_de_url_tambem_e_credencial(self) -> None:
        # Serviços de tile comerciais (ex.: MapTiler) usam "?key=" para a
        # chave de API — mesma palavra que, em URI PostGIS, é a coluna de
        # chave primária. Como parâmetro de URL, é segredo.
        bruta = "https://maps.example.com/tiles/{z}/{x}/{y}.png?key=ABC123XYZ"
        self.assertNotIn("ABC123XYZ", redact_source(bruta))

    def test_key_de_coluna_primaria_do_postgis_nao_e_credencial(self) -> None:
        # key='id' é o nome da coluna de chave primária em URI PostGIS/MSSQL,
        # não segredo — redigir isso não protege nada e estraga a leitura.
        fonte = "dbname='x' key='id' host=y"
        self.assertEqual(redact_source(fonte), fonte)

    def test_apikey_dentro_de_url_percent_encoded(self) -> None:
        # Uri que o SIGMAI monta para XYZ/WMS/ArcGIS REST: a URL original
        # (com a apikey) vai inteira, percent-encoded, dentro de um "url=".
        from urllib.parse import quote

        url_original = "https://tiles.example.com/{z}/{x}/{y}.png?apikey=SECRETKEY123"
        uri = f"type=xyz&url={quote(url_original, safe='')}&zmin=0&zmax=19"
        redigida = redact_source(uri)
        self.assertNotIn("SECRETKEY123", redigida)
        # A estrutura do resto da URI (zmin/zmax) continua legível.
        self.assertIn("zmin=0", redigida)
        self.assertIn("zmax=19", redigida)


class CaminhoDeArquivoContinuaLegivel(unittest.TestCase):
    """O caso comum não pode virar vítima da redação: a IA precisa do caminho."""

    def test_caminho_de_shapefile_absoluto_intacto(self) -> None:
        caminho = "/home/joao/Documentos/Projeto SIGMAI/dados/trilha.shp"
        self.assertEqual(redact_source(caminho), caminho)

    def test_caminho_de_geopackage_com_camada_intacto(self) -> None:
        caminho = "/home/joao/dados/limites.gpkg|layername=municipios"
        self.assertEqual(redact_source(caminho), caminho)

    def test_caminho_com_espacos_e_acentos_intacto(self) -> None:
        caminho = "/mnt/user-data/uploads/03 SIGMAI/Shapes/_teste_sigmai/estações.shp"
        self.assertEqual(redact_source(caminho), caminho)

    def test_string_vazia_e_none_nao_quebram(self) -> None:
        self.assertEqual(redact_source(""), "")

    def test_camada_falsa_sem_credencial_sai_igual(self) -> None:
        camada = _CamadaFalsa("/dados/limites_municipais.shp")
        self.assertEqual(redact_layer_source(camada), "/dados/limites_municipais.shp")


class RedactLayerSourceComCamada(unittest.TestCase):
    """``redact_layer_source`` é o ponto único usado pelas cinco ações que vazavam."""

    def test_redige_a_senha_da_camada(self) -> None:
        camada = _CamadaFalsa("dbname='x' host=y user='postgres' password='S3cr3t!'")
        redigida = redact_layer_source(camada)
        self.assertNotIn("S3cr3t!", redigida)
        self.assertIn("<omitido>", redigida)

    def test_layer_source_que_lanca_excecao_nao_derruba_a_acao(self) -> None:
        # source() pode lançar (provedor quebrado); a ação tem que devolver
        # string vazia, não propagar a exceção.
        self.assertEqual(redact_layer_source(_CamadaQueEstoura()), "")


class SaidasQueUsamOPontoUnicoDeRedacao(unittest.TestCase):
    """Guarda de regressão: as cinco ações do audit têm de chamar a redação, não layer.source() cru.

    Achado ao investigar: dentro do escopo (data_sources.py, get_layer_info.py,
    raster.py, layer_tree.py, project_overview.py), só existem os cinco
    pontos que a auditoria listou — nenhum sexto ``layer.source()`` devolvido
    cru foi encontrado. Este teste impede que uma edição futura reintroduza
    exatamente esse defeito num desses cinco lugares.
    """

    def _fonte(self, caminho: str) -> str:
        return (QGIS_ACTIONS / caminho).read_text(encoding="utf-8")

    def test_get_layer_info_usa_redact_layer_source(self) -> None:
        codigo = self._fonte("get_layer_info.py")
        self.assertIn("redact_layer_source(layer)", codigo)
        self.assertNotIn('"source": layer.source()', codigo)

    def test_raster_info_usa_redact_layer_source(self) -> None:
        codigo = self._fonte("raster.py")
        self.assertIn("redact_layer_source(layer)", codigo)
        self.assertNotIn('"source": layer.source()', codigo)

    def test_data_sources_usa_redact_layer_source_nos_dois_lugares(self) -> None:
        codigo = self._fonte("data_sources.py")
        # broken_data_source_report e list_gpx_layers: os dois pontos do audit.
        self.assertEqual(codigo.count("redact_layer_source(layer)"), 2)
        self.assertNotIn('"source": layer.source()', codigo)

    def test_layer_tree_layer_record_usa_redact_layer_source(self) -> None:
        codigo = self._fonte("layer_tree.py")
        self.assertIn('"source": redact_layer_source(layer)', codigo)

    def test_project_overview_continua_com_a_redacao_original(self) -> None:
        codigo = self._fonte("project_overview.py")
        self.assertIn("def redact_source(", codigo)
        self.assertIn("def redact_layer_source(", codigo)


class SessaoRecusaSymlink(unittest.TestCase):
    """Defeito 4: escrever a sessão não pode seguir um symlink pré-posicionado."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="sigmai_session_test_")
        self.work = Path(self._tmp.name)
        self._originais = {
            "session_file_path": session.session_file_path,
            "pairing_session_file": session.pairing_session_file,
            "fallback_session_dir": session.fallback_session_dir,
            "fallback_session_file_path": session.fallback_session_file_path,
        }

    def tearDown(self) -> None:
        for nome, valor in self._originais.items():
            setattr(session, nome, valor)
        self._tmp.cleanup()

    def _fixa_caminhos_de_sessao(self, caminho: Path) -> None:
        session.session_file_path = lambda: caminho
        session.pairing_session_file = lambda code: caminho
        session.fallback_session_dir = lambda: caminho.parent
        session.fallback_session_file_path = lambda: caminho

    def test_write_session_file_recusa_symlink_e_nao_sobrescreve_o_alvo(self) -> None:
        vitima = self.work / "arquivo_vitima.txt"
        vitima.write_text("conteúdo original\n", encoding="utf-8")
        sessions_dir = self.work / "sessions"
        sessions_dir.mkdir()
        caminho_reserva = sessions_dir / "current_bridge_session.json"
        caminho_reserva.symlink_to(vitima)
        self._fixa_caminhos_de_sessao(caminho_reserva)

        payload = session.build_session_payload(
            host="127.0.0.1", port=9999, token="TOKEN-SECRETO",
            qgis_version="3.34", plugin_version="1.0", running=True,
        )
        with self.assertRaises(RuntimeError):
            session.write_session_file(payload)

        self.assertEqual(vitima.read_text(encoding="utf-8"), "conteúdo original\n")
        self.assertTrue(caminho_reserva.is_symlink())

    def test_invalidate_session_file_tambem_recusa_symlink(self) -> None:
        vitima = self.work / "arquivo_vitima2.txt"
        vitima.write_text("conteúdo original 2\n", encoding="utf-8")
        sessions_dir = self.work / "sessions"
        sessions_dir.mkdir()
        caminho_reserva = sessions_dir / "current_bridge_session.json"
        caminho_reserva.symlink_to(vitima)
        self._fixa_caminhos_de_sessao(caminho_reserva)

        # invalidate_session_file() é silenciosa por design (mesmo padrão da
        # função original) — o que importa é que a vítima fica intacta.
        session.invalidate_session_file()
        self.assertEqual(vitima.read_text(encoding="utf-8"), "conteúdo original 2\n")

    def test_write_text_secure_recusa_symlink_diretamente(self) -> None:
        vitima = self.work / "vitima3.txt"
        vitima.write_text("x", encoding="utf-8")
        link = self.work / "link.json"
        link.symlink_to(vitima)
        with self.assertRaises(RuntimeError):
            session._write_text_secure(link, "conteudo malicioso")
        self.assertEqual(vitima.read_text(encoding="utf-8"), "x")


class PermissaoDoArquivoDeSessao(unittest.TestCase):
    """O token de sessão não pode existir, nem por um instante, com permissão mais aberta que 0600."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="sigmai_session_perm_")
        self.work = Path(self._tmp.name)
        self._originais = {
            "session_file_path": session.session_file_path,
            "pairing_session_file": session.pairing_session_file,
            "fallback_session_dir": session.fallback_session_dir,
            "fallback_session_file_path": session.fallback_session_file_path,
        }
        self._umask_anterior = os.umask(0o022)

    def tearDown(self) -> None:
        os.umask(self._umask_anterior)
        for nome, valor in self._originais.items():
            setattr(session, nome, valor)
        self._tmp.cleanup()

    def test_arquivo_e_criado_com_modo_0600(self) -> None:
        sessions_dir = self.work / "sessions"
        session.session_file_path = lambda: sessions_dir / "current_bridge_session.json"
        session.pairing_session_file = lambda code: sessions_dir / f"{code}.json"
        session.fallback_session_dir = lambda: sessions_dir / "fallback"
        session.fallback_session_file_path = lambda: sessions_dir / "fallback" / "current_bridge_session.json"

        payload = session.build_session_payload(
            host="127.0.0.1", port=9999, token="TOKEN-NORMAL",
            qgis_version="3.34", plugin_version="1.0", running=True,
        )
        caminho = session.write_session_file(payload)
        modo = stat.S_IMODE(os.stat(caminho).st_mode)
        self.assertEqual(modo, 0o600)

    def test_permissao_permanece_0600_apos_invalidate(self) -> None:
        sessions_dir = self.work / "sessions"
        session.session_file_path = lambda: sessions_dir / "current_bridge_session.json"
        session.pairing_session_file = lambda code: sessions_dir / f"{code}.json"
        session.fallback_session_dir = lambda: sessions_dir / "fallback"
        session.fallback_session_file_path = lambda: sessions_dir / "fallback" / "current_bridge_session.json"

        payload = session.build_session_payload(
            host="127.0.0.1", port=9999, token="TOKEN-NORMAL",
            qgis_version="3.34", plugin_version="1.0", running=True,
        )
        caminho = session.write_session_file(payload)
        session.invalidate_session_file()
        modo = stat.S_IMODE(os.stat(caminho).st_mode)
        self.assertEqual(modo, 0o600)


if __name__ == "__main__":
    unittest.main()
