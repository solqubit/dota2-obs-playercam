import pathlib
import threading

import pytest

from conftest import FakeClock, FakeSink, gsi_payload
from overpower_cams.dota_keys import fix_keys_text, parse_player_keys
from overpower_cams.engine import Engine, EngineStatus
from overpower_cams.portraits import PortraitModel

DATA = pathlib.Path(__file__).parent / "data"
POST = "DOTA_GAMERULES_STATE_POST_GAME"


def _keys():
    text = (DATA / "dotakeys_ejemplo.lst").read_bytes().decode("utf-8").replace("\r\n", "\n")
    return parse_player_keys(fix_keys_text(text))


class Fx:
    """Motor listo para probar, con reloj, sink y bitácora falsos."""

    def __init__(self, portraits=None, **kw):
        self.clock = FakeClock(100.0)
        self.sink = FakeSink()
        self.events = []
        self.learned = 0
        self.portraits = portraits or PortraitModel({})
        self.engine = Engine(
            self.sink, self.portraits, _keys(), clock=self.clock,
            on_event=self.events.append, on_learned=self._learned, **kw)

    def _learned(self):
        self.learned += 1

    def post(self, sel, dt=0.0, **kw):
        self.clock.t += dt
        self.engine.process(gsi_payload(sel, **kw))

    def key(self, vk, dt=0.0):
        self.clock.t += dt
        self.engine.handle_input(self.clock.t, "key", vk)

    def click(self, rx, ry, dt=0.0):
        self.clock.t += dt
        self.engine.handle_input(self.clock.t, "click", (rx, ry))

    @property
    def cams(self):
        return [c[0] for c in self.sink.calls]


@pytest.fixture
def fx():
    return Fx()


def test_las_teclas_de_prueba_son_las_esperadas():
    k = _keys()
    assert [k[v] for v in (0x31, 0x35, 0x36, 0x39, 0x30)] == ["r1", "r5", "d1", "d4", "d5"]


def test_gsi_enciende_y_apaga_sin_heroe(fx):
    fx.post("r2")
    assert fx.cams == ["1 Mid laner"]
    assert fx.engine.status().camera == "1 Mid laner"
    fx.post(None, dt=1.0)                       # torre / creep: sin héroe
    assert fx.cams == ["1 Mid laner", None]       # apaga en ESE POST
    assert fx.engine.status().camera is None
    assert fx.events[-1] == "sin héroe → oculto"


def test_gsi_no_repite_llamadas_si_no_cambia(fx):
    fx.post("r2")
    fx.post("r2", dt=1.0)
    fx.post(None, dt=1.0)
    fx.post(None, dt=1.0)
    assert fx.cams == ["1 Mid laner", None]


def test_fuera_de_partida_apaga(fx):
    fx.post("r2")
    fx.post("r2", dt=1.0, state=POST)
    assert fx.cams == ["1 Mid laner", None]
    assert fx.engine.status().camera is None
    assert fx.engine.status().game_state == POST
    fx.post("r2", dt=1.0)                       # vuelve la partida: re-enciende
    assert fx.cams[-1] == "1 Mid laner"


def test_pre_game_cuenta_como_partida(fx):
    fx.post("d1", state="DOTA_GAMERULES_STATE_PRE_GAME")
    assert fx.cams == ["2 Hard carry"]


def test_tecla_instantanea_y_post_viejo_ignorado(fx):
    fx.post("r2")
    fx.key(0x38, dt=0.2)                        # tecla 8 = d3
    assert fx.cams == ["1 Mid laner", "2 Offlaner"]
    assert fx.sink.calls[-1][1] == "tecla d3"
    assert fx.events[-1] == "tecla 8 → 2 Offlaner"
    fx.post("r2", dt=0.4)                       # +0,6 s: foto vieja
    fx.post("r2", dt=1.1)                       # +1,7 s: foto vieja
    fx.post("d3", dt=0.1)                       # GSI ya lo confirma
    assert fx.cams == ["1 Mid laner", "2 Offlaner"]
    assert fx.engine.status().camera == "2 Offlaner"


def test_teclas_rapidas_sin_parpadeo(fx):
    fx.post("r1")
    for vk in (0x32, 0x33, 0x34):
        fx.key(vk, dt=0.1)
    assert fx.cams == ["1 Hard carry", "1 Mid laner", "1 Offlaner", "1 Soft support"]
    n = len(fx.cams)
    for sel in ("r1", "r2", "r3"):
        fx.post(sel, dt=0.5)
    assert len(fx.cams) == n
    assert fx.engine.status().camera == "1 Soft support"


def test_seleccion_nueva_se_aplica_ya(fx):
    fx.post("r1")
    fx.key(0x32, dt=0.1)                        # previsto r2, viejo r1
    fx.post("d1", dt=0.5)                       # otro jugador: GSI manda ya
    assert fx.cams == ["1 Hard carry", "1 Mid laner", "2 Hard carry"]


