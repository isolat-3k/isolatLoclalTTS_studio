"""后台工作线程：把模型加载与推理移出 Qt 主线程。

worker 只依赖 TTSService，不接触任何 UI 控件；
结果全部通过 Qt signal 返回，异常在终端保留完整 traceback。
"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from .tts_service import TTSService


def _short_error(exc: BaseException) -> str:
    """给界面显示的简洁错误信息（完整 traceback 只输出到终端）。"""
    return f"{type(exc).__name__}: {exc}"


class LoadModelWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, service: TTSService, parent=None) -> None:
        super().__init__(parent)
        self._service = service

    def run(self) -> None:
        self.status_changed.emit("正在加载模型，首次运行需要下载模型文件…")
        try:
            self._service.load_model()
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(_short_error(exc))
            return
        self.succeeded.emit()


class GenerateWorker(QThread):
    succeeded = Signal(object)  # 生成成功的 WAV 路径 (pathlib.Path)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(
        self,
        service: TTSService,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._text = text
        self._language = language
        self._speaker = speaker
        self._instruct = instruct

    def run(self) -> None:
        self.status_changed.emit("正在生成音频…")
        try:
            wav_path = self._service.generate(
                text=self._text,
                language=self._language,
                speaker=self._speaker,
                instruct=self._instruct,
            )
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(_short_error(exc))
            return
        self.succeeded.emit(wav_path)
