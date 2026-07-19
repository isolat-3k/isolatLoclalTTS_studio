"""Select the built-in backend appropriate for the current operating system."""

from __future__ import annotations

import platform

from .base import TTSBackend
from .qwen_mps import DEFAULT_MODEL_KEY as MPS_DEFAULT_MODEL_KEY
from .qwen_mps import QwenMpsBackend
from .qwen_torch import DEFAULT_MODEL_KEY as CUDA_DEFAULT_MODEL_KEY
from .qwen_torch import QwenTorchBackend


def create_default_backend() -> tuple[TTSBackend, str]:
    """Create the local backend and its safest default model key.

    Apple Silicon uses PyTorch MPS.  Windows and Linux keep using the existing
    CUDA backend, whose ``load`` method reports a clear error if CUDA is absent.
    """

    if platform.system() == "Darwin":
        return QwenMpsBackend(), MPS_DEFAULT_MODEL_KEY
    return QwenTorchBackend(), CUDA_DEFAULT_MODEL_KEY
