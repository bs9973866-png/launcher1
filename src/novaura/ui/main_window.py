from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

import requests
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget, QInputDialog, QDialog, QFormLayout, QDialogButtonBox, QPlainTextEdit
)

from novaura.config import load_config, save_config, make_instance, game_root, slugify, default_config
from novaura.i18n import tr
from novaura.services.accounts import AccountStore
from novaura.services.files import export_instance, import_instance, import_pack_file, open_managed_folder
from novaura.services.launcher import available_versions, launch_instance, loader_ids
from novaura.services.modrinth import search_modrinth, search_curseforge, download_project, install_curseforge_project, install_modrinth_modpack
from novaura.ui.skin_preview import SkinCubeWidget
from novaura.ui.theme import PALETTES, stylesheet
from novaura.workers import TaskWorker

log = logging.getLogger(__name__)


def asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate = base / "novaura" / "assets" / name
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent / "assets" / name


def make_card(role: str = "surface", parent=None) -> QFrame:
    frame = QFrame(parent)
    frame.setProperty("role", role)
    frame.setObjectName("surfaceCard")
    return frame


def title_block(title: str, subtitle: str = "") -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(5)
    heading = QLabel(title)
    heading.setProperty("class", "pageTitle")
    layout.addWidget(heading)
    if subtitle:
        description = QLabel(subtitle)
        description.setProperty("class", "subtitle")
        description.setWordWrap(True)
        layout.addWidget(description)
    return widget


