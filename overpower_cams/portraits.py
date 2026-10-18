"""Modelo de los retratos de la barra superior de Dota: dónde está cada uno.

Sin variables globales ni E/S. Las coordenadas son relativas al ALTO de la ventana de Dota y al centro de la
pantalla (la interfaz escala con el alto y va centrada: sirve en cualquier
resolución).
"""
import math
import threading

from .config import (DEFAULT_ROW_OFFSET, DEFAULT_WEIGHT, PORTRAIT_PITCH, SLOTS,
                     TOPBAR_MAX_Y)

MAX_N = 10   # tope de clicks que "pesa" un retrato aprendido


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _slot_index(slot: str) -> int:
    """Posición del retrato contando desde el centro de la barra: r5 y d1 = 0, r1 y d5 = 4."""
    n = int(slot[1:])
    return 5 - n if slot[0] == "r" else n - 1


def _limpiar(learned) -> dict[str, list[float]]:
    """Se queda solo con las entradas válidas: slot conocido y [x, y, n] numéricos.
    Un archivo corrupto nunca debe impedir que la app arranque."""
    out: dict[str, list[float]] = {}
    if not isinstance(learned, dict):
        return out
    for slot, v in learned.items():
        if slot not in SLOTS:
            continue
        if not isinstance(v, (list, tuple)) or len(v) != 3 or not all(_numero(c) for c in v):
            continue
        x, y, n = v
        n = min(int(n), MAX_N)
        if n < 1:
            continue
        out[slot] = [x, y, n]
    return out


class PortraitModel:
    """Retratos aprendidos: slot ('r1'..'d5') -> [x, y, n] (centro promedio de los
    últimos clicks y cuántos se promediaron). Seguro entre hilos."""

    def __init__(self, learned: dict[str, list[float]] | None = None):
        self._pts = _limpiar(learned)
        self._lock = threading.Lock()

    def _row_offsets(self) -> dict[str, float]:
        est = {side: [off] * DEFAULT_WEIGHT for side, off in DEFAULT_ROW_OFFSET.items()}
        for slot, (x, _, n) in self._pts.items():
            est[slot[0]] += [abs(x) - _slot_index(slot) * PORTRAIT_PITCH] * int(n)
        out = {}
        for side, vals in est.items():
            med = sorted(vals)[len(vals) // 2]
            good = [v for v in vals if abs(v - med) <= PORTRAIT_PITCH / 2]
            out[side] = sum(good) / len(good)
        return out

    def row_offsets(self) -> dict[str, float]:
        """Distancia del centro de la pantalla al retrato más cercano de cada fila
        (Radiant/Dire). Como la separación entre retratos es fija, con esto quedan
        ubicados los 10. Parte de DEFAULT_ROW_OFFSET y se afina con los clicks
        aprendidos; la mediana evita que un click raro la mueva."""
        with self._lock:
            return self._row_offsets()

    def portrait_at(self, rx: float, ry: float) -> str | None:
        """Slot del retrato bajo el click (coordenadas relativas al alto), o None."""
        if ry > TOPBAR_MAX_Y:
            return None
        side = "r" if rx < 0 else "d"
        with self._lock:
            off = self._row_offsets()[side]
        k = round((abs(rx) - off) / PORTRAIT_PITCH)
        if not 0 <= k <= 4:
            return None     # entre las dos filas (reloj) o más allá del último retrato
        return f"r{5 - k}" if side == "r" else f"d{k + 1}"

    def learn(self, slot: str, rx: float, ry: float) -> None:
        """Suma un click al promedio del retrato `slot` (n con tope MAX_N)."""
        with self._lock:
            x, y, n = self._pts.get(slot, (rx, ry, 0))
            n = min(n + 1, MAX_N)
            self._pts[slot] = [round((x * (n - 1) + rx) / n, 4),
                               round((y * (n - 1) + ry) / n, 4), n]

    def forget(self, slot: str) -> bool:
        """Olvida un retrato. Devuelve True si estaba aprendido."""
        with self._lock:
            return self._pts.pop(slot, None) is not None

    def forget_all(self) -> None:
        with self._lock:
            self._pts = {}

    def as_dict(self) -> dict[str, list[float]]:
        """Copia lista para guardar en disco: slot -> [x, y, n]."""
        with self._lock:
            return {s: list(v) for s, v in self._pts.items()}
