# Qwen3-TTS 本地测试面板

PySide6 桌面工具，用于本地测试 Qwen3-TTS（当前仅 CustomVoice 模式、Windows + NVIDIA CUDA）。

## 环境要求

- Python 3.10+（建议 3.11）
- NVIDIA 显卡 + CUDA 环境（Windows 上 PyPI 的 torch 默认即 CUDA 构建）

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows；macOS/Linux 用 source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 说明

- 首次点击“加载模型”会从 Hugging Face 下载 `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`（约 1.2 GB），需要等待。
- 未检测到可用 CUDA 时，加载模型会报明确错误；当前版本不支持 CPU 推理。
- 生成结果先写入 `outputs/` 下的临时 WAV，“另存为 WAV”可复制到任意位置。
- 若系统缺少媒体后端导致无法试听，生成与保存功能不受影响。
- 输入长度限制（600 字符）是本工具的临时保护，不代表模型上限。