def test_hold_vence_a_los_3s(fx):
    fx.post("r1")
    fx.key(0x32, dt=0.1)
    fx.post("r1", dt=2.0)                       # aún dentro del hold: se ignora
    assert fx.engine.status().camera == "1 Mid laner"
    fx.post("r1", dt=1.1)                       # >3 s sin confirmar: vuelve al viejo
    assert fx.engine.status().camera == "1 Hard carry"
    assert any("no seleccionó" in e for e in fx.events)


def test_swap(fx):
    fx.post("r1")
    fx.engine.set_radiant_team(2)
    assert fx.engine.status().radiant_team == 2
    fx.key(0x31, dt=0.2)                        # tecla 1 = r1, ahora del equipo 2
    assert fx.cams[-1] == "2 Hard carry"
    fx.post("r1", dt=0.3)                       # GSI lo confirma
    fx.post("d1", dt=1.0)                       # d1 = equipo 1
    assert fx.cams[-1] == "1 Hard carry"


def test_motor_creado_con_equipo_2_en_radiant():
    f = Fx(radiant_team=2)
    f.post("r3")
    assert f.cams == ["2 Offlaner"]


def test_swap_reaplica_la_camara_en_auto(fx):
    fx.post("r1")
    fx.engine.set_radiant_team(2)
    fx.post("r1", dt=1.0)                       # mismo héroe, otro equipo
    assert fx.cams == ["1 Hard carry", "2 Hard carry"]


def test_ocultar_bloquea(fx):
    fx.post("r2")
    fx.engine.set_mode("hidden")
    assert fx.cams == ["1 Mid laner", None]
    assert fx.engine.status().mode == "hidden"
    fx.post("r3", dt=1.0)
    fx.key(0x31, dt=0.1)
    fx.click(-0.2, 0.02, dt=0.1)
    fx.post("d1", dt=1.0)
    assert fx.cams == ["1 Mid laner", None]
    fx.engine.set_mode("auto")
    fx.post("r3", dt=1.0)
    assert fx.cams[-1] == "1 Offlaner"


def test_oculto_igual_actualiza_el_estado_de_la_partida(fx):
    fx.post("r2")
    assert fx.engine.status().game_state == "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"
    fx.engine.set_mode("hidden")
    fx.post("r2", dt=1.0, state=POST)
    assert fx.engine.status().game_state == POST
    assert fx.cams == ["1 Mid laner", None]           # y no toca OBS


def test_click_aprende_retrato(fx):
    fx.post("r1")
    rx, ry = 139 / 1080 + 4 * 62 / 1080, 0.02   # d5 con el modelo por defecto
    fx.click(rx, ry, dt=0.2)
    assert fx.cams[-1] == "2 Hard support"           # al instante
    assert fx.events[-1] == "click retrato d5 → 2 Hard support"
    assert fx.learned == 0
    fx.post("d5", dt=0.6)                       # GSI confirma: aprende
    assert fx.learned == 1
    assert "d5" in fx.portraits.as_dict()
    assert fx.cams[-1] == "2 Hard support"


def test_click_en_el_mapa_no_cambia_nada_y_gsi_manda(fx):
    fx.post("r1")
    fx.click(0.1, 0.5, dt=0.2)
    assert fx.cams == ["1 Hard carry"]
    fx.post("r2", dt=0.5)
    assert fx.cams[-1] == "1 Mid laner"
    assert fx.learned == 0


def test_click_en_el_mapa_vuelve_ambiguo_el_aprendizaje(fx):
    fx.post("r1")
    fx.click(0.3, 0.5, dt=0.2)                  # mapa (ry > TOPBAR_MAX_Y)
    fx.click(0.336, 0.02, dt=0.1)               # y un retrato
    fx.post("d5", dt=0.5)
    assert fx.learned == 0


def test_tecla_de_jugador_explica_el_cambio_y_no_aprende(fx):
    fx.post("r1")
    fx.click(-0.30, 0.02, dt=0.1)
    fx.key(0x32, dt=0.1)
    fx.post("r2", dt=0.5)
    assert fx.learned == 0


def test_retrato_mal_aprendido_se_olvida():
    # r2 aprendido donde en realidad no está: el click no se confirma nunca.
    pm = PortraitModel({"r2": [-0.289, 0.0247, 3]})
    f = Fx(portraits=pm)
    f.post("r1")
    f.click(-0.289, 0.0247, dt=0.2)
    assert f.cams[-1] == "1 Mid laner"
    f.post("r1", dt=3.5)                        # GSI nunca lo confirmó
    assert "r2" not in pm.as_dict()
    assert f.learned == 1
    assert f.cams[-1] == "1 Hard carry"


def test_tecla_antes_de_haber_partida_no_hace_nada(fx):
    fx.key(0x31)                                # aún no hay POST: sin partida
    assert fx.cams == []


def test_tecla_ajena_se_ignora(fx):
    fx.post("r1")
    fx.key(0x41, dt=0.1)                        # "A" no es tecla de jugador
    assert fx.cams == ["1 Hard carry"]


