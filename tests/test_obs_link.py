import threading
import time

from obsws_python.error import OBSSDKError
from websocket import WebSocketConnectionClosedException

from overpower_cams import config
from overpower_cams.obs_link import ItemReport, ObsLink
from conftest import FakeClock, FakeObsClient, layout_nuevo, layout_viejo


def make_link(fake, events=None):
    return ObsLink("127.0.0.1", 4455, "pw", client_factory=fake.factory,
                   on_event=(events.append if events is not None else (lambda t: None)))


def test_escena_nueva_con_grupos():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    assert link.connect() is True
    assert link.connected is True and link.error is None
    assert link.load_items() == ItemReport([], [], True)
    # los grupos CAM_* cuelgan de la escena
    assert fake.container_of("CAM_EQ2_5") == config.SCENE_NAME
    # al cargar se apaga todo: 10 cámaras + 2 acompañantes
    assert len(fake.named_calls) == 12
    assert all(enabled is False for _, enabled in fake.named_calls)


def test_escena_vieja_equipo1_sin_marco():
    fake = FakeObsClient(layout_viejo(companions=("Borde",)))
    link = make_link(fake)
    link.connect()
    report = link.load_items()
    assert report == ItemReport([], ["Marco"], True)
    fake.calls.clear()
    link.apply("CAM_EQ1_1", "test")
    assert ("Equipo 1", fake.id_of("CAM_EQ1_1"), True) in fake.calls
    assert fake.is_enabled("CAM_EQ1_1") is True
    assert fake.is_enabled("Borde") is True


def test_acompanantes_solo_con_camara():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    link.connect()
    link.load_items()

    fake.named_calls.clear()
    link.apply("CAM_EQ1_2", "a")
    assert fake.named_calls[0] == ("CAM_EQ1_2", True)
    assert set(fake.named_calls[1:]) == {("Borde", True), ("Marco", True)}

    fake.named_calls.clear()
    link.apply("CAM_EQ2_1", "b")
    # primero la nueva, luego la vieja, sin tocar acompañantes
    assert fake.named_calls == [("CAM_EQ2_1", True), ("CAM_EQ1_2", False)]
    assert fake.is_enabled("Borde") and fake.is_enabled("Marco")

    fake.named_calls.clear()
    link.apply(None, "c")
    assert fake.named_calls[0] == ("CAM_EQ2_1", False)
    assert set(fake.named_calls[1:]) == {("Borde", False), ("Marco", False)}

    fake.named_calls.clear()
    link.apply(None, "d")          # ya estaba oculto: no hace nada
    link.apply("CAM_EQ2_1", "e")
    link.apply("CAM_EQ2_1", "f")   # misma cámara: no repite llamadas
    assert len(fake.named_calls) == 3


def test_reconexion_recarga_ids():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    link.connect()
    link.load_items()
    link.apply("CAM_EQ1_2", "x")
    old_id = fake.id_of("CAM_EQ1_3")

    fake.restart()
    assert fake.id_of("CAM_EQ1_3") != old_id
    link.apply("CAM_EQ1_3", "tras reinicio")      # falla: no lanza
    assert link.connected is False
    assert link.pending_camera == "CAM_EQ1_3"

    fake.calls.clear()
    assert link.ensure_connected("CAM_EQ1_3") is True
    assert link.connected is True
    assert ("Escena Dota", fake.id_of("CAM_EQ1_3"), True) in fake.calls
    assert fake.is_enabled("CAM_EQ1_3") is True
    assert fake.is_enabled("Borde") is True


def test_reconexion_usa_camara_actual_si_no_hay_pedido_pendiente():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    link.connect()
    link.load_items()
    link.apply("CAM_EQ1_3", "x")                  # entregada: no queda pendiente
    fake.restart()
    assert link.get_image_path("Borde") is None   # la llamada falla
    assert link.connected is False and link.pending_camera is None

    assert link.ensure_connected("CAM_EQ1_3") is True
    assert fake.is_enabled("CAM_EQ1_3") is True   # con el ID nuevo
    assert ("Escena Dota", fake.id_of("CAM_EQ1_3"), True) in fake.calls


def test_ensure_connected_conectado_no_hace_nada():
    fake = FakeObsClient()
    link = make_link(fake)
    link.connect()
    link.load_items()
    assert link.ensure_connected("CAM_EQ1_1") is True
    assert fake.connections == 1


def test_ensure_connected_sin_obs_devuelve_false():
    fake = FakeObsClient()
    link = make_link(fake)
    link.connect()
    link.load_items()
    fake.fail_next = True
    link.apply("CAM_EQ1_1", "x")
    assert link.connected is False
    fake.connect_error = ConnectionRefusedError("cerrado")
    assert link.ensure_connected("CAM_EQ1_1") is False
    assert link.error == "refused"


