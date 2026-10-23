import threading
import time

from obsws_python.error import OBSSDKError
from websocket import WebSocketConnectionClosedException

from overpower_cams import config
from overpower_cams.config import HUD_FILTERS, source_name
from overpower_cams.obs_link import ObsLink, SceneReport
from overpower_cams.players import PlayerConfig
from conftest import FakeClock, FakeObsClient, fake_camaraman

HC, MID, OFF = "1 Hard carry", "1 Mid laner", "1 Offlaner"


def jugadores(**por_escena):
    """Los 10 jugadores con cámara y foto; `por_escena` pisa algunos (clave con _ en vez de espacio)."""
    out = {s: PlayerConfig(name=s, camera_url="http://cam", photo_url="http://foto", use="camera")
           for s in config.PLAYER_SCENES}
    for k, v in por_escena.items():
        out[k.replace("_", " ")] = v
    return out


def make_link(fake, events=None, players=None, **kw):
    prov = players if players is not None else jugadores()
    return ObsLink("127.0.0.1", 4455, "pw", client_factory=fake.factory,
                   players_provider=lambda: prov,
                   on_event=(events.append if events is not None else (lambda t: None)), **kw)


def listo(fake=None, **kw):
    fake = fake or fake_camaraman()
    link = make_link(fake, **kw)
    assert link.connect()
    link.load_items()
    fake.ops.clear()
    return fake, link


def pos(fake, nombre, escena="Juego"):
    return fake.is_enabled(nombre, escena)


# ---------- lectura de la colección ----------

def test_load_items_completo_lee_presets_de_los_filtros():
    fake = fake_camaraman()
    link = make_link(fake)
    assert link.connect() is True
    assert link.connected is True and link.error is None
    report = link.load_items()
    assert report == SceneReport(
        True, [], {}, {4: {"pos": (431.0, 1778.0), "scale": (0.199, 0.2)},
                       5: {"pos": (456.0, 1819.0), "scale": (0.18, 0.18)},
                       6: {"pos": (466.0, 1860.0), "scale": (0.157, 0.156)}}, True,
        {n: config.MOVE_FILTER_KIND for n in HUD_FILTERS}, True)
    # al cargar se apagan las 10 escenas y el Borde
    assert len(fake.named_calls) == 11
    assert all(enabled is False for _, enabled in fake.named_calls)


def test_load_items_informa_lo_que_falta():
    fake = fake_camaraman(skip_scenes=("2 Offlaner",), skip_sources=(source_name("Foto", MID),),
                          borde=False, omitir_filtros=("H 5 habilidades",))
    link = make_link(fake)
    link.connect()
    r = link.load_items()
    assert r.main_found is True and r.borde is False
    assert r.missing_scenes == ["2 Offlaner"]
    assert r.missing_sources == {MID: [source_name("Foto", MID)]}
    assert r.filters[5] is None and r.filters[4] is not None and r.filters[6] is not None
    assert r.filter_kinds == {4: config.MOVE_FILTER_KIND, 5: None, 6: config.MOVE_FILTER_KIND}


def test_load_items_lee_el_tipo_de_los_filtros_y_si_esta_move_transition():
    fake = fake_camaraman()
    fake.filters["Juego"]["H 6 habilidades"]["kind"] = "color_filter"
    fake.filter_kinds = ["color_filter", "mask_filter_v2"]
    link = make_link(fake)
    link.connect()
    r = link.load_items()
    assert r.move_plugin is False
    assert r.filter_kinds[6] == "color_filter" and r.filter_kinds[4] == config.MOVE_FILTER_KIND


def test_load_items_tolera_obs_sin_lista_de_tipos_de_filtro():
    fake = fake_camaraman()
    fake.filter_kinds = None
    events = []
    link = make_link(fake, events=events)
    link.connect()
    r = link.load_items()
    assert r.move_plugin is None and link.connected is True
    assert r.filters[4] is not None
    assert not any("rechazó" in e for e in events)


