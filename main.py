"""Qwen3-TTS 本地测试面板入口。

依赖装配：后端 -> TTSService -> MainWindow。
后续更换后端（如 MLX）时只需替换这里的 QwenTorchBackend。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from backends.qwen_torch import QwenTorchBackend
from core.tts_service import TTSService
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    backend = QwenTorchBackend()
    service = TTSService(
        backend=backend,
        output_dir=Path(__file__).resolve().parent / "outputs",
    )
    window = MainWindow(service)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
