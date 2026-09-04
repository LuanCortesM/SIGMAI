# -*- coding: utf-8 -*-
"""Provedor de Processing do TrilhaTeste."""
from qgis.core import QgsProcessingProvider
from .algoritmo import ComprimentoDaTrilha


class TrilhaTesteProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(ComprimentoDaTrilha())

    def id(self):
        return "trilhateste"

    def name(self):
        return "TrilhaTeste"

    def longName(self):
        return "TrilhaTeste — medidas de trilha"
