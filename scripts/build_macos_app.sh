#!/usr/bin/env bash
# Build a double-clickable Apple Silicon macOS app on an Apple Silicon Mac.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${PROJECT_DIR}/artifacts/macos"
VENV_DIR="${BUILD_ROOT}/.venv"
APP_NAME="Qwen3-TTS Test Panel"
APP_PATH="${BUILD_ROOT}/dist/${APP_NAME}.app"
ZIP_PATH="${BUILD_ROOT}/${APP_NAME// /-}-macos-arm64.zip"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERIFY_MPS="${VERIFY_MPS:-1}"
AUTO_INSTALL_SYSTEM_DEPS="${AUTO_INSTALL_SYSTEM_DEPS:-0}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script must run on macOS; macOS .app bundles cannot be built on Windows."
    exit 2
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "This application currently targets Apple Silicon (arm64), because it uses PyTorch MPS."
    exit 2
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python was not found. Install an arm64 Python 3.10+ or set PYTHON_BIN."
    exit 2
fi

if ! command -v sox >/dev/null 2>&1; then
    if [[ "${AUTO_INSTALL_SYSTEM_DEPS}" == "1" ]] && command -v brew >/dev/null 2>&1; then
        # GitHub-hosted runners can contain unrelated, untrusted third-party
        # taps.  Avoid Homebrew's global auto-update and install only the
        # core formula required for this bundle.
        HOMEBREW_NO_AUTO_UPDATE=1 brew install sox
    else
        echo "SoX is required by qwen-tts. Install it with: brew install sox"
        echo "For automated installation on a Homebrew-equipped build machine, set AUTO_INSTALL_SYSTEM_DEPS=1."
        exit 2
    fi
fi

SOX_BIN="$(command -v sox)"

mkdir -p "${BUILD_ROOT}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${PROJECT_DIR}/requirements.txt" pyinstaller

VERIFY_MPS="${VERIFY_MPS}" "${VENV_DIR}/bin/python" - <<'PY'
import os
import sys

import torch

mps = getattr(torch.backends, "mps", None)
if mps is None or not mps.is_built():
    sys.exit("This PyTorch build does not include Apple MPS support.")
if os.environ["VERIFY_MPS"] == "1" and not mps.is_available():
    sys.exit("PyTorch MPS is unavailable. Use an MPS-capable Apple Silicon macOS installation.")
PY

"${VENV_DIR}/bin/python" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name "${APP_NAME}" \
    --target-architecture arm64 \
    --osx-bundle-identifier "local.qwen3tts.testpanel" \
    --collect-all qwen_tts \
    --collect-all accelerate \
    --collect-all einops \
    --collect-all librosa \
    --collect-all onnxruntime \
    --collect-all sox \
    --collect-all torch \
    --collect-all torchaudio \
    --collect-all transformers \
    --collect-all tokenizers \
    --collect-all safetensors \
    --collect-all soundfile \
    --add-binary "${SOX_BIN}:." \
    --distpath "${BUILD_ROOT}/dist" \
    --workpath "${BUILD_ROOT}/build" \
    --specpath "${BUILD_ROOT}/spec" \
    "${PROJECT_DIR}/main.py"

# Ad-hoc signing makes the local bundle internally consistent.  Public
# distribution without macOS warnings requires a Developer ID signature and
# notarization, which intentionally are not attempted by this local script.
codesign --force --deep --sign - "${APP_PATH}"
codesign --verify --deep --strict "${APP_PATH}"

rm -f "${ZIP_PATH}"
ditto -c -k --keepParent "${APP_PATH}" "${ZIP_PATH}"

echo
echo "App: ${APP_PATH}"
echo "Shareable archive: ${ZIP_PATH}"
echo "The model weights are downloaded on the first model load."
