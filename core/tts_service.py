"""推理服务层：位于 UI / 后台线程与具体后端之间。

本层不依赖 PySide6，可以被任何前台调用。
长文本拆分在 core.text_splitter，本层负责把片段合成交给后端。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from backends.base import ModelSpec, TTSBackend

from .segments import SpeechSegment


class TTSService:
    """持有后端实例，对上提供模型管理与生成入口。"""

    def __init__(self, backend: TTSBackend, output_dir: Path) -> None:
        self._backend = backend
        self._output_dir = output_dir

    # ---------------- 模型管理 ----------------

    def get_model_specs(self) -> dict[str, ModelSpec]:
        """可选模型注册表（key -> ModelSpec），UI 不维护副本。"""
        return self._backend.get_available_models()

    @property
    def loaded_spec(self) -> ModelSpec | None:
        """当前已加载模型；未加载为 None。与 UI 的“已选择”状态明确区分。"""
        return self._backend.current_spec

    @property
    def is_model_loaded(self) -> bool:
        return self._backend.is_loaded

    def load_model(self, spec: ModelSpec) -> None:
        """加载指定模型；已加载其他模型时后端会先释放旧模型。"""
        self._backend.load(spec)

    def unload_model(self) -> None:
        self._backend.unload()

    # ---------------- 音色 / 语言 ----------------

    def get_speakers(self) -> list[str]:
        return self._backend.get_supported_speakers()

    def get_languages(self) -> list[str]:
        return self._backend.get_supported_languages()

    # ---------------- 生成 ----------------

    def generate(
        self,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
    ) -> Path:
        """单段生成：校验输入并调用后端，返回临时 WAV 路径。"""
        text = self._validate_text(text)
        self._validate_settings(language, speaker)
        return self._backend.generate(
            text=text,
            language=language,
            speaker=speaker,
            instruct=instruct.strip(),
            output_path=self._output_path_for(
                f"tts_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
            ),
        )

    def generate_segment(
        self,
        segment: SpeechSegment,
        language: str,
        speaker: str,
        instruct: str,
    ) -> Path:
        """分段生成：每个片段写入独立 WAV（segment_003_xxxxxxxx.wav）。

        片段上的覆盖值（language/speaker/instruct）优先，为 None 时跟随传入的全局设置。
        """
        text = self._validate_text(segment.text)
        language = segment.language or language
        speaker = segment.speaker or speaker
        instruct = segment.instruct if segment.instruct is not None else instruct
        self._validate_settings(language, speaker)
        return self._backend.generate(
            text=text,
            language=language,
            speaker=speaker,
            instruct=instruct.strip(),
            output_path=self._output_path_for(
                f"segment_{segment.order:03d}_{uuid.uuid4().hex[:8]}"
            ),
        )

    # ---------------- 内部 ----------------

    def _validate_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("配音文本为空。")
        return text

    def _validate_settings(self, language: str, speaker: str) -> None:
        if not self._backend.is_loaded:
            raise RuntimeError("模型尚未加载，请先点击“加载模型”。")
        # qwen_tts 对语言/音色按大小写不敏感校验（模型返回的列表也是小写），此处保持一致
        if language.casefold() not in {l.casefold() for l in self.get_languages()}:
            raise ValueError(f"不支持的语言：{language}")
        if speaker.casefold() not in {s.casefold() for s in self.get_speakers()}:
            raise ValueError(f"不支持的音色：{speaker}")

    def _output_path_for(self, stem: str) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir / f"{stem}.wav"