def test_escena_principal_inexistente():
    fake = fake_camaraman()
    fake.removed.add("Juego")
    link = make_link(fake)
    link.connect()
    r = link.load_items()
    assert r.main_found is False and r.missing_scenes == config.PLAYER_SCENES
    assert r.filters == {4: None, 5: None, 6: None} and r.borde is False
    assert link.connected is True


def test_main_scene_configurable():
    fake = FakeObsClient(scenes={"Directo": {"1 Hard carry": None, "Borde": None}, HC: {}},
                         scene="Directo")
    link = make_link(fake, main_scene="Directo")
    link.connect()
    assert link.load_items().main_found is True


# ---------- apply ----------

def test_apply_orden_transform_modo_escena_borde_filtros():
    fake, link = listo()
    link.apply(HC, "t", 4)
    assert fake.ops == [
        ("transform", "Juego", HC, {"positionX": 431.0, "positionY": 1778.0,
                                    "scaleX": 0.199, "scaleY": 0.2}),
        ("enable", HC, source_name("Camara", HC), True),
        ("enable", HC, source_name("Foto", HC), False),
        ("enable", "Juego", HC, True),
        ("enable", "Juego", "Borde", True),
        ("filter_settings", "H 4 habilidades", {"source": HC}),
        ("filter_settings", "H 5 habilidades", {"source": HC}),
        ("filter_settings", "H 6 habilidades", {"source": HC}),
    ]


def test_apply_enciende_la_nueva_antes_de_apagar_la_vieja_y_una_sola_encendida():
    fake, link = listo()
    link.apply(HC, "a", 4)
    fake.ops.clear()
    link.apply(MID, "b", 5)
    kinds = [(o[0], o[2], o[-1]) for o in fake.ops if o[0] == "enable"]
    assert kinds.index(("enable", MID, True)) < kinds.index(("enable", HC, False))
    assert fake.ops[0][0] == "transform" and fake.ops[0][3]["positionX"] == 456.0   # preset de 5
    assert pos(fake, MID) is True and pos(fake, HC) is False and pos(fake, "Borde") is True
    encendidas = [s for s in config.PLAYER_SCENES if pos(fake, s)]
    assert encendidas == [MID]


def test_camara_o_foto_dentro_de_la_escena():
    players = jugadores(**{"1_Hard_carry": PlayerConfig(camera_url="c", photo_url="f", use="photo")})
    fake, link = listo(players=players)
    link.apply(HC, "x")
    assert fake.is_enabled(source_name("Foto", HC), HC) is True
    assert fake.is_enabled(source_name("Camara", HC), HC) is False
    # sin URL en lo elegido se dejan ambas fuentes ocultas
    players = jugadores(**{"1_Mid_laner": PlayerConfig(camera_url="", photo_url="f", use="camera")})
    fake, link = listo(players=players)
    link.apply(MID, "x")
    assert fake.is_enabled(source_name("Foto", MID), MID) is False
    assert fake.is_enabled(source_name("Camara", MID), MID) is False


def test_sin_camara_ni_foto_ambas_apagadas_y_avisa():
    events = []
    players = jugadores(**{"1_Hard_carry": PlayerConfig()})
    fake, link = listo(players=players, events=events)
    link.apply(HC, "x")
    assert fake.is_enabled(source_name("Camara", HC), HC) is False
    assert fake.is_enabled(source_name("Foto", HC), HC) is False
    assert pos(fake, HC) is True
    assert any("la fuente elegida no tiene URL" in e for e in events)


def test_habilidades_fuera_de_rango_o_sin_datos():
    fake, link = listo()
    link.apply(HC, "x", 9)                                   # se ajusta a 6
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 466.0
    link.apply(None, "oculto")
    link.apply(HC, "x", 0)                                   # sin datos: 4
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 431.0


