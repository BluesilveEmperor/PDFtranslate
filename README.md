# PDFMathTranslate

科学 PDF 文档翻译工具，保留原始排版、公式、图表和注释。

## 功能特性

- 📊 保留公式、图表、目录和批注
- 🌐 支持多种语言和翻译服务（Google、DeepL、OpenAI、LongCat、Ollama 等）
- 🤖 提供命令行工具和 Gradio Web 界面
- ⚡ 支持 `--ultrafast` 模式加速纯文本 PDF 翻译

## 快速开始

### 安装

```bash
pip install -e .
```

### 启动 GUI

```bash
# 方式一：命令行
pdf2zh --interactive

# 方式二：双击启动脚本（Windows）
start.bat
```

启动后浏览器访问 `http://localhost:7860`。

### 命令行翻译

```bash
# 基本用法
pdf2zh input.pdf

# 指定语言和服务
pdf2zh input.pdf --lang-in en --lang-out zh --service google

# 指定页范围
pdf2zh input.pdf --pages 1-5

# 查看所有选项
pdf2zh --help
```

## 本地构建 Windows exe

使用 conda + PyStand 打包独立可执行文件：

```bash
# 1. 创建 conda 环境（Python 3.12.9）
conda create -n pdf2zh_build python=3.12.9 -y
conda run -n pdf2zh_build pip install .

# 2. 构建 exe
bash build.sh
# 或双击 build.bat
```

构建产物在 `build/` 目录，双击 `build/start.bat` 即可启动。

## Docker

```bash
docker run -d -p 7860:7860 byaidu/pdf2zh
```

## 已知问题与修复

### babeldoc BitStream 兼容性

babeldoc 依赖 `bitstring>=4.3.0`，但 bitstring 4.x/5.x 已移除 `BitStream`。
本项目通过 monkey-patch 解决（`pdf2zh/__init__.py` 和构建时的 `sitecustomize.py`）。

### 公式字体检测优化

收窄了 `vfont` 默认正则（`CM(MI|SY|EX|BSY)`），避免正文误判为公式。
同时优化了"正文误判为公式"的警告逻辑，减少误报。

## 开发

```bash
# 运行测试
pytest

# 单个测试
pytest -k test_name
```

## 致谢

基于 [PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate) 开发，感谢原作者及所有贡献者。

## License

[AGPL-3.0](LICENSE)
