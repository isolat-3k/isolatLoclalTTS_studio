"""主窗口：只依赖 TTSService 与 core.worker，不直接调用 qwen_tts / torch。"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.tts_service import MAX_TEXT_LENGTH, TTSService
from core.worker import GenerateWorker, LoadModelWorker


class MainWindow(QMainWindow):
    def __init__(self, service: TTSService, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._worker = None  # 当前正在运行的后台线程（LoadModelWorker / GenerateWorker）
        self._current_wav: Path | None = None

        self.setWindowTitle("Qwen3-TTS 本地测试面板")
        self.resize(640, 520)

        self._build_ui()
        self._setup_player()
        self._refresh_choices()
        self._set_status("模型未加载，请先点击“加载模型”。")

    # ---------------- UI 搭建 ----------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            f"请输入要配音的文本（当前工具限制 {MAX_TEXT_LENGTH} 字符以内）"
        )
        root.addWidget(QLabel("配音文本"))
        root.addWidget(self.text_edit)

        form = QFormLayout()
        self.language_combo = QComboBox()
        self.speaker_combo = QComboBox()
        self.instruct_edit = QLineEdit()
        self.instruct_edit.setPlaceholderText("可选，例如：用特别愤怒的语气说")
        form.addRow("语言", self.language_combo)
        form.addRow("音色", self.speaker_combo)
        form.addRow("风格指令", self.instruct_edit)
        root.addLayout(form)

        buttons = QHBoxLayout()
        self.load_button = QPushButton("加载模型")
        self.load_button.clicked.connect(self._on_load_clicked)
        self.generate_button = QPushButton("生成")
        self.generate_button.setEnabled(False)  # 模型加载后才可用
        self.generate_button.clicked.connect(self._on_generate_clicked)
        buttons.addWidget(self.load_button)
        buttons.addWidget(self.generate_button)
        root.addLayout(buttons)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        player_row = QHBoxLayout()
        self.play_button = QPushButton("播放")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self._on_play_clicked)
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.save_button = QPushButton("另存为 WAV")
        self.save_button.setEnabled(False)  # 有生成结果后才可用
        self.save_button.clicked.connect(self._on_save_clicked)
        player_row.addWidget(self.play_button)
        player_row.addWidget(self.stop_button)
        player_row.addStretch(1)
        player_row.addWidget(self.save_button)
        root.addLayout(player_row)

        self.setCentralWidget(central)

    def _setup_player(self) -> None:
        """初始化 QMediaPlayer；缺少系统媒体后端时只禁用播放，不影响生成与保存。"""
        try:
            self._audio_output = QAudioOutput(self)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._audio_output)
            self._player.errorOccurred.connect(self._on_player_error)
        except Exception as exc:  # pragma: no cover - 取决于系统媒体后端
            self._player = None
            self._audio_output = None
            self.play_button.setToolTip(f"音频播放不可用：{exc}")
            self.stop_button.setToolTip(f"音频播放不可用：{exc}")

    # ---------------- 状态与控件 ----------------

    def _set_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{text}")

    def _refresh_choices(self) -> None:
        """语言/音色列表始终以后端返回为准，UI 不维护副本。"""
        current_lang = self.language_combo.currentText()
        current_speaker = self.speaker_combo.currentText()

        self.language_combo.clear()
        self.language_combo.addItems(self._service.get_languages())
        self.speaker_combo.clear()
        self.speaker_combo.addItems(self._service.get_speakers())

        for combo, previous in (
            (self.language_combo, current_lang),
            (self.speaker_combo, current_speaker),
        ):
            index = combo.findText(previous)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _set_busy(self, busy: bool) -> None:
        self.load_button.setEnabled(not busy)
        self.generate_button.setEnabled(not busy and self._service.is_model_loaded)

    def _is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ---------------- 加载模型 ----------------

    def _on_load_clicked(self) -> None:
        if self._is_busy():
            return
        if self._service.is_model_loaded:
            self._set_status("模型已加载，无需重复加载。")
            return
        self._set_busy(True)
        worker = LoadModelWorker(self._service, self)
        worker.status_changed.connect(self._set_status)
        worker.succeeded.connect(self._on_load_succeeded)
        worker.failed.connect(self._on_load_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_load_succeeded(self) -> None:
        self._refresh_choices()  # 以模型实际支持的列表为准
        self._set_status("模型加载完成，可以生成。")

    def _on_load_failed(self, message: str) -> None:
        self._set_status(f"模型加载失败：{message}（详情见终端）")

    # ---------------- 生成 ----------------

    def _on_generate_clicked(self) -> None:
        if self._is_busy():
            return
        text = self.text_edit.toPlainText().strip()
        if not text:
            self._set_status("请先输入配音文本。")
            return
        if len(text) > MAX_TEXT_LENGTH:
            self._set_status(
                f"文本长度 {len(text)} 超过当前工具限制 {MAX_TEXT_LENGTH} 字符"
                "（临时保护限制，不代表模型上限）。"
            )
            return
        self._set_busy(True)
        worker = GenerateWorker(
            self._service,
            text=text,
            language=self.language_combo.currentText(),
            speaker=self.speaker_combo.currentText(),
            instruct=self.instruct_edit.text().strip(),
            parent=self,
        )
        worker.status_changed.connect(self._set_status)
        worker.succeeded.connect(self._on_generate_succeeded)
        worker.failed.connect(self._on_generate_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_generate_succeeded(self, wav_path: Path) -> None:
        self._current_wav = Path(wav_path)
        self._set_status(f"生成成功：{self._current_wav.name}")
        self.save_button.setEnabled(True)
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(str(self._current_wav)))
            self.play_button.setEnabled(True)
            self.stop_button.setEnabled(True)

    def _on_generate_failed(self, message: str) -> None:
        self._set_status(f"生成失败：{message}（详情见终端）")

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()

    # ---------------- 播放与保存 ----------------

    def _on_play_clicked(self) -> None:
        if self._player is None or self._current_wav is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.play_button.setText("播放")
        else:
            self._player.play()
            self.play_button.setText("暂停")

    def _on_stop_clicked(self) -> None:
        if self._player is None:
            return
        self._player.stop()
        self.play_button.setText("播放")

    def _on_player_error(self) -> None:
        if self._player is None:
            return
        self._set_status(
            f"音频播放不可用（{self._player.errorString()}）。"
            "生成与另存为 WAV 不受影响。"
        )

    def _on_save_clicked(self) -> None:
        if self._current_wav is None or not self._current_wav.exists():
            self._set_status("当前没有可保存的生成结果。")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "另存为 WAV",
            self._current_wav.name,
            "WAV 音频 (*.wav)",
        )
        if not target:
            return
        try:
            shutil.copyfile(self._current_wav, target)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"复制文件失败：{exc}")
            return
        self._set_status(f"已保存到：{target}")
