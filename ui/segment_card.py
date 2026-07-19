"""分段卡片：圆角卡片展示单个片段的序号、状态徽章、文本预览、波形与操作按钮。

卡片不直接操作业务逻辑，全部通过信号（带 segment_id）交给主窗口处理。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.segments import SegmentStatus, SpeechSegment

from .waveform import WaveformWidget

# 状态 -> (徽章文字, 样式 objectName)，配色见 ui/styles.py
_STATUS_BADGE = {
    SegmentStatus.NOT_GENERATED: ("未生成", "badgeNotGenerated"),
    SegmentStatus.QUEUED: ("排队中", "badgeQueued"),
    SegmentStatus.GENERATING: ("生成中", "badgeGenerating"),
    SegmentStatus.READY: ("已生成", "badgeReady"),
    SegmentStatus.ERROR: ("失败", "badgeError"),
}


class SegmentCardWidget(QFrame):
    generate_requested = Signal(str)  # segment_id
    play_pause_requested = Signal(str)  # segment_id
    details_requested = Signal(str)  # segment_id
    insert_below_requested = Signal(str)  # segment_id
    delete_requested = Signal(str)  # segment_id
    seek_requested = Signal(str, int)  # segment_id, 毫秒

    def __init__(self, segment: SpeechSegment, parent=None) -> None:
        super().__init__(parent)
        self._segment_id = segment.segment_id
        self._loaded_audio: Path | None = None  # 波形已加载的音频路径
        self.setObjectName("segmentCard")
        self.setProperty("playing", False)
        self._build_ui()
        self.update_from_segment(segment)

    @property
    def segment_id(self) -> str:
        return self._segment_id

    # ---------------- UI 搭建 ----------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.order_label = QLabel()
        self.order_label.setObjectName("cardOrderLabel")
        self.badge_label = QLabel()
        header.addWidget(self.order_label)
        header.addStretch(1)
        header.addWidget(self.badge_label)
        layout.addLayout(header)

        self.preview_label = QLabel()
        self.preview_label.setObjectName("cardPreviewLabel")
        self.preview_label.setWordWrap(True)
        # 文本预览只读、最多 3 行
        line_h = self.preview_label.fontMetrics().lineSpacing()
        self.preview_label.setFixedHeight(line_h * 3 + 8)
        layout.addWidget(self.preview_label)

        info_row = QHBoxLayout()
        self.char_label = QLabel()
        self.char_label.setObjectName("cardInfoLabel")
        self.override_label = QLabel()
        self.override_label.setObjectName("cardOverrideLabel")
        info_row.addWidget(self.char_label)
        info_row.addStretch(1)
        info_row.addWidget(self.override_label)
        layout.addLayout(info_row)

        self.waveform = WaveformWidget(self)
        self.waveform.seek_requested.connect(
            lambda ms: self.seek_requested.emit(self._segment_id, ms)
        )
        layout.addWidget(self.waveform)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.gen_button = QPushButton("生成")
        self.play_button = QPushButton("播放")
        self.details_button = QPushButton("详情")
        self.insert_button = QPushButton("在下方插入")
        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("dangerButton")
        sid = self._segment_id
        self.gen_button.clicked.connect(lambda _=False: self.generate_requested.emit(sid))
        self.play_button.clicked.connect(
            lambda _=False: self.play_pause_requested.emit(sid)
        )
        self.details_button.clicked.connect(
            lambda _=False: self.details_requested.emit(sid)
        )
        self.insert_button.clicked.connect(
            lambda _=False: self.insert_below_requested.emit(sid)
        )
        self.delete_button.clicked.connect(
            lambda _=False: self.delete_requested.emit(sid)
        )
        buttons.addWidget(self.gen_button)
        buttons.addWidget(self.play_button)
        buttons.addStretch(1)
        buttons.addWidget(self.details_button)
        buttons.addWidget(self.insert_button)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)

    # ---------------- 状态刷新 ----------------

    def update_from_segment(self, segment: SpeechSegment) -> None:
        """按片段数据刷新卡片全部内容。"""
        self.order_label.setText(f"片段 {segment.order}")

        text, badge_name = _STATUS_BADGE[segment.status]
        self.badge_label.setText(text)
        if self.badge_label.objectName() != badge_name:
            self.badge_label.setObjectName(badge_name)
            self._repolish(self.badge_label)
        self.badge_label.setToolTip(segment.error_message or "")

        preview = segment.text.strip() or "（空文本，点“详情”编辑）"
        self.preview_label.setText(preview)
        self.char_label.setText(f"{len(segment.text.strip())} 字")

        # 每段覆盖设置的小标签（如“角色: Serena”）
        tags = []
        if segment.speaker:
            tags.append(f"角色: {segment.speaker}")
        if segment.language:
            tags.append(f"语言: {segment.language}")
        if segment.instruct:
            tags.append(f"风格: {segment.instruct}")
        self.override_label.setText("　".join(tags))
        self.override_label.setVisible(bool(tags))

        self.gen_button.setText(
            "重新生成" if segment.status == SegmentStatus.READY else "生成"
        )
        has_audio = segment.audio_path is not None and segment.audio_path.exists()
        self.play_button.setEnabled(has_audio)

        # 音频路径变化时重载波形；无音频则恢复占位
        if segment.audio_path != self._loaded_audio:
            self._loaded_audio = segment.audio_path
            if has_audio:
                self.waveform.load_wav(segment.audio_path)
            else:
                self.waveform.clear()

    def set_playing(self, playing: bool, paused: bool = False) -> None:
        """播放中高亮卡片并把按钮切换为“暂停”。"""
        if self.property("playing") != playing:
            self.setProperty("playing", playing)
            self._repolish(self)
        self.play_button.setText("暂停" if playing and not paused else "播放")

    def set_waveform_position(self, ms: int) -> None:
        self.waveform.set_position(ms)

    def set_waveform_duration(self, ms: int) -> None:
        self.waveform.set_duration(ms)

    @staticmethod
    def _repolish(widget) -> None:
        """objectName / 动态属性变化后重新应用样式表。"""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
