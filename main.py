"""Qwen3-TTS 本地测试面板入口。

依赖装配：后端 -> TTSService -> MainWindow。
后续增加后端（如 MLX）时只需扩展 backends.factory。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from backends.factory import create_default_backend
from core.tts_service import TTSService
from ui.main_window import MainWindow
from ui.styles import STYLE_SHEET


def configure_bundled_runtime() -> None:
    """Expose bundled command-line helpers, such as SoX, to child processes."""
    if not getattr(sys, "frozen", False):
        return
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ["PATH"] = f"{bundle_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def default_output_dir() -> Path:
    """Return a writable output directory for source and bundled launches."""
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent / "outputs"

    if sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base_dir = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base_dir / "Qwen3-TTS-Test-Panel" / "outputs"


def main() -> int:
    configure_bundled_runtime()
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)

    backend, default_model_key = create_default_backend()
    service = TTSService(
        backend=backend,
        output_dir=default_output_dir(),
    )
    window = MainWindow(service, default_model_key=default_model_key)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
