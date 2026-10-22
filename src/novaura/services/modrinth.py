from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
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
                _check_cancel(report)
                if not chunk:
                    continue
                stream.write(chunk)
                downloaded += len(chunk)
                percent = int(downloaded * 100 / total) if total > 0 else -1
                report(f"Скачивание {filename} ({downloaded // (1024 * 1024)} МБ)", percent)
    temporary.replace(target)
    report(f"Установлено: {filename}", 100)
    return target



def _check_cancel(report: Progress) -> None:
    event = getattr(report, "cancel_event", None)
    if event is not None and event.is_set():
        raise InterruptedError("Операция отменена.")


def install_modrinth_modpack(
    project: dict[str, Any],
    instance: dict[str, Any],
    report: Progress,
) -> Path:
    """Install a Modrinth .mrpack with path validation and manifest hash checks."""
    project_id = str(project.get("project_id") or project.get("id") or "").strip()
    if not project_id:
        raise ValueError("В ответе каталога нет идентификатора проекта.")
    versions = get_project_versions(project_id)
    if not versions:
        raise ValueError("У модпака не найдено доступных версий.")
    preferred_mc = str(instance.get("minecraft_version", ""))
    selected = next((v for v in versions if preferred_mc in (v.get("game_versions") or [])), versions[0])
    files = selected.get("files") or []
    package_file = next(
        (f for f in files if str(f.get("filename", "")).lower().endswith(".mrpack")),
        next((f for f in files if f.get("primary")), files[0] if files else None),
    )
    if not package_file:
        raise ValueError("У модпака отсутствует файл для скачивания.")
    package_url = str(package_file.get("url", ""))
    if not package_url.startswith("https://"):
        raise ValueError("Каталог вернул недопустимую ссылку на модпак.")
    root = Path(instance["game_dir"])
    root.mkdir(parents=True, exist_ok=True)
    archive_path = root / ".novaura-import.mrpack"
    temporary = archive_path.with_suffix(".mrpack.part")
    report("Скачивание архива модпака…", 0)
    try:
        with requests.get(package_url, stream=True, timeout=(15, 60), headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            length = int(response.headers.get("Content-Length", "0") or 0)
            downloaded = 0
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(256 * 1024):
                    _check_cancel(report)
                    if chunk:
                        stream.write(chunk)
                        downloaded += len(chunk)
                        report("Скачивание архива модпака", int(downloaded * 100 / length) if length else -1)
        temporary.replace(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if "modrinth.index.json" not in names:
                raise ValueError("Это невалидный Modrinth-модпак: отсутствует modrinth.index.json.")
            if len(names) > 20000:
                raise ValueError("В модпаке слишком много файлов.")
            if sum(x.file_size for x in archive.infolist()) > 4 * 1024 * 1024 * 1024:
                raise ValueError("Архив модпака слишком большой (лимит 4 ГБ).")
            index = json.loads(archive.read("modrinth.index.json").decode("utf-8"))
            dependencies = index.get("dependencies") or {}
            mc = str(dependencies.get("minecraft") or preferred_mc)
            loader_spec = [
                ("fabric-loader", "Fabric"),
                ("forge", "Forge"),
                ("neoforge", "NeoForge"),
                ("quilt-loader", "Quilt"),
            ]
            chosen_loader = next(
                ((key, label, str(dependencies[key])) for key, label in loader_spec if dependencies.get(key)),
                None,
            )
            content_files = index.get("files") or []
            for index_no, item in enumerate(content_files):
                _check_cancel(report)
                env = item.get("env") or {}
                if env.get("client") == "unsupported":
                    continue
                relative = PurePosixPath(str(item.get("path", "")))
                if relative.is_absolute() or not relative.parts or ".." in relative.parts or ":" in relative.parts[0]:
                    raise ValueError("Модпак содержит небезопасный путь.")
                urls = item.get("downloads") or []
                if not urls:
                    continue
                file_url = str(urls[0])
                if not file_url.startswith("https://"):
                    raise ValueError("Модпак содержит недопустимый URL загрузки.")
                target = root.joinpath(*relative.parts)
                if root.resolve() not in target.resolve().parents:
                    raise ValueError("Путь файла выходит за пределы папки сборки.")
                target.parent.mkdir(parents=True, exist_ok=True)
                part = target.with_suffix(target.suffix + ".part")
                digest_sha1 = hashlib.sha1()
                digest_sha512 = hashlib.sha512()
                try:
                    with requests.get(file_url, stream=True, timeout=(15, 60),
                                      headers={"User-Agent": USER_AGENT}) as file_response:
                        file_response.raise_for_status()
                        length = int(file_response.headers.get("Content-Length", "0") or 0)
                        downloaded = 0
                        with part.open("wb") as stream:
                            for chunk in file_response.iter_content(256 * 1024):
                                _check_cancel(report)
                                if chunk:
                                    stream.write(chunk)
                                    digest_sha1.update(chunk)
                                    digest_sha512.update(chunk)
                                    downloaded += len(chunk)
                                    file_percent = int(downloaded * 100 / length) if length else 0
                                    overall = int((index_no + file_percent / 100) * 80 / max(1, len(content_files)))
                                    report(f"Скачивание {relative.name}", overall)
                    hashes = item.get("hashes") or {}
                    expected_sha1 = str(hashes.get("sha1") or "").lower()
                    expected_sha512 = str(hashes.get("sha512") or "").lower()
                    if expected_sha1 and digest_sha1.hexdigest().lower() != expected_sha1:
                        raise RuntimeError(f"SHA-1 не совпал: {relative.name}")
                    if expected_sha512 and digest_sha512.hexdigest().lower() != expected_sha512:
                        raise RuntimeError(f"SHA-512 не совпал: {relative.name}")
                    part.replace(target)
                except Exception:
                    part.unlink(missing_ok=True)
                    raise
            for member_name in names:
                _check_cancel(report)
                member = PurePosixPath(member_name)
                if member.is_absolute() or ".." in member.parts or (member.parts and ":" in member.parts[0]):
                    raise ValueError("Архив содержит небезопасный путь.")
                if not member.parts or member.parts[0] not in {"overrides", "client-overrides"} or len(member.parts) < 2:
                    continue
                relative = PurePosixPath(*member.parts[1:])
                if not relative.parts:
                    continue
                target = root.joinpath(*relative.parts)
                if root.resolve() not in target.resolve().parents:
                    raise ValueError("Путь overrides выходит за пределы папки сборки.")
                if member_name.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member_name) as source, target.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        instance["minecraft_version"] = mc
        instance["loader"] = chosen_loader[1] if chosen_loader else "Vanilla"
        instance["loader_version"] = chosen_loader[2] if chosen_loader else ""
        instance["installed_version"] = ""
        report("Модпак импортирован", 100)
        return root
    finally:
        archive_path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


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
                _check_cancel(report)
                if chunk:
                    stream.write(chunk)
                    downloaded += len(chunk)
                    report(f"Скачивание {filename}", int(downloaded * 100 / length) if length else -1)
    temporary.replace(target)
    return target