def test_contrasena_incorrecta():
    fake = FakeObsClient()
    fake.connect_error = OBSSDKError("failed to identify client with the server")
    link = make_link(fake)
    assert link.connect() is False
    assert link.connected is False
    assert link.error == "auth"

    fake.connect_error = WebSocketConnectionClosedException("Connection to remote host was lost.")
    assert link.connect() is False and link.error == "auth"


def test_obs_cerrado_es_refused_y_otro_error_lleva_texto():
    fake = FakeObsClient()
    link = make_link(fake)
    fake.connect_error = ConnectionRefusedError(10061, "rechazada")
    assert link.connect() is False and link.error == "refused"
    fake.connect_error = ValueError("algo raro")
    assert link.connect() is False and "algo raro" in link.error
    fake.connect_error = None
    assert link.connect() is True and link.error is None


def test_escena_inexistente():
    fake = FakeObsClient(scene_exists=False)
    link = make_link(fake)
    link.connect()
    report = link.load_items()
    assert report.scene_found is False
    assert report.missing_cameras == config.CAMERAS_TEAM1 + config.CAMERAS_TEAM2
    assert report.missing_companions == config.COMPANIONS_V1
    assert link.connected is True


def test_camaras_faltantes_se_reportan():
    layout = layout_nuevo()
    del layout["CAM_EQ2_4"]
    fake = FakeObsClient(layout)
    link = make_link(fake)
    link.connect()
    assert link.load_items() == ItemReport(["CAM_EQ2_4"], [], True)
    link.apply("CAM_EQ2_4", "x")        # cámara inexistente: se trata como ocultar, sin lanzar
    assert link.connected is True


def test_rutas_de_imagen():
    fake = FakeObsClient(layout_nuevo(), inputs={"Borde": {"file": "C:/a.png", "otra": 1}})
    link = make_link(fake)
    link.connect()
    assert link.get_image_path("Borde") == "C:/a.png"
    assert link.get_image_path("Marco") is None          # no existe la entrada
    assert link.set_image_path("Borde", "C:/b.png") is True
    assert fake.inputs["Borde"] == {"file": "C:/b.png", "otra": 1}   # overlay


def test_crear_acompanante():
    fake = FakeObsClient(layout_nuevo(companions=("Borde",)))
    link = make_link(fake)
    link.connect()
    assert link.load_items().missing_companions == ["Marco"]
    assert link.create_companion("Marco") is True
    assert fake.created == [("Escena Dota", "Marco", "image_source", {}, False)]
    # desde ahora se conmuta como los demás
    link.apply("CAM_EQ1_1", "x")
    assert fake.is_enabled("Marco") is True
    link.apply(None, "y")
    assert fake.is_enabled("Marco") is False


def test_crear_acompanante_con_camara_al_aire_queda_visible():
    fake = FakeObsClient(layout_nuevo(companions=("Borde",)))
    link = make_link(fake)
    link.connect()
    link.load_items()
    link.apply("CAM_EQ1_1", "x")
    link.create_companion("Marco")
    assert fake.is_enabled("Marco") is True


def test_fallo_en_set_image_path_marca_desconectado():
    fake = FakeObsClient(layout_nuevo(), inputs={"Borde": {"file": "x"}})
    link = make_link(fake)
    link.connect()
    fake.fail_next = True
    assert link.set_image_path("Borde", "y") is False
    assert link.connected is False


def test_perdida_en_vivo_no_se_reporta_como_auth():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    link.connect()
    link.load_items()
    link.apply("CAM_EQ1_1", "x")

    def cerrado(*a, **k):
        raise WebSocketConnectionClosedException("Connection to remote host was lost.")

    fake.set_scene_item_enabled = cerrado
    link.apply("CAM_EQ1_2", "y")                  # no lanza
    assert link.connected is False
    assert link.error is not None and link.error != "auth"
    assert link.pending_camera == "CAM_EQ1_2"


def test_apply_no_espera_a_una_reconexion_en_curso():
    fake = FakeObsClient(layout_nuevo())
    gate, entered = threading.Event(), threading.Event()
    gate.set()

    def lenta(**kw):
        entered.set()
        assert gate.wait(5)
        return fake.factory(**kw)

    link = ObsLink("127.0.0.1", 4455, "pw", client_factory=lenta)
    link.connect()
    link.load_items()
    fake.fail_next = True
    link.apply("CAM_EQ1_1", "falla")
    assert link.connected is False

    gate.clear()
    entered.clear()
    result = []
    t = threading.Thread(target=lambda: result.append(link.ensure_connected(None)))
    t.start()
    assert entered.wait(5)                        # la reconexión está colgada en la factory
    t0 = time.monotonic()
    link.apply("CAM_EQ2_3", "durante la reconexión")
    assert time.monotonic() - t0 < 0.5            # volvió de inmediato
    assert link.pending_camera == "CAM_EQ2_3"
    assert link.ensure_connected(None) is False   # una sola reconexión a la vez

    gate.set()
    t.join(5)
    assert result == [True]
    assert fake.is_enabled("CAM_EQ2_3") is True   # gana el último pedido
    assert link.pending_camera is None


