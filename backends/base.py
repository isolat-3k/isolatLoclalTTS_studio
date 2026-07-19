"""TTS 后端统一接口。

UI 与 core 只依赖这里的抽象，不感知具体推理实现。
后续新增后端（例如 macOS MLX）时，实现同一接口即可，主界面无需改动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelSpec:
    """模型能力描述。

    后续逻辑统一基于 ModelSpec 判断能力，禁止按模型名称写分支。
    """

    display_name: str
    model_id: str
    supports_instruct: bool


class TTSBackend(ABC):
    """所有推理后端需要实现的最小接口。"""

    @abstractmethod
    def load(self, spec: ModelSpec) -> None:
        """加载指定模型。

        重复加载同一模型必须是幂等的；已加载其他模型时先安全释放旧模型再加载。
        显存中任何时候只保留一个模型实例。
        """

    @abstractmethod
    def unload(self) -> None:
        """释放当前模型并清理显存。未加载时为空操作。"""

    @abstractmethod
    def generate(
        self,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
        output_path: Path,
    ) -> Path:
        """合成音频并写入 output_path（WAV），返回实际写入的路径。

        当前模型不支持风格指令时，实现必须忽略 instruct（按 None/空值传给模型）。
        """

    @abstractmethod
    def get_supported_speakers(self) -> list[str]:
        """返回当前模型可用的音色列表。"""

    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """返回当前模型可用的语言列表。"""

    @abstractmethod
    def get_available_models(self) -> dict[str, ModelSpec]:
        """返回该后端可选模型的注册表（key -> ModelSpec）。"""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """模型是否已加载。"""

    @property
    @abstractmethod
    def current_spec(self) -> ModelSpec | None:
        """当前已加载模型的能力描述；未加载时为 None。"""
