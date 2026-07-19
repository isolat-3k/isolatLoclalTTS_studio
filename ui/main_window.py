"""主窗口：双栏工作台布局，只依赖 TTSService 与 core.worker，不直接调用 qwen_tts / torch。

左侧为文本输入 + 默认配音设置 + 操作按钮；右侧为可拖拽排序的分段卡片列表。
播放统一走一个共享 QMediaPlayer：正在播放的卡片高亮，切换卡片自动停止上一段。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.segments import SegmentStatus, SpeechSegment, create_segments
from core.text_splitter import DEFAULT_MAX_CHARS, split_long_text
from core.tts_service import TTSService
from core.worker import (
    BatchGenerateWorker,
    GenerateSegmentWorker,
    GenerateWorker,
    LoadModelWorker,
)

from .segment_card import SegmentCardWidget
from .segment_dialog import SegmentEditDialog
from .segment_list import SegmentListWidget

_INSTRUCT_PLACEHOLDER = "可选，例如：用特别愤怒的语气说"


class MainWindow(QMainWindow):
    def __init__(
        self,
        service: TTSService,
        default_model_key: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._default_model_key = default_model_key
        # 当前正在运行的后台线程（加载/单段/分段/批量共用同一个槽位，保证串行）
        self._worker = None
        self._current_wav: Path | None = None  # 单段生成结果（“另存为 WAV”的来源）
        self._segments: list[SpeechSegment] = []
        self._cards: dict[str, SegmentCardWidget] = {}  # segment_id -> 卡片
        self._card_items: dict[str, QListWidgetItem] = {}  # segment_id -> 列表项
        self._playing_segment_id: str | None = None  # 当前占用共享播放器的片段
        self._updating_choices = False  # 刷新下拉列表期间不触发“设置已更改”提示

        self.setWindowTitle("Qwen3-TTS 本地测试面板")
        self.resize(1080, 760)

        self._build_ui()
        self._setup_player()
        self._populate_model_combo()
        self._refresh_choices()
        self._update_model_state()
        self._update_instruct_state()
        self._update_action_states()
        self._on_text_changed()
        self._set_status("模型未加载，请先点击“加载模型”。")

    # ---------------- UI 搭建 ----------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

        # 顶栏：模型下拉 | 加载模型 | 模型状态 | 状态消息
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("模型"))
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(
            self._on_model_selection_changed
        )
        top_bar.addWidget(self.model_combo, 1)
        self.load_button = QPushButton("加载模型")
        self.load_button.setObjectName("primaryButton")
        self.load_button.clicked.connect(self._on_load_clicked)
        top_bar.addWidget(self.load_button)
        self.model_state_label = QLabel()
        top_bar.addWidget(self.model_state_label)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        top_bar.addWidget(self.status_label, 2)
        root.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 640])  # 左侧初始约 400px
        root.addWidget(splitter, 1)

        self.setCentralWidget(central)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(320)
        layout = QVBoxLayout(panel)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "请输入要配音的文本。点击下方“拆分为片段”可按约 150 字自动分段生成。"
        )
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit, 1)

        self.char_count_label = QLabel()
        self.char_count_label.setObjectName("charCountLabel")
        layout.addWidget(self.char_count_label)

        # 全局默认配音设置；卡片详情弹窗里的设置是对该段的覆盖
        settings_group = QGroupBox("默认配音设置")
        form = QFormLayout(settings_group)
        self.language_combo = QComboBox()
        self.speaker_combo = QComboBox()
        self.instruct_edit = QLineEdit()
        form.addRow("语言", self.language_combo)
        form.addRow("音色", self.speaker_combo)
        form.addRow("风格指令", self.instruct_edit)
        layout.addWidget(settings_group)
        self.language_combo.currentTextChanged.connect(self._on_settings_changed)
        self.speaker_combo.currentTextChanged.connect(self._on_settings_changed)
        self.instruct_edit.textChanged.connect(self._on_settings_changed)

        self.split_button = QPushButton("拆分为片段")
        self.split_button.clicked.connect(self._on_split_clicked)
        layout.addWidget(self.split_button)

        batch_row = QHBoxLayout()
        self.batch_button = QPushButton("生成全部")
        self.batch_button.setObjectName("primaryButton")
        self.batch_button.clicked.connect(self._on_batch_clicked)
        self.batch_stop_button = QPushButton("停止")
        self.batch_stop_button.clicked.connect(self._on_batch_stop_clicked)
        batch_row.addWidget(self.batch_button, 1)
        batch_row.addWidget(self.batch_stop_button)
        layout.addLayout(batch_row)

        single_row = QHBoxLayout()
        self.generate_button = QPushButton("单段试听")
        self.generate_button.clicked.connect(self._on_generate_clicked)
        self.save_button = QPushButton("另存WAV")
        self.save_button.setEnabled(False)  # 有单段生成结果后才可用
        self.save_button.clicked.connect(self._on_save_clicked)
        single_row.addWidget(self.generate_button, 1)
        single_row.addWidget(self.save_button)
        layout.addLayout(single_row)

        return panel

    def _build_right_panel(self) -> QWidget:
        self.segment_list = SegmentListWidget()
        self.segment_list.order_changed.connect(self._on_order_changed)
        return self.segment_list

    def _setup_player(self) -> None:
        """初始化共享 QMediaPlayer；缺少系统媒体后端时只禁用播放，不影响生成。"""
        try:
            self._audio_output = QAudioOutput(self)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._audio_output)
            self._player.errorOccurred.connect(self._on_player_error)
            self._player.positionChanged.connect(self._on_player_position)
            self._player.durationChanged.connect(self._on_player_duration)
            self._player.playbackStateChanged.connect(
                lambda _state: self._refresh_playing_cards()
            )
            self._player.mediaStatusChanged.connect(self._on_media_status)
        except Exception as exc:  # pragma: no cover - 取决于系统媒体后端
            self._player = None
            self._audio_output = None

    # ---------------- 状态与控件 ----------------

    def _set_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{text}")

    def _is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _is_batch_running(self) -> bool:
        return isinstance(self._worker, BatchGenerateWorker) and self._worker.isRunning()

    def _selected_spec(self):
        key = self.model_combo.currentData()
        return self._service.get_model_specs().get(key)

    def _populate_model_combo(self) -> None:
        specs = self._service.get_model_specs()
        for key, spec in specs.items():
            self.model_combo.addItem(spec.display_name, userData=key)
        index = self.model_combo.findData(self._default_model_key)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

    def _update_model_state(self) -> None:
        """明确区分“已选择模型”和“已加载模型”。"""
        selected = self._selected_spec()
        loaded = self._service.loaded_spec
        lines = [
            f"已选择：{selected.display_name if selected else '无'}",
            f"已加载：{loaded.display_name if loaded else '无'}",
        ]
        if loaded is not None and loaded != selected:
            lines.append("请重新加载模型")
        self.model_state_label.setText("\n".join(lines))

    def _update_instruct_state(self) -> None:
        """按所选模型的 ModelSpec 启停 instruct，不改动已有内容。"""
        spec = self._selected_spec()
        if spec is not None and not spec.supports_instruct:
            self.instruct_edit.setEnabled(False)
            self.instruct_edit.setPlaceholderText(
                f"当前 {spec.display_name} 后端不支持风格指令。"
            )
            self.instruct_edit.setToolTip(
                f"当前 {spec.display_name} 后端不支持风格指令。"
            )
        else:
            self.instruct_edit.setEnabled(True)
            self.instruct_edit.setPlaceholderText(_INSTRUCT_PLACEHOLDER)
            self.instruct_edit.setToolTip("")

    def _update_action_states(self) -> None:
        busy = self._is_busy()
        loaded = self._service.is_model_loaded
        matched = loaded and self._service.loaded_spec == self._selected_spec()
        self.model_combo.setEnabled(not busy)  # 生成/加载期间禁止切换模型
        self.load_button.setEnabled(not busy)
        self.generate_button.setEnabled(not busy and matched)
        self.split_button.setEnabled(not busy)
        self.batch_button.setEnabled(not busy and matched and bool(self._segments))
        self.batch_stop_button.setEnabled(self._is_batch_running())
        self.text_edit.setEnabled(not busy)
        self.language_combo.setEnabled(not busy)
        self.speaker_combo.setEnabled(not busy)
        if busy:
            self.instruct_edit.setEnabled(False)
        else:
            self._update_instruct_state()
        self.segment_list.setEnabled(not busy)
        self.save_button.setEnabled(
            not busy and self._current_wav is not None and self._current_wav.exists()
        )

    def _refresh_choices(self) -> None:
        """语言/音色列表始终以后端返回为准；尽量保留原选择，不支持则回退默认。"""
        self._updating_choices = True
        try:
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
        finally:
            self._updating_choices = False

    def _on_model_selection_changed(self) -> None:
        self._update_model_state()
        self._update_instruct_state()
        self._update_action_states()
        self._on_settings_changed()

    def _on_settings_changed(self) -> None:
        """全局设置变化：不自动重新生成，已生成音频保留，仅提示。"""
        if self._updating_choices:
            return
        if any(s.status == SegmentStatus.READY for s in self._segments):
            self._set_status(
                "设置已更改：已有音频由之前的设置生成；"
                "未生成与重新生成的片段将使用新设置。"
            )

    def _on_text_changed(self) -> None:
        """实时字符计数（按 strip 后长度统计）。"""
        count = len(self.text_edit.toPlainText().strip())
        self.char_count_label.setText(f"当前已输入 {count} 字符")

    # ---------------- 加载模型 ----------------

    def _on_load_clicked(self) -> None:
        if self._is_busy():
            return
        spec = self._selected_spec()
        if spec is None:
            return
        if self._service.loaded_spec == spec:
            self._set_status("模型已加载，无需重复加载。")
            return
        worker = LoadModelWorker(self._service, spec, self)
        worker.status_changed.connect(self._set_status)
        worker.succeeded.connect(self._on_load_succeeded)
        worker.failed.connect(self._on_load_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._update_action_states()
        worker.start()

    def _on_load_succeeded(self) -> None:
        self._refresh_choices()  # 以模型实际支持的列表为准
        self._update_model_state()
        loaded = self._service.loaded_spec
        self._set_status(
            f"模型加载完成：{loaded.display_name if loaded else ''}，可以生成。"
        )

    def _on_load_failed(self, message: str) -> None:
        self._set_status(f"模型加载失败：{message}（详情见终端）")

    # ---------------- 单段生成（试听整段输入文本） ----------------

    def _on_generate_clicked(self) -> None:
        if self._is_busy():
            return
        text = self.text_edit.toPlainText().strip()
        if not text:
            self._set_status("请先输入配音文本。")
            return
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
        self._update_action_states()
        worker.start()

    def _on_generate_succeeded(self, wav_path: Path) -> None:
        self._current_wav = Path(wav_path)
        self._set_status(f"生成成功：{self._current_wav.name}")
        self._update_action_states()
        # 单段试听：生成完直接用共享播放器播放
        if self._player is not None:
            self._stop_playback()
            self._player.setSource(QUrl.fromLocalFile(str(self._current_wav)))
            self._player.play()

    def _on_generate_failed(self, message: str) -> None:
        self._set_status(f"生成失败：{message}（详情见终端）")

    # ---------------- 长文本拆分 ----------------

    def _on_split_clicked(self) -> None:
        if self._is_busy():
            return
        text = self.text_edit.toPlainText().strip()
        if not text:
            self._set_status("空文本不拆分，请先输入文本。")
            return
        if self._segments:
            answer = QMessageBox.question(
                self,
                "重新拆分",
                "已有片段列表。重新拆分将替换当前列表"
                "（已有 WAV 文件保留在 outputs/ 中，不会删除）。是否继续？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        texts = split_long_text(text, DEFAULT_MAX_CHARS)
        if not texts:
            self._set_status("空文本不拆分。")
            return
        self._stop_playback()
        self._segments = create_segments(texts)
        self._rebuild_segment_cards()
        self._update_action_states()
        self._set_status(f"已拆分为 {len(self._segments)} 个片段。")

    # ---------------- 分段卡片列表 ----------------

    def _make_card(self, segment: SpeechSegment) -> SegmentCardWidget:
        card = SegmentCardWidget(segment)
        card.generate_requested.connect(self._on_segment_generate)
        card.play_pause_requested.connect(self._on_segment_play_pause)
        card.details_requested.connect(self._on_segment_details)
        card.insert_below_requested.connect(self._on_segment_insert_below)
        card.delete_requested.connect(self._on_segment_delete)
        card.seek_requested.connect(self._on_card_seek)
        return card

    def _rebuild_segment_cards(self) -> None:
        self.segment_list.clear()
        self._cards.clear()
        self._card_items.clear()
        for segment in self._segments:
            card = self._make_card(segment)
            self._cards[segment.segment_id] = card
            self._card_items[segment.segment_id] = self.segment_list.add_card(
                segment.segment_id, card
            )

    def _update_card(self, segment: SpeechSegment) -> None:
        card = self._cards.get(segment.segment_id)
        if card is None:
            return
        card.update_from_segment(segment)
        item = self._card_items.get(segment.segment_id)
        if item is not None:
            item.setSizeHint(card.sizeHint())

    def _find_segment(self, segment_id: str) -> SpeechSegment | None:
        for segment in self._segments:
            if segment.segment_id == segment_id:
                return segment
        return None

    def _renumber_segments(self) -> None:
        """按 self._segments 当前顺序重编号 order 并刷新卡片。"""
        for index, segment in enumerate(self._segments):
            segment.order = index + 1
            self._update_card(segment)

    def _on_order_changed(self) -> None:
        """拖拽结束：按视觉顺序重排 self._segments 并重编号 order。"""
        ids = self.segment_list.visual_segment_ids()
        by_id = {s.segment_id: s for s in self._segments}
        if sorted(ids) != sorted(by_id):
            return
        self._segments = [by_id[sid] for sid in ids]
        # 同步卡片映射；个别部件在拖拽中丢失时兜底整体重建
        cards: dict[str, SegmentCardWidget] = {}
        items: dict[str, QListWidgetItem] = {}
        for i in range(self.segment_list.count()):
            item = self.segment_list.item(i)
            card = self.segment_list.itemWidget(item)
            sid = item.data(Qt.ItemDataRole.UserRole)
            if card is None or sid not in by_id:
                self._renumber_segments()
                self._rebuild_segment_cards()
                self._set_status("片段顺序已调整。")
                return
            cards[sid] = card
            items[sid] = item
        self._cards = cards
        self._card_items = items
        self._renumber_segments()
        self._set_status("片段顺序已调整。")

    # ---------------- 片段操作 ----------------

    def _current_settings(self) -> tuple[str, str, str]:
        return (
            self.language_combo.currentText(),
            self.speaker_combo.currentText(),
            self.instruct_edit.text().strip(),
        )

    def _on_segment_generate(self, segment_id: str) -> None:
        if self._is_busy():
            return
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        if not segment.text.strip():
            self._set_status(f"片段 {segment.order} 文本为空，未生成。")
            return
        language, speaker, instruct = self._current_settings()
        worker = GenerateSegmentWorker(
            self._service, segment, language, speaker, instruct, self
        )
        worker.status_changed.connect(self._set_status)
        worker.succeeded.connect(self._on_segment_succeeded)
        worker.failed.connect(self._on_segment_failed)
        worker.finished.connect(self._on_worker_finished)
        segment.status = SegmentStatus.GENERATING
        segment.error_message = None
        self._update_card(segment)
        self._worker = worker
        self._update_action_states()
        worker.start()

    def _on_segment_succeeded(self, segment_id: str, wav_path: Path) -> None:
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        segment.audio_path = Path(wav_path)  # 成功后替换音频文件
        segment.status = SegmentStatus.READY
        segment.error_message = None
        self._update_card(segment)
        self._set_status(f"片段 {segment.order} 生成成功：{segment.audio_path.name}")

    def _on_segment_failed(self, segment_id: str, message: str) -> None:
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        segment.status = SegmentStatus.ERROR
        segment.error_message = message
        self._update_card(segment)
        self._set_status(f"片段 {segment.order} 生成失败：{message}（详情见终端）")

    def _on_segment_details(self, segment_id: str) -> None:
        if self._is_busy():
            return
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        spec = self._selected_spec()
        dialog = SegmentEditDialog(
            segment,
            speakers=self._service.get_speakers(),
            languages=self._service.get_languages(),
            supports_instruct=bool(spec and spec.supports_instruct),
            parent=self,
        )
        dialog.exec()
        if not dialog.saved:
            return
        self._update_card(segment)
        if dialog.generate_after_save:
            self._on_segment_generate(segment_id)

    def _on_segment_insert_below(self, segment_id: str) -> None:
        if self._is_busy():
            return
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        new_segment = create_segments([""])[0]
        self._segments.insert(self._segments.index(segment) + 1, new_segment)
        self._rebuild_segment_cards()
        self._renumber_segments()
        self._update_action_states()
        self._set_status(
            f"已在片段 {segment.order} 下方插入新片段，点“详情”编辑其文本。"
        )

    def _on_segment_delete(self, segment_id: str) -> None:
        segment = self._find_segment(segment_id)
        if segment is None or self._is_busy():
            return
        if self._playing_segment_id == segment_id:
            self._stop_playback()
        self._segments.remove(segment)
        self._rebuild_segment_cards()
        self._renumber_segments()
        self._update_action_states()
        self._set_status(
            f"已删除片段 {segment.order}（其 WAV 文件保留在 outputs/ 中）。"
        )

    # ---------------- 批量生成 ----------------

    def _on_batch_clicked(self) -> None:
        if self._is_busy():
            return
        pending = [
            s
            for s in self._segments
            if s.status in (SegmentStatus.NOT_GENERATED, SegmentStatus.ERROR)
        ]
        if not pending:
            self._set_status("没有待生成的片段。")
            return
        language, speaker, instruct = self._current_settings()
        worker = BatchGenerateWorker(
            self._service, self._segments, language, speaker, instruct, self
        )
        worker.status_changed.connect(self._set_status)
        worker.segment_started.connect(self._on_batch_segment_started)
        worker.segment_succeeded.connect(self._on_segment_succeeded)
        worker.segment_failed.connect(self._on_segment_failed)
        worker.finished_with_summary.connect(self._on_batch_summary)
        worker.finished.connect(self._on_worker_finished)
        for segment in pending:
            segment.status = SegmentStatus.QUEUED
            self._update_card(segment)
        self._worker = worker
        self._update_action_states()
        worker.start()

    def _on_batch_segment_started(self, segment_id: str) -> None:
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        segment.status = SegmentStatus.GENERATING
        segment.error_message = None
        self._update_card(segment)

    def _on_batch_summary(self, ok_count: int, fail_count: int) -> None:
        self._set_status(f"批量生成完成：成功 {ok_count} 个，失败 {fail_count} 个。")

    def _on_batch_stop_clicked(self) -> None:
        if self._is_batch_running():
            self._worker.request_stop()
            self.batch_stop_button.setEnabled(False)
            self._set_status("已请求停止：当前片段完成后停止，已完成结果保留。")

    # ---------------- 播放 ----------------

    def _activate_player_source(self, segment: SpeechSegment) -> None:
        """共享播放器切换到指定片段的音频；切换卡片自动停止上一段。"""
        previous = self._cards.get(self._playing_segment_id or "")
        if previous is not None and self._playing_segment_id != segment.segment_id:
            previous.set_waveform_position(0)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(segment.audio_path)))
        self._playing_segment_id = segment.segment_id

    def _on_segment_play_pause(self, segment_id: str) -> None:
        segment = self._find_segment(segment_id)
        if (
            segment is None
            or segment.audio_path is None
            or not segment.audio_path.exists()
        ):
            self._set_status("该片段还没有音频，无法播放。")
            return
        if self._player is None:
            self._set_status("音频播放不可用。生成与另存为 WAV 不受影响。")
            return
        state = self._player.playbackState()
        if self._playing_segment_id == segment_id:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
                return
            if state == QMediaPlayer.PlaybackState.PausedState:
                self._player.play()
                return
        self._activate_player_source(segment)
        self._player.play()
        self._set_status(f"正在播放片段 {segment.order}。")

    def _on_card_seek(self, segment_id: str, ms: int) -> None:
        """波形点击/拖动：定位播放位置（未占用播放器的卡片先切换过来）。"""
        segment = self._find_segment(segment_id)
        if (
            segment is None
            or segment.audio_path is None
            or not segment.audio_path.exists()
            or self._player is None
        ):
            return
        if self._playing_segment_id != segment_id:
            self._activate_player_source(segment)
        self._player.setPosition(ms)
        card = self._cards.get(segment_id)
        if card is not None:
            card.set_waveform_position(ms)

    def _stop_playback(self) -> None:
        """停止共享播放器并清除卡片高亮。"""
        if self._player is not None:
            self._player.stop()
        self._playing_segment_id = None
        self._refresh_playing_cards()

    def _refresh_playing_cards(self) -> None:
        if self._player is None:
            return
        state = self._player.playbackState()
        for sid, card in self._cards.items():
            if sid != self._playing_segment_id:
                card.set_playing(False)
            elif state == QMediaPlayer.PlaybackState.PlayingState:
                card.set_playing(True, paused=False)
            elif state == QMediaPlayer.PlaybackState.PausedState:
                card.set_playing(True, paused=True)
            else:
                card.set_playing(False)

    def _on_player_position(self, ms: int) -> None:
        card = self._cards.get(self._playing_segment_id or "")
        if card is not None:
            card.set_waveform_position(ms)

    def _on_player_duration(self, ms: int) -> None:
        card = self._cards.get(self._playing_segment_id or "")
        if card is not None:
            card.set_waveform_duration(ms)

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._playing_segment_id = None
            self._refresh_playing_cards()

    def _on_player_error(self) -> None:
        if self._player is None:
            return
        self._set_status(
            f"音频播放不可用（{self._player.errorString()}）。"
            "生成与另存为 WAV 不受影响。"
        )

    # ---------------- 另存为 WAV ----------------

    def _on_save_clicked(self) -> None:
        if self._current_wav is None or not self._current_wav.exists():
            self._set_status("当前没有可保存的单段生成结果。")
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

    # ---------------- Worker 收尾 ----------------

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._update_model_state()
        self._update_action_states()

    def closeEvent(self, event) -> None:
        """销毁前正确清理 Worker：批量先请求停止，等待当前任务结束。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            if isinstance(worker, BatchGenerateWorker):
                worker.request_stop()
            if not worker.wait(15000):
                QMessageBox.information(
                    self, "任务进行中", "当前任务尚未结束，请稍后关闭。"
                )
                event.ignore()
                return
        if self._player is not None:
            self._player.stop()
        super().closeEvent(event)
