from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


def app_data_dir() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    return root / "NOVAURA"


def game_root() -> Path:
    return Path(os.environ.get("NOVAURA_GAME_ROOT", app_data_dir() / "game" / "instances"))


def ensure_app_dirs() -> None:
    app_data_dir().mkdir(parents=True, exist_ok=True)
    game_root().mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value.strip(), flags=re.UNICODE).strip(".-_")
    return (value or "instance")[:48]


def default_config() -> dict[str, Any]:
    root = game_root()
    return {
        "language": "ru",
        "theme": "violet",
        "accent": "#e84dff",
        "window_opacity": 1.0,
        "ui_scale": 1.0,
        "corner_radius": 18,
        "animations": True,
        "theme_presets": {},
        "background_image": "",
        "game_root": str(root),
        "java_path": "",
        "ram_gb": 4,
        "jvm_arguments": "",
        "microsoft_client_id": "",
        "microsoft_redirect_uri": "http://localhost:8765/callback",
        "active_instance": "main",
        "instances": [
            {
                "id": "main",
                "name": "Основная сборка",
                "minecraft_version": "1.21.11",
                "loader": "Vanilla",
                "loader_version": "",
                "installed_version": "",
                "game_dir": str(root / "main"),
            }
        ],
    }


def config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config() -> dict[str, Any]:
    ensure_app_dirs()
    defaults = default_config()
    try:
        saved = json.loads(config_path().read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            defaults.update(saved)
    except (OSError, json.JSONDecodeError):
        pass
    if not isinstance(defaults.get("instances"), list) or not defaults["instances"]:
        defaults["instances"] = default_config()["instances"]
    return defaults


def save_config(config: dict[str, Any]) -> None:
    ensure_app_dirs()
    path = config_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def make_instance(name: str, version: str, loader: str, config: dict[str, Any]) -> dict[str, str]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Укажите название сборки.")
    if not version.strip():
        raise ValueError("Выберите версию Minecraft.")
    instance_id = slugify(clean_name).lower()
    existing = {item.get("id") for item in config.get("instances", [])}
    base_id = instance_id
    suffix = 2
    while instance_id in existing:
        instance_id = f"{base_id}-{suffix}"
        suffix += 1
    root = Path(config.get("game_root") or game_root())
    return {
        "id": instance_id,
        "name": clean_name,
        "minecraft_version": version.strip(),
        "loader": loader,
        "loader_version": "",
        "installed_version": "",
        "game_dir": str(root / instance_id),
    }
