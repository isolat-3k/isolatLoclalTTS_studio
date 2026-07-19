"""Qwen3-TTS 的 PyTorch / CUDA 后端。

注意：torch 与 qwen_tts 只在 load() 内部延迟导入，
因此 import 本模块不需要 GPU、torch 或模型权重，也不会触发模型加载。
"""

from __future__ import annotations

import gc
import sys
import threading
from pathlib import Path

from .base import ModelSpec, TTSBackend

# 模型注册表：UI 通过后端获取该表，不自行维护模型清单。
MODEL_SPECS: dict[str, ModelSpec] = {
    "qwen3-tts-0.6b-customvoice": ModelSpec(
        display_name="Qwen3-TTS 0.6B CustomVoice",
        model_id="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        # qwen_tts 源码中对 0.6B 强制 instruct=None，不支持风格指令
        supports_instruct=False,
    ),
    "qwen3-tts-1.7b-customvoice": ModelSpec(
        display_name="Qwen3-TTS 1.7B CustomVoice",
        model_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        supports_instruct=True,
    ),
}

DEFAULT_MODEL_KEY = "qwen3-tts-1.7b-customvoice"

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

    def __init__(self) -> None:
        self._model = None
        self._spec: ModelSpec | None = None
        # RLock：load() 内部可能调用 unload()（切换模型）
        self._lock = threading.RLock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def current_spec(self) -> ModelSpec | None:
        return self._spec

    def get_available_models(self) -> dict[str, ModelSpec]:
        return dict(MODEL_SPECS)

    def load(self, spec: ModelSpec) -> None:
        with self._lock:
            if self._model is not None:
                if self._spec == spec:
                    return  # 同一模型只加载一次，重复调用直接返回
                self.unload()  # 已加载其他模型：先安全释放旧模型

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
                spec.model_id,
                device_map="cuda:0",
                dtype=dtype,
                # 暂不依赖 FlashAttention，使用默认 attention 实现
            )
            self._spec = spec

    def unload(self) -> None:
        with self._lock:
            if self._model is None:
                return
            self._model = None
            self._spec = None
            gc.collect()
            if "torch" in sys.modules:
                import torch

                cuda = getattr(torch, "cuda", None)
                if cuda is not None and cuda.is_available():
                    cuda.empty_cache()
                    cuda.ipc_collect()

    def generate(
        self,
        text: str,
        language: str,
        speaker: str,
        instruct: str,
        output_path: Path,
    ) -> Path:
        if self._model is None or self._spec is None:
            raise RuntimeError("模型尚未加载，请先加载模型。")

        import soundfile as sf  # 延迟导入

        wavs, sample_rate = self._model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker,
            # 能力判断来自 ModelSpec：不支持风格指令的模型传 None，不伪装生效
            instruct=instruct if self._spec.supports_instruct else None,
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
