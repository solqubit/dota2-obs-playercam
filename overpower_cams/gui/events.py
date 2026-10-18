"""Canal de eventos hacia la ventana.

Los eventos nacen en otros hilos (motor con su lock tomado, servidor GSI, entrada local,
OBS). `post` solo emite una señal de Qt: la ventana la recibe con conexión en cola, en
el hilo de la interfaz. Nunca bloquea ni vuelve a llamar al motor.
"""
import time

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    posted = Signal(str, str)   # (hora HH:MM:SS, texto)

    def post(self, text) -> None:
        try:
            self.posted.emit(time.strftime("%H:%M:%S"), str(text))
        except RuntimeError:
            pass   # la interfaz ya se cerró
