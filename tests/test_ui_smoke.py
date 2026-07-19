"""UI 层冒烟测试（offscreen 平台，不依赖 CUDA 与真实模型）。

覆盖：
- 用 mock 后端实例化 MainWindow（双栏布局、字符计数、拆分建卡片）；
- WaveformWidget 加载正弦波 WAV 不崩溃、seek 毫秒换算正确；
- TTSService.generate_segment 的每段覆盖逻辑与 600 字限制移除；
- import main 级别的入口导入冒烟。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backends.base import ModelSpec, TTSBackend
from core.segments import SegmentStatus, SpeechSegment
from core.tts_service import TTSService
from ui.styles import STYLE_SHEET
from ui.waveform import WaveformWidget

_SAMPLE_RATE = 24000


class _MockBackend(TTSBackend):
    """TTSService 的最小后端替身：不写真模型，只记录 generate 调用参数。"""

    def __init__(self) -> None:
        self._spec: ModelSpec | None = None
        self.generate_calls: list[dict] = []

    def load(self, spec: ModelSpec) -> None:
        self._spec = spec

    def unload(self) -> None:
        self._spec = None

    @property
    def is_loaded(self) -> bool:
        return self._spec is not None

    @property
    def current_spec(self) -> ModelSpec | None:
        return self._spec

    def get_supported_speakers(self) -> list[str]:
        return ["Serena", "Ethan"]

    def get_supported_languages(self) -> list[str]:
        return ["Chinese", "English"]

    def get_available_models(self) -> dict[str, ModelSpec]:
        return {
            "mock-1.7b": ModelSpec("Mock 1.7B", "mock/1.7b", True),
            "mock-0.6b": ModelSpec("Mock 0.6B", "mock/0.6b", False),
        }

    def generate(self, text, language, speaker, instruct, output_path) -> Path:
        self.generate_calls.append(
            {
                "text": text,
                "language": language,
                "speaker": speaker,
                "instruct": instruct,
            }
        )
        sf.write(str(output_path), np.zeros(_SAMPLE_RATE // 10, dtype=np.float32), _SAMPLE_RATE)
        return output_path


def _make_service(tmp_dir: Path) -> tuple[TTSService, _MockBackend]:
    backend = _MockBackend()
    return TTSService(backend=backend, output_dir=tmp_dir), backend


def _write_sine_wav(path: Path, seconds: float = 1.0) -> None:
    t = np.linspace(0, seconds, int(_SAMPLE_RATE * seconds), endpoint=False)
    sf.write(str(path), (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), _SAMPLE_RATE)


class TestMainWindowSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE_SHEET)  # 顺带验证 QSS 可被解析

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.service, self.backend = _make_service(Path(self._tmp.name))
        from ui.main_window import MainWindow

        self.window = MainWindow(self.service, default_model_key="mock-1.7b")

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self._tmp.cleanup()

    def test_window_builds(self) -> None:
        self.assertEqual(self.window.char_count_label.text(), "当前已输入 0 字符")
        self.assertEqual(self.window.segment_list.count(), 0)
        self.assertTrue(self.window.status_label.text())

    def test_char_count_updates(self) -> None:
        self.window.text_edit.setPlainText("  你好，世界。  ")
        self.assertEqual(self.window.char_count_label.text(), "当前已输入 6 字符")

    def test_split_creates_cards(self) -> None:
        self.window.text_edit.setPlainText("第一句话。第二句话！第三句话？" * 20)
        self.window._on_split_clicked()
        self.assertTrue(self.window._segments)
        self.assertEqual(self.window.segment_list.count(), len(self.window._segments))
        # 卡片视觉顺序与数据顺序一致，order 从 1 开始连续编号
        ids = self.window.segment_list.visual_segment_ids()
        self.assertEqual(ids, [s.segment_id for s in self.window._segments])
        self.assertEqual([s.order for s in self.window._segments],
                         list(range(1, len(ids) + 1)))

    def test_insert_below_and_delete(self) -> None:
        self.window.text_edit.setPlainText("甲。乙。")
        self.window._on_split_clicked()
        initial_count = len(self.window._segments)
        self.assertGreaterEqual(initial_count, 1)
        first = self.window._segments[0]
        self.window._on_segment_insert_below(first.segment_id)
        self.assertEqual(len(self.window._segments), initial_count + 1)
        self.assertEqual(
            [s.order for s in self.window._segments],
            list(range(1, initial_count + 2)),
        )
        new_segment = self.window._segments[1]
        self.assertEqual(new_segment.text, "")
        self.window._on_segment_delete(new_segment.segment_id)
        self.assertEqual(len(self.window._segments), initial_count)
        self.assertEqual(
            [s.order for s in self.window._segments],
            list(range(1, initial_count + 1)),
        )


class TestWaveformWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wav_path = Path(self._tmp.name) / "sine.wav"
        _write_sine_wav(self.wav_path, seconds=1.0)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_placeholder_then_load(self) -> None:
        widget = WaveformWidget()
        self.assertFalse(widget.has_audio)
        widget.repaint()  # 占位绘制不崩溃
        self.assertTrue(widget.load_wav(self.wav_path))
        self.assertTrue(widget.has_audio)
        self.assertEqual(widget.duration_ms, 1000)
        widget.resize(400, 56)
        widget.repaint()  # 波形绘制不崩溃

    def test_load_invalid_wav_recovers(self) -> None:
        bad = Path(self._tmp.name) / "bad.wav"
        bad.write_bytes(b"not a wav")
        widget = WaveformWidget()
        self.assertFalse(widget.load_wav(bad))
        self.assertFalse(widget.has_audio)
        widget.repaint()

    def test_position_to_ms_mapping(self) -> None:
        widget = WaveformWidget()
        widget.resize(400, 56)
        widget.load_wav(self.wav_path)
        self.assertEqual(widget.position_to_ms(200), 500)  # 中点 -> 一半时长
        self.assertEqual(widget.position_to_ms(0), 0)
        self.assertEqual(widget.position_to_ms(400), 1000)
        self.assertEqual(widget.position_to_ms(9999), 1000)  # 越界裁剪

    def test_click_emits_seek_ms(self) -> None:
        widget = WaveformWidget()
        widget.resize(400, 56)
        widget.load_wav(self.wav_path)
        widget.show()
        received: list[int] = []
        widget.seek_requested.connect(received.append)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(200, 28))
        self.assertEqual(received, [500])
        widget.close()


class TestSegmentOverrides(unittest.TestCase):
    def test_generate_segment_prefers_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, backend = _make_service(Path(tmp))
            spec = backend.get_available_models()["mock-1.7b"]
            service.load_model(spec)
            segment = SpeechSegment(
                segment_id="abc12345",
                order=1,
                text="你好",
                speaker="Ethan",
                instruct="用耳语说",
            )
            service.generate_segment(segment, "Chinese", "Serena", "全局提示")
            call = backend.generate_calls[-1]
            self.assertEqual(call["speaker"], "Ethan")  # 覆盖优先
            self.assertEqual(call["language"], "Chinese")  # None -> 跟随全局
            self.assertEqual(call["instruct"], "用耳语说")

    def test_long_text_no_longer_rejected(self) -> None:
        import core.tts_service as tts_service_module

        self.assertFalse(hasattr(tts_service_module, "MAX_TEXT_LENGTH"))
        with tempfile.TemporaryDirectory() as tmp:
            service, backend = _make_service(Path(tmp))
            spec = backend.get_available_models()["mock-1.7b"]
            service.load_model(spec)
            long_text = "长" * 800  # 超过原 600 字保护限制
            wav = service.generate(long_text, "Chinese", "Serena", "")
            self.assertTrue(wav.exists())
            self.assertEqual(backend.generate_calls[-1]["text"], long_text)


class TestImportSmoke(unittest.TestCase):
    def test_import_main(self) -> None:
        module = importlib.import_module("main")
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
