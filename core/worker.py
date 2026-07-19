"""后台工作线程：把模型加载与推理移出 Qt 主线程。

worker 只依赖 TTSService 与 Qt-free 的数据结构，不接触任何 UI 控件；
结果全部通过 Qt signal 返回，异常在终端保留完整 traceback。
"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from backends.base import ModelSpec

from .segments import SegmentStatus, SpeechSegment
from .tts_service import TTSService


def _short_error(exc: BaseException) -> str:
    """给界面显示的简洁错误信息（完整 traceback 只输出到终端）。"""
    return f"{type(exc).__name__}: {exc}"


class LoadModelWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, service: TTSService, spec: ModelSpec, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._spec = spec

    def run(self) -> None:
        self.status_changed.emit(
            f"正在加载模型：{self._spec.display_name}，首次运行需要下载模型文件…"
        )
        try:
            self._service.load_model(self._spec)
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(_short_error(exc))
            return
        self.succeeded.emit()


class GenerateWorker(QThread):
    """单段生成（保持原有链路）。"""

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


class GenerateSegmentWorker(QThread):
    """单个片段生成（片段上的每段覆盖在 TTSService.generate_segment 内生效）。"""

    succeeded = Signal(str, object)  # segment_id, WAV 路径 (pathlib.Path)
    failed = Signal(str, str)  # segment_id, 简洁错误信息
    status_changed = Signal(str)

    def __init__(
        self,
        service: TTSService,
        segment: SpeechSegment,
        language: str,
        speaker: str,
        instruct: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._segment = segment
        self._language = language
        self._speaker = speaker
        self._instruct = instruct

    def run(self) -> None:
        self.status_changed.emit(f"正在生成片段 {self._segment.order}…")
        try:
            wav_path = self._service.generate_segment(
                self._segment,
                language=self._language,
                speaker=self._speaker,
                instruct=self._instruct,
            )
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(self._segment.segment_id, _short_error(exc))
            return
        self.succeeded.emit(self._segment.segment_id, wav_path)


class BatchGenerateWorker(QThread):
    """批量生成：串行处理 NOT_GENERATED / ERROR / QUEUED 片段。

    单段失败不终止整体；request_stop() 在当前段完成后生效。
    片段上的每段覆盖在 TTSService.generate_segment 内生效。
    """

    segment_started = Signal(str)  # segment_id
    segment_succeeded = Signal(str, object)  # segment_id, WAV 路径
    segment_failed = Signal(str, str)  # segment_id, 简洁错误信息
    finished_with_summary = Signal(int, int)  # 成功数, 失败数
    status_changed = Signal(str)

    def __init__(
        self,
        service: TTSService,
        segments: list[SpeechSegment],
        language: str,
        speaker: str,
        instruct: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        # 构造时快照待生成片段；UI 在此期间禁止增删改片段
        self._pending = [
            s
            for s in segments
            if s.status
            in (SegmentStatus.NOT_GENERATED, SegmentStatus.ERROR, SegmentStatus.QUEUED)
        ]
        self._language = language
        self._speaker = speaker
        self._instruct = instruct
        self._stop_requested = False

    def request_stop(self) -> None:
        """请求停止：当前片段生成完成后停止，已完成结果保留。"""
        self._stop_requested = True

    def run(self) -> None:
        ok_count = 0
        fail_count = 0
        total = len(self._pending)
        for segment in self._pending:
            if self._stop_requested:
                break
            self.segment_started.emit(segment.segment_id)
            try:
                wav_path = self._service.generate_segment(
                    segment,
                    language=self._language,
                    speaker=self._speaker,
                    instruct=self._instruct,
                )
            except Exception as exc:
                traceback.print_exc()
                fail_count += 1
                self.segment_failed.emit(segment.segment_id, _short_error(exc))
            else:
                ok_count += 1
                self.segment_succeeded.emit(segment.segment_id, wav_path)
            self.status_changed.emit(
                f"批量生成中… 已处理 {ok_count + fail_count}/{total}"
            )
        self.finished_with_summary.emit(ok_count, fail_count)
