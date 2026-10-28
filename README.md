# PDFMathTranslate

**简体中文 | [English](README.en.md)**

科学 PDF 文档翻译工具，保留原始排版、公式、图表和注释。

本仓库为个人维护的 fork，主要增强：跨平台便携版构建（Windows / Linux / macOS）、离线资产打包、翻译缺陷修复、GUI 优化。

🧩 **配套 Zotero 插件**：[PDFTranslate-Zotero](https://github.com/BluesilveEmperor/PDFTranslate-Zotero) —— 在 Zotero 内直接调用本项目翻译 PDF，支持双语对照、裁剪阅读与批量翻译。

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

## 使用教程

> 下文命令统一写作 `pdf2zh`。便携版用户请替换为 `build\pdf2zh.exe`（Windows）或 `./build/pdf2zh`（Linux / macOS），参数完全一致；源码安装方式见[从源码运行](#从源码运行)。

### 快速开始

```bash
# 1. GUI 模式：启动后浏览器打开 http://localhost:7860 操作
pdf2zh --interactive

# 2. 命令行模式：默认 Google 翻译，英文 → 中文
pdf2zh paper.pdf

# 3. 纯文本 PDF 极速模式（不加载布局模型，默认 16 线程）
pdf2zh paper.pdf --ultrafast
```

翻译完成后，源文件同目录会生成 `Traned_single_paper.pdf`（纯译文）与 `Traned_double_paper.pdf`（双语对照）。

### GUI 模式

1. **启动**：运行 `pdf2zh --interactive`（便携版双击 `build\start.bat` 或直接运行启动器）。首次启动约需半分钟解压离线资产、加载布局模型，属正常现象。
2. **打开界面**：浏览器访问 `http://localhost:7860`。
3. **选择输入**：「文件」区选择 *本地文件*（支持 `.pdf` / `.doc` / `.docx`，Word 文档会自动转换为 PDF 后翻译）或 *链接*（直接填入 PDF 下载地址）。
4. **选择翻译服务**：在下拉框选择服务；LLM 类服务可继续选择或填写模型名（支持在线获取模型列表），并在凭据框中填入 API Key 等信息，保存后持久生效。
5. **选择语言**：设置源语言与目标语言。
6. **设置页面范围**：默认全部页面；也可填入自定义页码，如 `1-5`、`1,3,5-8`（从 1 开始）。
7. **开始翻译**：点击翻译按钮，等待进度完成。
8. **获取结果**：在输出区下载 `Traned_single_*.pdf`（纯译文）与 `Traned_double_*.pdf`（双语对照）。

「更多实验选项」折叠区可调整：线程数、跳过字体子集化、忽略缓存（强制重翻）、自定义公式字体正则（vfont）、自定义 Prompt（LLM 服务）与翻译模式（fast / precise）。

### 命令行模式

基本语法：`pdf2zh <文件...> [选项]`

常用参数：

| 参数 | 短写 | 默认值 | 说明 |
|---|---|---|---|
| `--pages` | `-p` | 全部 | 页码范围，如 `1-5`、`1,3,5-8`（从 1 开始） |
| `--lang-in` | `-li` | `en` | 源语言代码 |
| `--lang-out` | `-lo` | `zh` | 目标语言代码 |
| `--service` | `-s` | `google` | 翻译服务，可用 `服务名:模型名` 指定模型，如 `openai:gpt-4o-mini` |
| `--output` | `-o` | 源文件所在目录 | 输出目录 |
| `--thread` | `-t` | `4`（`--ultrafast` 时为 16） | 翻译并发线程数 |
| `--dir` | | | 递归翻译整个目录下的 PDF / Word 文件 |
| `--ultrafast` | | | 极速模式：纯文本 PDF 跳过布局模型，速度大幅提升 |
| `--ignore-cache` | | | 忽略翻译缓存，强制重新翻译 |
| `--compatible` | `-cp` | | 输出转换为 PDF/A，提升兼容性 |
| `--skip-subset-fonts` | | | 跳过字体子集化（解决部分阅读器乱码/缺字，文件变大） |
| `--prompt` | | | 自定义 Prompt 模板文件路径（LLM 类服务） |
| `--vfont` | `-f` | | 公式字体名正则 |
| `--vchar` | `-c` | | 公式字符正则 |
| `--onnx` | | | 自定义 DocLayout-YOLO ONNX 模型路径 |
| `--backend` | | `auto` | 布局模型推理后端：`auto` / `cpu` / `cuda` / `dml` |
| `--conf` | | `0.25` | 布局检测置信度阈值 |
| `--reserved-classes` | | `abandon,figure,table,isolate_formula,formula_caption` | 受保护不翻译的布局类别，可删减条目 |
| `--mode` | | `fast` | 翻译模式：`fast`（v1）或 `precise`（v2） |
| `--babeldoc` | | | 使用 babeldoc 实验后端 |
| `--interactive` | `-i` | | 启动 GUI |
| `--serverport` | | | 自定义 WebUI 端口 |
| `--share` | | | 开启 Gradio 公网分享链接 |
| `--authorized` | | | GUI 登录用户名与密码 |
| `--config` | | | 指定 JSON 配置文件 |
| `--mcp` / `--sse` | | | 启动 MCP 服务器（STDIO / SSE 模式） |
| `--debug` | `-d` | | 输出调试日志 |

常用示例：

```bash
# 翻译指定页码
pdf2zh paper.pdf --pages 1-10
pdf2zh paper.pdf -p 1,3,5-8

# 指定语言与服务
pdf2zh paper.pdf --lang-in en --lang-out zh --service google

# 使用 OpenAI 并指定模型（需配置 OPENAI_API_KEY）
pdf2zh paper.pdf -s openai:gpt-4o-mini

# 批量翻译整个目录（递归查找 PDF / Word）
pdf2zh papers/ --dir

# 自定义输出目录
pdf2zh paper.pdf -o output/

# 提高并发线程
pdf2zh paper.pdf -t 8

# GPU 加速布局识别（NVIDIA / AMD）
pdf2zh paper.pdf --backend cuda
pdf2zh paper.pdf --backend dml

# 修改 Prompt / 模型后强制重新翻译
pdf2zh paper.pdf --ignore-cache

# 完整帮助
pdf2zh --help
```

### 翻译服务与 API Key 配置

主要服务及其凭据：

| 服务 | `--service` 取值 | 环境变量 | 默认模型 |
|---|---|---|---|
| Google（免费，默认） | `google` | 无需配置 | — |
| Bing | `bing` | 无需配置 | — |
| OpenAI | `openai` | `OPENAI_API_KEY`（可选 `OPENAI_BASE_URL`、`OPENAI_MODEL`） | `gpt-4o-mini` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-1.5-flash` |
| DeepL | `deepl` | `DEEPL_AUTH_KEY` | — |
| DeepLX | `deeplx` | `DEEPLX_ENDPOINT`、`DEEPLX_ACCESS_TOKEN` | — |
| 智谱 GLM | `zhipu` | `ZHIPU_API_KEY` | `glm-4-flash` |
| LongCat | `longcat` | `LONGCAT_API_KEY` | `LongCat-Flash-Chat` |
| 硅基流动 | `silicon` | `SILICON_API_KEY` | `Qwen/Qwen2.5-7B-Instruct` |
| Grok | `grok` | `GROK_API_KEY` | `grok-2-1212` |
| Groq | `groq` | `GROQ_API_KEY` | `llama-3-3-70b-versatile` |
| MiniMax | `minimax` | `MINIMAX_API_KEY` | `MiniMax-M2.7` |
| Azure OpenAI | `azure-openai` | `AZURE_OPENAI_BASE_URL`、`AZURE_OPENAI_API_KEY` 等 | `gpt-4o-mini` |
| Ollama（本地） | `ollama` | `OLLAMA_HOST`、`OLLAMA_MODEL` | `gemma2` |
| OpenAI 兼容接口 | `openailiked` | `OPENAILIKED_BASE_URL`、`OPENAILIKED_API_KEY`、`OPENAILIKED_MODEL` | — |
| 腾讯云 | `tencent` | `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` | — |
| Azure 文本翻译 | `azure` | `AZURE_ENDPOINT`、`AZURE_API_KEY` | — |

另有 `modelscope`、`xinference`、`dify`、`anythingllm`、`qwen-mt`、`302ai`、`argos`（离线）等服务，完整列表见 `pdf2zh/translator.py`。

配置 API Key 的三种方式：

1. **环境变量（命令行推荐）**：

   ```bash
   # Linux / macOS
   export OPENAI_API_KEY="sk-..."

   # Windows (PowerShell)
   $env:OPENAI_API_KEY = "sk-..."

   # Windows (CMD)
   set OPENAI_API_KEY=sk-...
   ```

2. **GUI 填写**：在界面选择服务后于凭据输入框中填写，保存后持久生效。

3. **配置文件**：凭据持久保存在 `~/.config/PDFMathTranslate/config.json`（Windows 为 `C:\Users\<用户名>\.config\PDFMathTranslate\config.json`），也可用 `--config` 指定自定义配置。

### 输出文件说明

- `Traned_single_<文件名>.pdf`：纯译文版本
- `Traned_double_<文件名>.pdf`：双语对照版本（保留原文排版）
- 中间产物写入源文件同目录的 `.staging/` 隐藏子目录，翻译完成后自动清理改名
- 翻译结果带本地缓存：相同内容 + 相同参数重复翻译直接命中缓存；更换 Prompt / 模型 / 语言或使用 `--ignore-cache` 可强制重翻

### 常见问题

<details>
<summary>首次启动很慢？</summary>

首次启动需解压离线资产并加载布局识别模型，约半分钟，属正常现象；后续启动会明显变快。
</details>

<details>
<summary>提示 Proxy environment variables detected？</summary>

检测到系统设置了 `HTTP_PROXY` / `HTTPS_PROXY` 等代理环境变量。若代理已关闭，所有请求（包括国内 API）都会失败，请清除相关变量，或为 API 域名设置 `NO_PROXY`。
</details>

<details>
<summary>公式被翻译 / 正文被当成公式跳过？</summary>

- 公式字体误判：用 `--vfont` / `--vchar` 自定义公式字体与字符正则；
- 布局区域误判：调整 `--reserved-classes`（删减被保护类别，让误判区域参与翻译），或用 `--conf` 调整置信度阈值；
- 仍不理想时可用 `--onnx` 换用自行训练的 DocLayout-YOLO 模型。
</details>

<details>
<summary>触发 API 限流（429）？</summary>

LLM 类服务内置指数退避自动重试；仍频繁限流时用 `--thread` 调低并发数。
</details>

<details>
<summary>输出 PDF 在部分阅读器中乱码 / 缺字？</summary>

加 `--skip-subset-fonts` 跳过字体子集化，或加 `--compatible` 转为 PDF/A；代价是文件体积增大。
</details>

<details>
<summary>翻译太慢？</summary>

- 纯文本（少公式图表）PDF 加 `--ultrafast`；
- 有 NVIDIA / AMD 显卡时加 `--backend cuda` / `--backend dml` 加速布局识别；
- LLM 服务可适当调高 `--thread`。
</details>

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
