# Tasks: PDFtranslate Intel 芯片 macOS 适配

**Input**: Design documents from `spec/macos-intel-adapt/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: 未在规格中显式要求新增测试套件；验证依赖现有 CI 冒烟测试与本机干跑审计。

**Organization**: 按用户故事分组（US1 便携版 → US2 源码安装 → US3 CI → US4 文档），Setup/Foundational 前置。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无依赖冲突）
- **[Story]**: 所属用户故事（US1–US4，映射 spec.md）

## Path Conventions

- 仓库根目录直接放置构建脚本与工作流：`build.sh`、`pyproject.toml`、`uv.lock`、`README.md`、`README.en.md`
- GitHub Actions 工作流：`.github/workflows/*.yml`
- 规格文档：`spec/macos-intel-adapt/`（本特性）
- 本项目无 `src/` 目录，Python 包为根目录 `pdf2zh/`（本特性不修改应用代码）

---

## Phase 1: Setup（共享基础设施）

**Purpose**: 准备本机（Windows）可执行的依赖审计工具链

- [X] T001 检查/安装 uv 工具链并确认支持 `--python-platform` 交叉解析（`uv --version`、`uv pip compile --help` 核对参数；缺失则经 pip 或官方安装器安装），记录版本到实施报告

---

## Phase 2: Foundational（阻塞性前置）

**Purpose**: 完成 Intel macOS 依赖解析审计与 pyproject 平台条件 pin——所有用户故事的地基

**⚠️ CRITICAL**: 本阶段完成前不得开始任何用户故事

- [X] T002 用 `uv pip compile --python-platform x86_64-apple-darwin --python-version 3.12`（及 3.11）对当前依赖声明干跑解析，逐项审计 plan.md R8 清单（numpy、onnx、scikit-image、tiktoken、pikepdf、orjson、pydantic-core、grpcio 等）在 macOS x86_64 的 wheel 可用性与最低 macOS 版本，产出需加 marker pin 的包清单（含具体版本边界）
- [X] T003 在 pyproject.toml 的 `dependencies` 中追加 Intel macOS 平台条件 pin 行（不改现有行）：`onnxruntime==1.19.2; sys_platform == 'darwin' and platform_machine == 'x86_64'`、`opencv-python-headless<5; sys_platform == 'darwin' and platform_machine == 'x86_64'`，以及 T002 审计确定的其他包（注意 TOML 字符串内使用单引号包裹 marker 值）
- [X] T004 交叉验证其他平台零回归：对 `aarch64-apple-darwin`、`x86_64-unknown-linux-gnu`、`windows` 三个目标平台干跑解析，对比 T003 前后解析结果，确认除 Intel macOS 外逐包一致（满足 FR-003/SC-004）

**Checkpoint**: 依赖声明就绪，Intel macOS 可解析、其他平台零变化

---

## Phase 3: User Story 1 - Intel Mac 便携版 (Priority: P1) 🎯 MVP

**Goal**: `build.sh` 支持 `TARGET_ARCH=x86_64` 在 ARM 主机交叉产出 x86_64 便携包

**Independent Test**: `bash -n build.sh` 语法通过；缺省 `TARGET_ARCH` 时脚本执行路径与现状逐行一致；交叉依赖安装干跑可产出 x86_64 site-packages 布局（CI 上完整构建）

### Implementation for User Story 1

- [X] T005 [US1] 为 build.sh 的 Linux/macOS 分支新增 `TARGET_ARCH` 环境变量支持（plan.md C1 契约）：缺省/空 = 跟随本机（现状不变）；`x86_64` = macOS 下经 uv 安装 x86_64 python-build-standalone（uv 不支持时回退 GitHub Releases 直接下载 install_only 包解压为 runtime），依赖安装加 `--python-platform x86_64-apple-darwin`，sitecustomize.py/launch_pdf2zh.py/启动器/离线资产步骤原样复用；Windows 分支忽略该变量
- [X] T006 [US1] 校验 build.sh：`bash -n` 语法检查；人工走查确认 `TARGET_ARCH` 缺省时与 git HEAD 版本行为零差异（diff 对比确认仅新增分支逻辑）；确认产物 tar 命名遵循 `pdf2zh-macos-{arch}.tar.gz` 约定（plan.md C2）

**Checkpoint**: 便携版交叉构建脚本就绪（完整构建由 US3 的 CI 执行）

---

## Phase 4: User Story 2 - Intel Mac 源码安装 (Priority: P2)

**Goal**: pip/uv 源码安装在 Intel macOS 上依赖解析自动生效，uv.lock 与声明同步

**Independent Test**: 干跑解析确认 Intel macOS 解析出 onnxruntime 1.19.2 / opencv 4.x；uv.lock 出现 Intel macOS 解析分叉；其他平台锁定结果不变

### Implementation for User Story 2

- [X] T007 [P] [US2] 用 uv 重新生成 uv.lock（`uv lock`）：验证产生解析分叉——Intel macOS 分支 onnxruntime==1.19.2、opencv-python-headless 4.x，其余平台维持 1.31.0 / 5.0.0.93；对比旧锁确认非 macOS-x86_64 平台条目无变化
- [X] T008 [US2] 验证源码安装路径（FR-008）：以 `uv pip compile --python-platform x86_64-apple-darwin --python-version 3.11`（及 3.12）对项目根 pyproject 干跑，确认 marker 在 Python 3.11/3.12 两版本均生效且全依赖可解析

**Checkpoint**: 源码安装路径就绪，锁文件与声明一致

---

## Phase 5: User Story 3 - CI 构建/测试/发布 (Priority: P3)

**Goal**: macOS CI 双架构矩阵 + Rosetta 2 冒烟测试 + 发布流程纳入 x64 产物

**Independent Test**: workflow YAML 解析通过；matrix/artifact/tar 命名与 plan.md C2 契约逐项一致；测试步骤逻辑与 arm64 现状对等

### Implementation for User Story 3

- [X] T009 [US3] 改造 .github/workflows/macos-build.yml：build/test 两作业加 `matrix: arch: [arm64, x86_64]` + `fail-fast: false`；`TARGET_ARCH` 传入 build.sh；x86_64 分支前置 Rosetta 2 安装步骤（`softwareupdate --install-rosetta --agree-to-license || true`）；tar 命名 `pdf2zh-macos-{arm64|x64}.tar.gz`、artifact 命名 `macos-exe-{arm64|x64}`；babeldoc 资产缓存与 `ASSETS_ALLOW_DOWNLOAD=1` 按矩阵分支保留；测试作业按矩阵下载对应 artifact 执行既有冒烟测试
- [X] T010 [P] [US3] 改造 .github/workflows/release-assets.yml：macOS 部分从同一 `mac_run_id` 下载 `macos-exe-arm64` 与 `macos-exe-x64` 两个 artifact，解出内层 tar.gz 后将两个 macOS 产物与 win/linux 一并 `gh release upload`；输入参数（三个 run id）不变
- [X] T011 [US3] 校验 workflow：用 Python yaml（或 actionlint/yamllint 若可用）解析两个 workflow 文件确认语法有效；人工走查 matrix 展开、needs/artifact 传递、upload/download artifact 名匹配

**Checkpoint**: CI/发布流程就绪（实际运行需推送后由维护者手动触发 workflow_dispatch）

---

## Phase 6: User Story 4 - 双语文档更新 (Priority: P4)

**Goal**: README 中英文同步反映 Intel macOS 支持

**Independent Test**: 产物表格含 macos-x64 行；全文检索无"Intel 暂不支持"残留（中文与对应英文表述）

### Implementation for User Story 4

- [X] T012 [P] [US4] 更新 README.md：便携版产物表格增加 `pdf2zh-macos-x64.tar.gz | macOS 11+ | Intel` 行；删除"macOS 仅提供 Apple Silicon 版；Intel 芯片 Mac 暂不支持便携版"声明；按 plan.md R9 在合适位置注明 precise 模式（--mode precise）在 Intel macOS 上为已知限制
- [X] T013 [P] [US4] 更新 README.en.md：与 T012 逐项对应（产物表格行、删除 Intel 不支持声明、precise 限制注明）

**Checkpoint**: 文档与实际产物/能力一致

---

## Phase 7: Polish（横切收尾）

**Purpose**: 跨故事一致性检查与清理

- [X] T014 全仓一致性检查：grep 确认无"暂不支持"残留（README.md/README.en.md 及其他文档）；确认所有产物命名与 plan.md C2 契约一致；确认 pyproject marker 表述（darwin + x86_64）在 pyproject/build.sh/workflows 中语义统一；更新 spec/macos-intel-adapt/ 下任务勾选状态

---

## Phase 8: Verification

<!-- verification_scope: build-only -->

**Purpose**: 构建级验证（本机为 Windows，macOS x64 产物构建与 GUI 冒烟由 CI 承担；本阶段验证依赖可解析性、脚本/workflow 有效性与零回归）

- [X] T015 全平台依赖解析最终验证：对 `x86_64-apple-darwin`（3.11/3.12）、`aarch64-apple-darwin`、`x86_64-unknown-linux-gnu`、`windows` 干跑 `uv pip compile`，全部成功且与 T004 基线一致；失败则修复（marker/版本边界）后重跑
- [X] T016 部署就绪静态校验：`bash -n build.sh` 通过；两个 workflow YAML 解析通过；pyproject.toml 可被 uv 解析（`uv lock --check` 或等价校验）；确认 git 变更集仅含 plan.md Project Structure 所列文件

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，立即开始
- **Foundational (Phase 2)**: 依赖 Phase 1（uv 工具链就绪）——**阻塞所有用户故事**
- **US1 (Phase 3)**: 依赖 T003（依赖声明）完成后开始
- **US2 (Phase 4)**: 依赖 T003；T007 可与 US1 并行
- **US3 (Phase 5)**: 依赖 T005/T006（build.sh 契约就绪）
- **US4 (Phase 6)**: 依赖 T009（产物命名最终确认）
- **Polish (Phase 7)**: 依赖全部用户故事完成
- **Verification (Phase 8)**: 依赖 T004 基线与 Phase 7 完成

### User Story Dependencies

- **US1 (P1)**: Foundational 后即可开始，不依赖其他故事——MVP 核心
- **US2 (P2)**: Foundational 后即可开始，与 US1 无文件冲突，可并行
- **US3 (P3)**: 依赖 US1 的 build.sh 契约（T005），产物命名引用其接口
- **US4 (P4)**: 依赖 US3 确定最终产物命名（虽 plan.md C2 已固定，仍以实现结果为准）

### Within Each User Story

- 审计（T002）先于声明（T003），声明先于回归验证（T004）
- 脚本实现（T005）先于脚本校验（T006）
- workflow 实现（T009/T010）先于 workflow 校验（T011）

## Parallel Example: US2 × US1

```bash
# T007 与 T005 并行（不同文件，均依赖 T003）：
Task: "T007 重新生成 uv.lock（uv.lock）"
Task: "T005 build.sh 新增 TARGET_ARCH 交叉构建（build.sh）"

# US4 内部两任务并行（不同文件）：
Task: "T012 更新 README.md"
Task: "T013 更新 README.en.md"
```

## Implementation Strategy

### MVP First（US1 优先）

1. 完成 Phase 1（Setup）+ Phase 2（Foundational）
2. 完成 Phase 3（US1 便携版交叉构建脚本）
3. **STOP and VALIDATE**: `bash -n` + 缺省路径 diff 走查 + 交叉解析干跑
4. CI 完整构建验证（推送后触发 macos-build workflow）

### Incremental Delivery

1. Setup + Foundational → 依赖声明就绪（US2 源码安装路径即刻生效）
2. + US1 → 便携版交叉构建脚本（MVP）
3. + US2 → uv.lock 同步（开发路径一致）
4. + US3 → CI 自动化构建/测试/发布
5. + US4 → 文档对外可见
6. Polish + Verification → 收尾验证

## Notes

- **总任务数**: 16（T001–T016）
- **按阶段**: Setup 1 / Foundational 3 / US1 2 / US2 2 / US3 3 / US4 2 / Polish 1 / Verification 2
- **按故事**: US1（P1）2、US2（P2）2、US3（P3）3、US4（P4）2、横切 7
- **并行机会**: T005×T007、T012×T013、T010 与 T009 后半
- **MVP 范围**: T001–T006
- [P] 任务 = 不同文件、无依赖冲突
- [Story] 标签映射 spec.md 用户故事，保证可追溯
- 每个故事独立可测试；在任意 Checkpoint 停下均可独立验证
- 本机为 Windows：macOS 产物构建、Rosetta 2 冒烟测试必须经 CI（推送后手动触发 workflow_dispatch）完成，本机验证止于干跑解析与静态校验
