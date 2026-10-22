from pathlib import Path
import os
import tempfile

from novaura.config import default_config, make_instance, slugify
from novaura.services.accounts import offline_uuid
from novaura.services.files import export_instance, import_instance


def test_offline_uuid_is_deterministic():
    assert offline_uuid("Alex") == offline_uuid("Alex")
    assert offline_uuid("Alex") != offline_uuid("Steve")


def test_slugify_has_safe_fallback():
    assert slugify("My test pack") == "My-test-pack"
    assert slugify("///") == "instance"


def test_instance_ids_are_unique():
    config = default_config()
    first = make_instance("PvP", "1.21.11", "Fabric", config)
    config["instances"].append(first)
    second = make_instance("PvP", "1.21.11", "Fabric", config)
    assert first["id"] != second["id"]


def test_instance_export_import_roundtrip():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        instance = {
            "id": "sample",
            "name": "Sample",
            "minecraft_version": "1.21.11",
            "loader": "Fabric",
            "loader_version": "0.16.0",
            "game_dir": str(root / "instance"),
        }
        (root / "instance" / "mods").mkdir(parents=True)
        (root / "instance" / "mods" / "test.jar").write_bytes(b"not a real mod")
        archive = export_instance(instance, str(root / "sample.zip"))
        target = root / "imported"
        manifest = import_instance(str(archive), str(target))
        assert manifest["instance"]["name"] == "Sample"
        assert (target / "mods" / "test.jar").read_bytes() == b"not a real mod"


def test_main_window_constructs_without_network(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory() as temp:
        monkeypatch.setenv("APPDATA", temp)
        from PySide6.QtWidgets import QApplication
        from novaura.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        monkeypatch.setattr(MainWindow, "refresh_versions_async", lambda self: None)
        window = MainWindow(default_config())
        try:
            assert window.windowTitle() == "NOVAURA Launcher"
            assert window.stack.count() == 7
            assert set(window._pages) == {"home", "instances", "mods", "resources", "optimize", "accounts", "settings"}
        finally:
            window.close()
            app.processEvents()
