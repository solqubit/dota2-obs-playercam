"""Consola de OverPower · Cámaras Dota: lo mismo que la app, sin ventana (y sin Qt).

Usa el paquete `overpower_cams` y comparte con la app los ajustes, el estado (bando y modo)
y los retratos aprendidos, que viven en %APPDATA%\\OverPowerCamarasDota\\.
Comandos: swap, hide, auto, status, olvidar (o forget), quit.
"""
import sys
import threading
import time
from pathlib import Path


from overpower_cams import config, paths
from overpower_cams.dota_keys import key_name, missing_slots, read_player_keys
from overpower_cams.engine import Engine
from overpower_cams.gsi_server import GsiServer, PortInUse
from overpower_cams.i18n import detect_default, set_language, tr
from overpower_cams.local_input import LocalInput, set_dpi_awareness
from overpower_cams.obs_link import ObsLink
from overpower_cams.portraits import PortraitModel
from overpower_cams.storage import LiveState, Storage

KEYS_POLL_S = 2.0


class ObsSink:
    """Destino de escenas del motor: lo reenvía al ObsLink."""

    def __init__(self, obs):
        self.obs = obs

    def apply(self, scene, reason, abilities=4):
        self.obs.apply(scene, reason, abilities)

    def retrigger(self, scene, abilities):
        self.obs.retrigger(scene, abilities)


def _prefix(template):
    """Lo que va antes del primer {marcador} de un texto ya traducido."""
    return template.split("{", 1)[0]


def engine_event(text):
    """Eventos del motor (sin prefijo) -> líneas con los prefijos de siempre. Los eventos se
    reconocen por el comienzo de su texto, en el idioma actual."""
    if text.startswith("["):
        return text
    learn = (_prefix(tr("retrato {slot} mal aprendido: se vuelve a aprender")),
             _prefix(tr("click en la barra superior (x={x}): esperando a GSI para aprenderlo")))
    if text.startswith(learn):
        return f"[LEARN] {text}"
    if text.startswith(_prefix(tr("la tecla {key} no seleccionó a {slot} en Dota"))):
        return f"[KEYS] {text}"
    return f"[AUTO] {text}"


def show_keys(keys):
    by_slot = {slot: key_name(vk) for vk, slot in keys.items()}
    print("[KEYS] " + tr("Teclas de Dota: {keys}",
                         keys="  ".join(f"{s}={by_slot.get(s, '-')}" for s in config.SLOTS)))
    if missing_slots(keys):
        print("[KEYS] " + tr("Sin tecla en Dota: {slots}  (asígnalas en Dota > Teclas > Espectador)",
                             slots=", ".join(missing_slots(keys))))


def keys_signature(keys_file):
    try:
        return str(keys_file), keys_file.stat().st_mtime_ns
    except (AttributeError, OSError):
        return None


def side_line(radiant_team):
    return tr("Radiant = Equipo {radiant}   |   Dire = Equipo {dire}",
              radiant=radiant_team, dire=3 - radiant_team)


def startup_lines(state):
    """Bando y modo con los que arranca (sobre todo: avisa si arranca oculto, guardado de antes)."""
    lines = ["[SIDE] " + side_line(state.radiant_team)]
    if state.mode == "hidden":
        lines.append("[AUTO] " + tr("Modo: Ocultar todo — escribe 'auto' para reanudar"))
    else:
        lines.append("[AUTO] " + tr("Modo: Automático — siguiendo el héroe seleccionado"))
    return lines


def show_items(obs):
    """Avisa de lo que falta en la colección de OBS (escenas de jugador, fuentes, filtros, Borde)."""
    report = obs.report
    if report is None:
        return
    if not report.main_found:
        print("[OBS] " + tr("La escena '{scene}' no existe en OBS", scene=obs.main_scene) + ".")
        return
    faltas = list(report.missing_scenes)
    for names in report.missing_sources.values():
        faltas += names
    faltas += [config.HUD_FILTERS[n] for n, f in sorted(report.filters.items()) if f is None]
    if not report.borde:
        faltas.append("Borde")
    for name in faltas:
        print("  [WARN] " + tr("{name} no está en la escena", name=name))
    if not faltas:
        print("  [OK] " + tr("Fuentes de OBS cargadas"))


def background(engine, obs, steam):
    """Reintenta OBS cada OBS_RETRY_S y recarga las teclas de Dota si su archivo cambia."""
    def retry_obs():
        shown = obs.report
        while True:
            time.sleep(config.OBS_RETRY_S)
            if obs.connected:
                obs.ping()
            elif obs.ensure_connected(engine.status().camera) and obs.report is not shown:
                shown = obs.report
                show_items(obs)

    def watch_keys(signature):
        roster = None
        while True:
            time.sleep(KEYS_POLL_S)
            keys_file = paths.dota_keys_file(steam)
            if keys_signature(keys_file) != signature:
                signature = keys_signature(keys_file)
                engine.set_player_keys(read_player_keys(keys_file))
                print("[KEYS] " + tr("Teclas de Dota recargadas"))
            st = engine.status()
            if st.roster and (st.roster, st.radiant_team) != roster:
                roster = (st.roster, st.radiant_team)
                print("[MAP] " + tr("Roster ({n}/10)  [Radiant = Equipo {team}]:",
                                    n=len(st.roster), team=st.radiant_team))
                for slot in sorted(st.roster):
                    print(f"  {slot} -> {st.roster[slot]}")

    signature = keys_signature(paths.dota_keys_file(steam))
    for target, args in ((retry_obs, ()), (watch_keys, (signature,))):
        threading.Thread(target=target, args=args, daemon=True).start()


