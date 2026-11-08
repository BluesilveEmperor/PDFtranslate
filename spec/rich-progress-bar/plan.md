# Implementation Plan: 翻译进度条彩色化（pip 风格 rich 进度条）

**Input**: Feature specification from `spec/rich-progress-bar/spec.md`

## Summary

将翻译过程中终端纯色 tqdm 进度条升级为 pip 风格 rich 彩色进度条，覆盖三个场景：CLI fast 模式（high_level 自研管线）、GUI 模式控制台（同一管线）、CLI precise 模式（pdf2zh_next 子进程，父进程渲染）。核心手段：新建统一进度模块（数据模型 `ProgressInfo` + 渲染器族 rich/tqdm + 工厂），将现有耦合 tqdm 对象的回调接口（`callback(t: tqdm)`）归一化为纯数据回调（`callback(info: ProgressInfo)`），渲染与数据上报彻底解耦；CLI 增加 `--progress-style` 回退开关（默认 rich）。

## Technical Context

**Language/Version**: Python 3.11–3.12（requires-python >=3.11,<3.13）
**Primary Dependencies**: rich（已在依赖树）、tqdm（已在依赖树）、babeldoc 0.2.x（fast 内核底层、precise 子进程底层）
**State Management**: N/A（CLI/进程内进度状态，无持久化）
**Storage**: N/A
**Testing**: 人工终端验证 + CI 冒烟（macos/win/linux build 的 GUI 启动 + 7860 端口轮询，判据不变）
**Target Platform**: Windows / Linux / macOS 终端（含 ANSI 支持检测与降级）
**Project Type**: CLI + GUI（gradio）桌面工具
**Performance Goals**: 进度更新不拖慢翻译（渲染刷新频率限制在 rich 默认 10 次/秒以内；回调传递为纯内存对象构造，开销可忽略）
**Constraints**: 零新增第三方依赖；GUI 网页端进度、celery 后端上报零回归；CI 冒烟判据不变
**Scale/Scope**: 改动 7 个文件 + 新增 1 个模块，接口重构型小特性

## Project Structure

### Documentation (this feature)

```text
spec/rich-progress-bar/
├── spec.md              # 需求规格
├── plan.md              # 本文件
└── tasks.md             # 任务拆解（Phase 3 生成）
```

### Source Code (repository root)

```text
pdf2zh/
├── progress.py           # [新增] ProgressInfo 数据模型 + 渲染器族（Rich/Tqdm/Null）+ 工厂 + 全局样式配置
├── high_level.py         # [修改] translate_patch 管线：tqdm → 渲染器；callback 改传 ProgressInfo
├── pdf2zh.py             # [修改] CLI 增加 --progress-style 参数；解析后写入全局样式；yadt_main 联动 use_rich_pbar
├── gui.py                # [修改] progress_bar 回调改为消费 ProgressInfo → gradio 进度
├── backend.py            # [修改] progress_bar 回调改为消费 ProgressInfo → celery 状态上报
├── mcp_server.py         # [修改] 若其 translate 调用接收 callback，同步适配 ProgressInfo（实现期核查）
└── kernel/
    └── precise.py        # [修改] 父进程消费 v2_worker 进度事件 → 渲染器渲染 + callback(ProgressInfo)
```

**Structure Decision**: 遵循现有项目架构（pdf2zh 包内平铺模块 + kernel 子包），仅新增一个进度模块 `pdf2zh/progress.py` 承载渲染器与数据模型，不引入新目录层级。该模块是三场景共用的唯一渲染实现点，避免 rich 渲染逻辑散落在 high_level/gui/precise 三处。

## Complexity Tracking

无 Constitution Check 违规。单一新模块 + 既有文件接口适配，无过度设计。

## Research & Decisions

### 现状调研结论（进度条全景）

| 场景 | 调用链 | 当前进度渲染 | 问题 |
|---|---|---|---|
| CLI fast（默认） | main → KernelRegistry(fast) → LegacyKernel → high_level.translate → translate_stream → translate_patch | tqdm 纯色（high_level.py:150/248/262 三处） | 无彩色 |
| CLI precise | main → KernelRegistry(precise) → PreciseKernel → v2_worker 子进程（pdf2zh_next） | 子进程内 pdf2zh_next 自行渲染；事件 JSON 转发父进程 | 父进程无统一渲染 |
| CLI --babeldoc（实验） | yadt_main → babeldoc create_progress_handler | rich 彩色（babeldoc 默认 use_rich_pbar=True） | 已达标，仅开关联动 |
| GUI fast/fast 网页 | gui.translate_file → KernelRegistry → LegacyKernel → 同 CLI fast | 控制台 tqdm 纯色 + 网页 gradio 进度（progress_bar 回调读 tqdm 属性） | 控制台无彩色；回调耦合 tqdm |
| GUI precise | gui → PreciseKernel | 同 CLI precise；GUI 回调收到事件 dict 时按 tqdm 访问会出错 | 回调接口不统一（隐患） |
| backend（celery） | translate_task → translate_stream | 回调读 tqdm 属性 → celery 状态 | 回调耦合 tqdm |

