# Implementation Plan: PDFtranslate Intel 芯片 macOS 适配

**Input**: Feature specification from `spec/macos-intel-adapt/spec.md`

## Summary

为 PDFtranslate 增加 macOS x86_64（Intel）平台支持：通过 PEP 508 平台条件依赖 pin 解决 onnxruntime 等依赖无 Intel macOS wheel 的问题；扩展 `build.sh` 支持 `TARGET_ARCH` 交叉构建参数；macOS CI 工作流改为双架构矩阵（Apple Silicon runner 上交叉构建 x86_64 + Rosetta 2 冒烟测试）；发布与双语 README 同步更新。便携版构建路径（`uv pip install --target`）不依赖 uv.lock，改动风险可控。

## Technical Context

**Language/Version**: Python 3.11–3.12（便携版运行时 3.12，python-build-standalone）
**Primary Dependencies**: onnxruntime（Intel macOS 需 pin 1.19.2）、opencv-python-headless（Intel macOS 需 pin 4.x）、babeldoc 0.2.x、pymupdf 1.25.2、uv（交叉依赖安装）、GitHub Actions（macos arm64 runner）
**State Management**: N/A
**Storage**: N/A（离线资产 zip 沿用现有机制）
**Testing**: CI 冒烟测试（`--version`、GUI 7860 端口探测）+ Rosetta 2 环境执行；本机（Windows）仅做依赖解析审计（`uv pip compile --python-platform` 干跑）
**Target Platform**: macOS 11+（Intel x86_64）便携版 + 源码安装；既有平台零回归
**Project Type**: CLI/GUI 桌面工具（Python），便携版分发
**Performance Goals**: N/A（与 arm64 版对等即可）
**Constraints**: 不得影响 Windows/Linux/macOS arm64 既有构建与依赖解析；CI 不依赖退役中的 macos-13 Intel runner
**Scale/Scope**: 修改 6 个文件 + uv.lock 重新生成

## Project Structure

### Documentation (this feature)

```text
spec/macos-intel-adapt/
├── spec.md              # 需求规格
├── plan.md              # 本文件
└── tasks.md             # 任务清单（Phase 3 生成）
```

### Source Code (repository root)

```text
pyproject.toml                          # 依赖声明：新增 Intel macOS 平台条件 pin
build.sh                                # 便携版构建脚本：新增 TARGET_ARCH 交叉构建支持
uv.lock                                 # 依赖锁：pyproject 变更后重新生成
.github/workflows/macos-build.yml       # macOS CI：双架构矩阵 + Rosetta 2
.github/workflows/release-assets.yml    # 发布流程：纳入 macos-x64 产物
README.md                               # 中文文档：产物表格 + 移除"暂不支持"声明
README.en.md                            # 英文文档：同步更新
```

**Structure Decision**: 遵循项目现有结构，不新增目录或模块。本特性是构建/分发层适配，不触及 `pdf2zh/` 应用代码（`doclayout.py` 通过 `onnxruntime.get_available_providers()` 动态选择 provider，API 在 1.19.2 与 1.31 间兼容，无需改动）。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 同一包双版本解析（onnxruntime 1.31 vs 1.19.2） | Intel macOS 无新版 wheel，必须按平台分叉 | 全平台统一降级 1.19.2 会使其他平台损失 1.20+ 的修复与优化，违反 FR-002/FR-003 |

## Research & Decisions

### R1: onnxruntime 的 Intel macOS 版本边界

- **Decision**: onnxruntime 1.20.0 起停止发布 macOS x86_64 wheel，最后可用版本为 **1.19.2**（含 cp311/cp312 的 macosx_10_15_x86_64 wheel）。Intel macOS 路径 pin `onnxruntime==1.19.2`。
- **Rationale**: uv.lock 显示当前锁定 1.31.0（仅 arm64 mac wheel）；babeldoc 0.2.33 与 rapidocr-onnxruntime 1.4.4 对 onnxruntime 均为不带版本上限的依赖，1.19.2 满足其约束；`doclayout.py` 使用的 `SessionOptions/GraphOptimizationLevel/InferenceSession/get_available_providers` API 在 1.19.2 中全部存在。
- **Alternatives considered**: ① 全平台降级——被否（见 Complexity Tracking）；② 在 Intel macOS 放弃布局模型（禁用 onnx）——被否（核心翻译质量依赖布局识别，违背对等体验目标）。

### R2: 依赖 pin 的声明机制

