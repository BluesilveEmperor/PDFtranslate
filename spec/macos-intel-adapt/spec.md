# Feature Specification: PDFtranslate Intel 芯片 macOS 适配

**Created**: 2026-11-08  
**Status**: Draft  
**Input**: User description: "给这个项目做intel芯片的macos的适配"（项目名：PDFtranslate）

## Overview

PDFtranslate 目前仅提供 Apple Silicon（arm64）macOS 便携版，README 明确声明"Intel 芯片 Mac 暂不支持便携版"。本特性为 macOS x86_64（Intel）平台提供与 arm64 版对等的完整体验：便携版解压即用、源码安装（pip/uv）可用，并纳入 CI 自动构建、Rosetta 2 冒烟测试与发布流程，同时更新双语文档。

核心挑战：`onnxruntime` 1.20+ 已停止发布 macOS x86_64 wheel（最后可用版本为 1.19.2），依赖声明必须按平台条件化 pin，不能影响其他平台的版本范围。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Intel Mac 用户下载并使用便携版 (Priority: P1)

Intel 芯片 Mac 用户（macOS 11+）从 Releases 下载 `pdf2zh-macos-x64.tar.gz`，去除 Gatekeeper 隔离标记后解压，运行 `./build/pdf2zh` 进入 GUI 模式或 `./build/pdf2zh input.pdf` 进行命令行翻译，体验与 Apple Silicon 版完全一致（含离线资产自动解压、首次启动约半分钟的资产加载）。

**Why this priority**: 便携版是本项目推荐的使用方式（README 中标注"推荐，免安装"），是 Intel Mac 用户获得价值的最短路径，也是本次适配的核心交付物。

**Independent Test**: 在 Intel Mac（或 ARM Mac 的 Rosetta 2 环境）解压产物，运行 `--version`、启动 GUI 访问 7860 端口、翻译样例 PDF，验证输出文件生成。

**Acceptance Scenarios**:

1. **Given** 用户已下载 `pdf2zh-macos-x64.tar.gz` 并执行 `xattr -dr com.apple.quarantine build/`，**When** 运行 `./build/pdf2zh --version`，**Then** 正常输出版本号，无 dyld/架构错误
2. **Given** 便携包已解压，**When** 无参数运行 `./build/pdf2zh`（或 `-i`），**Then** 离线资产 zip 自动解压恢复，Gradio GUI 在 7860 端口可访问
3. **Given** GUI 已启动且离线资产就绪，**When** 上传纯文本样例 PDF 并点击翻译，**Then** 生成 `Traned_single_*.pdf` 与 `Traned_double_*.pdf` 且内容正确
4. **Given** 便携包在 Intel Mac 上运行，**When** 执行 `./build/pdf2zh paper.pdf` 命令行翻译，**Then** 翻译正常完成，`.staging/` 中间产物自动清理

---

### User Story 2 - Intel Mac 用户从源码安装运行 (Priority: P2)

Intel Mac 开发者/高级用户通过 `pip install .` 或 `uv` 从源码安装 PDFtranslate，依赖解析在 Intel macOS 上自动生效（含 onnxruntime 平台条件 pin），CLI `pdf2zh` 与 GUI 模式均可正常使用。

**Why this priority**: 源码安装是开发者和贡献者的主要路径，依赖元数据的平台正确性是便携版构建的前置条件（同一份依赖声明）。

**Independent Test**: 在 Intel macOS（或 Rosetta 2 环境）的 Python 3.11/3.12 环境中执行源码安装，验证安装成功且 `pdf2zh --version`、翻译样例 PDF 正常。

**Acceptance Scenarios**:

1. **Given** Intel macOS + Python 3.12 环境，**When** 执行 `uv pip install .`（或 `pip install .`），**Then** 安装成功，无"no matching distribution"错误
2. **Given** 源码安装完成，**When** 运行 `pdf2zh --version` 与 `pdf2zh test.pdf`，**Then** 命令正常执行，翻译产出正确
3. **Given** 非 macOS x86_64 平台（Windows/Linux/Apple Silicon），**When** 解析同一份依赖声明，**Then** 版本范围与适配前完全一致，零回归

---

### User Story 3 - 维护者通过 CI 构建、测试并发布 Intel 便携版 (Priority: P3)

