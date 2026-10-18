# PDFMathTranslate

科学 PDF 文档翻译工具，保留原始排版、公式、图表和注释。

本仓库为个人维护的 fork，主要增强：跨平台便携版构建（Windows / Linux / macOS）、离线资产打包、翻译缺陷修复、GUI 优化。

## 功能特性

- 📊 保留公式、图表、目录和批注
- 🌐 支持多种语言和翻译服务（Google、DeepL、OpenAI、LongCat、Ollama 等）
- 🤖 提供命令行工具和 Gradio Web 界面
- ⚡ 支持 `--ultrafast` 模式加速纯文本 PDF 翻译
- 📦 三平台便携版：解压即用，自带 Python 运行时、全部依赖与离线资产，无需安装任何环境

## 便携版（推荐，免安装）

从 [Releases](https://github.com/BluesilveEmperor/PDFtranslate/releases) 下载对应平台产物（当前版本 v0.0.1）：

| 产物 | 平台 | 架构 |
|---|---|---|
| `pdf2zh-win64.zip` | Windows 10/11 | x64 |
| `pdf2zh-linux-x64.tar.gz` | Linux (glibc) | x64 |
| `pdf2zh-macos-arm64.tar.gz` | macOS 11+ | Apple Silicon (M1-M4) |

> macOS 仅提供 Apple Silicon 版；Intel 芯片 Mac 暂不支持便携版。

### Windows

```bat
:: 解压 zip 后，双击 build\start.bat
:: 或命令行启动
build\pdf2zh.exe
```

### Linux / macOS

```bash
tar xzf pdf2zh-<平台>.tar.gz
./build/pdf2zh            # 无参数自动进入 GUI 模式
```

macOS 首次运行需先去除 Gatekeeper 隔离标记（浏览器下载的文件会触发"无法验证开发者"）：

```bash
xattr -dr com.apple.quarantine build/
```

### 使用说明

- GUI 模式启动后浏览器访问 `http://localhost:7860`
- 命令行模式：`./build/pdf2zh input.pdf`（或 Windows 下 `build\pdf2zh.exe input.pdf`）
- 翻译输出在源文件同目录：`Traned_single_*.pdf`（纯译文）与 `Traned_double_*.pdf`（双语对照）；中间产物写入 `.staging/` 隐藏子目录，翻译完成后自动清理改名
- 首次启动较慢（约半分钟）：需解压离线资产、加载布局模型，属正常现象
- 完全离线可用（翻译服务除外），布局识别模型与字体资产已内置

## 从源码运行

```bash
pip install -e .

# 启动 GUI
pdf2zh --interactive

# 命令行翻译
pdf2zh input.pdf
pdf2zh input.pdf --lang-in en --lang-out zh --service google
pdf2zh input.pdf --pages 1-5
pdf2zh --help
```

## 从源码构建便携版

统一入口 `build.sh`，自动检测平台：

```bash
bash build.sh
```

| 平台 | 方案 | 前置条件 |
|---|---|---|
| Windows | conda Python 3.12.9 embed + PyStand | conda 环境 `pdf2zh_build`（脚本内 `PY_EXE`/`CONDA_SP` 路径需按实际机器调整） |
| Linux / macOS | uv 下载 python-build-standalone 便携解释器 + shell 启动器 | 安装 [uv](https://docs.astral.sh/uv/)：`curl -LsSf https://astral.sh/uv/install.sh \| sh` |

构建产物在 `build/` 目录：`pdf2zh.exe`（Windows）或 `pdf2zh`（Linux/macOS）启动器 + `runtime/` + `site-packages/` + 离线资产。

### 离线资产缓存

构建最后一步用 `script/make_offline_assets.py` 打包 babeldoc 离线资产（布局模型、字体），默认从 `~/.cache/babeldoc/` 本地缓存生成，避免联网校验。可用环境变量控制：

```bash
# 指定缓存目录（如 WSL 里复用 Windows 侧缓存）
ASSETS_CACHE_DIR=/mnt/c/Users/<user>/.cache/babeldoc bash build.sh

# 缓存缺失时允许联网 warmup 下载（CI / 网络畅通环境）
ASSETS_ALLOW_DOWNLOAD=1 bash build.sh
```

## CI / CD

三个手动触发的 GitHub Actions workflow 分别构建三平台产物（`exe-build.yml` / `linux-build.yml` / `macos-build.yml`），构建后自动做 GUI 冒烟测试（启动服务 + 轮询 7860 端口 + 验证离线资产恢复）；`release-assets.yml` 将三个构建 run 的产物汇总上传到 Release。

## 已知问题与修复记录

### 输出 PDF 多余黑色实线（已修复）

原版在部分 PDF 上输出交织的黑色实线。根因是 `pdf2zh/converter.py` 中 DEBUG 模式的追踪线绘制与全局线条重绘逻辑误触发；已修复 `converter.py` / `pdfinterp.py` / `high_level.py` 相关代码路径。

### 译文缺失（已修复）

原版 `vfont` 公式字体检测正则过宽，导致正文被误判为公式而跳过翻译。已收窄为 `CM(MI|SY|EX|BSY)` 并优化误报警告逻辑。

### babeldoc BitStream 兼容性

babeldoc 依赖 `bitstring>=4.3.0`，但 bitstring 4.x/5.x 已移除 `BitStream`。本项目通过 monkey-patch 解决（`pdf2zh/__init__.py` 和构建时注入的 `sitecustomize.py`）。

### 非 UTF-8 终端下的中文输出崩溃（已修复）

英语 Windows（cp1252 代码页）输出重定向时，启动横幅的中文 print 会 `UnicodeEncodeError` 崩溃。已在 `pdf2zh/__init__.py` 包级强制 stdout/stderr 为 UTF-8。

## 开发

```bash
pytest              # 运行全部测试
pytest -k test_name # 单个测试
```

## 致谢

基于 [PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate) 开发，感谢原作者及所有贡献者。

## License

[AGPL-3.0](LICENSE)