def test_los_presets_se_releen_de_los_filtros_en_cada_entrada():
    fake, link = listo()
    fake.filter_settings("H 4 habilidades")["pos"] = {"x": 10.0, "y": 20.0}
    link.apply(HC, "x", 4)
    assert fake.ops[0] == ("transform", "Juego", HC, {"positionX": 10.0, "positionY": 20.0,
                                                      "scaleX": 0.199, "scaleY": 0.2})


def test_sin_filtros_enciende_la_escena_sin_transform_y_no_lanza():
    fake, link = listo(fake_camaraman(omitir_filtros=tuple(HUD_FILTERS.values())))
    link.apply(HC, "x", 4)
    assert not [o for o in fake.ops if o[0] in ("transform", "filter_settings")]
    assert pos(fake, HC) is True and pos(fake, "Borde") is True
    assert link.connected is True


def test_falta_un_filtro_no_impide_el_resto():
    fake, link = listo(fake_camaraman(omitir_filtros=("H 5 habilidades",)))
    link.apply(HC, "x", 5)                                   # no hay preset de 5: sin transform
    assert not [o for o in fake.ops if o[0] == "transform"]
    assert fake.filter_settings("H 4 habilidades")["source"] == HC
    assert fake.filter_settings("H 6 habilidades")["source"] == HC
    assert pos(fake, HC) is True and link.connected is True


def test_falta_la_escena_apaga_la_anterior_y_el_borde_y_avisa_una_vez():
    events = []
    fake, link = listo(fake_camaraman(skip_scenes=("2 Offlaner",)), events=events)
    link.apply(HC, "a")
    link.apply("2 Offlaner", "b")
    assert pos(fake, HC) is False and pos(fake, "Borde") is False
    link.apply(HC, "c")
    link.apply("2 Offlaner", "d")
    avisos = [e for e in events if "2 Offlaner no está en la escena de OBS" in e]
    assert len(avisos) == 1
    assert link.connected is True and pos(fake, HC) is False


def test_ocultar_apaga_escena_y_borde_y_no_repite():
    fake, link = listo()
    link.apply(HC, "a")
    fake.ops.clear()
    link.apply(None, "b")
    assert fake.ops == [("enable", "Juego", HC, False), ("enable", "Juego", "Borde", False)]
    fake.ops.clear()
    link.apply(None, "c")
    link.apply(HC, "d")
    link.apply(HC, "e")                                      # misma escena: sin llamadas nuevas
    assert len([o for o in fake.ops if o[0] == "enable" and o[2] == HC]) == 1


def test_borde_ausente_no_rompe():
    fake, link = listo(fake_camaraman(borde=False))
    link.apply(HC, "x")
    assert pos(fake, HC) is True


# ---------- retrigger y probar ----------

def test_retrigger_activa_solo_el_filtro_pedido():
    fake, link = listo()
    link.apply(HC, "x", 4)
    fake.ops.clear()
    link.retrigger(HC, 5)
    assert fake.ops == [("filter_enabled", "H 5 habilidades", True)]
    fake.ops.clear()
    link.retrigger(HC, 3)                                    # se ajusta a 4
    assert fake.ops == [("filter_enabled", "H 4 habilidades", True)]


def test_retrigger_sin_conexion_o_sin_filtro_no_lanza():
    fake, link = listo(fake_camaraman(omitir_filtros=("H 6 habilidades",)))
    link.apply(HC, "x")
    link.retrigger(HC, 6)
    assert link.connected is True
    link.close()
    link.retrigger(HC, 4)


def test_test_filter_apunta_los_filtros_y_activa():
    fake, link = listo()
    link.apply(MID, "x", 4)
    fake.ops.clear()
    assert link.test_filter(6) is True
    assert [o for o in fake.ops if o[0] == "filter_settings"] == [
        ("filter_settings", n, {"source": MID}) for n in HUD_FILTERS.values()]
    assert fake.ops[-1] == ("filter_enabled", "H 6 habilidades", True)


def test_test_filter_sin_escena_al_aire_usa_la_primera():
    fake, link = listo()
    assert link.test_filter(4) is True
    assert fake.filter_settings("H 4 habilidades")["source"] == HC


