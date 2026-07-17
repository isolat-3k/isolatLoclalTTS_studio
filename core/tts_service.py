"""推理服务层：位于 UI / 后台线程与具体后端之间。

本层不依赖 PySide6，可以被任何前台调用。
后续增加长文本自动切分等处理时，应插入到本层（如 generate 内部），
UI 与后端都不需要改动。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from backends.base import TTSBackend

# 当前工具的保护性输入长度上限（字符数）。
# 这只是本地测试工具的临时限制，不代表模型的实际上限。
MAX_TEXT_LENGTH = 600


class TTSService:
    """持有后端实例，对上提供模型加载与生成入口。"""

    def __init__(self, backend: TTSBackend, output_dir: Path) -> None:
        self._backend = backend
        self._output_dir = output_dir

    @property
    def is_model_loaded(self) -> bool:
        return self._backend.is_loaded

    def get_speakers(self) -> list[str]:
        return self._backend.get_supported_speakers()

    def get_languages(self) -> list[str]:
        return self._backend.get_supported_languages()

    def load_model(self) -> None:
        self._backend.load()

    def generate(
        self,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
    ) -> Path:
        """校验输入并调用后端生成，返回生成的临时 WAV 路径。"""
        text = text.strip()
        if not text:
            raise ValueError("配音文本为空。")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(
                f"文本长度 {len(text)} 超过当前工具限制 {MAX_TEXT_LENGTH} 字符"
                "（临时保护限制，不代表模型上限），请分段测试。"
            )
        if not self._backend.is_loaded:
            raise RuntimeError("模型尚未加载，请先点击“加载模型”。")
        # qwen_tts 对语言/音色按大小写不敏感校验（模型返回的列表也是小写），此处保持一致
        if language.casefold() not in {l.casefold() for l in self.get_languages()}:
            raise ValueError(f"不支持的语言：{language}")
        if speaker.casefold() not in {s.casefold() for s in self.get_speakers()}:
            raise ValueError(f"不支持的音色：{speaker}")

        output_path = self._new_output_path()
        return self._backend.generate(
            text=text,
            language=language,
            speaker=speaker,
            instruct=instruct.strip(),
            output_path=output_path,
        )

    def _new_output_path(self) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        name = f"tts_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.wav"
        return self._output_dir / name