def scroll_page(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


class MainWindow(QMainWindow):
    NAV = [
        ("home", "nav_home", "⌂"),
        ("instances", "nav_instances", "▦"),
        ("mods", "nav_mods", "▤"),
        ("resources", "nav_resources", "▧"),
        ("optimize", "nav_optimize", "✧"),
        ("accounts", "nav_accounts", "◎"),
        ("settings", "nav_settings", "⚙"),
    ]

    def __init__(self, config: dict[str, Any], parent=None):
        super().__init__(parent)
        self.config = config
        self.store = AccountStore()
        self.versions: list[dict[str, Any]] = []
        self.version_combos: list[QComboBox] = []
        self.workers: list[TaskWorker] = []
        self.current_worker: TaskWorker | None = None
        self.result_cards: list[QWidget] = []
        self.skin_widget: SkinCubeWidget | None = None
        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._language = str(config.get("language", "ru"))
        if not self.store.list_accounts():
            try:
                self.store.add_offline("Player")
            except Exception:
                log.exception("Unable to create initial offline profile")
        self.setObjectName("mainWindow")
        self.setWindowTitle("NOVAURA Launcher")
        self.setWindowIcon(QIcon(str(asset_path("novaura-mark.svg"))))
        self.setMinimumSize(1040, 700)
        self.resize(1390, 880)
        self.setStyleSheet(stylesheet(self.config))
        self.setWindowOpacity(float(self.config.get("window_opacity", 1.0)))
        self.rebuild_ui()
        self.refresh_versions_async()

    def text(self, key: str) -> str:
        return tr(self._language, key)

    def save(self) -> None:
        save_config(self.config)

    def active_instance(self) -> dict[str, Any]:
        active_id = self.config.get("active_instance")
        for item in self.config.get("instances", []):
            if item.get("id") == active_id:
                return item
        instances = self.config.get("instances", [])
        if instances:
            self.config["active_instance"] = instances[0]["id"]
            return instances[0]
        created = make_instance("Основная сборка", "1.21.11", "Vanilla", self.config)
        instances.append(created)
        self.config["active_instance"] = created["id"]
        self.save()
        return created

    def rebuild_ui(self) -> None:
        self.version_combos = []
        self._pages = {}
        self._nav_buttons = {}
        center = QWidget(self)
        base = QHBoxLayout(center)
        base.setContentsMargins(12, 12, 12, 12)
        base.setSpacing(12)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 16, 12, 14)
        side.setSpacing(7)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(4, 0, 0, 14)
        brand_layout.setSpacing(10)
        mark = QLabel("N")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(40, 40)
        mark.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff439c,stop:1 #8f4bff); border-radius: 13px; font-size: 23pt; font-weight: 900;")
        brand_layout.addWidget(mark)
        brand_names = QVBoxLayout()
        brand_name = QLabel("NOVAURA")
        brand_name.setStyleSheet("font-size: 15pt; font-weight: 900; letter-spacing: 1px;")
        brand_tagline = QLabel("MINECRAFT LAUNCHER")
        brand_tagline.setStyleSheet("color: #a99ab9; font-size: 7pt; letter-spacing: 1px;")
        brand_names.addWidget(brand_name)
        brand_names.addWidget(brand_tagline)
        brand_layout.addLayout(brand_names, 1)
        side.addWidget(brand)

        self._nav_buttons = {}
        for page_id, label_key, glyph in self.NAV:
            button = QPushButton(f"{glyph}    {self.text(label_key)}")
            button.setObjectName("navButton")
            button.setProperty("active", page_id == "home")
            button.setMinimumHeight(43)
            button.clicked.connect(lambda checked=False, p=page_id: self.navigate(p))
            side.addWidget(button)
            self._nav_buttons[page_id] = button

        side.addStretch(1)
        footer = QFrame()
        footer.setProperty("role", "soft")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 12, 12, 12)
        version_label = QLabel("NOVAURA  •  v0.1.0")
        version_label.setStyleSheet("font-weight: 800;")
        hint = QLabel("Сделано для твоей игры")
        hint.setProperty("class", "subtitle")
        footer_layout.addWidget(version_label)
        footer_layout.addWidget(hint)
        side.addWidget(footer)
        base.addWidget(sidebar)

        right = QVBoxLayout()
        right.setSpacing(10)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(16, 10, 16, 10)
        page_title = QLabel("NOVAURA  /  GAME CENTER")
        page_title.setStyleSheet("font-weight: 800; letter-spacing: 1px;")
        page_title.setProperty("class", "muted")
        top.addWidget(page_title)
        top.addStretch(1)
        account = self.store.active_account()
        current_name = account.get("name", "Player") if account else "Player"
        current_provider = account.get("provider", "Офлайн") if account else "Офлайн"
        account_label = QLabel(f"●  {current_name}  ·  {current_provider}")
        account_label.setStyleSheet("color: #dfd3ea; padding: 7px 10px; background: #21172c; border-radius: 10px;")
        top.addWidget(account_label)
        right.addWidget(topbar)

        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(650)
        page_builders: list[tuple[str, Callable[[], QWidget]]] = [
            ("home", self.build_home_page),
            ("instances", self.build_instances_page),
            ("mods", self.build_mods_page),
            ("resources", self.build_resources_page),
            ("optimize", self.build_optimization_page),
            ("accounts", self.build_accounts_page),
            ("settings", self.build_settings_page),
        ]
        for page_id, builder in page_builders:
            page = builder()
            self._pages[page_id] = page
            self.stack.addWidget(page)
        right.addWidget(self.stack, 1)

        bottom = QFrame()
        bottom.setProperty("role", "soft")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(12, 5, 12, 5)
        self.status_label = QLabel(self.text("status_ready"))
        self.status_label.setProperty("class", "subtitle")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(190)
        self.progress.setFixedHeight(8)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.cancel_button = QPushButton("Отменить")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_current_task)
        bottom_layout.addWidget(QLabel("●"))
        bottom_layout.addWidget(self.status_label, 1)
        bottom_layout.addWidget(self.progress)
        bottom_layout.addWidget(self.cancel_button)
        right.addWidget(bottom)
        base.addLayout(right, 1)
        self.setCentralWidget(center)
        self.navigate("home")

    def navigate(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        for key, button in self._nav_buttons.items():
            button.setProperty("active", key == page_id)
            button.style().unpolish(button)
            button.style().polish(button)
        if self.config.get("animations", True):
            effect = page.graphicsEffect()
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(page)
                page.setGraphicsEffect(effect)
            effect.setOpacity(0.2)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(170)
            animation.setStartValue(0.2)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.start()
            self._page_animation = animation

    def cancel_current_task(self) -> None:
        worker = self.current_worker
        if worker and worker.isRunning():
            worker.cancel()
            self._set_status("Запрошена отмена…", -1)

    def _task_finished(self, worker: TaskWorker) -> None:
        if worker in self.workers:
            self.workers.remove(worker)
        if self.current_worker is worker:
            active = [item for item in self.workers if item.isRunning()]
            self.current_worker = active[-1] if active else None
        if hasattr(self, "cancel_button"):
            self.cancel_button.setVisible(any(item.isRunning() for item in self.workers))

    def _page_content(self) -> tuple[QWidget, QVBoxLayout]:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 5, 8, 18)
        layout.setSpacing(14)
        return widget, layout

    def _button(self, label: str, primary: bool = False, callback: Callable | None = None) -> QPushButton:
        button = QPushButton(label)
        if primary:
            button.setObjectName("primary")
        if callback:
            button.clicked.connect(callback)
        return button

    def _combo(self, values: list[str], current: str = "") -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        if current and combo.findText(current) < 0:
            combo.addItem(current)
        if current:
            combo.setCurrentText(current)
        return combo

    def _current_loader_id(self, instance: dict[str, Any] | None = None) -> str:
        instance = instance or self.active_instance()
        return {
            "Vanilla": "",
            "Fabric": "fabric",
            "Forge": "forge",
            "NeoForge": "neoforge",
            "Quilt": "quilt",
        }.get(str(instance.get("loader", "Vanilla")), "")

    def _loader_choices(self) -> list[str]:
        installed = set(loader_ids())
        result = ["Vanilla"]
        for label, loader_id in [("Fabric", "fabric"), ("Forge", "forge"), ("NeoForge", "neoforge"), ("Quilt", "quilt")]:
            if not installed or loader_id in installed:
                result.append(label)
        return result

    def refresh_versions_async(self) -> None:
        if any(worker.isRunning() for worker in self.workers):
            # Version loading is independent; do not start duplicate manifest requests.
            if self.versions:
                return
        self._start_task(
            "Загрузка списка версий…",
            lambda report: available_versions(),
            on_success=self._versions_loaded,
            show_error=True,
        )

    def _versions_loaded(self, versions: list[dict[str, Any]]) -> None:
        self.versions = versions
        labels = [str(item.get("id")) for item in versions if item.get("id")]
        for combo in self.version_combos:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(labels)
            if current and combo.findText(current) < 0:
                combo.insertItem(0, current)
            if current:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        self._set_status(f"{len(labels)} {self.text('versions_loaded')}")
        if hasattr(self, "home_version_combo"):
            version = self.active_instance().get("minecraft_version", "")
            if self.home_version_combo.findText(version) < 0:
                self.home_version_combo.insertItem(0, version)
            self.home_version_combo.setCurrentText(version)

    def _set_status(self, message: str, percent: int = -1) -> None:
        if hasattr(self, "status_label"):
            self.status_label.setText(message)
        if hasattr(self, "progress"):
            if percent >= 0:
                self.progress.setVisible(True)
                self.progress.setValue(percent)
            elif percent == -1:
                self.progress.setVisible(False)

    def _start_task(
        self,
        title: str,
        task: Callable[[Callable[[str, int], None]], Any],
        on_success: Callable[[Any], None] | None = None,
        show_error: bool = True,
    ) -> None:
        self._set_status(title, 0)

        worker = TaskWorker(task, self)
        self.current_worker = worker
        self.workers.append(worker)
        if hasattr(self, "cancel_button"):
            self.cancel_button.setVisible(True)
        worker.progress.connect(self._set_status)

        def succeeded(result: Any) -> None:
            self._set_status(self.text("status_ready"), -1)
            if hasattr(self, "home_play_button"):
                self.home_play_button.setEnabled(True)
            if on_success:
                try:
                    on_success(result)
                except Exception as exc:
                    log.exception("Post-task update failed")
                    if show_error:
                        QMessageBox.critical(self, "NOVAURA", str(exc))

        def failed(message: str) -> None:
            if message == "Операция отменена.":
                self._set_status("Операция отменена", -1)
            else:
                self._set_status(f"Ошибка: {message}", -1)
                if show_error:
                    QMessageBox.critical(self, "NOVAURA", message)
            if hasattr(self, "home_play_button"):
                self.home_play_button.setEnabled(True)

        worker.succeeded.connect(succeeded)
        worker.failed.connect(failed)
        worker.finished.connect(lambda w=worker: self._task_finished(w))
        worker.start()

    def _set_active_instance(self, instance_id: str) -> None:
        if not any(item.get("id") == instance_id for item in self.config["instances"]):
            return
        self.config["active_instance"] = instance_id
        self.save()
        self.rebuild_ui()

    def build_home_page(self) -> QWidget:
        content, layout = self._page_content()
        hero = QFrame()
        hero.setProperty("role", "hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 18, 20)
        hero_layout.setSpacing(12)
        left = QVBoxLayout()
        eyebrow = QLabel("N O V A U R A   /   M C   J A V A")
        eyebrow.setProperty("class", "eyebrow")
        welcome = QLabel(self.text("welcome"))
        welcome.setWordWrap(True)
        welcome.setStyleSheet("font-size: 24pt; font-weight: 900;")
        subtitle = QLabel(self.text("home_subtitle"))
        subtitle.setProperty("class", "subtitle")
        subtitle.setWordWrap(True)
        left.addWidget(eyebrow)
        left.addSpacing(5)
        left.addWidget(welcome)
        left.addWidget(subtitle)
        left.addStretch(1)
        self.home_play_button = self._button("▶   " + self.text("launch"), True, self.launch_active_instance)
        self.home_play_button.setMinimumHeight(54)
        self.home_play_button.setMinimumWidth(190)
        left.addWidget(self.home_play_button, 0, Qt.AlignmentFlag.AlignLeft)
        hero_layout.addLayout(left, 3)
        artwork = QSvgWidget(str(asset_path("hero-art.svg")))
        artwork.setMinimumSize(240, 160)
        artwork.setMaximumSize(390, 220)
        hero_layout.addWidget(artwork, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(hero)

        label_row = QHBoxLayout()
        label_row.addWidget(title_block(self.text("active_instance"), self.text("launch_hint")))
        label_row.addStretch(1)
        label_row.addWidget(self._button("↻  " + self.text("refresh"), False, self.refresh_versions_async))
        layout.addLayout(label_row)

        settings_card = make_card()
        settings_layout = QGridLayout(settings_card)
        settings_layout.setContentsMargins(18, 18, 18, 18)
        settings_layout.setHorizontalSpacing(14)
        settings_layout.setVerticalSpacing(10)
        settings_layout.addWidget(QLabel(self.text("active_instance")), 0, 0)
        self.home_instance_combo = self._combo([item["name"] for item in self.config["instances"]], self.active_instance()["name"])
        self.home_instance_combo.currentTextChanged.connect(self._home_instance_changed)
        for i, item in enumerate(self.config["instances"]):
            self.home_instance_combo.setItemData(i, item.get("id", ""))
        settings_layout.addWidget(self.home_instance_combo, 1, 0)
        settings_layout.addWidget(QLabel(self.text("version")), 0, 1)
        instance = self.active_instance()
        self.home_version_combo = self._combo([instance.get("minecraft_version", "1.21.11")], instance.get("minecraft_version", "1.21.11"))
        self.home_version_combo.currentTextChanged.connect(self._home_version_changed)
        self.version_combos.append(self.home_version_combo)
        settings_layout.addWidget(self.home_version_combo, 1, 1)
        settings_layout.addWidget(QLabel(self.text("loader")), 0, 2)
        self.home_loader_combo = self._combo(self._loader_choices(), instance.get("loader", "Vanilla"))
        self.home_loader_combo.currentTextChanged.connect(self._home_loader_changed)
        settings_layout.addWidget(self.home_loader_combo, 1, 2)
        account = self.store.active_account()
        active_name = account.get("name", "Player") if account else "Player"
        account_widget = QLabel(f"◎  {active_name}")
        account_widget.setStyleSheet("background:#21172c;border:1px solid #3a2b48;border-radius:10px;padding:10px;")
        settings_layout.addWidget(QLabel(self.text("profile")), 0, 3)
        settings_layout.addWidget(account_widget, 1, 3)
        layout.addWidget(settings_card)

        lower = QGridLayout()
        lower.setHorizontalSpacing(12)
        lower.setVerticalSpacing(12)
        features = [
            ("01", "Fabric / Forge / NeoForge", "Раздельные профили и свои папки игры", "instances"),
            ("02", "Modrinth + CurseForge", "Подбор модов под версию сборки", "mods"),
            ("03", "Ресурсы", "Ресурс-паки и шейдеры отдельно от сборок", "resources"),
        ]
        for index, (number, title, detail, destination) in enumerate(features):
            card = make_card()
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 15, 16, 16)
            num = QLabel(number)
            num.setProperty("class", "eyebrow")
            heading = QLabel(title)
            heading.setStyleSheet("font-size: 12pt;font-weight:800;")
            desc = QLabel(detail)
            desc.setProperty("class", "subtitle")
            desc.setWordWrap(True)
            jump = self._button("Открыть  →", False, lambda checked=False, p=destination: self.navigate(p))
            box.addWidget(num)
            box.addWidget(heading)
            box.addWidget(desc, 1)
            box.addWidget(jump, 0, Qt.AlignmentFlag.AlignLeft)
            lower.addWidget(card, index // 3, index % 3)
        layout.addLayout(lower)
        layout.addStretch(1)
        return scroll_page(content)

    def _home_instance_changed(self, name: str) -> None:
        for item in self.config.get("instances", []):
            if item.get("name") == name:
                self.config["active_instance"] = item["id"]
                self.save()
                if self.home_version_combo.currentText() != item.get("minecraft_version"):
                    self.home_version_combo.blockSignals(True)
                    self.home_version_combo.setCurrentText(item.get("minecraft_version", "1.21.11"))
                    self.home_version_combo.blockSignals(False)
                if self.home_loader_combo.currentText() != item.get("loader"):
                    self.home_loader_combo.blockSignals(True)
                    self.home_loader_combo.setCurrentText(item.get("loader", "Vanilla"))
                    self.home_loader_combo.blockSignals(False)
                return

    def _home_version_changed(self, version: str) -> None:
        if not version:
            return
        self.active_instance()["minecraft_version"] = version
        self.save()

    def _home_loader_changed(self, loader: str) -> None:
        if not loader:
            return
        self.active_instance()["loader"] = loader
        self.active_instance()["installed_version"] = ""
        self.save()

    def build_instances_page(self) -> QWidget:
        content, layout = self._page_content()
        layout.addWidget(title_block(self.text("nav_instances"), "Создавай независимые игровые сборки с разными версиями и загрузчиками."))
        create_card = make_card()
        box = QVBoxLayout(create_card)
        box.setContentsMargins(18, 17, 18, 18)
        box.setSpacing(12)
        box.addWidget(QLabel(self.text("new_instance")))
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        self.instance_name_input = QLineEdit()
        self.instance_name_input.setPlaceholderText(self.text("instance_name"))
        version_list = [self.active_instance().get("minecraft_version", "1.21.11")]
        self.instance_version_combo = self._combo(version_list)
        self.version_combos.append(self.instance_version_combo)
        self.instance_loader_combo = self._combo(self._loader_choices(), "Fabric" if "Fabric" in self._loader_choices() else "Vanilla")
        form.addWidget(QLabel(self.text("instance_name")), 0, 0)
        form.addWidget(QLabel(self.text("version")), 0, 1)
        form.addWidget(QLabel(self.text("loader")), 0, 2)
        form.addWidget(self.instance_name_input, 1, 0)
        form.addWidget(self.instance_version_combo, 1, 1)
        form.addWidget(self.instance_loader_combo, 1, 2)
        box.addLayout(form)
        box.addWidget(self._button("＋  " + self.text("create"), True, self.create_instance), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(create_card)
        layout.addWidget(QLabel(self.text("recent")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for index, instance in enumerate(self.config.get("instances", [])):
            card = make_card()
            inner = QVBoxLayout(card)
            inner.setContentsMargins(16, 15, 16, 15)
            header = QHBoxLayout()
            mark = QLabel("N")
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mark.setFixedSize(38, 38)
            mark.setStyleSheet("font-size:18pt;font-weight:900;background:#2e1b40;border:1px solid #6d3b85;border-radius:12px;")
            name = QLabel(instance.get("name", "Instance"))
            name.setStyleSheet("font-size:12pt;font-weight:800;")
            header.addWidget(mark)
            header.addWidget(name, 1)
            is_active = instance.get("id") == self.config.get("active_instance")
            if is_active:
                active_tag = QLabel("● " + self.text("active"))
                active_tag.setStyleSheet("color:#6ff0bc;font-size:9pt;")
                header.addWidget(active_tag)
            inner.addLayout(header)
            details = QLabel(f"Minecraft {instance.get('minecraft_version', '?')}  ·  {instance.get('loader', 'Vanilla')}")
            details.setProperty("class", "subtitle")
            details.setWordWrap(True)
            inner.addWidget(details)
            folder = QLabel(instance.get("game_dir", ""))
            folder.setProperty("class", "subtitle")
            folder.setWordWrap(True)
            inner.addWidget(folder)
            buttons = QHBoxLayout()
            play = self._button("▶  " + self.text("launch"), True, lambda checked=False, iid=instance["id"]: self.activate_and_launch(iid))
            buttons.addWidget(play, 2)
            if not is_active:
                buttons.addWidget(self._button("Выбрать", False, lambda checked=False, iid=instance["id"]: self._set_active_instance(iid)), 1)
            buttons.addWidget(self._button("Папка", False, lambda checked=False, it=instance: self._open_instance_folder(it)), 1)
            if len(self.config["instances"]) > 1:
                buttons.addWidget(self._button("×", False, lambda checked=False, iid=instance["id"]: self.remove_instance(iid)), 0)
            inner.addLayout(buttons)
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addStretch(1)
        return scroll_page(content)

    def create_instance(self) -> None:
        try:
            instance = make_instance(
                self.instance_name_input.text(),
                self.instance_version_combo.currentText(),
                self.instance_loader_combo.currentText(),
                self.config,
            )
            self.config.setdefault("instances", []).append(instance)
            self.config["active_instance"] = instance["id"]
            self.save()
            self.rebuild_ui()
            self.navigate("instances")
            self._set_status(f"Создана сборка «{instance['name']}»")
        except Exception as exc:
            QMessageBox.warning(self, "NOVAURA", str(exc))

    def remove_instance(self, instance_id: str) -> None:
        if len(self.config.get("instances", [])) <= 1:
            QMessageBox.information(self, "NOVAURA", "Нельзя удалить последнюю сборку.")
            return
        answer = QMessageBox.question(self, "NOVAURA", "Удалить сборку из списка? Файлы на диске останутся.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.config["instances"] = [item for item in self.config["instances"] if item.get("id") != instance_id]
        if self.config.get("active_instance") == instance_id:
            self.config["active_instance"] = self.config["instances"][0]["id"]
        self.save()
        self.rebuild_ui()
        self.navigate("instances")

    def activate_and_launch(self, instance_id: str) -> None:
        if self.config.get("active_instance") != instance_id:
            self.config["active_instance"] = instance_id
            self.save()
        self.launch_active_instance()

    def _open_instance_folder(self, instance: dict[str, Any]) -> None:
        path = Path(instance.get("game_dir") or game_root())
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def launch_active_instance(self) -> None:
        instance = self.active_instance()
        account = self.store.active_account()
        if not account:
            QMessageBox.information(self, "NOVAURA", self.text("no_account"))
            self.navigate("accounts")
            return
        if account.get("type") != "offline" and not (account.get("credentials") or {}).get("access_token"):
            QMessageBox.warning(self, "NOVAURA", "Токен аккаунта недоступен. Удалите этот профиль и войдите снова.")
            return
        self.home_play_button.setEnabled(False)
        self._start_task(
            f"Подготовка {instance.get('name', '')}…",
            lambda report: launch_instance(instance, account, self.config, report),
            on_success=lambda result: self._launch_completed(result),
        )

    def _launch_completed(self, result: dict[str, str]) -> None:
        self.save()
        self.home_play_button.setEnabled(True)
        QMessageBox.information(
            self,
            "NOVAURA",
            f"{self.text('launch_success')}.\nPID: {result.get('pid')}\nЛог: {result.get('log_path')}",
        )

    def build_mods_page(self) -> QWidget:
        content, layout = self._page_content()
        layout.addWidget(title_block(self.text("nav_mods"), "Поиск контента по выбранной версии сборки. Совместимость проверяется перед установкой."))
        search_card = make_card()
        box = QVBoxLayout(search_card)
        box.setContentsMargins(16, 15, 16, 15)
        row = QHBoxLayout()
        self.mod_query = QLineEdit()
        self.mod_query.setPlaceholderText(self.text("search_placeholder"))
        self.mod_query.returnPressed.connect(self.search_projects)
        self.mod_source = self._combo(["Modrinth", "CurseForge"])
        self.mod_type = self._combo([
            self.text("mods"), self.text("modpacks"), self.text("resourcepacks"), self.text("shaders")
        ])
        self.mod_search_button = self._button("⌕  " + self.text("search"), True, self.search_projects)
        row.addWidget(self.mod_query, 3)
        row.addWidget(self.mod_source, 1)
        row.addWidget(self.mod_type, 1)
        row.addWidget(self.mod_search_button)
        box.addLayout(row)
        box.addWidget(QLabel(f"Сборка: {self.active_instance().get('name')} · Minecraft {self.active_instance().get('minecraft_version')}"))
        layout.addWidget(search_card)
        self.mods_results_widget = QWidget()
        self.mods_results = QVBoxLayout(self.mods_results_widget)
        self.mods_results.setContentsMargins(0, 0, 0, 0)
        self.mods_results.setSpacing(10)
        empty = QLabel("Введи название мода или ресурс-пака и нажми «Поиск».")
        empty.setProperty("class", "subtitle")
        self.mods_results.addWidget(empty)
        layout.addWidget(self.mods_results_widget)
        layout.addStretch(1)
        return scroll_page(content)

    def _selected_project_type(self) -> str:
        return {
            self.text("mods"): "mod",
            self.text("modpacks"): "modpack",
            self.text("resourcepacks"): "resourcepack",
            self.text("shaders"): "shader",
        }.get(self.mod_type.currentText(), "mod")

    def search_projects(self) -> None:
        query = self.mod_query.text().strip()
        if not query:
            QMessageBox.information(self, "NOVAURA", "Сначала введи название проекта.")
            return
        instance = dict(self.active_instance())
        project_type = self._selected_project_type()
        source = self.mod_source.currentText()
        loader = self._current_loader_id(instance)

        def perform(report):
            report("Поиск проектов…", -1)
            if source == "CurseForge":
                hits = search_curseforge(query, instance.get("minecraft_version", ""), project_type)
                return [{"_source": "CurseForge", **item} for item in hits]
            return [{"_source": "Modrinth", **item} for item in search_modrinth(
                query, project_type, instance.get("minecraft_version", ""), loader
            )]

        self._start_task(self.text("search"), perform, on_success=self._render_project_results)

    def _clear_results(self) -> None:
        while self.mods_results.count():
            item = self.mods_results.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render_project_results(self, projects: list[dict[str, Any]]) -> None:
        self._clear_results()
        if not projects:
            label = QLabel(self.text("no_results"))
            label.setProperty("class", "subtitle")
            self.mods_results.addWidget(label)
            return
        project_type = self._selected_project_type()
        for project in projects:
            source = project.get("_source", "Modrinth")
            name = project.get("title") or project.get("name") or "Unnamed project"
            summary = project.get("description") or project.get("summary") or "Описание отсутствует."
            downloads = project.get("downloads", 0)
            icon_url = (project.get("icon_url") or (project.get("logo") or {}).get("url") or "").strip()
            card = make_card()
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 13, 14, 13)
            logo = QLabel("N")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setFixedSize(48, 48)
            logo.setStyleSheet("font-size:18pt;font-weight:900;background:#2d1d3c;border:1px solid #62427a;border-radius:12px;")
            title_desc = QVBoxLayout()
            heading = QLabel(str(name))
            heading.setStyleSheet("font-size:11pt;font-weight:800;")
            description = QLabel(str(summary))
            description.setProperty("class", "subtitle")
            description.setWordWrap(True)
            source_meta = QLabel(f"{source}  ·  {downloads:,} загрузок".replace(",", " "))
            source_meta.setStyleSheet("color:#be9bea;font-size:8pt;")
            title_desc.addWidget(heading)
            title_desc.addWidget(description)
            title_desc.addWidget(source_meta)
            button = self._button("↓  " + self.text("install"), True)
            button.setMinimumWidth(120)
            button.clicked.connect(
                lambda checked=False, p=project, src=source, pt=project_type: self.install_project(p, src, pt)
            )
            row.addWidget(logo)
            row.addLayout(title_desc, 1)
            row.addWidget(button)
            self.mods_results.addWidget(card)
            if icon_url:
                self._load_project_icon(icon_url, logo)

    def _load_project_icon(self, url: str, label: QLabel) -> None:
        # Icons are decorative; failures never block project installation.
        def fetch_icon(report):
            response = requests.get(url, timeout=8, headers={"User-Agent": "NOVAURA-Launcher/0.1.0"})
            response.raise_for_status()
            return response.content
        def show_icon(data: bytes):
            from PySide6.QtGui import QPixmap
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                label.setPixmap(pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        self._start_task("Загрузка значка проекта…", fetch_icon, show_icon, show_error=False)

    def install_project(self, project: dict[str, Any], source: str, project_type: str) -> None:
        instance = self.active_instance()
        if project_type == "mod" and instance.get("loader", "Vanilla") == "Vanilla":
            QMessageBox.information(self, "NOVAURA", "Большинству модов нужен загрузчик. Переключи сборку на Fabric, Forge, NeoForge или Quilt.")
            self.navigate("instances")
            return
        if project_type == "modpack" and source == "CurseForge":
            QMessageBox.information(self, "NOVAURA", "Установка CurseForge-модпаков через manifest пока не поддерживается. Modrinth-модпаки импортируются целиком.")
            return
        def perform(report):
            if project_type == "modpack" and source == "Modrinth":
                return install_modrinth_modpack(project, instance, report)
            if source == "CurseForge":
                return install_curseforge_project(project, instance, project_type, report)
            return download_project(project, instance, project_type, report)
        self._start_task(
            f"Установка {project.get('title') or project.get('name') or 'проекта'}…",
            perform,
            on_success=lambda path: self._project_install_complete(path, project_type),
        )

    def _project_install_complete(self, path: Any, project_type: str) -> None:
        if project_type == "modpack":
            self.save()
            self.rebuild_ui()
            self.navigate("instances")
            QMessageBox.information(self, "NOVAURA", f"Модпак импортирован в сборку «{self.active_instance().get('name')}».\nПроверь загрузчик и запусти игру.")
        else:
            QMessageBox.information(self, "NOVAURA", f"Файл установлен:\n{path}")

    def build_resources_page(self) -> QWidget:
        content, layout = self._page_content()
        layout.addWidget(title_block(self.text("nav_resources"), "Все файлы ресурсов хранятся в папке выбранной сборки."))
        instance = self.active_instance()
        banner = make_card("soft")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(18, 15, 18, 15)
        banner_layout.addWidget(QLabel("АКТИВНАЯ СБОРКА"))
        banner_layout.addWidget(QLabel(f"{instance.get('name')}  ·  {instance.get('minecraft_version')}"), 1)
        banner_layout.addWidget(self._button("Сменить сборку", False, lambda: self.navigate("instances")))
        layout.addWidget(banner)
        cards = QGridLayout()
        sections = [
            ("mods", "Моды", "JAR-файлы модификаций", "Открыть папку", "mods"),
            ("resourcepacks", "Ресурс-паки", "ZIP-паки текстур и звуков", "Открыть папку", "resourcepacks"),
            ("shaderpacks", "Шейдеры", "Паки шейдеров для совместимых рендереров", "Открыть папку", "shaderpacks"),
            ("config", "Конфигурация", "Настройки установленных модов", "Открыть папку", "config"),
        ]
        for index, (icon, name, desc, action, folder) in enumerate(sections):
            card = make_card()
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 15, 16, 16)
            glyph = QLabel({"mods": "▤", "resourcepacks": "▧", "shaderpacks": "✧", "config": "⚙"}[icon])
            glyph.setStyleSheet("font-size:24pt;color:#d68bff;")
            heading = QLabel(name)
            heading.setStyleSheet("font-size:12pt;font-weight:800;")
            detail = QLabel(desc)
            detail.setProperty("class", "subtitle")
            detail.setWordWrap(True)
            box.addWidget(glyph)
            box.addWidget(heading)
            box.addWidget(detail, 1)
            box.addWidget(self._button(action, False, lambda checked=False, f=folder: self.open_resource_folder(f)))
            cards.addWidget(card, index // 2, index % 2)
        layout.addLayout(cards)
        import_card = make_card()
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(18, 17, 18, 17)
        import_layout.addWidget(QLabel("Быстрый импорт"))
        import_layout.addWidget(QLabel("Добавь .jar-мод или ZIP ресурс-пак / шейдер в активную сборку."))
        import_row = QHBoxLayout()
        self.import_target_combo = self._combo(["mods", "resourcepacks", "shaderpacks"])
        import_row.addWidget(self.import_target_combo)
        import_row.addWidget(self._button("Импортировать файл…", True, self.import_resource_file))
        import_row.addWidget(self._button(self.text("export_pack"), False, self.export_active_instance))
        import_row.addWidget(self._button(self.text("import_pack"), False, self.import_instance_archive))
        import_layout.addLayout(import_row)
        layout.addWidget(import_card)
        layout.addStretch(1)
        return scroll_page(content)

    def open_resource_folder(self, folder: str) -> None:
        try:
            path = open_managed_folder(self.active_instance(), folder)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as exc:
            QMessageBox.warning(self, "NOVAURA", str(exc))

    def import_resource_file(self) -> None:
        target = self.import_target_combo.currentText()
        filters = "Файлы модов (*.jar)" if target == "mods" else "ZIP-файлы (*.zip)"
        source, _ = QFileDialog.getOpenFileName(self, "Импортировать файл", str(Path.home()), filters)
        if not source:
            return
        self._start_task("Импорт файла…", lambda report: import_pack_file(source, self.active_instance(), target),
                         on_success=lambda path: QMessageBox.information(self, "NOVAURA", f"Импортировано:\n{path}"))

    def export_active_instance(self) -> None:
        default_name = slugify(self.active_instance().get("name", "novaura-instance")) + ".zip"
        target, _ = QFileDialog.getSaveFileName(self, "Экспорт сборки", str(Path.home() / default_name), "ZIP archive (*.zip)")
        if not target:
            return
        if not target.lower().endswith(".zip"):
            target += ".zip"
        self._start_task("Экспорт сборки…", lambda report: export_instance(self.active_instance(), target),
                         on_success=lambda path: QMessageBox.information(self, "NOVAURA", f"{self.text('export_success')}:\n{path}"))

    def import_instance_archive(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Импорт сборки", str(Path.home()), "ZIP archive (*.zip)")
        if not source:
            return
        default_name = Path(source).stem
        name, ok = QInputDialog.getText(self, "Импорт сборки", self.text("instance_name"), text=default_name)
        if not ok or not name.strip():
            return
        try:
            new_instance = make_instance(name, self.active_instance().get("minecraft_version", "1.21.11"),
                                         self.active_instance().get("loader", "Vanilla"), self.config)
            self.config["instances"].append(new_instance)
            self.config["active_instance"] = new_instance["id"]
            self.save()
            def perform(report):
                manifest = import_instance(source, new_instance["game_dir"])
                details = manifest.get("instance", {})
                if details.get("minecraft_version"):
                    new_instance["minecraft_version"] = str(details["minecraft_version"])
                if details.get("loader"):
                    new_instance["loader"] = str(details["loader"])
                if details.get("loader_version"):
                    new_instance["loader_version"] = str(details["loader_version"])
                self.save()
                return manifest
            self._start_task("Импорт сборки…", perform, on_success=lambda _: self._finish_instance_import(new_instance))
        except Exception as exc:
            QMessageBox.warning(self, "NOVAURA", str(exc))

    def _finish_instance_import(self, instance: dict[str, Any]) -> None:
        self.rebuild_ui()
        self.navigate("instances")
        QMessageBox.information(self, "NOVAURA", f"Импортирована сборка «{instance['name']}».")

    def build_optimization_page(self) -> QWidget:
        content, layout = self._page_content()
        layout.addWidget(title_block(self.text("optimization_title"), self.text("optimization_hint")))
        intro = make_card("hero")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("PERFORMANCE PROFILE")
        title.setProperty("class", "eyebrow")
        subtitle = QLabel("Sodium · Lithium · FerriteCore · EntityCulling")
        subtitle.setStyleSheet("font-size:16pt;font-weight:800;")
        subtitle.setWordWrap(True)
        body = QLabel("Набор подбирает совместимые релизы из Modrinth для версии Minecraft и загрузчика активной сборки. Перед установкой убедись, что моды поддерживают твою конфигурацию.")
        body.setProperty("class", "subtitle")
        body.setWordWrap(True)
        intro_layout.addWidget(title)
        intro_layout.addWidget(subtitle)
        intro_layout.addWidget(body)
        intro_layout.addWidget(self._button("✦  " + self.text("install_performance"), True, self.install_performance_bundle), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(intro)
        items = [
            ("Sodium", "Рендеринг мира с более высокой производительностью.", "sodium"),
            ("Lithium", "Оптимизация игровых тиков и логики.", "lithium"),
            ("FerriteCore", "Снижение расхода оперативной памяти.", "ferrite-core"),
            ("EntityCulling", "Не рендерит скрытые объекты без необходимости.", "entityculling"),
        ]
        for name, desc, slug in items:
            card = make_card()
            row = QHBoxLayout(card)
            row.setContentsMargins(15, 12, 15, 12)
            label = QLabel("✧")
            label.setStyleSheet("font-size:23pt;color:#dd8cff;")
            text_box = QVBoxLayout()
            heading = QLabel(name)
            heading.setStyleSheet("font-size:11pt;font-weight:800;")
            description = QLabel(desc)
            description.setProperty("class", "subtitle")
            description.setWordWrap(True)
            text_box.addWidget(heading)
            text_box.addWidget(description)
            row.addWidget(label)
            row.addLayout(text_box, 1)
            layout.addWidget(card)
        memory_card = make_card()
        memory = QVBoxLayout(memory_card)
        memory.setContentsMargins(16, 15, 16, 15)
        memory.addWidget(QLabel("Выделение памяти"))
        memory.addWidget(QLabel("Используй настройки Java и RAM. Слишком большое значение может ухудшить отзывчивость системы."))
        memory.addWidget(self._button("Открыть настройки Java", False, lambda: self.navigate("settings")), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(memory_card)
        layout.addStretch(1)
        return scroll_page(content)

    def install_performance_bundle(self) -> None:
        instance = self.active_instance()
        if instance.get("loader", "Vanilla") == "Vanilla":
            QMessageBox.information(self, "NOVAURA", "Для набора оптимизации выбери Fabric или Quilt. Переключить загрузчик можно на странице «Сборки».")
            self.navigate("instances")
            return
        projects = ["sodium", "lithium", "ferrite-core", "entityculling"]
        def perform(report):
            installed = []
            for index, slug in enumerate(projects):
                report(f"Поиск совместимой версии: {slug}", int(index * 100 / len(projects)))
                hits = search_modrinth(slug, "mod", instance.get("minecraft_version", ""), self._current_loader_id(instance), limit=5)
                exact = next((project for project in hits if project.get("slug") == slug), hits[0] if hits else None)
                if not exact:
                    continue
                installed_path = download_project(exact, instance, "mod", report)
                installed.append(installed_path.name)
            return installed
        def done(installed):
            if not installed:
                QMessageBox.warning(self, "NOVAURA", "Не найдено совместимых модов для этой сборки.")
            else:
                QMessageBox.information(self, "NOVAURA", "Установлено:\n" + "\n".join(installed))
        self._start_task("Установка оптимизационного набора…", perform, done)

    def build_accounts_page(self) -> QWidget:
        content, layout = self._page_content()
        layout.addWidget(title_block(self.text("accounts_title"), "Токены хранятся в системном хранилище учётных данных; пароли в файлы лаунчера не записываются."))
        active = self.store.active_account()
        card = make_card("hero")
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 16, 16, 16)
        self.skin_widget = SkinCubeWidget()
        if active:
            self.skin_widget.set_skin_path("", active.get("name", "Player"))
        row.addWidget(self.skin_widget)
        details = QVBoxLayout()
        details.addWidget(QLabel("ТЕКУЩИЙ ПРОФИЛЬ"))
        name = QLabel(active.get("name", "Player") if active else "Нет профиля")
        name.setStyleSheet("font-size:17pt;font-weight:900;")
        provider = QLabel(active.get("provider", "Офлайн") if active else "Добавь игровой аккаунт")
        provider.setProperty("class", "subtitle")
        provider.setWordWrap(True)
        details.addWidget(name)
        details.addWidget(provider)
        details.addWidget(QLabel("Офлайн-профили подходят для одиночной игры и серверов, разрешающих offline-mode. Они не подтверждают лицензию."))
        row.addLayout(details, 1)
        layout.addWidget(card)
        login_grid = QGridLayout()
        actions = [
            ("＋  " + self.text("add_offline"), self.add_offline_account),
            ("Microsoft  ·  " + self.text("microsoft"), self.add_microsoft_account),
            ("Ely.by  ·  " + self.text("ely"), self.add_ely_account),
        ]
        for index, (label, callback) in enumerate(actions):
            button = self._button(label, index == 0, callback)
            button.setMinimumHeight(49)
            login_grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(login_grid)
        layout.addWidget(QLabel("Сохранённые аккаунты"))
        for account in self.store.list_accounts():
            account_card = make_card()
            account_row = QHBoxLayout(account_card)
            account_row.setContentsMargins(14, 10, 14, 10)
            icon = QLabel("◎")
            icon.setStyleSheet("font-size:22pt;color:#d48bff;")
            labels = QVBoxLayout()
            title = QLabel(account.get("name", "Player"))
            title.setStyleSheet("font-weight:800;")
            subtitle = QLabel(account.get("provider", account.get("type", "offline")))
            subtitle.setProperty("class", "subtitle")
            labels.addWidget(title)
            labels.addWidget(subtitle)
            account_row.addWidget(icon)
            account_row.addLayout(labels, 1)
            if account.get("uuid") == self.store.active_uuid():
                active_label = QLabel("● " + self.text("active"))
                active_label.setStyleSheet("color:#6ff0bc;")
                account_row.addWidget(active_label)
            else:
                account_row.addWidget(self._button("Сделать активным", False,
                                                   lambda checked=False, uid=account["uuid"]: self.switch_account(uid)))
            account_row.addWidget(self._button("×", False, lambda checked=False, uid=account["uuid"]: self.remove_account(uid)))
            layout.addWidget(account_card)
        if active and active.get("skin_url"):
            skin_url = active["skin_url"]
            self._start_task("Загрузка скина…", lambda report: self._download_skin(skin_url, report),
                             on_success=lambda path: self.skin_widget.set_skin_path(path, active.get("name", "Player")),
                             show_error=False)
        layout.addStretch(1)
        return scroll_page(content)

    def _download_skin(self, url: str, report) -> str:
        from novaura.config import app_data_dir
        import hashlib
        response = requests.get(url, timeout=15, headers={"User-Agent": "NOVAURA-Launcher/0.1.0"})
        response.raise_for_status()
        data = response.content
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Файл скина неожиданно большой.")
        skin_cache = app_data_dir() / "skins"
        skin_cache.mkdir(parents=True, exist_ok=True)
        path = skin_cache / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".png")
        path.write_bytes(data)
        return str(path)

    def add_offline_account(self) -> None:
        current = self.store.active_account()
        name, ok = QInputDialog.getText(self, "NOVAURA", "Ник (1–16 символов):", text=current.get("name", "") if current else "")
        if not ok:
            return
        try:
            self.store.add_offline(name)
            self.rebuild_ui()
            self.navigate("accounts")
        except Exception as exc:
            QMessageBox.warning(self, "NOVAURA", str(exc))

    def add_microsoft_account(self) -> None:
        client_id = str(self.config.get("microsoft_client_id", "")).strip()
        redirect_uri = str(self.config.get("microsoft_redirect_uri", "http://localhost:8765/callback"))
        if not client_id:
            QMessageBox.information(
                self, "NOVAURA",
                "В настройках укажи Microsoft Client ID и Redirect URI, зарегистрированный в Microsoft Entra. "
                "Для Minecraft API приложению может потребоваться одобрение Microsoft."
            )
            self.navigate("settings")
            return
        self._start_task(
            "Ожидание входа Microsoft в браузере…",
            lambda report: self.store.login_microsoft(client_id, redirect_uri),
            on_success=lambda account: self._account_added(account),
        )

    def add_ely_account(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Вход Ely.by")
        form = QFormLayout(dialog)
        username = QLineEdit()
        password = QLineEdit()
        password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Логин или email:", username)
        form.addRow("Пароль:", password)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_task(
            "Вход в Ely.by…",
            lambda report: self.store.login_ely(username.text(), password.text()),
            on_success=lambda account: self._account_added(account),
        )

    def _account_added(self, account: dict[str, Any]) -> None:
        self.rebuild_ui()
        self.navigate("accounts")
        QMessageBox.information(self, "NOVAURA", f"Аккаунт {account.get('name')} добавлен.")

    def switch_account(self, account_uuid: str) -> None:
        try:
            self.store.set_active(account_uuid)
            self.rebuild_ui()
            self.navigate("accounts")
        except Exception as exc:
            QMessageBox.warning(self, "NOVAURA", str(exc))

    def remove_account(self, account_uuid: str) -> None:
        answer = QMessageBox.question(self, "NOVAURA", "Удалить профиль из лаунчера?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.remove(account_uuid)
        if not self.store.list_accounts():
            self.store.add_offline("Player")
        self.rebuild_ui()
        self.navigate("accounts")

    def build_settings_page(self) -> QWidget:
        content, layout = self._page_content()
        layout.addWidget(title_block(self.text("settings_title"), "Темы, Java, память и интеграции. Секреты API не следует помещать в конфигурацию или репозиторий."))
        appearance = make_card()
        app_layout = QGridLayout(appearance)
        app_layout.setContentsMargins(17, 16, 17, 17)
        app_layout.setHorizontalSpacing(14)
        app_layout.setVerticalSpacing(10)
        app_layout.addWidget(QLabel(self.text("language")), 0, 0)
        self.language_combo = self._combo(["Русский", "English"], "Русский" if self._language == "ru" else "English")
        app_layout.addWidget(self.language_combo, 1, 0)
        app_layout.addWidget(QLabel(self.text("theme")), 0, 1)
        self.theme_combo = self._combo(["violet", "pink", "cyan", "custom"], str(self.config.get("theme", "violet")))
        app_layout.addWidget(self.theme_combo, 1, 1)
        app_layout.addWidget(QLabel(self.text("accent") + "  (HEX)"), 0, 2)
        self.accent_input = QLineEdit(str(self.config.get("accent", PALETTES.get(self.config.get("theme"), PALETTES["violet"]))))
        app_layout.addWidget(self.accent_input, 1, 2)
        app_layout.addWidget(QLabel(self.text("scale")), 2, 0)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(90, 115)
        self.scale_slider.setValue(int(float(self.config.get("ui_scale", 1.0)) * 100))
        app_layout.addWidget(self.scale_slider, 3, 0)
        app_layout.addWidget(QLabel(self.text("radius")), 2, 1)
        self.radius_slider = QSlider(Qt.Orientation.Horizontal)
        self.radius_slider.setRange(10, 30)
        self.radius_slider.setValue(int(self.config.get("corner_radius", 18)))
        app_layout.addWidget(self.radius_slider, 3, 1)
        app_layout.addWidget(QLabel(self.text("opacity")), 2, 2)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(80, 100)
        self.opacity_slider.setValue(int(float(self.config.get("window_opacity", 1.0)) * 100))
        app_layout.addWidget(self.opacity_slider, 3, 2)
        self.animations_check = QCheckBox(self.text("animations"))
        self.animations_check.setChecked(bool(self.config.get("animations", True)))
        app_layout.addWidget(self.animations_check, 4, 0, 1, 2)
        bg_row = QHBoxLayout()
        self.background_label = QLabel(Path(str(self.config.get("background_image", ""))).name or "NOVAURA default")
        self.background_label.setProperty("class", "subtitle")
        bg_row.addWidget(self.background_label, 1)
        bg_row.addWidget(self._button(self.text("choose"), False, self.choose_background))
        app_layout.addWidget(QLabel(self.text("background")), 5, 0)
        app_layout.addLayout(bg_row, 5, 1, 1, 2)
        layout.addWidget(appearance)

        preset_card = make_card("soft")
        preset_layout = QGridLayout(preset_card)
        preset_layout.setContentsMargins(17, 13, 17, 13)
        preset_layout.setHorizontalSpacing(10)
        preset_layout.addWidget(QLabel("Сохранённые темы"), 0, 0)
        self.preset_combo = self._combo(sorted(self.config.get("theme_presets", {}).keys()))
        preset_layout.addWidget(self.preset_combo, 1, 0)
        preset_layout.addWidget(self._button("Сохранить как пресет", False, self.save_theme_preset), 1, 1)
        preset_layout.addWidget(self._button("Применить", False, self.apply_theme_preset), 1, 2)
        preset_layout.addWidget(self._button("Удалить", False, self.delete_theme_preset), 1, 3)
        layout.addWidget(preset_card)

        java_card = make_card()
        java_form = QGridLayout(java_card)
        java_form.setContentsMargins(17, 16, 17, 17)
        java_form.setHorizontalSpacing(12)
        java_form.setVerticalSpacing(8)
        java_form.addWidget(QLabel(self.text("java")), 0, 0, 1, 2)
        self.java_input = QLineEdit(str(self.config.get("java_path", "")))
        self.java_input.setPlaceholderText(self.text("java_auto"))
        java_form.addWidget(self.java_input, 1, 0)
        java_form.addWidget(self._button(self.text("choose"), False, self.choose_java), 1, 1)
        java_form.addWidget(QLabel(self.text("ram")), 2, 0)
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(2, 32)
        self.ram_spin.setValue(int(self.config.get("ram_gb", 4)))
        self.ram_spin.setSuffix(" GB")
        java_form.addWidget(self.ram_spin, 3, 0)
        java_form.addWidget(QLabel(self.text("jvm_args")), 2, 1)
        self.jvm_input = QLineEdit(str(self.config.get("jvm_arguments", "")))
        self.jvm_input.setPlaceholderText("-XX:+UseG1GC")
        java_form.addWidget(self.jvm_input, 3, 1)
        java_form.addWidget(QLabel(self.text("game_root")), 4, 0, 1, 2)
        self.game_root_input = QLineEdit(str(self.config.get("game_root", game_root())))
        java_form.addWidget(self.game_root_input, 5, 0)
        java_form.addWidget(self._button(self.text("choose"), False, self.choose_game_root), 5, 1)
        layout.addWidget(java_card)

        auth_card = make_card()
        auth_form = QGridLayout(auth_card)
        auth_form.setContentsMargins(17, 16, 17, 17)
        auth_form.setHorizontalSpacing(12)
        auth_form.setVerticalSpacing(8)
        auth_form.addWidget(QLabel(self.text("client_id")), 0, 0, 1, 2)
        self.client_id_input = QLineEdit(str(self.config.get("microsoft_client_id", "")))
        self.client_id_input.setPlaceholderText("Application (client) ID")
        auth_form.addWidget(self.client_id_input, 1, 0, 1, 2)
        auth_form.addWidget(QLabel(self.text("redirect_uri")), 2, 0, 1, 2)
        self.redirect_input = QLineEdit(str(self.config.get("microsoft_redirect_uri", "http://localhost:8765/callback")))
        auth_form.addWidget(self.redirect_input, 3, 0, 1, 2)
        info = QLabel("Microsoft: требуется собственное приложение Entra и совместимый Redirect URI. CurseForge: API key задаётся только через переменную окружения CURSEFORGE_API_KEY.")
        info.setProperty("class", "subtitle")
        info.setWordWrap(True)
        auth_form.addWidget(info, 4, 0, 1, 2)
        layout.addWidget(auth_card)

        footer_buttons = QHBoxLayout()
        footer_buttons.addWidget(self._button("↻  " + self.text("reset"), False, self.reset_settings))
        footer_buttons.addStretch(1)
        footer_buttons.addWidget(self._button("✓  " + self.text("save"), True, self.save_settings))
        layout.addLayout(footer_buttons)
        layout.addStretch(1)
        return scroll_page(content)

    def _current_theme_values(self) -> dict[str, Any]:
        return {
            "theme": self.theme_combo.currentText(),
            "accent": self.accent_input.text().strip(),
            "ui_scale": self.scale_slider.value() / 100,
            "corner_radius": self.radius_slider.value(),
            "window_opacity": self.opacity_slider.value() / 100,
            "animations": self.animations_check.isChecked(),
            "background_image": self.config.get("pending_background", self.config.get("background_image", "")),
        }

    def _refresh_preset_combo(self, selected: str = "") -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(sorted(self.config.get("theme_presets", {}).keys()))
        if selected:
            self.preset_combo.setCurrentText(selected)
        self.preset_combo.blockSignals(False)

    def save_theme_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "NOVAURA", "Название пресета темы:")
        name = name.strip()
        if not ok or not name:
            return
        presets = self.config.setdefault("theme_presets", {})
        presets[name] = self._current_theme_values()
        self.save()
        self._refresh_preset_combo(name)
        self._set_status(f"Сохранён пресет «{name}»")

    def apply_theme_preset(self) -> None:
        name = self.preset_combo.currentText()
        preset = self.config.get("theme_presets", {}).get(name)
        if not preset:
            QMessageBox.information(self, "NOVAURA", "Сначала выбери сохранённый пресет.")
            return
        self.theme_combo.setCurrentText(str(preset.get("theme", "violet")))
        self.accent_input.setText(str(preset.get("accent", PALETTES["violet"])))
        self.scale_slider.setValue(int(float(preset.get("ui_scale", 1.0)) * 100))
        self.radius_slider.setValue(int(preset.get("corner_radius", 18)))
        self.opacity_slider.setValue(int(float(preset.get("window_opacity", 1.0)) * 100))
        self.animations_check.setChecked(bool(preset.get("animations", True)))
        background = str(preset.get("background_image", ""))
        self.background_label.setText(Path(background).name or "NOVAURA default")
        if background:
            self.config["pending_background"] = background
        else:
            self.config.pop("pending_background", None)
        self.save_settings()

    def delete_theme_preset(self) -> None:
        name = self.preset_combo.currentText()
        if name not in self.config.get("theme_presets", {}):
            QMessageBox.information(self, "NOVAURA", "Сначала выбери сохранённый пресет.")
            return
        answer = QMessageBox.question(self, "NOVAURA", f"Удалить пресет «{name}»?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.config["theme_presets"].pop(name, None)
        self.save()
        self._refresh_preset_combo()
        self._set_status(f"Удалён пресет «{name}»")

    def choose_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Фоновое изображение", str(Path.home()), "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.background_label.setText(Path(path).name)
            self.config["pending_background"] = path

    def choose_java(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать Java", str(Path.home()), "Java executable (java.exe javaw.exe);;All files (*)")
        if path:
            self.java_input.setText(path)

    def choose_game_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Папка игровых сборок", self.game_root_input.text())
        if path:
            self.game_root_input.setText(path)

    def save_settings(self) -> None:
        old_language = self._language
        language = "ru" if self.language_combo.currentText() == "Русский" else "en"
        accent = self.accent_input.text().strip()
        if not (accent.startswith("#") and len(accent) in {4, 7}):
            QMessageBox.warning(self, "NOVAURA", "Укажи цвет в формате HEX, например #e84dff.")
            return
        java = self.java_input.text().strip()
        if java and not Path(java).is_file():
            QMessageBox.warning(self, "NOVAURA", "Файл Java не найден. Проверь путь или оставь поле пустым для автоматического runtime.")
            return
        game_folder = Path(self.game_root_input.text().strip()).expanduser()
        if not str(game_folder):
            QMessageBox.warning(self, "NOVAURA", "Укажи папку для игровых сборок.")
            return
        try:
            game_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "NOVAURA", f"Не удалось создать папку: {exc}")
            return
        self.config.update({
            "language": language,
            "theme": self.theme_combo.currentText(),
            "accent": accent,
            "ui_scale": self.scale_slider.value() / 100,
            "corner_radius": self.radius_slider.value(),
            "window_opacity": self.opacity_slider.value() / 100,
            "animations": self.animations_check.isChecked(),
            "background_image": self.config.pop("pending_background", self.config.get("background_image", "")),
            "java_path": java,
            "ram_gb": self.ram_spin.value(),
            "jvm_arguments": self.jvm_input.text().strip(),
            "microsoft_client_id": self.client_id_input.text().strip(),
            "microsoft_redirect_uri": self.redirect_input.text().strip(),
            "game_root": str(game_folder),
        })
        self._language = language
        for instance in self.config.get("instances", []):
            if not instance.get("game_dir"):
                instance["game_dir"] = str(game_folder / slugify(instance.get("id", "instance")))
        self.save()
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet(self.config))
            font = QFont("Segoe UI", max(9, int(10 * self.config["ui_scale"])))
            app.setFont(font)
        self.setWindowOpacity(self.config["window_opacity"])
        self.setStyleSheet(stylesheet(self.config))
        if old_language != language:
            self.rebuild_ui()
            self.navigate("settings")
        else:
            QMessageBox.information(self, "NOVAURA", self.text("save_success"))

    def reset_settings(self) -> None:
        answer = QMessageBox.question(self, "NOVAURA", "Сбросить тему и настройки лаунчера? Список игровых сборок и аккаунты сохранятся.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        original_instances = self.config.get("instances", default_config()["instances"])
        original_active = self.config.get("active_instance", "main")
        self.config.clear()
        self.config.update(default_config())
        self.config["instances"] = original_instances
        self.config["active_instance"] = original_active
        self._language = str(self.config.get("language", "ru"))
        self.save()
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet(self.config))
        self.setWindowOpacity(1.0)
        self.rebuild_ui()
        self.navigate("settings")
