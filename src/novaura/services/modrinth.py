from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

API_ROOT = "https://api.modrinth.com/v2"
USER_AGENT = "NOVAURA-Launcher/0.1.0 (launcher1)"
Progress = Callable[[str, int], None]


def _request_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        timeout=25,
    )
    response.raise_for_status()
    return response.json()


def search_modrinth(
    query: str,
    project_type: str = "mod",
    game_version: str = "",
    loader: str = "fabric",
    limit: int = 12,
) -> list[dict[str, Any]]:
    facets: list[list[str]] = [[f"project_type:{project_type}"]]
    if game_version.strip():
        facets.append([f"versions:{game_version.strip()}"])
    if project_type == "mod" and loader and loader.lower() != "vanilla":
        facets.append([f"categories:{loader.lower()}"])
    params = {
        "query": query.strip(),
        "facets": json.dumps(facets),
        "limit": max(1, min(50, limit)),
        "index": "relevance",
    }
    data = _request_json(f"{API_ROOT}/search", params=params)
    return data.get("hits", [])


def get_project_versions(
    project_id: str,
    game_version: str = "",
    loader: str = "",
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    if loader and loader.lower() not in {"vanilla", ""}:
        params["loaders"] = json.dumps([loader.lower()])
    return _request_json(f"{API_ROOT}/project/{project_id}/version", params=params)


def download_project(
    project: dict[str, Any],
    instance: dict[str, Any],
    project_type: str,
    report: Progress,
) -> Path:
    project_id = str(project.get("project_id") or project.get("id") or "").strip()
    if not project_id:
        raise ValueError("В ответе каталога нет идентификатора проекта.")
    loader_names = {
        "Fabric": "fabric",
        "Forge": "forge",
        "NeoForge": "neoforge",
        "Quilt": "quilt",
        "Vanilla": "",
    }
    version = str(instance.get("minecraft_version", ""))
    loader = loader_names.get(str(instance.get("loader", "Vanilla")), "")
    candidates = get_project_versions(project_id, version, loader)
    if not candidates:
        raise ValueError(f"Для Minecraft {version} не найдено подходящей версии проекта.")
    selected = candidates[0]
    files = selected.get("files") or []
    if not files:
        raise ValueError("У этой версии проекта нет доступного файла.")
    file_info = next((item for item in files if item.get("primary")), files[0])
    url = str(file_info.get("url", ""))
    filename = Path(str(file_info.get("filename") or urlparse(url).path.split("/")[-1])).name
    if not url.startswith("https://") or not filename or filename in {".", ".."}:
        raise ValueError("Каталог вернул некорректную ссылку на файл.")
    target_folder_name = {
        "mod": "mods",
        "resourcepack": "resourcepacks",
        "shader": "shaderpacks",
        "modpack": "modpacks",
    }.get(project_type, "mods")
    directory = Path(instance["game_dir"]) / target_folder_name
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    temporary = target.with_suffix(target.suffix + ".part")
    report(f"Скачивание {filename}", 0)
    with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=(15, 60)) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        with temporary.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                stream.write(chunk)
                downloaded += len(chunk)
                percent = int(downloaded * 100 / total) if total > 0 else -1
                report(f"Скачивание {filename} ({downloaded // (1024 * 1024)} МБ)", percent)
    temporary.replace(target)
    report(f"Установлено: {filename}", 100)
    return target


def search_curseforge(
    query: str,
    game_version: str = "",
    project_type: str = "mod",
    limit: int = 12,
) -> list[dict[str, Any]]:
    api_key = os.environ.get("CURSEFORGE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "CurseForge API требует отдельный API-ключ. Задайте переменную окружения CURSEFORGE_API_KEY; "
            "ключ не нужно хранить в исходниках или отправлять в публичный репозиторий."
        )
    class_ids = {"mod": 6, "resourcepack": 12, "shader": 6552, "modpack": 4471}
    params: dict[str, Any] = {
        "gameId": 432,
        "classId": class_ids.get(project_type, 6),
        "searchFilter": query.strip(),
        "pageSize": max(1, min(50, limit)),
        "sortField": 1,
        "sortOrder": "desc",
    }
    if game_version:
        params["gameVersion"] = game_version
    response = requests.get(
        "https://api.curseforge.com/v1/mods/search",
        params=params,
        headers={"x-api-key": api_key, "User-Agent": USER_AGENT},
        timeout=25,
    )
    response.raise_for_status()
    return response.json().get("data", [])


def install_curseforge_project(
    project: dict[str, Any],
    instance: dict[str, Any],
    project_type: str,
    report: Progress,
) -> Path:
    api_key = os.environ.get("CURSEFORGE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Задайте переменную окружения CURSEFORGE_API_KEY для использования CurseForge.")
    project_id = int(project.get("id", 0))
    if not project_id:
        raise ValueError("У проекта CurseForge отсутствует ID.")
    response = requests.get(
        f"https://api.curseforge.com/v1/mods/{project_id}/files",
        params={"gameVersion": str(instance.get("minecraft_version", "")), "pageSize": 50},
        headers={"x-api-key": api_key, "User-Agent": USER_AGENT},
        timeout=25,
    )
    response.raise_for_status()
    files = response.json().get("data", [])
    if not files:
        raise ValueError("CurseForge не нашёл файл для выбранной версии Minecraft.")
    file_info = files[0]
    url = str(file_info.get("downloadUrl") or "")
    if not url.startswith("https://"):
        raise RuntimeError("Для этого файла CurseForge не предоставил прямую ссылку на скачивание.")
    filename = Path(str(file_info.get("fileName", ""))).name
    if not filename or filename in {".", ".."}:
        raise ValueError("Некорректное имя файла от CurseForge.")
    folder = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks", "modpack": "modpacks"}.get(project_type, "mods")
    target_dir = Path(instance["game_dir"]) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    temporary = target.with_suffix(target.suffix + ".part")
    report(f"Скачивание {filename}", 0)
    with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=(15, 60)) as response_file:
        response_file.raise_for_status()
        length = int(response_file.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        with temporary.open("wb") as stream:
            for chunk in response_file.iter_content(262144):
                if chunk:
                    stream.write(chunk)
                    downloaded += len(chunk)
                    report(f"Скачивание {filename}", int(downloaded * 100 / length) if length else -1)
    temporary.replace(target)
    return target
