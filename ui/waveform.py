"""波形显示控件：加载 WAV 后按控件宽度聚合成 min/max 柱列，支持点击/拖动定位。

播放进度由共享 QMediaPlayer 的 positionChanged/durationChanged 驱动（画进度竖线），
seek 请求通过 seek_requested(ms) 信号交给主窗口处理。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    seek_requested = Signal(int)  # 目标播放位置（毫秒）

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(56)
        self._samples: np.ndarray | None = None  # 单声道 float 采样
        self._columns: np.ndarray | None = None  # 按宽度聚合的 (min, max) 柱列缓存
        self._duration_ms = 0
        self._position_ms = 0
        self._dragging = False

    # ---------------- 数据 ----------------

    @property
    def has_audio(self) -> bool:
        return self._samples is not None

    @property
    def duration_ms(self) -> int:
        return self._duration_ms

    def load_wav(self, path: Path) -> bool:
        """读取 WAV 并重建柱列缓存；读取失败返回 False 并恢复占位状态。"""
        try:
            data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        except Exception:
            self.clear()
            return False
        if data.shape[0] == 0 or sample_rate <= 0:
            self.clear()
            return False
        self._samples = data.mean(axis=1)  # 多声道折叠为单声道
        self._duration_ms = round(len(self._samples) / sample_rate * 1000)
        self._position_ms = 0
        self._rebuild_columns()
        self.update()
        return True

    def clear(self) -> None:
        """清空音频，恢复“尚未生成”占位。"""
        self._samples = None
        self._columns = None
        self._duration_ms = 0
        self._position_ms = 0
        self.update()

    def set_position(self, ms: int) -> None:
        """由播放器 positionChanged 驱动，移动进度竖线。"""
        self._position_ms = max(0, ms)
        self.update()

    def set_duration(self, ms: int) -> None:
        """由播放器 durationChanged 驱动（加载文件时已按采样率给出初始值）。"""
        if ms > 0:
            self._duration_ms = ms
            self.update()

    # ---------------- 绘制 ----------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if not self.has_audio or self._columns is None or len(self._columns) == 0:
            # 未加载音频：灰色占位条 + 提示
            painter.fillRect(rect, QColor("#eceef3"))
            painter.setPen(QColor("#9aa0ab"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "尚未生成")
            painter.end()
            return
        painter.fillRect(rect, QColor("#f3f6fc"))
        mid = rect.height() / 2.0
        amp = rect.height() / 2.0 - 2
        n = len(self._columns)
        col_w = rect.width() / n
        painter.setPen(QPen(QColor("#4a7dff"), 1))
        for i in range(n):
            x = rect.left() + i * col_w
            ymin, ymax = self._columns[i]
            painter.drawLine(
                QPointF(x, mid - float(ymax) * amp),
                QPointF(x, mid - float(ymin) * amp),
            )
        if self._duration_ms > 0 and self._position_ms > 0:
            ratio = min(self._position_ms / self._duration_ms, 1.0)
            x = rect.left() + rect.width() * ratio
            painter.setPen(QPen(QColor("#d64545"), 2))
            painter.drawLine(QPointF(x, 0), QPointF(x, rect.height()))
        painter.end()

    # ---------------- 交互 ----------------

    def position_to_ms(self, x: float) -> int:
        """把控件内 x 坐标换算为毫秒位置（越界裁剪到 [0, duration]）。"""
        width = max(self.width(), 1)
        ratio = min(max(x / width, 0.0), 1.0)
        return round(ratio * self._duration_ms)

    def _emit_seek(self, x: float) -> None:
        if self.has_audio and self._duration_ms > 0:
            self.seek_requested.emit(self.position_to_ms(x))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._emit_seek(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._emit_seek(event.position().x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    # ---------------- 内部 ----------------

    def resizeEvent(self, event) -> None:
        self._rebuild_columns()
        super().resizeEvent(event)

    def _rebuild_columns(self) -> None:
        """按当前控件宽度把采样聚合成每列 (min, max) 缓存。"""
        if self._samples is None:
            self._columns = None
            return
        n = max(self.width(), 1)
        samples = self._samples
        columns = np.zeros((n, 2), dtype=np.float32)
        edges = np.linspace(0, len(samples), n + 1).astype(int)
        for i in range(n):
            start, end = edges[i], edges[i + 1]
            end = min(max(end, start + 1), len(samples))  # 每列至少取一个采样点
            chunk = samples[start:end]
            columns[i] = (chunk.min(), chunk.max())
        self._columns = columns