### R1: 统一进度数据模型（ProgressInfo）

- **Decision**: 新增纯数据进度对象 `ProgressInfo`（字段见 Data Model），所有回调签名统一为 `callback(info: ProgressInfo)`；渲染器消费同一对象。
- **Rationale**: 现有回调把 tqdm 实例直接传给消费方（gui.py:599 读 `t.n/t.total`、backend.py:45 同），是 GUI 被迫关闭彩色渲染（gui.py:749 use_rich_pbar=False）的根因，也是 precise 模式向 GUI 回调传事件 dict 的接口裂缝。数据与渲染解耦后，终端样式可自由替换，消费方零感知。
- **Alternatives considered**: 保留 tqdm 对象传递、给 rich 渲染器做 tqdm 属性伪装（duck-typing shim）——被否：伪装层脆弱（tqdm 属性集大且含方法），且 precise/事件型进度源根本没有 tqdm 对象可伪装。

### R2: 渲染器族 + 工厂（progress.py 单模块）

- **Decision**: `pdf2zh/progress.py` 内实现三类渲染器，统一接口（start/update/finish/close，支持上下文管理器）：
  - `RichRenderer`：rich Progress（描述列 + 彩条 + 完成数 M/N + 已耗时 + 剩余时间预估），列组合与 babeldoc 内置 rich 模式一致（`TextColumn/BarColumn/MofNCompleteColumn/TimeElapsedColumn/TimeRemainingColumn`），保证 `--babeldoc` 与 fast/precise 三场景观感一致；
  - `TqdmRenderer`：纯色回退（包装 tqdm，行为对齐现状）；
  - `NullRenderer`：无输出（关闭进度）。
  - 工厂 `create_renderer()` 按全局样式 + 环境自动选择：默认 rich；`PDF2ZH_PROGRESS=plain/tqdm` 或 CLI `--progress-style plain` → tqdm；`NO_COLOR` 环境变量或 stdout 非 TTY（重定向）→ 降级 tqdm/无 ANSI 输出（rich 自身亦具备非终端降级能力，工厂层显式兜底）。
- **Rationale**: 渲染可替换性是本特性核心；rich 与 pip 进度条同源，默认观感即达标。单模块集中实现避免三处调用点各自渲染逻辑漂移。
- **Alternatives considered**: 直接在各管线内散写 rich Progress——被否：fast/precise/GUI 三处重复，且回退开关无处统一生效。

### R3: fast 管线改造（high_level.translate_patch）

- **Decision**: translate_patch 内三处 tqdm（页面主循环 150、段落翻译 248、排版 262）替换为工厂创建的渲染器；阶段描述沿用现有文案（"Translate paragraphs"/"Typeset pages" 等）；`callback(progress)` 三处调用点改为构造 `ProgressInfo`（stage/current/total/overall/message）后调用 `callback(info)`。overall 进度语义：页面循环按已完成页/总页；段落翻译与排版阶段按阶段内进度换算为总体进度（实现期定义换算权重，保持单调不减）。
- **Rationale**: 最小侵入：管线结构、阶段划分、取消机制（cancellation_event）全部不动，只替换显示层与回调数据。
- **Alternatives considered**: 重构整条管线为事件流架构——被否：范围蔓延，本特性只需换显示层。

### R4: 消费方适配（gui/backend/mcp）

- **Decision**: gui.py `progress_bar`、backend.py `progress_bar` 改为消费 ProgressInfo：GUI → `gradio progress(info.overall, desc=info.message)`；backend → `update_state(meta={"n": info.current, "total": info.total})`。mcp_server.py 在实现期核查是否存在 callback 消费点，同步适配。
- **Rationale**: 消费方只关心数值与描述文案，ProgressInfo 字段覆盖两者；适配后 FR-006/FR-007 同时满足。
- **Alternatives considered**: 在消费方做 tqdm/rich 双类型兼容判断——被否：类型分支不可枚举（dict/事件/对象），归一化才是根治。

### R5: CLI 回退开关

- **Decision**: 新增 `--progress-style {rich,plain}`（默认 rich），解析后写入 progress 模块的全局样式配置；同时支持环境变量 `PDF2ZH_PROGRESS`（取值 rich/plain）供 GUI/脚本场景覆盖。默认彩色。
- **Rationale**: 满足 FR-004；枚举式参数比布尔开关（--no-rich）更可扩展（未来可加 off/auto）；环境变量覆盖让无 CLI 参数的入口（GUI 便携版直接双击）也能切换。
- **Alternatives considered**: `--no-rich-progress` 布尔 flag——被否：不可扩展，且与 pip 的 `--progress-bar <style>` 枚举风格不一致。

### R6: precise 模式父进程渲染