# ---------- reconexión ----------

def test_reconexion_con_ids_nuevos_reaplica_escena_modo_y_posicion():
    players = jugadores(**{"1_Mid_laner": PlayerConfig(camera_url="c", photo_url="f", use="photo")})
    fake, link = listo(players=players)
    link.apply(HC, "x", 5)
    old_id = fake.id_of(MID, "Juego")

    fake.restart()
    assert fake.id_of(MID, "Juego") != old_id
    link.apply(MID, "tras reinicio", 6)                      # falla: no lanza
    assert link.connected is False
    assert link.pending_scene == MID

    fake.ops.clear()
    assert link.ensure_connected(MID) is True
    assert link.connected is True
    assert pos(fake, MID) is True and pos(fake, "Borde") is True
    assert fake.is_enabled(source_name("Foto", MID), MID) is True
    assert fake.is_enabled(source_name("Camara", MID), MID) is False
    assert fake.transforms[("Juego", fake.id_of(MID, "Juego"))]["positionX"] == 466.0   # preset de 6


def test_reconexion_usa_escena_actual_y_habilidades_si_no_hay_pedido_pendiente():
    fake, link = listo()
    link.apply(HC, "x", 5)                                   # entregada: no queda pendiente
    fake.restart()
    assert link.get_image_path("Borde") is None              # la llamada falla
    assert link.connected is False and link.pending_scene is None

    assert link.ensure_connected(HC) is True
    assert pos(fake, HC) is True
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 456.0


def test_ensure_connected_conectado_no_hace_nada():
    fake, link = listo()
    assert link.ensure_connected(HC) is True
    assert fake.connections == 1


def test_ensure_connected_sin_obs_devuelve_false():
    fake, link = listo()
    fake.fail_next = True
    link.apply(HC, "x")
    assert link.connected is False
    fake.connect_error = ConnectionRefusedError("cerrado")
    assert link.ensure_connected(HC) is False
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


def test_perdida_en_vivo_no_se_reporta_como_auth():
    fake, link = listo()
    link.apply(HC, "x")

    def cerrado(*a, **k):
        raise WebSocketConnectionClosedException("Connection to remote host was lost.")

    fake.set_scene_item_enabled = cerrado
    link.apply(MID, "y")                                     # no lanza
    assert link.connected is False
    assert link.error is not None and link.error != "auth"
    assert link.pending_scene == MID


def test_apply_no_espera_a_una_reconexion_en_curso():
    fake = fake_camaraman()
    gate, entered = threading.Event(), threading.Event()
    gate.set()

    def lenta(**kw):
        entered.set()
        assert gate.wait(5)
        return fake.factory(**kw)

    link = ObsLink("127.0.0.1", 4455, "pw", client_factory=lenta, players_provider=jugadores)
    link.connect()
    link.load_items()
    fake.fail_next = True
    link.apply(HC, "falla")
    assert link.connected is False

    gate.clear()
    entered.clear()
    result = []
    t = threading.Thread(target=lambda: result.append(link.ensure_connected(None)))
    t.start()
    assert entered.wait(5)                                   # la reconexión está colgada en la factory
    t0 = time.monotonic()
    link.apply("2 Mid laner", "durante la reconexión")
    assert time.monotonic() - t0 < 0.5                       # volvió de inmediato
    assert link.pending_scene == "2 Mid laner"
    assert link.ensure_connected(None) is False              # una sola reconexión a la vez

    gate.set()
    t.join(5)
    assert result == [True]
    assert pos(fake, "2 Mid laner") is True                  # gana el último pedido
    assert link.pending_scene is None


def test_ensure_connected_reaplica_ocultar_si_fue_lo_ultimo_pedido():
    fake, link = listo()
    fake.fail_next = True
    link.apply(HC, "x")                                      # falla
    link.apply(None, "oculto")                               # desconectado: queda pendiente "ocultar"
    assert link.ensure_connected(HC) is True
    assert pos(fake, HC) is False