- **Decision**: 在 `pyproject.toml` 中采用**追加带 marker 的约束行**（PEP 508），而非给现有行加 marker：
  - 保留 `"onnxruntime"`（所有平台，无版本约束）不动，追加 `"onnxruntime==1.19.2; sys_platform == 'darwin' and platform_machine == 'x86_64'"`
  - 追加 `"opencv-python-headless<5; sys_platform == 'darwin' and platform_machine == 'x86_64'"`
  - pip/uv 的同包多约束为**交集**语义：Intel macOS 上解析为 `1.19.2` / `<5`，其他平台仅受原约束，**零变化**。
- **Rationale**: 最小 diff、对其他平台完全无感；`uv pip install`（build.sh 与 CI 路径）不读取 uv.lock，直接按 pyproject 约束从 PyPI 解析，marker 生效路径唯一且确定；Rosetta 2 下运行的 x86_64 Python 的 `platform_machine` 同样报告 `x86_64`，与真实 Intel Mac 一致。
- **Alternatives considered**: ① 拆分 requirements 文件按平台维护——被否（与单文件依赖声明现状冲突，易漂移）；② 构建时用 `--override` 注入——被否（源码安装路径 US2 无法覆盖，pip 安装者拿不到 override）。

### R3: opencv-python-headless 与最低 macOS 版本

- **Decision**: Intel macOS pin `opencv-python-headless<5`（解析到 4.x，含 macosx_10_15/11_0 x86_64 wheel）。
- **Rationale**: 锁定的 5.0.0.93 的 x86_64 wheel 为 `macosx_14_0`（最低 macOS 14），而绝大多数 Intel Mac 止步于 macOS 11–13；4.x 系列的 x86_64 wheel 最低支持 macOS 10.15/11，与目标 macOS 11+ 对齐。arm64 不受影响（仍解析 5.x，arm64 wheel 为 macosx_13_0）。
- **Alternatives considered**: 接受 macOS 14 下限——被否（Spec 目标为 macOS 11+，Intel Mac 用户群大量停留在旧系统）。

### R4: 交叉构建机制（ARM 主机产出 x86_64 便携包）

- **Decision**: `build.sh` macOS 分支新增 `TARGET_ARCH` 环境变量（缺省为空 = 跟随本机架构，现有行为不变）。当 `TARGET_ARCH=x86_64` 且本机为 arm64 时：
  1. 通过 uv 安装 x86_64 的 python-build-standalone（`uv python install` 的架构限定请求；若所用 uv 版本不支持该用法，回退为直接从 python-build-standalone GitHub Releases 下载 `cpython-3.12.x-x86_64-apple-darwin-install_only` 包并解压为 runtime）；
  2. 依赖安装 `uv pip install --python <x86_64 runtime 解释器> --python-platform x86_64-apple-darwin --target build/site-packages .`（显式平台标签覆盖，确保解析 macosx x86_64 wheel）；
  3. `sitecustomize.py`、`launch_pdf2zh.py`、`pdf2zh` 启动器、离线资产打包步骤与 arm64 完全复用；离线资产为架构无关数据，生成时使用同一解释器（Rosetta 2 下可执行 x86_64 解释器）。
- **Rationale**: 不依赖退役中的 macos-13 Intel runner；python-build-standalone 官方提供 x86_64-apple-darwin 产物；ARM macOS 上 Rosetta 2 可执行 x86_64 解释器完成资产打包步骤；产物的 runtime/site-packages/启动器结构与 arm64 版同构（FR-001）。
- **Alternatives considered**: ① macos-13 Intel runner 原生构建——被否（Phase 1 已确认退役风险，用户选择交叉构建）；② 仅用 `--python-platform` 干装不落 runtime——被否（产物必须自带 x86_64 runtime 才能解压即用）。

### R5: CI 工作流设计

- **Decision**: `macos-build.yml` 的 build/test 作业改为 `matrix: arch: [arm64, x86_64]`，`fail-fast: false`：
  - build 作业：`TARGET_ARCH` 传入 `build.sh`；x86_64 分支先执行 Rosetta 2 安装（`softwareupdate --install-rosetta --agree-to-license || true`）；tar 命名 `pdf2zh-macos-{arm64|x64}.tar.gz`；artifact 命名 `macos-exe-{arm64|x64}`。
  - test 作业：按矩阵下载对应 artifact，执行与现状相同的冒烟测试（`--version`、离线资产恢复日志检查、GUI 7860 端口 HTTP 200 探测）；x64 产物在 ARM runner 上经 Rosetta 2 自动以转译模式执行，无需改测试脚本，仅加 Rosetta 安装步骤。
  - babeldoc 资产缓存（actions/cache）与 `ASSETS_ALLOW_DOWNLOAD=1` 按矩阵分支各自保留。
