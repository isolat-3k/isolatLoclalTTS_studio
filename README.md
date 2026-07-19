# Qwen3-TTS 本地测试面板

PySide6 桌面工具，用于本地测试 Qwen3-TTS（当前仅 CustomVoice 模式；Windows/Linux 使用 NVIDIA CUDA，macOS Apple Silicon 使用 MPS）。

## 环境要求

- Python 3.10+（建议 3.11）
- Windows/Linux：NVIDIA 显卡 + CUDA 环境
- macOS：Apple Silicon、原生 arm64 Python，以及支持 MPS 的 PyTorch

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows；macOS/Linux 用 source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## macOS（Apple Silicon / MPS）

程序在 macOS 上会自动选择 `QwenMpsBackend`，通过 PyTorch MPS 使用 Apple
GPU；Windows 和 Linux 仍使用 CUDA 后端。无需在界面中切换后端。

请使用原生 arm64 Python，并在安装依赖后先确认 MPS 可用：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -c "import torch; print(torch.backends.mps.is_available())"
python main.py
```

- 上述检查必须输出 `True`；否则应用在加载模型时会给出 MPS 不可用的明确错误。
- macOS 默认选择 0.6B CustomVoice，以降低统一内存压力；可在界面手动切换到
  1.7B，但需要预留更多统一内存。
- MPS 后端使用 FP32 和 SDPA，并启用 PyTorch 的 MPS CPU fallback。未实现的 MPS
  算子会在 CPU 运行，因此不同 macOS/PyTorch 版本的速度可能不同。

## 打包为 macOS 应用

`.app` 需要在 Apple Silicon Mac 上构建，不能从 Windows 交叉打包。把项目拷到
Mac 后，在项目目录执行：

```bash
chmod +x scripts/build_macos_app.sh
./scripts/build_macos_app.sh
```

脚本会建立独立的打包环境、安装依赖、验证 MPS、生成并临时签名应用。完成后可直接
双击打开的应用位于：

```text
artifacts/macos/dist/Qwen3-TTS Test Panel.app
```

便于传输的压缩包位于：

```text
artifacts/macos/Qwen3-TTS-Test-Panel-macos-arm64.zip
```

首次点击“加载模型”仍会下载模型权重。此脚本只做 ad-hoc 本地签名；如需将程序发给
其他 Mac 用户且不出现 Gatekeeper 提示，需要使用 Apple Developer ID 证书进行签名并公证。

### 没有 Mac：用 GitHub Actions 打包

仓库已包含 [macOS 打包工作流](.github/workflows/build-macos-app.yml)。将项目推送到 GitHub
后，依次打开 **Actions → Build macOS application → Run workflow**。云端 Apple Silicon
runner 会执行打包；任务成功后，在该次运行页面的 **Artifacts** 区下载
`Qwen3-TTS-Test-Panel-macos-arm64`，解压即可得到 `.app`。

云端打包会自动安装 SoX，并只验证 PyTorch 是否包含 MPS 后端；实际 Apple GPU 可用性由
最终运行应用的 Mac 决定。

## 单元测试

```bash
python -m unittest discover -s tests
```

## 界面说明

- 界面为双栏工作台布局：左侧是文本输入区与默认配音设置，右侧是分段卡片列表；顶栏为模型选择与状态。
- 文本输入框下方实时显示“当前已输入 xx 字符”（按去掉首尾空白后的长度统计）。
- 支持 `Qwen3-TTS 0.6B / 1.7B CustomVoice` 两个模型；CUDA 默认选择 1.7B，MPS 默认选择 0.6B；设备内存中任何时候只保留一个模型，切换时先释放旧模型再加载。
- 首次加载某个模型会从 Hugging Face 下载权重（0.6B 约 1.2 GB，1.7B 约 3.5 GB），需要等待。
- 0.6B 不支持风格指令（界面会禁用并提示）；1.7B 支持，可为空。
- 长文本点击“拆分为片段”自动分段（固定按约 150 字目标长度），每个片段生成独立 WAV，支持单段生成、批量串行生成与中途停止。
- 分段以卡片展示：序号 + 状态徽章、文本预览、字数、波形，以及“生成/重新生成、播放/暂停、详情、在下方插入、删除”按钮；卡片可拖拽排序。
- “详情”弹窗可为单个片段设置角色（音色）/语言/风格提示词覆盖，选择“跟随默认”则使用左侧全局设置；文本改动后该段状态自动置回未生成。
- 播放走一个共享播放器：正在播放的卡片高亮、按钮变“暂停”，切换卡片自动停止上一段；点击或拖动波形可定位播放进度。
- Windows/Linux 未检测到可用 CUDA，或 macOS 未检测到可用 MPS 时，加载模型会报明确错误；当前版本不支持纯 CPU 推理。
- 生成结果写入 `outputs/`（单段 `tts_*.wav`，分段 `segment_*.wav`），“另存WAV”可复制单段试听结果到任意位置。
- 若系统缺少媒体后端导致无法试听，生成与保存功能不受影响。