def test_ping_detecta_obs_cerrado_sin_cambios_de_escena():
    fake = fake_camaraman()
    link = make_link(fake)
    link.connect()
    assert link.ping() is True and link.connected is True
    fake.dead = True                                         # OBS se cerró con la app quieta
    assert link.ping() is False
    assert link.connected is False and link.error == "lost"
    assert link.ping() is False                              # sin conexión: no llama al cliente


def test_close_desconecta():
    fake, link = listo()
    link.close()
    assert link.connected is False
    link.apply(HC, "x")                                      # no lanza: queda pendiente
    assert link.pending_scene == HC


# ---------- la colección cambia con la conexión viva ----------

def test_escena_importada_despues_de_conectar_se_usa_sin_reconectar():
    fake = fake_camaraman()
    fake.removed.add("Juego")
    clock = FakeClock(10.0)
    link = ObsLink("127.0.0.1", 4455, "pw", client_factory=fake.factory, clock=clock,
                   players_provider=jugadores)
    link.connect()
    assert link.load_items().main_found is False
    fake.removed.discard("Juego")                            # el usuario importa la colección
    link.apply(HC, "GSI")
    assert pos(fake, HC) is True and pos(fake, "Borde") is True
    assert fake.connections == 1
    assert link.report.main_found is True


def test_refresh_items_no_apaga_nada_y_conserva_la_escena():
    fake, link = listo()
    link.apply(HC, "x")
    fake.ops.clear()
    assert link.refresh_items().missing_scenes == []
    assert [o for o in fake.ops if o[0] == "enable"] == []
    assert pos(fake, HC) is True
    link.apply(MID, "y")
    assert pos(fake, HC) is False and pos(fake, MID) is True


def test_refresh_al_aplicar_tiene_tope_de_frecuencia():
    fake = fake_camaraman(skip_scenes=("2 Offlaner",))
    clock = FakeClock(10.0)
    link = ObsLink("127.0.0.1", 4455, "pw", client_factory=fake.factory, clock=clock,
                   players_provider=jugadores)
    link.connect()
    link.load_items()
    reads = []
    original = fake.get_scene_item_list
    fake.get_scene_item_list = lambda name: (reads.append(name), original(name))[1]
    link.apply("2 Offlaner", "a")
    link.apply("2 Offlaner", "b")
    assert reads.count("Juego") == 1                         # el segundo pedido no vuelve a leer
    clock.t += 2.5
    link.apply("2 Offlaner", "c")
    assert reads.count("Juego") == 2


def test_refresh_con_la_conexion_caida_guarda_la_escena_pendiente():
    fake, link = listo(fake_camaraman(skip_scenes=("2 Offlaner",)))
    fake.fail_next = True
    link.apply("2 Offlaner", "x")                            # no lanza
    assert link.connected is False and link.pending_scene == "2 Offlaner"


# ---------- imágenes del Borde ----------

def test_rutas_de_imagen():
    fake = fake_camaraman(inputs={"Borde": {"file": "C:/a.png", "otra": 1}})
    link = make_link(fake)
    link.connect()
    assert link.get_image_path("Borde") == "C:/a.png"
    assert link.get_image_path("Inexistente") is None            # no existe la entrada
    assert link.set_image_path("Borde", "C:/b.png") is True
    assert fake.inputs["Borde"] == {"file": "C:/b.png", "otra": 1}   # overlay


def test_fallo_en_set_image_path_marca_desconectado():
    fake = fake_camaraman(inputs={"Borde": {"file": "x"}})
    link = make_link(fake)
    link.connect()
    fake.fail_next = True
    assert link.set_image_path("Borde", "y") is False
    assert link.connected is False