def main() -> int:
    storage = Storage(paths.app_data_dir())
    settings = storage.load_settings()
    set_language(settings.language or detect_default())   # antes de cualquier texto
    print("=== Dota 2 GSI -> OBS ===")
    state = storage.load_state(settings.default_radiant_team, settings.default_mode)
    portraits = PortraitModel(storage.load_portraits(Path(__file__).resolve().parent / "input_map.json"))
    steam = paths.steam_path()
    keys = read_player_keys(paths.dota_keys_file(steam))

    obs = ObsLink(settings.obs_host, settings.obs_port, settings.obs_password,
                  main_scene=settings.main_scene, players_provider=storage.load_players,
                  on_event=lambda text: print(f"[OBS] {text}"))
    engine = Engine(ObsSink(obs), portraits, keys, radiant_team=state.radiant_team, mode=state.mode,
                    on_event=lambda text: print(engine_event(text)),
                    on_learned=lambda: storage.save_portraits(portraits.as_dict()))
    gsi = GsiServer(engine, on_event=print)
    local = LocalInput(engine, on_event=print)

    try:
        gsi.start()
    except PortInUse as e:
        print(f"[GSI] {e}")
        return 1

    if not settings.obs_password:
        settings.obs_password = obs.password = input(tr("Contraseña de OBS: ")).strip()
        storage.save_settings(settings)

    if obs.connect():
        try:
            obs.load_items()
            show_items(obs)
        except Exception as e:  # noqa: BLE001 - el reintento en segundo plano lo recupera
            print("[OBS] " + tr("No pude cargar las fuentes ({error}): se reintenta solo.", error=e))
    else:
        print("[OBS] " + tr("No pude conectar ({error}): se reintenta solo cada {seconds} s.",
                            error=obs.error, seconds=f"{config.OBS_RETRY_S:g}"))
    show_keys(keys)
    print("[LEARN] " + tr("Retratos: {n}/10 afinados con tus clicks", n=len(portraits.as_dict())))
    for line in startup_lines(state):
        print(line)

    def start_input():   # igual que la app: teclado y mouse solo en modo automático
        try:
            set_dpi_awareness()
            local.start()
        except Exception as e:  # noqa: BLE001 - sin teclado/mouse sigue solo con GSI
            print("[INPUT] " + tr("No pude escuchar teclado y mouse ({error}): solo GSI, con ~1 s "
                                  "de retraso.", error=e))

    if state.mode == "auto":
        start_input()
    background(engine, obs, steam)
    print(f"[GSI] http://{config.GSI_HOST}:{gsi.server_port}/\n")
    console(engine, obs, portraits, storage, local, start_input)
    for stop in (gsi.stop, local.stop, obs.close):
        stop()
    return 0


def console(engine, obs, portraits, storage, local, start_input):
    def save(mode=None, radiant=None):
        st = engine.status()
        storage.save_state(LiveState(radiant or st.radiant_team, mode or st.mode))

    forget = tr("olvidar")   # el comando se escribe en el idioma de la consola
    print(tr("Comandos:"))
    print("  swap    -> " + tr("Equipo 1 cambia de bando (úsalo si la moneda invirtió los lados)"))
    print("  hide    -> " + tr("ocultar todo   (bloqueado hasta 'auto')"))
    print("  auto    -> " + tr("seguir héroe seleccionado"))
    print("  status  -> " + tr("modo, bando y cámara actual"))
    print(f"  {forget:<7} -> " + tr("borrar los retratos aprendidos (se vuelven a aprender solos)"))
    print("  quit\n")
    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if cmd == "swap":
            n = 2 if engine.status().radiant_team == 1 else 1
            engine.set_radiant_team(n)
            save(radiant=n)
            print("[SIDE] " + side_line(n))
        elif cmd == "hide":
            engine.set_mode("hidden")
            local.stop()
            save(mode="hidden")
            print("[HIDE] " + tr("Bloqueado. Escribe 'auto' para reanudar."))
        elif cmd == "auto":
            engine.set_mode("auto")
            start_input()
            save(mode="auto")
            print("[AUTO] " + tr("Siguiendo héroe seleccionado."))
        elif cmd == "status":
            st = engine.status()
            print("  " + tr("Modo:    {mode}", mode=st.mode))
            print("  " + tr("Radiant: Equipo {radiant}   (Dire = Equipo {dire})",
                            radiant=st.radiant_team, dire=3 - st.radiant_team))
            print("  " + tr("OBS:     {state}",
                            state=tr("conectado") if obs.connected else tr("sin conexión")))
            print("  " + tr("Cámara:  {camera}", camera=st.camera or tr("ninguna")))
            print("  " + tr("Héroe:   {hero}", hero=st.hero or tr("ninguno")))
            print("  " + tr("Retratos: {n}/10 aprendidos", n=len(portraits.as_dict())))
        elif cmd in ("olvidar", "forget", forget):
            portraits.forget_all()
            storage.save_portraits(portraits.as_dict())
            print("[LEARN] " + tr("Retratos olvidados. Se vuelven a aprender al hacerles click."))
        elif cmd == "quit":
            return
        elif cmd:
            print(f"? swap, hide, auto, status, {forget}, quit")


if __name__ == "__main__":
    sys.exit(main())
