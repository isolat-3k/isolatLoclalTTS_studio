"""Backend-selection and Apple MPS backend tests without real model downloads."""

from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch

from backends.qwen_mps import DEFAULT_MODEL_KEY, QwenMpsBackend
from backends.qwen_torch import MODEL_SPECS, QwenTorchBackend


class _FakeMpsBackend:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class _FakeMps:
    def __init__(self) -> None:
        self.empty_cache_calls = 0

    def empty_cache(self) -> None:
        self.empty_cache_calls += 1


class _FakeCuda:
    @staticmethod
    def is_available() -> bool:
        return False


def _fake_torch(mps_available: bool) -> tuple[types.ModuleType, _FakeMps]:
    torch = types.ModuleType("torch")
    torch.float32 = object()
    torch.cuda = _FakeCuda()
    torch.backends = types.SimpleNamespace(mps=_FakeMpsBackend(mps_available))
    mps = _FakeMps()
    torch.mps = mps
    return torch, mps


class TestQwenMpsBackend(unittest.TestCase):
    def test_load_uses_mps_fp32_and_sdpa(self) -> None:
        torch, mps = _fake_torch(mps_available=True)
        qwen_tts = types.ModuleType("qwen_tts")
        calls: list[dict[str, object]] = []

        class FakeModel:
            @classmethod
            def from_pretrained(
                cls, model_id: str, **kwargs: object
            ) -> object:
                calls.append({"model_id": model_id, **kwargs})
                return object()

        qwen_tts.Qwen3TTSModel = FakeModel
        backend = QwenMpsBackend()
        spec = MODEL_SPECS[DEFAULT_MODEL_KEY]
        original_fallback = os.environ.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
        try:
            with patch.dict(sys.modules, {"torch": torch, "qwen_tts": qwen_tts}):
                backend.load(spec)
                self.assertTrue(backend.is_loaded)
                self.assertEqual(calls, [{
                    "model_id": spec.model_id,
                    "device_map": "mps",
                    "dtype": torch.float32,
                    "attn_implementation": "sdpa",
                }])
                self.assertEqual(os.environ["PYTORCH_ENABLE_MPS_FALLBACK"], "1")
                backend.unload()
        finally:
            if original_fallback is None:
                os.environ.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
            else:
                os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = original_fallback

        self.assertEqual(mps.empty_cache_calls, 1)

    def test_load_explains_when_mps_is_unavailable(self) -> None:
        torch, _ = _fake_torch(mps_available=False)
        qwen_tts = types.ModuleType("qwen_tts")
        qwen_tts.Qwen3TTSModel = object()
        backend = QwenMpsBackend(enable_mps_fallback=False)

        with patch.dict(sys.modules, {"torch": torch, "qwen_tts": qwen_tts}):
            with self.assertRaisesRegex(RuntimeError, "MPS is unavailable"):
                backend.load(MODEL_SPECS[DEFAULT_MODEL_KEY])


class TestBackendFactory(unittest.TestCase):
    def test_darwin_uses_mps_backend_and_small_default_model(self) -> None:
        with patch("backends.factory.platform.system", return_value="Darwin"):
            from backends.factory import create_default_backend

            backend, default_model_key = create_default_backend()

        self.assertIsInstance(backend, QwenMpsBackend)
        self.assertEqual(default_model_key, DEFAULT_MODEL_KEY)

    def test_non_darwin_keeps_cuda_backend(self) -> None:
        with patch("backends.factory.platform.system", return_value="Windows"):
            from backends.factory import create_default_backend

            backend, _ = create_default_backend()

        self.assertIsInstance(backend, QwenTorchBackend)


if __name__ == "__main__":
    unittest.main()
