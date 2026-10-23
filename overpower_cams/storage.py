"""Guardado de ajustes, estado vivo y retratos aprendidos (JSON en la carpeta de datos),
y copias de seguridad con fecha de los archivos que la app edita."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_MAIN_SCENE, DEFAULT_OBS_PORT, OBS_HOST, PLAYER_SCENES
from .i18n import LANGUAGES
from .players import USES, PlayerConfig, TeamsConfig

MODES = ("auto", "hidden")


@dataclass
class Settings:
    obs_port: int = DEFAULT_OBS_PORT
    obs_password: str = ""
    dota_dir: str | None = None
    default_radiant_team: int = 1
    language: str | None = None   # "es" | "en"; None = el idioma de Windows
    main_scene: str = DEFAULT_MAIN_SCENE
    obs_host: str = OBS_HOST
    default_mode: str = "auto"    # modo inicial si no hay estado guardado


@dataclass
class LiveState:
    radiant_team: int
    mode: str   # "auto" | "hidden"


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


class Storage:
    def __init__(self, base: Path):
        self.base = Path(base)

    # ---- utilidades ----
    def _read_json(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_json(self, path: Path, data) -> None:
        """Escritura atómica: archivo temporal en la misma carpeta + os.replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ---- ajustes ----
    def load_settings(self) -> Settings:
        s = Settings()
        raw = self._read_json(self.base / "settings.json")
        if not isinstance(raw, dict):
            return s
        if _is_int(raw.get("obs_port")) and 1 <= raw["obs_port"] <= 65535:
            s.obs_port = raw["obs_port"]
        if isinstance(raw.get("obs_password"), str):
            s.obs_password = raw["obs_password"]
        if isinstance(raw.get("dota_dir"), str):
            s.dota_dir = raw["dota_dir"]
        if raw.get("default_radiant_team") in (1, 2) and _is_int(raw["default_radiant_team"]):
            s.default_radiant_team = raw["default_radiant_team"]
        if isinstance(raw.get("language"), str) and raw["language"] in LANGUAGES:
            s.language = raw["language"]
        if isinstance(raw.get("main_scene"), str) and raw["main_scene"].strip():
            s.main_scene = raw["main_scene"]
        if isinstance(raw.get("obs_host"), str) and raw["obs_host"].strip():
            s.obs_host = raw["obs_host"].strip()
        if raw.get("default_mode") in MODES:
            s.default_mode = raw["default_mode"]
        return s

    def save_settings(self, s: Settings) -> None:
        self._write_json(self.base / "settings.json", asdict(s))

    # ---- estado vivo ----
    def load_state(self, default_radiant_team: int, default_mode: str = "auto") -> LiveState:
        st = LiveState(default_radiant_team, default_mode if default_mode in MODES else "auto")
        raw = self._read_json(self.base / "state.json")
        if not isinstance(raw, dict):
            return st
        if _is_int(raw.get("radiant_team")) and raw["radiant_team"] in (1, 2):
            st.radiant_team = raw["radiant_team"]
        if raw.get("mode") in MODES:
            st.mode = raw["mode"]
        return st

    def save_state(self, st: LiveState) -> None:
        self._write_json(self.base / "state.json", asdict(st))

    # ---- retratos ----
    @staticmethod
    def _portraits_from(raw) -> dict[str, list[float]] | None:
        if isinstance(raw, dict) and isinstance(raw.get("portraits"), dict):
            return raw["portraits"]
        return None

    def load_portraits(self, legacy: Path | None) -> dict[str, list[float]]:
        found = self._portraits_from(self._read_json(self.base / "portraits.json"))
        if found is not None:
            return found
        if legacy is not None:
            found = self._portraits_from(self._read_json(Path(legacy)))
            if found is not None:
                self.save_portraits(found)
                return found
        return {}

    def save_portraits(self, d: dict[str, list[float]]) -> None:
        self._write_json(self.base / "portraits.json", {"portraits": d})

    # ---- jugadores y equipos ----
    def load_players(self) -> dict[str, PlayerConfig]:
        out = {scene: PlayerConfig() for scene in PLAYER_SCENES}
        raw = self._read_json(self.base / "players.json")
        players = raw.get("players") if isinstance(raw, dict) else None
        if not isinstance(players, dict):
            return out
        for scene in PLAYER_SCENES:
            item = players.get(scene)
            if not isinstance(item, dict):
                continue
            p = out[scene]
            for f in ("name", "camera_url", "photo_url"):
                if isinstance(item.get(f), str):
                    setattr(p, f, item[f])
            if item.get("use") in USES:
                p.use = item["use"]
        return out

    def save_players(self, d: dict[str, PlayerConfig]) -> None:
        raw = self._read_json(self.base / "players.json")
        teams = raw.get("teams") if isinstance(raw, dict) and isinstance(raw.get("teams"), dict) else {}
        self._write_json(self.base / "players.json", {
            "teams": teams,
            "players": {scene: asdict(p) for scene, p in d.items() if scene in PLAYER_SCENES},
        })

    def load_teams(self) -> TeamsConfig:
        t = TeamsConfig()
        raw = self._read_json(self.base / "players.json")
        teams = raw.get("teams") if isinstance(raw, dict) else None
        if isinstance(teams, dict):
            if isinstance(teams.get("team1"), str):
                t.team1 = teams["team1"]
            if isinstance(teams.get("team2"), str):
                t.team2 = teams["team2"]
        return t

    def save_teams(self, t: TeamsConfig) -> None:
        raw = self._read_json(self.base / "players.json")
        players = raw.get("players") if isinstance(raw, dict) and isinstance(raw.get("players"), dict) else {}
        self._write_json(self.base / "players.json", {"teams": asdict(t), "players": players})

    # ---- copias de seguridad ----
    def backup(self, src: Path) -> Path:
        src = Path(src)
        folder = self.base / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        dst = folder / f"{src.stem}_{stamp}{src.suffix}"
        n = 1
        while dst.exists():   # dos copias en el mismo segundo: no pisar la anterior
            n += 1
            dst = folder / f"{src.stem}_{stamp}-{n}{src.suffix}"
        shutil.copy2(src, dst)
        return dst
