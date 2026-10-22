from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

EXPORT_DIRS = {"mods", "config", "resourcepacks", "shaderpacks", "saves"}


def open_managed_folder(instance: dict[str, Any], folder: str) -> Path:
    if folder not in EXPORT_DIRS and folder not in {"logs", "screenshots"}:
        raise ValueError("Неизвестная папка игры.")
    path = Path(instance["game_dir"]) / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def import_pack_file(source: str, instance: dict[str, Any], target_folder: str) -> Path:
    if target_folder not in {"mods", "resourcepacks", "shaderpacks"}:
        raise ValueError("Нельзя импортировать файл в эту папку.")
    source_path = Path(source)
    if not source_path.is_file() or source_path.suffix.lower() not in {".zip", ".jar"}:
        raise ValueError("Выберите ZIP или JAR файл.")
    destination = Path(instance["game_dir"]) / target_folder
    destination.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() == ".zip" and target_folder == "mods":
        raise ValueError("Для модов выберите JAR-файл. ZIP модпаки нужно импортировать как сборку.")
    target = destination / source_path.name
    shutil.copy2(source_path, target)
    return target


def export_instance(instance: dict[str, Any], destination: str) -> Path:
    source = Path(instance["game_dir"])
    source.mkdir(parents=True, exist_ok=True)
    target = Path(destination)
    manifest = {
        "formatVersion": 1,
        "launcher": "NOVAURA",
        "instance": {
            "name": instance.get("name", "NOVAURA instance"),
            "minecraft_version": instance.get("minecraft_version", ""),
            "loader": instance.get("loader", "Vanilla"),
            "loader_version": instance.get("loader_version", ""),
        },
        "includedFolders": sorted(EXPORT_DIRS),
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("novaura-instance.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for folder in EXPORT_DIRS:
            path = source / folder
            if not path.exists():
                continue
            for item in path.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(source).as_posix())
    return target


def import_instance(source_file: str, target_directory: str) -> dict[str, Any]:
    archive_path = Path(source_file)
    target_root = Path(target_directory)
    target_root.mkdir(parents=True, exist_ok=True)
    manifest_data: dict[str, Any] = {}
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 20000:
            raise ValueError("В архиве слишком много файлов.")
        total_size = sum(member.file_size for member in members)
        if total_size > 4 * 1024 * 1024 * 1024:
            raise ValueError("Архив слишком большой для безопасного импорта (лимит 4 ГБ).")
        for member in members:
            if member.is_dir():
                continue
            relative = PurePosixPath(member.filename)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("Архив содержит небезопасный путь.")
            if relative.parts[0] == "novaura-instance.json":
                try:
                    manifest_data = json.loads(archive.read(member).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise ValueError("Не удалось прочитать манифест сборки.")
                continue
            if relative.parts[0] not in EXPORT_DIRS:
                continue
            target = target_root.joinpath(*relative.parts)
            resolved_root = target_root.resolve()
            if resolved_root not in target.resolve().parents:
                raise ValueError("Архив содержит путь за пределы папки сборки.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return manifest_data