维护者触发 macOS 构建工作流后，CI 在 Apple Silicon runner 上交叉构建 x86_64 便携包（不依赖已退役/退役中的 macos-13 Intel runner），在 Rosetta 2 下完成冒烟测试，产出可上传至 Release 的 `pdf2zh-macos-x64.tar.gz` artifact；发布资产工作流支持将该产物纳入 Release。

**Why this priority**: 没有自动化构建与发布流程，前两个用户故事无法持续交付；放在便携版可用性验证之后构建，可确保流程建立在被验证的产物结构上。

**Independent Test**: 手动触发工作流，观察构建、Rosetta 2 测试步骤全绿，artifact 下载后可解压运行。

**Acceptance Scenarios**:

1. **Given** 维护者触发 macOS 构建工作流，**When** 构建任务运行，**Then** 在 Apple Silicon runner 上产出 x86_64 架构的便携包（runtime、site-packages 二进制均为 x86_64）
2. **Given** x86_64 便携包构建完成，**When** CI 在 Rosetta 2 环境执行冒烟测试（`--version`、GUI 7860 端口探测），**Then** 测试全部通过
3. **Given** 构建与测试通过，**When** artifact 上传并经发布工作流处理，**Then** Release 页面出现 `pdf2zh-macos-x64.tar.gz` 且可下载
4. **Given** 同一工作流同时产出 arm64 与 x86_64 两个产物，**When** 任一架构构建失败，**Then** 互不阻塞（fail-fast 关闭）

---

### User Story 4 - 用户查阅文档了解 Intel 版用法 (Priority: P4)

用户阅读 README（中/英），在便携版产物表格中看到 `pdf2zh-macos-x64.tar.gz`（macOS 11+，Intel）一行及对应使用说明，原有"Intel 芯片 Mac 暂不支持便携版"声明被移除。

**Why this priority**: 文档是用户发现和使用新产物的入口，但价值依赖前三个故事的产物实际存在。

**Independent Test**: 检查 README.md / README.en.md 中产物表格、macOS 使用章节已更新且与实际产物名一致。

**Acceptance Scenarios**:

1. **Given** 用户打开 README.md，**When** 查看便携版产物表格，**Then** 存在 `pdf2zh-macos-x64.tar.gz | macOS 11+ | Intel` 行
2. **Given** 用户阅读 macOS 章节，**When** 查找 Intel 支持声明，**Then** 不再出现"暂不支持"，且 Gatekeeper 隔离处理说明对两种架构均适用

---

### Edge Cases

- **Rosetta 2 环境缺失**：CI runner 未安装 Rosetta 2 时，冒烟测试步骤需能自动安装（`softwareupdate --install-rosetta`）或给出明确失败原因，不得静默跳过
- **离线资产跨架构**：离线资产包（字体、布局 ONNX 模型）与 CPU 架构无关，但需在 x86_64 环境验证解压恢复与模型加载路径无架构假设
- **依赖 wheel 缺失**：若审计发现除 onnxruntime 外仍有依赖无 macOS x86_64 wheel（如 pymupdf、opencv-python-headless 的特定版本），需按同样的平台条件化 pin 处理；若某依赖完全无任何 x86_64 macOS 版本，构建须给出明确报错而非产出坏包
- **Apple Silicon 上误运行 x64 包**：用户在 M 系列 Mac 上解压了 x64 包时，应能通过 Rosetta 2 运行（自然兼容），无需额外处理，文档不承诺此场景
- **uv 交叉安装的平台标签**：交叉安装的 site-packages 中纯 Python 包与二进制包混合，需保证产物在真实 Intel Mac 上无架构混装

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 构建系统 MUST 支持"目标架构"参数（如 `TARGET_ARCH=x86_64`），在 Apple Silicon 主机上产出完整 x86_64 便携包，目录结构与 arm64 版一致（`build/runtime`、`build/site-packages`、离线资产 zip、`pdf2zh` 启动器、`launch_pdf2zh.py`）
- **FR-002**: 依赖声明 MUST 保证 macOS x86_64 平台上全部依赖可解析安装；对停止发布 x86_64 macOS wheel 的依赖（onnxruntime），MUST 仅在 Intel macOS 平台条件下 pin 到最后可用版本（1.19.2），其他平台的版本范围 MUST 保持不变
- **FR-003**: 默认构建行为（不指定目标架构时跟随本机架构）MUST 与现状完全兼容，既有 Windows/Linux/macOS arm64 构建流程零回归
- **FR-004**: CI 的 macOS 构建工作流 MUST 在 Apple Silicon runner 上同时产出 arm64 与 x86_64 两个便携包，互不阻塞，且两个产物名符合 `pdf2zh-macos-{arm64|x64}.tar.gz` 约定
- **FR-005**: CI MUST 对 x86_64 产物在 Rosetta 2 环境下执行冒烟测试，至少覆盖：`--version` 输出、离线资产恢复日志、GUI 7860 端口 HTTP 200 探测
- **FR-006**: 发布资产工作流（release-assets.yml）MUST 支持将 `pdf2zh-macos-x64.tar.gz` 上传至 Release，与现有 win64/linux/arm64 产物并列
- **FR-007**: README.md 与 README.en.md MUST 更新：产物表格增加 macos-x64 行，移除"Intel 暂不支持"声明
- **FR-008**: 源码安装路径（pip/uv，Python 3.11–3.12）在 Intel macOS 上 MUST 可安装、可运行，平台条件 pin 在该路径自动生效
- **FR-009**: 交叉构建 MUST 复用现有离线资产打包逻辑（`make_offline_assets.py`），资产内容与架构无关、与 arm64 产物一致

