"""Transporte do chat pelo gerenciador de rede do QGIS.

Roda na thread de trabalho do chat: o ``QgsNetworkAccessManager.instance()``
de uma thread que não é a principal é um gerenciador próprio daquela thread,
com o proxy, os certificados e o tempo limite configurados no QGIS. A resposta
chega aos poucos (SSE) e é entregue linha a linha.
"""

from __future__ import annotations

from typing import Callable

from .providers import ProviderError, check_url

#: Sem nenhum byte por este tempo, o pedido é dado como perdido. O QGIS usa 60 s
#: (Configurações ▸ Rede), e um modelo raciocinando com 20 ferramentas pode
#: levar mais que isso até o primeiro byte: o Gemini gratuito levou.
INACTIVITY_S = 180


def qgis_transport(url: str, headers: dict, body: bytes, on_line: Callable[[str], None],
                   should_stop: Callable[[], bool]) -> tuple[int, str]:
    from qgis.core import QgsNetworkAccessManager  # type: ignore
    from qgis.PyQt.QtCore import QByteArray, QEventLoop, QTimer, QUrl  # type: ignore
    from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest  # type: ignore

    from ..cartography.qtcompat import qt_enum

    check_url(url)
    request = QNetworkRequest(QUrl(url))
    for name, value in headers.items():
        request.setRawHeader(name.encode("ascii"), str(value).encode("utf-8"))
    reply = QgsNetworkAccessManager.instance().post(request, QByteArray(body))
    # O QGIS pendura no pedido um QTimer "timeoutTimer" com o tempo limite de
    # rede dele, reiniciado a cada byte. Só neste pedido, o intervalo passa a
    # ser o do chat; o tempo limite do resto do QGIS não muda.
    qgis_timer = reply.findChild(QTimer, "timeoutTimer")
    if qgis_timer is not None:
        qgis_timer.setInterval(INACTIVITY_S * 1000)
    loop = QEventLoop()
    buffer = bytearray()
    collected = bytearray()
    status_attribute = qt_enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute")
    cancelled = []

    def status() -> int:
        value = reply.attribute(status_attribute)
        return int(value) if value is not None else 0

    def read() -> None:
        chunk = bytes(reply.readAll())
        if status() not in (0, 200):
            collected.extend(chunk)
            return
        buffer.extend(chunk)
        while b"\n" in buffer:
            line, _, rest = bytes(buffer).partition(b"\n")
            buffer[:] = rest
            on_line(line.decode("utf-8", errors="replace").rstrip("\r"))

    def check_stop() -> None:
        if should_stop() and not cancelled:
            cancelled.append(True)
            reply.abort()

    reply.readyRead.connect(read)
    reply.finished.connect(loop.quit)
    timer = QTimer()
    timer.timeout.connect(check_stop)
    timer.start(200)
    if not reply.isFinished():
        loop.exec()
    timer.stop()
    read()
    if buffer:
        on_line(bytes(buffer).decode("utf-8", errors="replace").rstrip("\r"))
    code = status()
    error = reply.error()
    reply.deleteLater()
    if cancelled:
        return 499, ""
    if code == 0 and error == qt_enum(QNetworkReply, "NetworkError", "OperationCanceledError"):
        raise ProviderError("timeout", f"O provedor não mandou nenhum dado em {INACTIVITY_S} s.")
    if code == 0 and error != qt_enum(QNetworkReply, "NetworkError", "NoError"):
        raise ProviderError("network", f"Sem conexão com o provedor: {reply.errorString()}")
    if code != 200:
        return code, bytes(collected).decode("utf-8", errors="replace")
    return 200, ""
