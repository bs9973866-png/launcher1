from __future__ import annotations

from pathlib import Path
from typing import Any

PALETTES = {
    "violet": "#b36aff",
    "pink": "#ff439c",
    "cyan": "#35dfd0",
    "custom": "#e84dff",
}


def accent_for(config: dict[str, Any]) -> str:
    key = str(config.get("theme", "violet"))
    return str(config.get("accent") or PALETTES.get(key, PALETTES["violet"]))


def stylesheet(config: dict[str, Any]) -> str:
    accent = accent_for(config)
    radius = max(10, min(30, int(config.get("corner_radius", 18))))
    background = "#0b0912"
    panel = "#15111f"
    raised = "#1d1729"
    border = "#34253f"
    muted = "#a99ab9"
    background_image = str(config.get("background_image", "")).strip()
    window_bg = f"background-color: {background};"
    if background_image and Path(background_image).is_file():
        safe_path = background_image.replace("\\", "/").replace('"', "")
        window_bg = f'background-color: {background}; background-image: url("{safe_path}"); background-position: center; background-repeat: no-repeat;'
    return f"""
    * {{ font-family: "Segoe UI", "Arial", sans-serif; color: #f7f1fb; }}
    QMainWindow#mainWindow {{ {window_bg} }}
    QWidget {{ background: transparent; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ border: none; background: transparent; }}
    QFrame#sidebar {{ background: rgba(15, 11, 23, 245); border-right: 1px solid {border}; }}
    QFrame#topbar {{ background: rgba(18, 13, 26, 235); border: 1px solid {border}; border-radius: 16px; }}
    QFrame[role="surface"], QFrame.surface {{ background: rgba(24, 18, 34, 242); border: 1px solid {border}; border-radius: {radius}px; }}
    QFrame[role="hero"] {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #27122e,stop:0.55 #21152f,stop:1 #11101b); border: 1px solid {accent}; border-radius: {radius + 4}px; }}
    QFrame[role="soft"] {{ background: rgba(31, 23, 43, 230); border: 1px solid {border}; border-radius: {radius}px; }}
    QLabel {{ background: transparent; }}
    QLabel[class="muted"] {{ color: {muted}; }}
    QLabel[class="eyebrow"] {{ color: {accent}; font-size: 10pt; font-weight: 800; letter-spacing: 2px; }}
    QLabel[class="pageTitle"] {{ font-size: 23pt; font-weight: 750; }}
    QLabel[class="subtitle"] {{ color: {muted}; font-size: 10pt; }}
    QPushButton {{ background: {raised}; border: 1px solid {border}; border-radius: 12px; padding: 10px 15px; font-size: 10pt; font-weight: 600; }}
    QPushButton:hover {{ background: #2b2039; border-color: {accent}; }}
    QPushButton:pressed {{ background: #3b2248; }}
    QPushButton:disabled {{ color: #655b70; background: #17121e; border-color: #2a2032; }}
    QPushButton#primary {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {accent},stop:1 #963df6); border: none; color: #ffffff; font-size: 12pt; font-weight: 800; padding: 13px 20px; }}
    QPushButton#primary:hover {{ background: #ff5aa8; }}
    QPushButton#secondary {{ background: rgba(35, 23, 47, 245); border-color: {accent}; }}
    QPushButton#navButton {{ text-align: left; background: transparent; border: 1px solid transparent; padding: 11px 14px; border-radius: 12px; }}
    QPushButton#navButton:hover {{ background: #20162b; border-color: {border}; }}
    QPushButton#navButton[active="true"] {{ background: rgba(108, 55, 125, 100); border-color: {accent}; color: #ffffff; }}
    QPushButton#iconButton {{ padding: 7px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; border-radius: 10px; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{ background: #100d18; border: 1px solid #3a2b48; border-radius: 10px; padding: 9px 11px; selection-background-color: {accent}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{ border: 1px solid {accent}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: #17111f; border: 1px solid {border}; selection-background-color: {accent}; }}
    QCheckBox {{ spacing: 10px; }}
    QCheckBox::indicator {{ width: 19px; height: 19px; border-radius: 5px; border: 1px solid #564265; background: #100d18; }}
    QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
    QSlider::groove:horizontal {{ height: 5px; background: #34263e; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: #ffffff; border: 3px solid {accent}; width: 13px; height: 13px; margin: -7px 0; border-radius: 8px; }}
    QProgressBar {{ border: none; background: #2a2034; border-radius: 5px; height: 8px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
    QListWidget {{ background: transparent; border: none; outline: none; }}
    QToolTip {{ background: #21172c; color: #ffffff; border: 1px solid {accent}; padding: 5px; }}
    """