### Key Entities

- **目标产物**: `pdf2zh-macos-x64.tar.gz` — 内含 `build/` 目录（x86_64 便携 Python runtime、site-packages、离线资产 zip、启动脚本），与 arm64 产物同构
- **平台条件依赖约束**: pyproject 依赖声明中按 `sys_platform == "darwin" and platform_machine == "x86_64"`（PEP 508 环境标记）条件化的版本 pin，仅影响 Intel macOS 的依赖解析
- **交叉构建参数**: `build.sh` 的目标架构环境变量，控制 python-build-standalone 下载目标（x86_64-apple-darwin）与依赖安装目标平台（`uv --python-platform x86_64-apple-darwin`）

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Intel macOS（或 Rosetta 2 环境）上解压 x64 便携包后，`./build/pdf2zh --version`、GUI 7860 端口访问、样例 PDF 翻译 3 项验证 100% 通过
- **SC-002**: `uv pip install .` 在 Intel macOS 的 Python 3.12 环境一次成功，`pdf2zh` CLI 可翻译样例 PDF
- **SC-003**: CI 工作流触发一次即产出 arm64 + x64 两个 macOS 便携包 artifact，Rosetta 2 冒烟测试全绿
- **SC-004**: 适配前后，Windows/Linux/macOS arm64 三条既有构建产物依赖解析结果零变化（diff 为空）
- **SC-005**: 双语 README 各含 1 处 macos-x64 产物行，0 处"Intel 暂不支持"残留

## Assumptions

- 目标系统为 macOS 11+ 的 Intel Mac（x86_64）；实际最低版本以所选依赖 wheel 的最低系统要求为准，不单独承诺更低版本
- Rosetta 2 仅用于 CI 冒烟测试环境，最终用户在 Intel Mac 上原生运行，不对 Rosetta 场景做性能承诺
- 离线资产（字体、BabelDOC 布局 ONNX 模型）与 CPU 架构无关，可直接复用现有生成逻辑与缓存
- 不制作 macOS Universal2 双架构单包，沿用"平台-架构"独立产物分发方式
- pymupdf、opencv-python-headless 等其余二进制依赖假定在 Python 3.12 + macOS x86_64 存在可用 wheel，实现前经审计确认；若个别缺失，按 FR-002 同样方式处理
- `babeldoc`（>=0.1.22,<0.3.0）的依赖链假定兼容 onnxruntime 1.19.2；若审计发现冲突，在实现期以平台条件覆盖解决
- GitHub Actions 的 Apple Silicon runner（macos-latest/macos-14+）长期可用，Rosetta 2 可通过软件更新自动安装

## Open Questions

- [实现期审计] babeldoc 对 onnxruntime 的版本约束下限是否与 1.19.2 冲突？若冲突，Intel macOS 路径的布局模型推理是否需要替代方案或版本妥协（如 babeldoc 降版本 pin）
- [实现期审计] 除 onnxruntime 外，pymupdf<1.25.3、opencv-python-headless、onnx 等二进制依赖在 macOS x86_64 + Python 3.11/3.12 的 wheel 可用性与最低 macOS 版本
- [低优先] 是否需要在 CI 冒烟测试中增加真实 PDF 翻译用例（现有 macos-build.yml 仅测 --version 与 GUI 起服），还是保持与 arm64 流程对等
