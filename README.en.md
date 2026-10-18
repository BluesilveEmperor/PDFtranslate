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