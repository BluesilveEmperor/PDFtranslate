# 国内网络（无代理）使用指南

pdf2zh 的核心翻译流程不依赖海外服务：布局分析模型（DocLayout-YOLO ONNX）、字体等资产由 babeldoc 内置的 **hf-mirror.com / modelscope.cn 镜像**自动竞速下载，翻译走你配置的服务商（如 DeepSeek `api.deepseek.com`、智谱 `open.bigmodel.cn`）。以下配置可让全流程在国内直连网络下可用。

## 1. Python 依赖安装

```powershell
# uv（推荐，自动管理 Python 3.11/3.12）
$env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
uv sync

# 或 pip
pip install pdf2zh -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 2. 首次运行自动下载（无需代理）

- **模型/字体**：首次翻译时 babeldoc 自动从 hf-mirror.com / modelscope.cn 下载到 `~/.cache/babeldoc/`，国内直连可用。
- **OCR 语言数据**：翻译扫描版 PDF 时自动下载 Tesseract 语言包到 `~/.cache/pdf2zh/tessdata/4.1.0/`。内置多镜像按序回退（原源 GitHub → cdn.jsdelivr.net → gcore.jsdelivr.net → ghfast.top），单个镜像连接超时 5 秒即切换下一个。

## 3. 环境变量卫生（重要）

确保没有残留代理变量，否则国内 API 请求可能被劫持到不可达的代理：

```powershell
# 检查
Get-ChildItem env: | Where-Object Name -match "proxy"
# 临时清空（仅当前会话）
Remove-Item env:HTTP_PROXY, env:HTTPS_PROXY, env:ALL_PROXY -ErrorAction SilentlyContinue
```

pdf2zh 启动时如检测到这些变量也会打印警告。

## 4. GUI 配置（`~/.config/pdf2zh/config.json`）

```json
{
  "ENABLED_SERVICES": ["Deepseek", "Zhipu", "LongCat", "ModelScope", "Silicon", "QwenMt"]
}
```

- `ENABLED_SERVICES` 中服务的**顺序即下拉框默认顺序**，第一项为默认翻译服务；未列出的 Google/Bing 会追加到列表末尾（不影响国内使用）。
- GUI 启动时默认已禁用 Gradio 遥测（`GRADIO_ANALYTICS_ENABLED=False`），不会向 huggingface.co 等海外端点发送统计请求。

各服务的 API Key 通过环境变量设置，例如 DeepSeek：

```powershell
setx DEEPSEEK_API_KEY "sk-..."
```

## 5. OCR 兜底方案

- 自定义镜像（逗号分隔，`{filename}` 为占位符，会排在内置镜像之前尝试）：

  ```powershell
  setx PDF2ZH_TESSDATA_MIRRORS "https://your-mirror.example/tessdata/{filename}"
  ```

- 手动放置：从任意可达渠道获取 `{语言}.traineddata`（如 `eng.traineddata`），放入 `%USERPROFILE%\.cache\pdf2zh\tessdata\4.1.0\`。
- 或指向已有的 Tesseract 数据目录：`setx TESSDATA_PREFIX "C:\Program Files\Tesseract-OCR\tessdata"`。

## 6. 常见问题

- **某语言 OCR 报错 "Could not download OCR data"**：说明所有内置镜像均不可达，按第 5 节配置自定义镜像或手动放置文件。
- **翻译结果大量未翻译段落**：优先检查 API Key 是否有效、代理变量是否残留；可用 `--ignore-cache` 忽略历史缓存重试。
- **babeldoc 模型下载慢/失败**：模型从 hf-mirror/modelscope 自动竞速下载，一般无需干预；完成后缓存在 `~/.cache/babeldoc/`，之后离线可用。