def test_crear_borde_en_la_escena_principal():
    fake = fake_camaraman(borde=False)
    link = make_link(fake)
    link.connect()
    assert link.load_items().borde is False
    assert link.create_companion("Borde") is True
    assert fake.created == [("Juego", "Borde", "image_source", {}, False)]
    link.apply(HC, "x")
    assert pos(fake, "Borde") is True
    link.apply(None, "y")
    assert pos(fake, "Borde") is False


# ---------- correcciones de la ronda 1 ----------

def test_retrigger_actualiza_las_habilidades_para_la_reconexion():
    fake, link = listo()
    link.apply(HC, "x", 4)
    link.retrigger(HC, 5)
    fake.restart()
    assert link.get_image_path("Borde") is None              # la llamada falla
    assert link.connected is False
    assert link.ensure_connected(HC) is True
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 456.0


def test_retrigger_actualiza_el_pedido_pendiente_de_la_misma_escena():
    fake, link = listo()
    fake.fail_next = True
    link.apply(HC, "x", 4)                                   # falla: queda pendiente con 4
    link.retrigger(HC, 6)
    assert link.ensure_connected(None) is True
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 466.0


def test_retrigger_de_otra_escena_no_hace_nada():
    fake, link = listo()
    link.apply(HC, "x", 4)
    fake.ops.clear()
    link.retrigger(MID, 5)
    assert fake.ops == []


def test_retrigger_no_espera_a_una_reconexion_en_curso():
    fake = fake_camaraman()
    gate, entered = threading.Event(), threading.Event()
    gate.set()

    def lenta(**kw):
        entered.set()
        assert gate.wait(5)
        return fake.factory(**kw)

    link = ObsLink("127.0.0.1", 4455, "pw", client_factory=lenta, players_provider=jugadores)
    link.connect()
    link.load_items()
    link.apply(HC, "x", 4)
    fake.fail_next = True
    link.apply(MID, "falla")
    assert link.connected is False

    gate.clear()
    entered.clear()
    t = threading.Thread(target=lambda: link.ensure_connected(None))
    t.start()
    assert entered.wait(5)
    t0 = time.monotonic()
    link.retrigger(HC, 5)
    assert time.monotonic() - t0 < 0.5                       # volvió de inmediato
    gate.set()
    t.join(5)


def test_ids_que_cambian_con_la_conexion_viva_se_recuperan():
    fake, link = listo()
    fake.restart()                                           # otra colección: IDs nuevos
    fake.dead = False
    link.apply(HC, "x", 4)
    assert pos(fake, HC) is True and pos(fake, "Borde") is True
    assert fake.is_enabled(source_name("Camara", HC), HC) is True
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 431.0
    assert link.connected is True


def test_rechazo_de_presets_no_marca_desconexion_ni_impide_encender():
    from obsws_python.error import OBSSDKRequestError
    fake, link = listo()

    def rechaza(name):
        raise OBSSDKRequestError("GetSourceFilterList", 702, "cancelado")

    fake.get_source_filter_list = rechaza
    link.apply(HC, "x", 4)
    assert link.connected is True
    assert not [o for o in fake.ops if o[0] == "transform"]
    assert pos(fake, HC) is True


def test_aviso_sin_camara_ni_foto_una_vez_por_escena():
    events = []
    players = jugadores(**{"1_Hard_carry": PlayerConfig()})
    fake, link = listo(players=players, events=events)
    link.apply(HC, "a")
    link.apply(None, "b")
    link.apply(HC, "c")
    assert len([e for e in events if "la fuente elegida no tiene URL" in e]) == 1


# ---------- nombre, URLs y Cámara/Foto en vivo ----------

def test_set_player_name_escribe_el_texto_de_la_fuente_nombre():
    fake = fake_camaraman(inputs={source_name("Nombre", HC): {"text": "viejo", "font": "x"}})
    fake, link = listo(fake)
    assert link.set_player_name(HC, "Yatoro") is True
    assert fake.inputs[source_name("Nombre", HC)] == {"text": "Yatoro", "font": "x"}


