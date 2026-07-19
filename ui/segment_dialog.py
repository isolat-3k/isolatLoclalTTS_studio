"""片段详情编辑弹窗：编辑片段文本与每段覆盖设置（角色/语言/风格提示词）。

覆盖项选择“跟随默认”（或提示词留空）即写回 None，生成时跟随全局默认设置。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from core.segments import SegmentStatus, SpeechSegment

FOLLOW_DEFAULT = "跟随默认"


class SegmentEditDialog(QDialog):
    def __init__(
        self,
        segment: SpeechSegment,
        speakers: list[str],
        languages: list[str],
        supports_instruct: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._segment = segment
        self.saved = False  # 是否点击了保存（取消则为 False）
        self.generate_after_save = False  # 是否“保存并生成此段”

        self.setWindowTitle(f"片段 {segment.order} 详情")
        self.resize(520, 460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("片段文本"))
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(segment.text)
        layout.addWidget(self.text_edit, 1)

        form = QFormLayout()
        self.speaker_combo = QComboBox()
        self.speaker_combo.addItem(FOLLOW_DEFAULT)
        self.speaker_combo.addItems(speakers)
        self._restore_combo(self.speaker_combo, segment.speaker)
        self.language_combo = QComboBox()
        self.language_combo.addItem(FOLLOW_DEFAULT)
        self.language_combo.addItems(languages)
        self._restore_combo(self.language_combo, segment.language)
        self.instruct_edit = QLineEdit()
        self.instruct_edit.setText(segment.instruct or "")
        if supports_instruct:
            self.instruct_edit.setPlaceholderText("留空则跟随默认设置")
        else:
            # 当前模型不支持 instruct：禁用并提示
            self.instruct_edit.setEnabled(False)
            self.instruct_edit.setPlaceholderText("当前模型不支持风格指令，此项不可用。")
            self.instruct_edit.setToolTip("当前模型不支持风格指令，此项不可用。")
        form.addRow("角色（音色）", self.speaker_combo)
        form.addRow("语言", self.language_combo)
        form.addRow("风格提示词", self.instruct_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        save_button = QPushButton("保存")
        save_button.setObjectName("primaryButton")
        save_generate_button = QPushButton("保存并生成此段")
        cancel_button = QPushButton("取消")
        save_button.clicked.connect(self._on_save)
        save_generate_button.clicked.connect(self._on_save_and_generate)
        cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        buttons.addWidget(save_generate_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    # ---------------- 保存 ----------------

    @staticmethod
    def _restore_combo(combo: QComboBox, value: str | None) -> None:
        if value:
            index = combo.findText(value)
            if index >= 0:
                combo.setCurrentIndex(index)

    @staticmethod
    def _combo_value(combo: QComboBox) -> str | None:
        text = combo.currentText()
        return None if text == FOLLOW_DEFAULT else text

    def _apply(self) -> None:
        """把编辑结果写回片段。文本改动后状态置回未生成（原 WAV 保留在磁盘）。"""
        segment = self._segment
        new_text = self.text_edit.toPlainText()
        if new_text != segment.text:
            segment.text = new_text
            if segment.status in (SegmentStatus.READY, SegmentStatus.ERROR):
                segment.status = SegmentStatus.NOT_GENERATED
                segment.audio_path = None
                segment.error_message = None
        segment.speaker = self._combo_value(self.speaker_combo)
        segment.language = self._combo_value(self.language_combo)
        instruct = self.instruct_edit.text().strip()
        segment.instruct = instruct or None

    def _on_save(self) -> None:
        self._apply()
        self.saved = True
        self.accept()

    def _on_save_and_generate(self) -> None:
        self._apply()
        self.saved = True
        self.generate_after_save = True
        self.accept()