- **Decision**: PreciseKernel 在父进程消费 v2_worker 转发的进度事件 JSON（stage/stage_progress/overall_progress 等字段已存在），转换为 ProgressInfo 后：a) 喂给工厂创建的渲染器（父进程终端彩色显示）；b) 调用 callback(info) 通知 GUI/backend。子进程 stderr 中的非进度日志行维持现状（父进程原样打印）。
- **Rationale**: 子进程内部渲染输出被父进程按行读取转发，rich 多行 live 输出无法安全透传（ANSI 光标控制序列按行拆分会乱码）；父进程统一渲染是唯一干净路径。同时天然修复 GUI precise 回调接口裂缝（R1 隐患）。
- **Alternatives considered**: 子进程直通终端（PTY 转发）——被否：复杂度高，Windows 无原生 PTY。

### R7: --babeldoc 路径联动

- **Decision**: yadt_main 中 `use_rich_pbar = (全局样式 == rich)`（当前默认 True 行为保持），继续复用 babeldoc 内置 rich 渲染（其列组合与 R2 的 RichRenderer 一致，观感统一）。
- **Rationale**: babeldoc 内置实现已达标，不重复造轮子；仅将开关与全局样式联通。
- **Alternatives considered**: 弃用 babeldoc 内置、统一走自研渲染器——被否：yadt 事件流与自研渲染器对接成本高且无收益。

### R8: rich 与日志输出共存

- **Decision**: 接受 rich Progress live 区与 logger 输出（RichHandler/普通 logging）的常规交错（`--babeldoc` 路径现状即如此，可用性已验证）；RichRenderer 支持注入共享 Console 作为实现期调优手段（若交错严重则与 RichHandler 共享同一 Console）。GUI 控制台中 gradio 访问日志与进度条的交错同样接受。
- **Rationale**: 完全消除交错需要接管全部输出流，收益低侵入大；babeldoc 路径已证明交错可接受。
- **Alternatives considered**: logging 全部重定向进 rich Live 区（rich.console 重定向）——被否：影响面大，非本特性目标。

## Data Model

### ProgressInfo（纯数据进度对象，progress.py 定义）

| 字段 | 类型 | 语义 |
|---|---|---|
| `stage` | str | 阶段标识（如 page_scan / translate_paragraphs / typeset / precise 子阶段名） |
| `current` | int \| float | 当前阶段进度当前值 |
| `total` | int \| float | 当前阶段进度总值 |
| `overall` | float | 总体进度 0.0–1.0（跨阶段单调不减，供网页端/celery 消费） |
| `message` | str | 人类可读描述（供网页端 gradio desc 与渲染器描述列） |

### 渲染器接口（progress.py，Protocol）

- `start(total, message)` / `update(current, total, message, overall)` / `finish()` / `close()`；支持上下文管理器（进入即 start、退出即 finish+close），对齐现有 `with tqdm.tqdm(...) as progress` 的使用形态。
- 工厂 `create_renderer()`：读取全局样式（默认 rich），叠加环境降级规则（NO_COLOR / 非 TTY / PDF2ZH_PROGRESS）返回具体渲染器实例。

### 全局样式配置（progress.py 模块级）

- 默认值 `rich`；CLI `--progress-style` 解析后调用模块级设置函数覆盖；环境变量 `PDF2ZH_PROGRESS` 在导入时读取。

## Contracts & Interfaces

### C1: 回调签名契约（变更）

| 项 | 现状 | 新契约 |
|---|---|---|
| callback 参数 | tqdm 实例（gui/backend 直读 .n/.total/.desc）；precise 为事件 dict | `callback(info: ProgressInfo)` 单一形态 |
| 消费方 | gui.py / backend.py / mcp_server.py（核查） | 同左，签名统一 |

### C2: CLI 参数契约（新增）

`--progress-style {rich,plain}`，默认 `rich`；环境变量 `PDF2ZH_PROGRESS=rich|plain` 同义覆盖（CLI 参数优先）。

### C3: 渲染器行为契约

- rich：多阶段分行彩条（描述/彩条/M/N/已耗时/ETA），退出时进度条定格收尾，无 ANSI 残留；
- plain：单行 tqdm，行为对齐现状；
- 非 TTY / 重定向：无 ANSI 控制序列输出（进度以纯文本行或无输出呈现），日志文件无乱码；
- 取消/异常：渲染器上下文正确退出，终端光标复位。

### C4: precise 事件转换契约

v2_worker 转发的进度事件 JSON（progress_start/progress_update/progress_end，含 stage/stage_current/stage_total/overall_progress 字段）在 PreciseKernel 内转换为 ProgressInfo 后分发（渲染 + callback）；转换不丢失 overall_progress 字段。

### C5: 零回归契约

- GUI 网页进度：翻译全流程 0→100% 推进，取消操作正常；
- backend celery 状态上报字段（n/total）语义不变；
- 依赖声明（pyproject.toml）零变更（rich/tqdm 均已在树内）；
- CI 冒烟（GUI 启动 + 7860 端口 + 离线资产恢复日志判据）不受影响。
