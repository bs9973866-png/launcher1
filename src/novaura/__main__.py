from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from novaura.config import ensure_app_dirs, load_config, save_config, app_data_dir
from novaura.ui.main_window import MainWindow
from novaura.ui.theme import stylesheet


def configure_logging() -> None:
    ensure_app_dirs()
    log_file = app_data_dir() / "novaura.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("NOVAURA Launcher")
    app.setOrganizationName("NOVAURA")
    app.setFont(QFont("Segoe UI", 10))
    configure_logging()
    config = load_config()
    app.setStyleSheet(stylesheet(config))
    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("Fatal NOVAURA startup error")
        try:
            QMessageBox.critical(None, "NOVAURA Launcher", f"Не удалось запустить лаунчер.\n\n{exc}")
        except Exception:
            print(f"Fatal NOVAURA error: {exc}", file=sys.stderr)
        raise