def test_set_player_keys(fx):
    fx.post("r1")
    fx.engine.set_player_keys({0x41: "d2"})
    fx.key(0x31, dt=0.1)
    assert fx.cams == ["1 Hard carry"]
    fx.key(0x41, dt=0.1)
    assert fx.cams[-1] == "2 Mid laner"


def test_status(fx):
    st = fx.engine.status()
    assert isinstance(st, EngineStatus)
    assert (st.mode, st.radiant_team, st.camera, st.hero, st.game_state, st.roster) == \
        ("auto", 1, None, None, None, {})
    fx.post("d2")
    st = fx.engine.status()
    assert st.camera == "2 Mid laner"
    assert st.hero == "test6"
    assert st.game_state == "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"
    assert len(st.roster) == 10
    assert st.roster["r1"] == "1 Hard carry" and st.roster["d5"] == "2 Hard support"
    fx.engine.set_radiant_team(2)
    assert fx.engine.status().roster["r1"] == "2 Hard carry"


def test_status_no_se_bloquea_con_un_sink_lento():
    entro, soltar = threading.Event(), threading.Event()

    class SinkLento(FakeSink):
        def apply(self, cam, reason, abilities=4):
            entro.set()
            soltar.wait(5)
            super().apply(cam, reason, abilities)

    e = Engine(SinkLento(), PortraitModel({}), _keys(), clock=FakeClock(1.0))
    t = threading.Thread(target=e.process, args=(gsi_payload("r1"),))
    t.start()
    assert entro.wait(5)
    st = e.status()                             # el sink sigue "ocupado"
    assert st.mode == "auto"
    soltar.set()
    t.join(5)
    assert e.status().camera == "1 Hard carry"


def test_payload_basura_no_rompe(fx):
    fx.engine.process({})
    fx.engine.process({"player": "x", "hero": 3, "map": None})
    fx.engine.process(None)
    assert fx.cams == []


# ---------- habilidades ----------

def test_sink_recibe_las_habilidades_del_jugador(fx):
    fx.post("r2", abilities={"1 Mid laner": 6})
    assert fx.sink.calls[-1] == ("1 Mid laner", "GSI", 6)


def test_cambio_de_habilidades_al_aire_reactiva(fx):
    fx.post("r2", abilities={"1 Mid laner": 5})
    assert fx.sink.calls[-1][2] == 5 and fx.sink.retriggers == []
    fx.post("r2", dt=1.0, abilities={"1 Mid laner": 6})
    assert fx.sink.retriggers == [("1 Mid laner", 6)]
    assert fx.cams == ["1 Mid laner"]           # no vuelve a encender la escena


def test_mismas_habilidades_no_reactivan(fx):
    fx.post("r2", abilities={"1 Mid laner": 6})
    fx.post("r2", dt=1.0, abilities={"1 Mid laner": 6})
    fx.post("r2", dt=1.0, abilities={"1 Mid laner": 6})
    fx.post("r2", dt=1.0, abilities={"1 Mid laner": 6})
    assert fx.sink.retriggers == []


def test_habilidades_de_otro_jugador_no_reactivan(fx):
    fx.post("r2", abilities={"1 Mid laner": 5, "2 Hard carry": 4})
    fx.post("r2", dt=1.0, abilities={"1 Mid laner": 5, "2 Hard carry": 6})
    assert fx.sink.retriggers == []


def test_sin_datos_de_habilidades_usa_4(fx):
    fx.post("r2")
    assert fx.sink.calls[-1] == ("1 Mid laner", "GSI", 4)
    assert fx.engine.status().abilities["1 Mid laner"] == 4


def test_habilidades_fuera_de_rango_se_ajustan(fx):
    fx.post("r2", abilities={"1 Mid laner": 9, "1 Hard carry": 2})
    assert fx.sink.calls[-1][2] == 6
    assert fx.engine.status().abilities["1 Hard carry"] == 4


def test_tecla_instantanea_usa_las_habilidades_ya_conocidas(fx):
    fx.post("r1", abilities={"1 Mid laner": 6})
    fx.key(0x32, dt=0.2)                        # tecla 2 = r2
    assert fx.sink.calls[-1] == ("1 Mid laner", "tecla r2", 6)


def test_status_expone_habilidades_por_escena(fx):
    fx.post("r1", abilities={"1 Hard carry": 5, "2 Hard support": 6})
    ab = fx.engine.status().abilities
    assert ab["1 Hard carry"] == 5 and ab["2 Hard support"] == 6 and ab["1 Mid laner"] == 4
    assert len(ab) == 10


def test_post_sin_seccion_de_habilidades_conserva_lo_conocido(fx):
    fx.post("r2", abilities={"1 Mid laner": 6})
    fx.post("r2", dt=1.0)
    assert fx.sink.retriggers == []
    assert fx.engine.status().abilities["1 Mid laner"] == 6


def test_habilidades_seccion_basura_no_rompe(fx):
    p = gsi_payload("r1")
    p["abilities"] = {"team2": {"player0": "x", "player1": {"ability0": 3}}, "team3": 7}
    fx.engine.process(p)
    assert fx.sink.calls[-1] == ("1 Hard carry", "GSI", 4)