- **Rationale**: 双架构互不阻塞（FR-004）；测试逻辑与 arm64 对等复用；artifact 名变更需与 release-assets.yml 同步（见 R6）。
- **Alternatives considered**: 两个独立 workflow 文件——被否（步骤 95% 重复，维护成本高）。

### R6: 发布流程适配

- **Decision**: `release-assets.yml` 的 macOS 部分改为：从同一 `mac_run_id` 下载 `macos-exe-arm64` 与 `macos-exe-x64` 两个 artifact（zip 套 tar.gz），解出内层 tar.gz 后，将 `pdf2zh-macos-arm64.tar.gz` 与 `pdf2zh-macos-x64.tar.gz` 一并 `gh release upload`。
- **Rationale**: 一次 mac 构建运行即产出双架构（R5 matrix），run id 输入参数数量不变，发布操作语义不变。
- **Alternatives considered**: 增加 `mac_x64_run_id` 独立输入——被否（双架构同 run 产出，拆分输入徒增操作负担）。

### R7: uv.lock 处理

- **Decision**: pyproject 变更后重新生成 uv.lock（`uv lock`）。uv 对 marker 不相交的同包冲突约束会产生**解析分叉**（Intel macOS 分支解析 onnxruntime 1.19.2 / opencv 4.x，其余平台维持现状）。
- **Rationale**: 保持锁文件与声明一致，供 `uv sync` 开发路径使用；便携版构建路径（`uv pip install`）不读锁文件，即使锁生成受阻也不阻塞核心交付（降级策略：在 CI 或有 uv 环境处重锁）。
- **Alternatives considered**: 删除 uv.lock——被否（仓库现状保留锁文件，删除影响开发工作流）。

### R8: 实现期待审计清单（按 R2 机制逐项处理）

- **Decision**: 以下二进制依赖的 macOS x86_64 wheel 可用性在实现首步用干跑审计（`uv pip compile --python-platform x86_64-apple-darwin --python-version 3.12`，可在 Windows 本机执行），缺失或下限过高者按 R2 同机制加 marker pin：
  - numpy：onnxruntime 1.19.2 的 numpy 上限约束与 2.4/2.5 的 x86_64 mac wheel 存在性；
  - onnx（babeldoc 依赖，锁定 1.23.2，需确认 cp312 的 universal2/x86_64 wheel）；
  - scikit-image、tiktoken、pikepdf、orjson、pydantic-core、grpcio 等带二进制扩展的传递依赖；
  - rapidocr-onnxruntime（1.4.4 为纯 Python wheel，已确认无架构问题）。
- **Rationale**: pymupdf 1.25.2（macosx_10_9_x86_64 wheel）、rapidocr-onnxruntime（py3-none-any）已确认可用；其余项逐一人工核对成本高且易漏，干跑解析可在数分钟内暴露全部缺口。
- **Alternatives considered**: 逐包查 PyPI 页面——被否（慢、易漏、不可重复）。

### R9: precise 模式（pdf2zh_next）边界

- **Decision**: `pdf2zh-setup-precise` 安装的 pdf2zh_next 为独立上游仓库（submodule `pdf2zh/kernel/PDFMathTranslate-next.git`），其自身依赖树不受本仓库 pyproject 控制。Intel macOS 上 precise 模式**列为已知限制**（README 不宣传、不承诺），不在本次范围内修复。
- **Rationale**: 跨仓库改动超出本特性边界；fast/GUI 模式（默认路径）已完整覆盖 Intel macOS 体验。
- **Alternatives considered**: fork 并 patch pdf2zh_next——被否（范围蔓延）。

## Data Model

无新增数据实体。本特性涉及的"数据"仅为构建输入/输出约定：

- **TARGET_ARCH**（构建输入，环境变量）：`""`（缺省，跟随本机）| `x86_64` | `arm64`；仅 macOS 分支生效，Windows/Linux 分支忽略。
- **目标产物**（构建输出）：`pdf2zh-macos-x64.tar.gz`，内含 `build/`（x86_64 runtime、site-packages、`offline_assets_*.zip`、`pdf2zh` 启动器、`launch_pdf2zh.py`、`sitecustomize.py`），结构与 `pdf2zh-macos-arm64.tar.gz` 同构。
- **平台条件依赖约束**（pyproject 声明）：形如 `依赖包<版本范围>; sys_platform == 'darwin' and platform_machine == 'x86_64'` 的追加行，仅收窄 Intel macOS 的解析结果。

