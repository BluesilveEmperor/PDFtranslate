# PDFMathTranslate

**[简体中文](README.md) | English**

A scientific PDF document translator that preserves the original layout, formulas, charts, and annotations.

This is a personally maintained fork with the following enhancements: cross-platform portable builds (Windows / Linux / macOS), offline asset bundling, translation defect fixes, and GUI polish.

## Features

- 📊 Preserves formulas, charts, tables of contents, and annotations
- 🌐 Multiple languages and translation services (Google, DeepL, OpenAI, LongCat, Ollama, etc.)
- 🤖 Both a CLI tool and a Gradio web interface
- ⚡ `--ultrafast` mode for accelerating text-only PDF translation
- 📦 Portable builds for three platforms: extract and run — bundled Python runtime, all dependencies, and offline assets; nothing to install

## Portable Builds (Recommended, No Installation)

Download the artifact for your platform from [Releases](https://github.com/BluesilveEmperor/PDFtranslate/releases) (current version: v0.0.1):

| Artifact | Platform | Architecture |
|---|---|---|
| `pdf2zh-win64.zip` | Windows 10/11 | x64 |
| `pdf2zh-linux-x64.tar.gz` | Linux (glibc) | x64 |
| `pdf2zh-macos-arm64.tar.gz` | macOS 11+ | Apple Silicon (M1–M4) |

> macOS is Apple Silicon only; Intel-based Macs are not supported by the portable build for now.

### Windows

```bat
:: After extracting the zip, double-click build\start.bat
:: or launch from the command line
build\pdf2zh.exe
```

### Linux / macOS

```bash
tar xzf pdf2zh-<platform>.tar.gz
./build/pdf2zh            # no arguments: launches GUI mode automatically
```

On macOS, remove the Gatekeeper quarantine attribute before the first run (browser-downloaded files trigger an "unidentified developer" warning):

```bash
xattr -dr com.apple.quarantine build/
```

### Usage Notes

- In GUI mode, open `http://localhost:7860` in your browser after launch
- CLI mode: `./build/pdf2zh input.pdf` (or `build\pdf2zh.exe input.pdf` on Windows)
- Translated output lands next to the source file: `Traned_single_*.pdf` (translation only) and `Traned_double_*.pdf` (side-by-side bilingual); intermediate files go into a hidden `.staging/` subdirectory and are cleaned up automatically
- The first launch is slow (~30 seconds): offline assets must be extracted and the layout model loaded — this is normal
- Works fully offline (except the translation service itself); the layout recognition model and font assets are bundled

## Usage Tutorial

> Commands below are written as `pdf2zh`. Portable-build users should substitute `build\pdf2zh.exe` (Windows) or `./build/pdf2zh` (Linux / macOS) — the arguments are identical. For source installation, see [Running from Source](#running-from-source).

### Quick Start

```bash
# 1. GUI mode: open http://localhost:7860 in your browser after launch
pdf2zh --interactive

# 2. CLI mode: default Google translation, English → Chinese
pdf2zh paper.pdf

# 3. Ultrafast mode for text-only PDFs (no layout model, 16 threads by default)
pdf2zh paper.pdf --ultrafast
```

When translation finishes, `Traned_single_paper.pdf` (translation only) and `Traned_double_paper.pdf` (side-by-side bilingual) appear next to the source file.

### GUI Mode

1. **Launch**: run `pdf2zh --interactive` (portable build: double-click `build\start.bat` or run the launcher). The first launch takes ~30 seconds to extract offline assets and load the layout model — this is normal.
2. **Open the UI**: visit `http://localhost:7860` in your browser.
3. **Choose input**: in the *File* section, pick *Local file* (`.pdf` / `.doc` / `.docx`; Word documents are converted to PDF automatically) or *Link* (a direct PDF download URL).
4. **Choose a translation service**: select one from the dropdown. For LLM services, pick or type a model name (an online model-list fetch is provided) and fill in your API key and other credentials — they are saved persistently.
5. **Choose languages**: set the source and target languages.
6. **Set the page range**: all pages by default, or a custom range such as `1-5` or `1,3,5-8` (1-based).
7. **Translate**: click the translate button and wait for completion.
8. **Get results**: download `Traned_single_*.pdf` (translation only) and `Traned_double_*.pdf` (bilingual) from the output area.

The *More experimental options* accordion lets you adjust: thread count, skip font subsetting, ignore cache (force retranslation), custom formula-font regex (vfont), custom prompt (LLM services), and translation mode (fast / precise).

### CLI Mode

Basic syntax: `pdf2zh <files...> [options]`

Common options:

| Option | Short | Default | Description |
|---|---|---|---|
| `--pages` | `-p` | all | Page range, e.g. `1-5`, `1,3,5-8` (1-based) |
| `--lang-in` | `-li` | `en` | Source language code |
| `--lang-out` | `-lo` | `zh` | Target language code |
| `--service` | `-s` | `google` | Translation service; specify a model via `service:model`, e.g. `openai:gpt-4o-mini` |
| `--output` | `-o` | source directory | Output directory |
| `--thread` | `-t` | `4` (16 with `--ultrafast`) | Translation worker threads |
| `--dir` | | | Recursively translate all PDF / Word files in a directory |
| `--ultrafast` | | | Ultrafast mode: skips the layout model for text-only PDFs, much faster |
| `--ignore-cache` | | | Ignore the translation cache and force retranslation |
| `--compatible` | `-cp` | | Convert output to PDF/A for compatibility |
| `--skip-subset-fonts` | | | Skip font subsetting (fixes garbled/missing glyphs in some readers; larger file) |
| `--prompt` | | | Path to a custom prompt template file (LLM services) |
| `--vfont` | `-f` | | Regex for formula font names |
| `--vchar` | `-c` | | Regex for formula characters |
| `--onnx` | | | Path to a custom DocLayout-YOLO ONNX model |
| `--backend` | | `auto` | Layout-model inference backend: `auto` / `cpu` / `cuda` / `dml` |
| `--conf` | | `0.25` | Layout detection confidence threshold |
| `--reserved-classes` | | `abandon,figure,table,isolate_formula,formula_caption` | Layout classes protected from translation; remove entries to translate misdetected regions |
| `--mode` | | `fast` | Translation mode: `fast` (v1) or `precise` (v2) |
| `--babeldoc` | | | Use the experimental babeldoc backend |
| `--interactive` | `-i` | | Launch the GUI |
| `--serverport` | | | Custom WebUI port |
| `--share` | | | Enable the Gradio public share link |
| `--authorized` | | | GUI username and password |
| `--config` | | | Path to a JSON config file |
| `--mcp` / `--sse` | | | Launch the MCP server (STDIO / SSE mode) |
| `--debug` | `-d` | | Debug logging |

Common examples:

```bash
# Translate specific pages
pdf2zh paper.pdf --pages 1-10
pdf2zh paper.pdf -p 1,3,5-8

# Specify languages and service
pdf2zh paper.pdf --lang-in en --lang-out zh --service google

# Use OpenAI with a specific model (requires OPENAI_API_KEY)
pdf2zh paper.pdf -s openai:gpt-4o-mini

# Batch-translate a whole directory (recursively finds PDF / Word files)
pdf2zh papers/ --dir

# Custom output directory
pdf2zh paper.pdf -o output/

# More worker threads
pdf2zh paper.pdf -t 8

# GPU-accelerated layout detection (NVIDIA / AMD)
pdf2zh paper.pdf --backend cuda
pdf2zh paper.pdf --backend dml

# Force retranslation after changing the prompt / model
pdf2zh paper.pdf --ignore-cache

# Full help
pdf2zh --help
```

### Translation Services & API Keys

Major services and their credentials:

| Service | `--service` value | Environment variables | Default model |
|---|---|---|---|
| Google (free, default) | `google` | none | — |
| Bing | `bing` | none | — |
| OpenAI | `openai` | `OPENAI_API_KEY` (optional `OPENAI_BASE_URL`, `OPENAI_MODEL`) | `gpt-4o-mini` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-1.5-flash` |
| DeepL | `deepl` | `DEEPL_AUTH_KEY` | — |
| DeepLX | `deeplx` | `DEEPLX_ENDPOINT`, `DEEPLX_ACCESS_TOKEN` | — |
| Zhipu GLM | `zhipu` | `ZHIPU_API_KEY` | `glm-4-flash` |
| LongCat | `longcat` | `LONGCAT_API_KEY` | `LongCat-Flash-Chat` |
| SiliconFlow | `silicon` | `SILICON_API_KEY` | `Qwen/Qwen2.5-7B-Instruct` |
| Grok | `grok` | `GROK_API_KEY` | `grok-2-1212` |
| Groq | `groq` | `GROQ_API_KEY` | `llama-3-3-70b-versatile` |
| MiniMax | `minimax` | `MINIMAX_API_KEY` | `MiniMax-M2.7` |
| Azure OpenAI | `azure-openai` | `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, etc. | `gpt-4o-mini` |
| Ollama (local) | `ollama` | `OLLAMA_HOST`, `OLLAMA_MODEL` | `gemma2` |
| OpenAI-compatible | `openailiked` | `OPENAILIKED_BASE_URL`, `OPENAILIKED_API_KEY`, `OPENAILIKED_MODEL` | — |
| Tencent Cloud | `tencent` | `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` | — |
| Azure Text Translation | `azure` | `AZURE_ENDPOINT`, `AZURE_API_KEY` | — |

Additional services include `modelscope`, `xinference`, `dify`, `anythingllm`, `qwen-mt`, `302ai`, and `argos` (offline); see `pdf2zh/translator.py` for the full list.

Three ways to configure an API key:

1. **Environment variables (recommended for the CLI)**:

   ```bash
   # Linux / macOS
   export OPENAI_API_KEY="sk-..."

   # Windows (PowerShell)
   $env:OPENAI_API_KEY = "sk-..."

   # Windows (CMD)
   set OPENAI_API_KEY=sk-...
   ```

2. **Via the GUI**: fill in the credential boxes after selecting a service; values are saved persistently.

3. **Config file**: credentials are persisted in `~/.config/PDFMathTranslate/config.json` (`C:\Users\<user>\.config\PDFMathTranslate\config.json` on Windows); `--config` points to a custom config file.

### Output Files

- `Traned_single_<name>.pdf`: translation-only version
- `Traned_double_<name>.pdf`: side-by-side bilingual version (original layout preserved)
- Intermediate files go into a hidden `.staging/` subdirectory next to the source file and are cleaned up automatically after translation
- Translations are cached locally: identical content with identical parameters hits the cache instantly; changing the prompt / model / language or passing `--ignore-cache` forces retranslation

### FAQ

<details>
<summary>First launch is slow?</summary>

The first launch extracts offline assets and loads the layout model (~30 seconds) — this is normal. Subsequent launches are much faster.
</details>

<details>
<summary>"Proxy environment variables detected" warning?</summary>

`HTTP_PROXY` / `HTTPS_PROXY` (or similar) variables are set in your environment. If your VPN/proxy is off, all requests (including domestic APIs) will fail. Clear those variables, or set `NO_PROXY` for your API domains.
</details>

<details>
<summary>Formulas get translated / body text is skipped as formulas?</summary>

- Formula-font misdetection: customize the formula font / character regexes with `--vfont` / `--vchar`;
- Layout-region misdetection: adjust `--reserved-classes` (remove protected classes so misdetected regions get translated), or tune the confidence threshold with `--conf`;
- If still unsatisfactory, swap in your own DocLayout-YOLO model with `--onnx`.
</details>

<details>
<summary>API rate limits (429)?</summary>

LLM services retry automatically with exponential backoff. If rate limiting persists, lower the concurrency with `--thread`.
</details>

<details>
<summary>Output PDF shows garbled / missing glyphs in some readers?</summary>

Add `--skip-subset-fonts` to skip font subsetting, or `--compatible` to convert to PDF/A; the trade-off is a larger file.
</details>

<details>
<summary>Translation is too slow?</summary>

- Add `--ultrafast` for text-only PDFs (few formulas/charts);
- Add `--backend cuda` / `--backend dml` for NVIDIA / AMD GPUs to accelerate layout detection;
- Raise `--thread` for LLM services.
</details>

## Running from Source

```bash
pip install -e .

# Start the GUI
pdf2zh --interactive

# CLI translation
pdf2zh input.pdf
pdf2zh input.pdf --lang-in en --lang-out zh --service google
pdf2zh input.pdf --pages 1-5
pdf2zh --help
```

## Building the Portable Version from Source

The single entry point is `build.sh`, which detects the platform automatically:

```bash
bash build.sh
```

| Platform | Approach | Prerequisites |
|---|---|---|
| Windows | conda Python 3.12.9 embed + PyStand | conda env `pdf2zh_build` (the `PY_EXE`/`CONDA_SP` paths inside the script must be adjusted per machine) |
| Linux / macOS | uv-fetched python-build-standalone portable interpreter + shell launcher | Install [uv](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

Build output lands in `build/`: the `pdf2zh.exe` (Windows) or `pdf2zh` (Linux/macOS) launcher + `runtime/` + `site-packages/` + offline assets.

### Offline Asset Cache

The final build step uses `script/make_offline_assets.py` to bundle babeldoc offline assets (layout model, fonts) from the local `~/.cache/babeldoc/` cache, skipping online verification. Control it via environment variables:

```bash
# Specify a cache directory (e.g. reuse the Windows-side cache from WSL)
ASSETS_CACHE_DIR=/mnt/c/Users/<user>/.cache/babeldoc bash build.sh

# Allow a network warmup download when the cache is incomplete (CI / well-connected environments)
ASSETS_ALLOW_DOWNLOAD=1 bash build.sh
```

## CI / CD

Three manually triggered GitHub Actions workflows build the platform artifacts (`exe-build.yml` / `linux-build.yml` / `macos-build.yml`), each followed by an automated GUI smoke test (launch the service + poll port 7860 + verify offline asset restoration); `release-assets.yml` collects the artifacts from the three build runs and uploads them to the Release.

## Known Issues & Fix Log

### Spurious black lines in the output PDF (fixed)

The upstream version produced interwoven solid black lines on some PDFs. Root cause: debug-mode tracing line drawing and the global line-redraw logic in `pdf2zh/converter.py` were triggered unintentionally; the affected code paths in `converter.py` / `pdfinterp.py` / `high_level.py` have been fixed.

### Missing translations (fixed)

The upstream `vfont` formula-font detection regex was too broad, causing body text to be misclassified as formulas and skipped. It has been narrowed to `CM(MI|SY|EX|BSY)`, with improved false-warning logic.

### babeldoc BitStream compatibility

babeldoc requires `bitstring>=4.3.0`, but bitstring 4.x/5.x removed `BitStream`. This project works around it with a monkey-patch (in `pdf2zh/__init__.py` and the `sitecustomize.py` injected at build time).

### Crash on Chinese output in non-UTF-8 terminals (fixed)

On English Windows (cp1252 code page) with output redirection, the Chinese print in the startup banner crashed with `UnicodeEncodeError`. stdout/stderr are now forced to UTF-8 at package level in `pdf2zh/__init__.py`.

## Development

```bash
pytest              # run all tests
pytest -k test_name # a single test
```

## Acknowledgements

Developed on top of [PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate). Many thanks to the original author and all contributors.

## License

[AGPL-3.0](LICENSE)