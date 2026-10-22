from __future__ import annotations

import hashlib
import logging
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import minecraft_launcher_lib
import requests

from novaura.config import app_data_dir

log = logging.getLogger(__name__)
Progress = Callable[[str, int], None]


def available_versions() -> list[dict[str, Any]]:
    return minecraft_launcher_lib.utils.get_version_list()


def loader_ids() -> list[str]:
    try:
        return minecraft_launcher_lib.mod_loader.list_mod_loader()
    except AttributeError:
        return []


def _callbacks(report: Progress) -> dict[str, Callable]:
    maximum = [100]

    def set_status(value: str) -> None:
        report(str(value), -1)

    def set_max(value: int) -> None:
        maximum[0] = max(1, int(value))

    def set_progress(value: int) -> None:
        percent = int(max(0, min(100, int(value) * 100 / maximum[0])))
        report("Загрузка файлов Minecraft", percent)

    return {"setStatus": set_status, "setMax": set_max, "setProgress": set_progress}



def ensure_authlib_injector(report: Progress) -> Path:
    """Download authlib-injector and verify its published SHA-256 when available."""
    destination = app_data_dir() / "libraries" / "authlib-injector.jar"
    if destination.is_file() and destination.stat().st_size > 50_000:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    report("Загрузка authlib-injector для Ely.by…", 0)
    metadata_url = "https://authlib-injector.yushi.moe/artifact/latest.json"
    response = requests.get(metadata_url, timeout=20, headers={"User-Agent": "NOVAURA-Launcher/0.1.0"})
    response.raise_for_status()
    metadata = response.json()
    download_url = str(metadata.get("download_url") or "")
    if not download_url.startswith("https://") or urlparse(download_url).hostname != "authlib-injector.yushi.moe":
        raise RuntimeError("Authlib-injector вернул недопустимый адрес загрузки.")
    expected_hash = str((metadata.get("checksums") or {}).get("sha256") or "").lower()
    temporary = destination.with_suffix(".jar.part")
    try:
        with requests.get(download_url, stream=True, timeout=(15, 60),
                          headers={"User-Agent": "NOVAURA-Launcher/0.1.0"}) as file_response:
            file_response.raise_for_status()
            total = int(file_response.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            digest = hashlib.sha256()
            with temporary.open("wb") as stream:
                for chunk in file_response.iter_content(256 * 1024):
                    event = getattr(report, "cancel_event", None)
                    if event is not None and event.is_set():
                        raise InterruptedError("Операция отменена.")
                    if chunk:
                        stream.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        report("Скачивание authlib-injector", int(downloaded * 100 / total) if total else -1)
        if expected_hash and digest.hexdigest().lower() != expected_hash:
            raise RuntimeError("Контрольная сумма authlib-injector не совпала.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def launch_instance(
    instance: dict[str, Any],
    account: dict[str, Any],
    config: dict[str, Any],
    report: Progress,
) -> dict[str, str]:
    version = str(instance.get("minecraft_version", "")).strip()
    if not version:
        raise ValueError("У сборки не указана версия Minecraft.")
    directory = Path(instance.get("game_dir") or config.get("game_root") or Path.home() / ".minecraft")
    directory.mkdir(parents=True, exist_ok=True)
    callback = _callbacks(report)
    java_path = str(config.get("java_path", "")).strip()
    if java_path:
        resolved = Path(java_path)
        if not resolved.is_file():
            raise FileNotFoundError(f"Указанный Java-файл не найден: {java_path}")
        java = str(resolved)
    else:
        java = None

    loader_name = str(instance.get("loader", "Vanilla"))
    installed_version = version
    loader_map = {
        "Fabric": "fabric",
        "Forge": "forge",
        "NeoForge": "neoforge",
        "Quilt": "quilt",
    }
    if loader_name in loader_map:
        report(f"Проверка совместимости {loader_name}…", -1)
        try:
            loader = minecraft_launcher_lib.mod_loader.get_mod_loader(loader_map[loader_name])
        except (ValueError, AttributeError) as exc:
            raise RuntimeError(f"Загрузчик {loader_name} недоступен в установленной версии minecraft-launcher-lib.") from exc
        if not loader.is_minecraft_version_supported(version):
            raise ValueError(f"{loader_name} пока не поддерживает Minecraft {version}. Выберите совместимую версию.")
        loader_version = str(instance.get("loader_version") or loader.get_latest_loader_version(version))
        report(f"Установка {loader_name} {loader_version}…", 0)
        installed_version = loader.install(
            version, str(directory), loader_version=loader_version, callback=callback, java=java
        )
        instance["loader_version"] = loader_version
        instance["installed_version"] = installed_version
    else:
        report(f"Подготовка Minecraft {version}…", 0)
        minecraft_launcher_lib.install.install_minecraft_version(version, str(directory), callback=callback)

    name = str(account.get("name", "Player")).strip() or "Player"
    uuid = str(account.get("uuid", "")).strip()
    if not uuid:
        raise ValueError("У выбранного аккаунта отсутствует UUID.")
    credentials = account.get("credentials") or {}
    token = str(credentials.get("access_token") or "0")
    ram = max(2, min(32, int(config.get("ram_gb", 4))))
    jvm_args = [f"-Xms{min(2, ram)}G", f"-Xmx{ram}G"]
    if account.get("type") == "ely":
        injector = ensure_authlib_injector(report)
        jvm_args.insert(0, f'-javaagent:"{injector}"=ely.by')
    custom_args = str(config.get("jvm_arguments", "")).strip()
    if custom_args:
        extra = shlex.split(custom_args, posix=False)
        bad = [item for item in extra if not item.startswith("-")]
        if bad:
            raise ValueError("Каждый пользовательский аргумент JVM должен начинаться с дефиса (-).")
        jvm_args.extend(extra)
    options: dict[str, Any] = {
        "username": name,
        "uuid": uuid.replace("-", ""),
        "token": token,
        "launcherName": "NOVAURA",
        "jvmArguments": jvm_args,
    }
    if java:
        options["executablePath"] = java
    else:
        discovered = minecraft_launcher_lib.utils.get_java_executable()
        if discovered and discovered != "java":
            options["defaultExecutablePath"] = discovered

    command = minecraft_launcher_lib.command.get_minecraft_command(installed_version, str(directory), options)
    log_dir = Path(directory) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "novaura-launch.log"
    report(f"Запуск {name}…", 100)
    try:
        with log_path.open("a", encoding="utf-8", errors="replace") as out:
            process = subprocess.Popen(
                command,
                cwd=str(directory),
                stdout=out,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Не удалось найти Java. Установите подходящую Java или укажите javaw.exe/java.exe в настройках."
        ) from exc
    return {
        "version": installed_version,
        "pid": str(process.pid),
        "log_path": str(log_path),
    }


def installed_versions(directory: str) -> list[dict[str, Any]]:
    return minecraft_launcher_lib.utils.get_installed_versions(directory)
