"""Chat dentro do QGIS: a pessoa conversa com um modelo que só tem as ferramentas do SIGMAI.

``providers`` e ``session`` não importam Qt nem QGIS, para serem testados
fora dele; ``qgis_transport`` e ``keys`` são a parte que depende do QGIS, e a
janela fica em ``sigmai/ui/chat_dock.py``.
"""