## Contracts & Interfaces

### C1: build.sh 外部接口（新增）

| 环境变量 | 取值 | 语义 |
|---|---|---|
| `TARGET_ARCH` | 缺省 / 空 | 跟随本机架构（现状行为，不变） |
| `TARGET_ARCH` | `x86_64` | macOS 分支：安装/使用 x86_64 python-build-standalone，依赖解析目标平台为 `x86_64-apple-darwin` |
| `TARGET_ARCH` | `arm64` | macOS 分支：显式指定 arm64（与缺省在本机为 ARM 时等价） |

既有环境变量（`ASSETS_CACHE_DIR`、`ASSETS_ALLOW_DOWNLOAD`）语义不变，交叉构建下同样生效。

### C2: CI 产物命名契约（变更）

| 项 | 现值 | 新值 |
|---|---|---|
| tar.gz 产物 | `pdf2zh-macos-arm64.tar.gz` | `pdf2zh-macos-arm64.tar.gz` + `pdf2zh-macos-x64.tar.gz` |
| build artifact 名 | `macos-exe` | `macos-exe-arm64` + `macos-exe-x64` |
| 发布产物 | （mac 仅 arm64） | 新增 `pdf2zh-macos-x64.tar.gz` 与 arm64 并列 |

`release-assets.yml` 的输入参数（win/linux/mac 三个 run id）保持不变。

### C3: 依赖声明契约（pyproject.toml）

- Intel macOS（`sys_platform == 'darwin' and platform_machine == 'x86_64'`）解析结果：`onnxruntime==1.19.2`、`cryptography<49`（解析到 48.0.1）、`opencv-python-headless<=4.11.0.86`（R8 审计 + CI 实测修复产生的完整 pin 集，见 Changelog）。
- 其他所有平台的解析结果与变更前**逐字节一致**（现有行不修改，仅追加带 marker 的行）。

## Changelog（CI 实测后修订）

### 2026-11: macos-build x86_64 leg 首次真实运行失败 → 追加 cryptography pin 并收紧 opencv 边界

- **现象**：macos-build run 42455171072 中 `build-macos-exe (x86_64, x64)` 失败（作业 128652518227）。`uv pip install` 阶段对 cryptography 50.0.2（pdfminer-six 传递依赖的最新版）触发 maturin/cargo 源码交叉编译，ARM runner 缺 x86_64 OpenSSL 开发库而失败（`OPENSSL_DIR` 未设置）。
- **根因**：cryptography 49.0.0 起不再发布任何 x86_64/universal2 macOS wheel（仅 arm64）。本机干跑审计（`uv pip compile --no-build`）与 CI 实际安装（`uv pip install` 允许源码构建）语义不同：前者遇无 wheel 候选会**回溯**到 48.0.1（`cp39-abi3-macosx_10_9_universal2`，地板 macOS 10.9），后者直接取最新版源码构建。arm64 leg 与 win/linux leg 均不受影响。
- **修复**（与 R2 同机制，两处 marker pin）：
  - `cryptography<49; sys_platform == 'darwin' and platform_machine == 'x86_64'` —— 同时修复便携版（uv pip install）与 Intel macOS 源码安装（pip install .）两条路径；与 toolbox extra 的 `cryptography>=42.0` 交集兼容（48.0.1 满足）。
  - `opencv-python-headless<=4.11.0.86; ...`（原 `<5` 收紧）—— 防止 CI 真实 x86_64 解释器（macOS 15 Rosetta）在 `--python-platform` 标签语义不确定时解析到 4.14.0.94（`macosx_14_0` x86_64 wheel，在 `<5` 约束内），将产物地板抬升至 macOS 14；4.11.0.86 为 `macosx_10_15` x86_64 wheel。
- **验证**：五平台干跑 A/B（新旧 pyproject 各 `uv pip compile --no-build`）依赖行零差异（126/126/121/120/120 包逐行一致）；darwin-x64 锁定 cryptography==48.0.1、opencv-python-headless==4.11.0.86、onnxruntime==1.19.2。
- **经验记录**：`--no-build` 干跑不能完全替代 CI 真机安装验证——回溯语义掩盖了"最新版无 wheel 会走源码构建"的失败路径；PyPI wheel 标签核实（pypi.org/pypi/<pkg>/json）是确定 pin 边界的权威手段。
