"""Qwen3-TTS backend for Apple Silicon through PyTorch MPS.

The qwen-tts package is imported only while loading a model.  This keeps the
module importable on Windows and in the test suite, where neither PyTorch nor
model weights are required.
"""

from __future__ import annotations

import os
import sys

from .base import ModelSpec
from .qwen_torch import QwenTorchBackend

# FP32 is the conservative choice for MPS.  It avoids the incomplete FP16/BF16
# coverage that can otherwise make Qwen3-TTS fail on some macOS/PyTorch pairs.
# The 0.6B model is a more practical default for unified-memory Macs.
DEFAULT_MODEL_KEY = "qwen3-tts-0.6b-customvoice"


class QwenMpsBackend(QwenTorchBackend):
    """CustomVoice Qwen3-TTS backend running on an Apple MPS device."""

    def __init__(self, *, enable_mps_fallback: bool = True) -> None:
        super().__init__()
        self._enable_mps_fallback = enable_mps_fallback

    def load(self, spec: ModelSpec) -> None:
        with self._lock:
            if self._model is not None:
                if self._spec == spec:
                    return
                self.unload()

            # Must be set before importing/initializing torch.  A few Qwen
            # operations are not implemented by every MPS release; PyTorch can
            # safely execute only those operations on CPU when enabled.
            if self._enable_mps_fallback:
                os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

            import torch
            from qwen_tts import Qwen3TTSModel

            mps_backend = getattr(getattr(torch, "backends", None), "mps", None)
            if mps_backend is None or not mps_backend.is_available():
                raise RuntimeError(
                    "MPS is unavailable. This backend requires an Apple Silicon "
                    "Mac with a current MPS-capable macOS release and an "
                    "MPS-enabled PyTorch build."
                )

            self._model = Qwen3TTSModel.from_pretrained(
                spec.model_id,
                device_map="mps",
                dtype=torch.float32,
                attn_implementation="sdpa",
            )
            self._spec = spec

    def unload(self) -> None:
        with self._lock:
            was_loaded = self._model is not None
            super().unload()
            if not was_loaded or "torch" not in sys.modules:
                return

            import torch

            mps_backend = getattr(getattr(torch, "backends", None), "mps", None)
            mps = getattr(torch, "mps", None)
            if (
                mps_backend is not None
                and mps_backend.is_available()
                and mps is not None
            ):
                empty_cache = getattr(mps, "empty_cache", None)
                if empty_cache is not None:
                    empty_cache()
