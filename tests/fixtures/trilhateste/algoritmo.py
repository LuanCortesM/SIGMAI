# -*- coding: utf-8 -*-
"""Um algoritmo real: mede o comprimento total de uma camada de linhas."""
from qgis.core import (
    QgsDistanceArea,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingOutputNumber,
    QgsUnitTypes,
)


class ComprimentoDaTrilha(QgsProcessingAlgorithm):
    ENTRADA = "INPUT"
    FATOR = "FATOR"
    COMPRIMENTO = "COMPRIMENTO_M"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ENTRADA, "Camada de trilha", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber(
            self.FATOR, "Fator de sinuosidade", QgsProcessingParameterNumber.Double,
            defaultValue=1.0, minValue=0.1, maxValue=5.0))
        self.addOutput(QgsProcessingOutputNumber(self.COMPRIMENTO, "Comprimento (m)"))

    def processAlgorithm(self, parameters, context, feedback):
        origem = self.parameterAsSource(parameters, self.ENTRADA, context)
        fator = self.parameterAsDouble(parameters, self.FATOR, context)
        medidor = QgsDistanceArea()
        medidor.setSourceCrs(origem.sourceCrs(), context.transformContext())
        medidor.setEllipsoid("WGS84")
        total = 0.0
        for feicao in origem.getFeatures():
            if feicao.hasGeometry():
                total += medidor.measureLength(feicao.geometry())
        return {self.COMPRIMENTO: round(total * fator, 2)}

    def name(self):
        return "comprimento_da_trilha"

    def displayName(self):
        return "Comprimento da trilha"

    def group(self):
        return "Medidas"

    def groupId(self):
        return "medidas"

    def createInstance(self):
        return ComprimentoDaTrilha()