def test_ensure_connected_reaplica_ocultar_si_fue_lo_ultimo_pedido():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    link.connect()
    link.load_items()
    fake.fail_next = True
    link.apply("CAM_EQ1_1", "x")                  # falla
    link.apply(None, "oculto")                    # desconectado: queda pendiente "ocultar"
    assert link.ensure_connected("CAM_EQ1_1") is True
    assert fake.is_enabled("CAM_EQ1_1") is False


def test_ping_detecta_obs_cerrado_sin_cambios_de_camara():
    fake = FakeObsClient(layout_nuevo())
    events = []
    link = make_link(fake, events)
    link.connect()
    assert link.ping() is True and link.connected is True
    fake.dead = True                              # OBS se cerró con la app quieta
    assert link.ping() is False
    assert link.connected is False and link.error == "lost"
    assert link.ping() is False                   # sin conexión: no llama al cliente


def test_close_desconecta():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    link.connect()
    link.close()
    assert link.connected is False
    link.apply("CAM_EQ1_1", "x")                  # no lanza: queda pendiente
    assert link.pending_camera == "CAM_EQ1_1"


# ---------- refresh_items: la escena cambia con la conexión viva ----------

def test_escena_importada_despues_de_conectar_se_usa_sin_reconectar():
    fake = FakeObsClient(layout_nuevo(), scene_exists=False)
    clock = FakeClock(10.0)
    link = ObsLink("127.0.0.1", 4455, "pw", client_factory=fake.factory, clock=clock)
    link.connect()
    assert link.load_items().scene_found is False
    fake.scene_exists = True                      # el usuario importa la escena en OBS
    link.apply("CAM_EQ1_1", "GSI")
    assert fake.is_enabled("CAM_EQ1_1") is True and fake.is_enabled("Borde") is True
    assert fake.connections == 1                  # sin reconectar
    assert link.report == ItemReport([], [], True)


def test_refresh_items_no_apaga_nada_y_conserva_la_camara():
    fake = FakeObsClient(layout_nuevo())
    link = make_link(fake)
    link.connect()
    link.load_items()
    link.apply("CAM_EQ1_2", "x")
    fake.named_calls.clear()
    assert link.refresh_items() == ItemReport([], [], True)
    assert fake.named_calls == []
    assert fake.is_enabled("CAM_EQ1_2") is True
    link.apply("CAM_EQ1_3", "y")                  # la cámara anterior se apaga normal
    assert fake.is_enabled("CAM_EQ1_2") is False and fake.is_enabled("CAM_EQ1_3") is True


def test_camara_que_no_esta_apaga_la_anterior_y_los_acompanantes():
    layout = layout_nuevo()
    del layout["CAM_EQ2_4"]
    fake = FakeObsClient(layout)
    events = []
    link = make_link(fake, events)
    link.connect()
    link.load_items()
    link.apply("CAM_EQ1_2", "x")
    assert fake.is_enabled("CAM_EQ1_2") and fake.is_enabled("Borde")
    link.apply("CAM_EQ2_4", "y")
    assert fake.is_enabled("CAM_EQ1_2") is False
    assert fake.is_enabled("Borde") is False and fake.is_enabled("Marco") is False
    assert any("CAM_EQ2_4 no está en la escena de OBS" in e for e in events)
    assert link.connected is True


def test_refresh_al_aplicar_tiene_tope_de_frecuencia():
    layout = layout_nuevo()
    del layout["CAM_EQ2_4"]
    fake = FakeObsClient(layout)
    clock = FakeClock(10.0)
    link = ObsLink("127.0.0.1", 4455, "pw", client_factory=fake.factory, clock=clock)
    link.connect()
    link.load_items()
    reads = []
    original = fake.get_scene_item_list
    fake.get_scene_item_list = lambda name: (reads.append(name), original(name))[1]
    link.apply("CAM_EQ2_4", "a")
    link.apply("CAM_EQ2_4", "b")
    assert len(reads) == 1                        # el segundo pedido no vuelve a leer
    clock.t += 2.5
    link.apply("CAM_EQ2_4", "c")
    assert len(reads) == 2


def test_refresh_con_la_conexion_caida_guarda_la_camara_pendiente():
    layout = layout_nuevo()
    del layout["CAM_EQ2_4"]
    fake = FakeObsClient(layout)
    link = make_link(fake)
    link.connect()
    link.load_items()
    fake.fail_next = True
    link.apply("CAM_EQ2_4", "x")                  # no lanza
    assert link.connected is False and link.pending_camera == "CAM_EQ2_4"