def test_set_player_url_camara_y_foto():
    fake = fake_camaraman(inputs={source_name("Camara", HC): {"url": "a"}, source_name("Foto", HC): {"url": "b"}})
    fake, link = listo(fake)
    assert link.set_player_url(HC, "camera", "http://nueva-cam") is True
    assert link.set_player_url(HC, "photo", "http://nueva-foto") is True
    assert fake.inputs[source_name("Camara", HC)]["url"] == "http://nueva-cam"
    assert fake.inputs[source_name("Foto", HC)]["url"] == "http://nueva-foto"


def test_set_player_sin_fuente_o_sin_conexion_devuelve_false_sin_lanzar():
    fake, link = listo(fake_camaraman(inputs={}))          # ninguna entrada existe
    assert link.set_player_name(HC, "x") is False
    assert link.set_player_url(HC, "camera", "u") is False
    assert link.set_player_url(HC, "otro", "u") is False
    assert link.connected is True
    link.close()
    assert link.set_player_name(HC, "x") is False
    assert link.set_player_url(HC, "photo", "u") is False
    assert link.refresh_player_mode(HC) is False


def test_set_player_con_obs_caido_marca_desconectado():
    fake = fake_camaraman(inputs={source_name("Nombre", HC): {}})
    fake, link = listo(fake)
    fake.fail_next = True
    assert link.set_player_name(HC, "x") is False
    assert link.connected is False


def test_foto_sin_url_no_muestra_la_camara_y_aplica_el_preset():
    events = []
    players = jugadores(**{"1_Hard_carry": PlayerConfig(camera_url="http://cam", photo_url="", use="photo")})
    fake, link = listo(players=players, events=events)
    link.apply(HC, "x", 5)
    assert fake.is_enabled(source_name("Camara", HC), HC) is False
    assert fake.is_enabled(source_name("Foto", HC), HC) is False
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 456.0
    assert pos(fake, HC) is True


def test_camara_sin_url_no_muestra_la_foto():
    events = []
    players = jugadores(**{"1_Hard_carry": PlayerConfig(camera_url="", photo_url="http://f", use="camera")})
    fake, link = listo(players=players, events=events)
    link.apply(HC, "x")
    assert fake.is_enabled(source_name("Foto", HC), HC) is False
    assert fake.is_enabled(source_name("Camara", HC), HC) is False


def test_cambiar_a_foto_vacia_al_aire_oculta_medios_obsoletos_y_reaplica_transform():
    players = jugadores(**{"1_Hard_carry": PlayerConfig(camera_url="http://cam")})
    fake, link = listo(players=players)
    link.apply(HC, "x", 6)
    assert fake.is_enabled(source_name("Camara", HC), HC) is True
    players[HC].use = "photo"
    fake.filter_settings("H 6 habilidades")["pos"] = {"x": 999.0, "y": 111.0}
    assert link.refresh_player_mode(HC) is True
    assert fake.is_enabled(source_name("Camara", HC), HC) is False
    assert fake.is_enabled(source_name("Foto", HC), HC) is False
    assert fake.transforms[("Juego", fake.id_of(HC, "Juego"))]["positionX"] == 999.0
    players[HC].photo_url = "http://foto"
    assert link.refresh_player_mode(HC) is True
    assert fake.is_enabled(source_name("Foto", HC), HC) is True


def test_refresh_player_mode_cambia_al_momento_con_el_jugador_al_aire():
    players = jugadores()
    fake, link = listo(players=players)
    link.apply(HC, "x")
    assert fake.is_enabled(source_name("Camara", HC), HC) is True
    players[HC].use = "photo"
    assert link.refresh_player_mode(HC) is True
    assert fake.is_enabled(source_name("Foto", HC), HC) is True
    assert fake.is_enabled(source_name("Camara", HC), HC) is False


def test_refresh_player_mode_ignora_escena_que_no_esta_al_aire():
    fake, link = listo()
    link.apply(HC, "x")
    fake.ops.clear()
    assert link.refresh_player_mode(MID) is False
    assert fake.ops == []
