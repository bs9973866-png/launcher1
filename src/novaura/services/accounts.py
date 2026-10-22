from __future__ import annotations

import json
import os
import threading
import time
import uuid as uuid_lib
import hashlib
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import keyring
import requests
import minecraft_launcher_lib

from novaura.config import app_data_dir, ensure_app_dirs

KEYRING_SERVICE = "NOVAURA Launcher"
ELY_AUTH_URL = "https://authserver.ely.by/auth/authenticate"


def offline_uuid(name: str) -> str:
    safe_name = name.strip()
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{safe_name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid_lib.UUID(bytes=bytes(digest)))


class AccountStore:
    def __init__(self) -> None:
        ensure_app_dirs()
        self.path = app_data_dir() / "accounts.json"
        if not self.path.exists():
            self._write({"accounts": [], "active_uuid": ""})

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("accounts", [])
                value.setdefault("active_uuid", "")
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"accounts": [], "active_uuid": ""}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def list_accounts(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._read()["accounts"]]

    def active_uuid(self) -> str:
        return str(self._read().get("active_uuid", ""))

    def active_account(self) -> dict[str, Any] | None:
        data = self._read()
        wanted = data.get("active_uuid")
        for item in data["accounts"]:
            if item.get("uuid") == wanted:
                account = dict(item)
                account["credentials"] = self._get_credentials(account)
                return account
        if data["accounts"]:
            account = dict(data["accounts"][0])
            account["credentials"] = self._get_credentials(account)
            return account
        return None

    def add_offline(self, name: str) -> dict[str, Any]:
        clean = name.strip()
        if not clean or len(clean) > 16 or not clean.replace("_", "").isalnum():
            raise ValueError("Ник должен содержать 1–16 латинских букв, цифр или символов подчёркивания.")
        account = {"name": clean, "uuid": offline_uuid(clean), "type": "offline", "provider": "Офлайн-профиль"}
        self._save_account(account, None)
        return account

    def login_ely(self, username: str, password: str) -> dict[str, Any]:
        if not username.strip() or not password:
            raise ValueError("Введите логин и пароль Ely.by.")
        response = requests.post(
            ELY_AUTH_URL,
            json={
                "agent": {"name": "Minecraft", "version": 1},
                "username": username.strip(),
                "password": password,
                "requestUser": True,
            },
            timeout=25,
        )
        if response.status_code >= 400:
            message = "Ely.by отклонил вход. Проверьте логин и пароль."
            try:
                details = response.json()
                message = details.get("errorMessage") or details.get("error") or message
            except ValueError:
                pass
            raise RuntimeError(str(message))
        data = response.json()
        profile = data.get("selectedProfile") or {}
        access_token = data.get("accessToken")
        profile_id = profile.get("id")
        player_name = profile.get("name") or username.strip()
        if not access_token or not profile_id:
            raise RuntimeError("Ely.by вернул неполные данные аккаунта.")
        normalized_uuid = str(profile_id)
        if len(normalized_uuid) == 32:
            normalized_uuid = str(uuid_lib.UUID(normalized_uuid))
        account = {
            "name": player_name,
            "uuid": normalized_uuid,
            "type": "ely",
            "provider": "Ely.by",
        }
        self._save_account(account, {"access_token": access_token, "client_token": data.get("clientToken", "")})
        return account

    def login_microsoft(self, client_id: str, redirect_uri: str) -> dict[str, Any]:
        client_id = client_id.strip()
        redirect_uri = redirect_uri.strip()
        if not client_id:
            raise ValueError("Сначала укажите Microsoft Client ID в настройках лаунчера.")
        parsed_redirect = urlparse(redirect_uri)
        if parsed_redirect.scheme not in {"http", "https"} or not parsed_redirect.hostname:
            raise ValueError("Некорректный Redirect URI.")
        if parsed_redirect.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Для встроенного входа нужен localhost Redirect URI, зарегистрированный в приложении Microsoft.")

        login_url, state, verifier = minecraft_launcher_lib.microsoft_account.get_secure_login_data(client_id, redirect_uri)
        host = parsed_redirect.hostname
        port = parsed_redirect.port or (443 if parsed_redirect.scheme == "https" else 80)
        callback_path = parsed_redirect.path or "/"
        result_url: list[str] = []

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                request_url = f"{redirect_uri}{self.path}" if "?" in self.path else f"{redirect_uri}?{self.path.lstrip('/')}"
                if urlparse(self.path).path != callback_path:
                    self.send_response(404)
                    self.end_headers()
                    return
                result_url.append(request_url)
                body = (
                    "<!doctype html><html><meta charset='utf-8'><title>NOVAURA</title>"
                    "<body style='font:16px Segoe UI;background:#100d18;color:#f7edf9;padding:48px'>"
                    "<h2>Вход завершён</h2><p>Можно вернуться в NOVAURA Launcher и закрыть это окно.</p></body></html>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return

        bind_host = "127.0.0.1" if host == "localhost" else host
        try:
            server = HTTPServer((bind_host, port), CallbackHandler)
        except OSError as exc:
            raise RuntimeError(f"Не удалось открыть локальный порт {port}. Закройте другое приложение, использующее этот порт.") from exc
        server.timeout = 1.0
        deadline = time.time() + 180
        try:
            webbrowser.open(login_url, new=2)
            while not result_url and time.time() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        if not result_url:
            raise TimeoutError("Вход Microsoft не завершён за 3 минуты. Попробуйте снова.")
        auth_code = minecraft_launcher_lib.microsoft_account.parse_auth_code_url(result_url[0], state)
        data = minecraft_launcher_lib.microsoft_account.complete_login(client_id, redirect_uri, auth_code, verifier)
        if not data.get("access_token") or not data.get("id") or not data.get("name"):
            raise RuntimeError("Microsoft/Minecraft вернул неполные данные профиля.")
        account = {
            "name": data["name"],
            "uuid": data["id"],
            "type": "microsoft",
            "provider": "Microsoft",
        }
        secrets = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
        }
        self._save_account(account, secrets)
        return account

    def set_active(self, account_uuid: str) -> None:
        data = self._read()
        if not any(item.get("uuid") == account_uuid for item in data["accounts"]):
            raise ValueError("Аккаунт не найден.")
        data["active_uuid"] = account_uuid
        self._write(data)

    def remove(self, account_uuid: str) -> None:
        data = self._read()
        item = next((a for a in data["accounts"] if a.get("uuid") == account_uuid), None)
        data["accounts"] = [a for a in data["accounts"] if a.get("uuid") != account_uuid]
        if data.get("active_uuid") == account_uuid:
            data["active_uuid"] = data["accounts"][0]["uuid"] if data["accounts"] else ""
        self._write(data)
        if item and item.get("type") != "offline":
            try:
                keyring.delete_password(KEYRING_SERVICE, account_uuid)
            except Exception:
                pass

    def _save_account(self, account: dict[str, Any], credentials: dict[str, Any] | None) -> None:
        data = self._read()
        data["accounts"] = [a for a in data["accounts"] if a.get("uuid") != account["uuid"]]
        data["accounts"].append(account)
        data["active_uuid"] = account["uuid"]
        if credentials:
            try:
                keyring.set_password(KEYRING_SERVICE, account["uuid"], json.dumps(credentials))
            except Exception as exc:
                raise RuntimeError(
                    "Не удалось сохранить токен в системном хранилище учётных данных. "
                    "Проверьте Credential Manager Windows и попробуйте снова."
                ) from exc
        self._write(data)

    def _get_credentials(self, account: dict[str, Any]) -> dict[str, Any]:
        if account.get("type") == "offline":
            return {"access_token": "0"}
        try:
            raw = keyring.get_password(KEYRING_SERVICE, str(account.get("uuid", "")))
            return json.loads(raw) if raw else {}
        except Exception:
            return {}
