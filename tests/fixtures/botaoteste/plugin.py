# -*- coding: utf-8 -*-
"""Plugin só de interface: menu, barra e diálogo. Nada chamável por programa."""
from qgis.PyQt.QtWidgets import QAction, QDialog, QDockWidget


class JanelaDeCalibracao(QDialog):
    """Diálogo modal — se alguém disparar isto por programa, a ponte congela."""


class BotaoTestePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.acoes = []

    def initGui(self):
        acao_calibrar = QAction("Calibrar altimetria", self.iface.mainWindow())
        acao_calibrar.triggered.connect(self.abrir_calibracao)
        self.iface.addPluginToMenu("&BotaoTeste", acao_calibrar)
        self.iface.addToolBarIcon(acao_calibrar)

        acao_exportar = QAction("Exportar perfil da trilha", self.iface.mainWindow())
        self.iface.addPluginToMenu("&BotaoTeste", acao_exportar)

        self.painel = QDockWidget("Perfil da trilha")
        self.iface.addDockWidget(0x2, self.painel)
        self.acoes = [acao_calibrar, acao_exportar]

    def abrir_calibracao(self):
        JanelaDeCalibracao(self.iface.mainWindow()).exec_()

    def unload(self):
        for acao in self.acoes:
            self.iface.removePluginMenu("&BotaoTeste", acao)
            self.iface.removeToolBarIcon(acao)
