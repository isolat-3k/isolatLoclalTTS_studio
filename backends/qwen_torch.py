"""Qwen3-TTS 的 PyTorch / CUDA 后端。

注意：torch 与 qwen_tts 只在 load() 内部延迟导入，
因此 import 本模块不需要 GPU、torch 或模型权重，也不会触发模型加载。
"""

from __future__ import annotations

import threading
from pathlib import Path

from .base import TTSBackend

DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"

# 模型加载前的展示用兜底列表，来自官方模型卡：
# https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
# 模型加载成功后，会以 model.get_supported_*() 的实际返回为准。
_FALLBACK_SPEAKERS: list[str] = [
    "Vivian",
    "Serena",
    "Uncle_Fu",
    "Dylan",
    "Eric",
    "Ryan",
    "Aiden",
    "Ono_Anna",
    "Sohee",
]
_FALLBACK_LANGUAGES: list[str] = [
    "Auto",
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
]


class QwenTorchBackend(TTSBackend):
    """基于官方 qwen-tts 包的 CUDA 推理后端（CustomVoice 模式）。"""

    def __init__(self, model_id: str = DEFAULT_MODEL_ID) -> None:
        self._model_id = model_id
        self._model = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return  # 只加载一次，重复调用直接返回

            import torch  # 延迟导入：见模块 docstring
            from qwen_tts import Qwen3TTSModel

            if not torch.cuda.is_available():
                raise RuntimeError(
                    "未检测到可用的 NVIDIA CUDA 设备。"
                    "当前后端只支持 CUDA，请检查显卡驱动与 CUDA 版 PyTorch 安装。"
                )

            dtype = (
                torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            )
            self._model = Qwen3TTSModel.from_pretrained(
                self._model_id,
                device_map="cuda:0",
                dtype=dtype,
                # 暂不依赖 FlashAttention，使用默认 attention 实现
            )

    def generate(
        self,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
        output_path: Path,
    ) -> Path:
        if self._model is None:
            raise RuntimeError("模型尚未加载，请先加载模型。")

        import soundfile as sf  # 延迟导入

        wavs, sample_rate = self._model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker,
            instruct=instruct,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), wavs[0], sample_rate)
        return output_path

    def get_supported_speakers(self) -> list[str]:
        if self._model is not None:
            # qwen_tts 在模型未暴露约束时可能返回 None，此处兜底
            names = self._model.get_supported_speakers()
            if names:
                return list(names)
        return list(_FALLBACK_SPEAKERS)

    def get_supported_languages(self) -> list[str]:
        if self._model is not None:
            names = self._model.get_supported_languages()
            if names:
                return list(names)
        return list(_FALLBACK_LANGUAGES)
