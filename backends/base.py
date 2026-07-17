"""TTS 后端统一接口。

UI 与 core 只依赖这里的抽象，不感知具体推理实现。
后续新增后端（例如 macOS MLX）时，实现同一接口即可，主界面无需改动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSBackend(ABC):
    """所有推理后端需要实现的最小接口。"""

    @abstractmethod
    def load(self) -> None:
        """加载模型。实现必须保证重复调用时只加载一次（幂等）。"""

    @abstractmethod
    def generate(
        self,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
        output_path: Path,
    ) -> Path:
        """合成音频并写入 output_path（WAV），返回实际写入的路径。"""

    @abstractmethod
    def get_supported_speakers(self) -> list[str]:
        """返回当前模型可用的音色列表。"""

    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """返回当前模型可用的语言列表。"""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """模型是否已加载。"""
