# Feature Specification: 翻译进度条彩色化（pip 风格 rich 进度条）

**Created**: 2026-11-08  
**Status**: Draft  
**Input**: User description: "翻译时终端里的进度条我要pip安装第三方库的时候的那样彩色的"

## Overview

将 PDF 翻译过程中终端里显示的纯色（tqdm）进度条，升级为与 pip 安装第三方库时一致的 rich 彩色进度条样式（彩色进度条 + 百分比/完成数 + 已耗时 + 剩余时间预估，多阶段分行显示）。覆盖三个终端场景：CLI fast 模式、CLI precise 模式、GUI 模式下的控制台窗口。提供回退开关，默认启用彩色。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - GUI 模式控制台彩色进度条 (Priority: P1)

用户以 `pdf2zh -i` 启动网页 GUI，上传 PDF 开始翻译。此时终端（控制台窗口）里显示的是纯色单行 tqdm 进度条；期望终端显示 pip 风格的 rich 彩色多行进度条（含阶段名、彩条、M/N、耗时、ETA），同时网页端的进度条显示不受任何影响、照常更新。

**Why this priority**: GUI 是用户的主要使用入口（用户实际看到纯色条的场景），且该场景当前显式关闭了彩色渲染，是问题的主要来源。

**Independent Test**: 启动 GUI，翻译一份多页 PDF，观察终端窗口出现 rich 彩色进度条、网页端进度百分比正常推进至 100%。

**Acceptance Scenarios**:

1. **Given** GUI 已启动且用户在网页发起翻译, **When** 翻译进行中, **Then** 终端显示 rich 彩色进度条（多阶段分行、彩条、M/N、耗时、ETA），网页端 gradio 进度条同步推进
2. **Given** 翻译完成, **Then** 终端进度条正常收尾（100%），无残留乱码或错位，网页端显示翻译完成
3. **Given** 用户在网页取消翻译, **Then** 终端进度条正常终止，不阻塞、不崩溃

---

### User Story 2 - CLI fast 模式保持并固化彩色进度条 (Priority: P2)

用户在命令行直接执行 `pdf2zh 文档.pdf`（fast 模式）翻译。当前该场景理论上已由 babeldoc 默认渲染 rich 彩色条；期望显式固化该行为并纳入统一开关管理，确保三场景观感一致。

**Why this priority**: CLI fast 已默认彩色（属"确认与固化"性质），优先级低于真正存在问题的 GUI 与 precise 场景。

**Independent Test**: 命令行翻译一份 PDF，终端出现与 GUI 场景一致的 rich 彩色进度条。

**Acceptance Scenarios**:

1. **Given** 命令行执行 fast 模式翻译, **When** 翻译进行中, **Then** 终端显示 rich 彩色进度条
2. **Given** 命令行加回退参数, **Then** 终端回退为纯色 tqdm 进度条，功能不受影响

---

### User Story 3 - CLI precise 模式彩色进度条 (Priority: P3)

用户执行 `pdf2zh --mode precise 文档.pdf` 高精度模式翻译。当前终端显示纯色 tqdm（阶段描述如 "Translate paragraphs" / "Typeset pages"）；期望升级为 rich 彩色进度条，各阶段（页面解析、段落翻译、排版）分行彩色显示。

**Why this priority**: precise 模式为非默认的高级路径，使用频率低于 fast/GUI，但观感一致性要求覆盖。

**Independent Test**: 命令行以 precise 模式翻译一份 PDF，终端出现 rich 彩色进度条且各阶段描述保留。

**Acceptance Scenarios**:

1. **Given** precise 模式翻译进行中, **Then** 终端显示 rich 彩色进度条，各阶段（页面处理/段落翻译/排版）分行展示
2. **Given** precise 模式翻译完成, **Then** 进度条正常收尾，产物文件正常生成

---

### Edge Cases

- 输出重定向（`> file.log`）或非交互终端时：rich 渲染需优雅降级（不输出 ANSI 控制序列污染日志，进度信息以可读形式保留或关闭）
- 用户显式选择回退模式：纯色 tqdm 分支必须完整保留并可用
- 翻译取消/异常中断：进度条上下文需正确退出，不产生终端残留或资源泄漏
- 翻译多文件（`--dir` 批量）：每个文件的进度条独立完整显示，前一个文件的进度条正常结束后才开始下一个
- 无颜色终端（`NO_COLOR` 环境变量或哑终端）：自动降级为无色纯文本
- Windows 传统控制台（无 ANSI 支持的旧 cmd）：rich/tqdm 的既有降级机制生效，不产生乱码

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: GUI 模式翻译进行中，终端 MUST 显示 rich 彩色进度条（阶段描述、彩色进度条、完成数 M/N、已耗时、剩余时间预估），且该场景 MUST NOT 因启用彩色渲染而影响网页端进度条的更新逻辑
- **FR-002**: CLI fast 模式翻译进行中，终端 MUST 显示 rich 彩色进度条，并 MUST 受统一回退开关控制
- **FR-003**: CLI precise 模式翻译进行中，终端 MUST 显示 rich 彩色进度条，原有阶段描述（页面处理/段落翻译/排版）MUST 保留，并受统一回退开关控制
- **FR-004**: 系统 MUST 提供命令行回退开关（默认彩色；切换后三场景统一回退为纯色 tqdm 风格）
- **FR-005**: 终端不支持彩色（重定向、哑终端、NO_COLOR）时，进度显示 MUST 优雅降级，MUST NOT 在日志文件中留下 ANSI 控制序列乱码
- **FR-006**: 后端服务（celery backend）的进度状态上报逻辑 MUST 保持功能不变（其回调消费进度数值，不依赖具体渲染样式）
- **FR-007**: 进度数值上报接口（供网页端、后端服务消费）MUST 与终端渲染实现解耦：更换渲染样式不影响任何消费方
- **FR-008**: 实现 MUST 复用依赖树中已有的 rich 与 tqdm 库，MUST NOT 新增第三方依赖

### Key Entities

- **进度事件**（Progress Event）：翻译过程中产生的进度信息，包含阶段名、当前值、总值、总体进度百分比；由翻译内核产生，同时供终端渲染器与外部回调消费
- **终端进度渲染器**（Terminal Progress Renderer）：消费进度事件并在终端渲染可视进度条的对象；存在彩色（rich）与纯色（tqdm）两种实现，可按开关联切换
- **进度回调**（Progress Callback）：外部消费方（GUI 网页进度、celery 状态上报）注册的回调，只消费进度数值，与终端渲染样式无关

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: GUI、CLI fast、CLI precise 三个场景翻译时，终端均显示彩色 rich 进度条（人工可视验证），三场景观感一致
- **SC-002**: GUI 网页端进度条在彩色化改造后功能零回归（翻译全流程推进至 100%，取消操作正常）
- **SC-003**: 回退开关生效：开启后三场景均为纯色 tqdm；终端输出重定向到文件时日志无 ANSI 乱码
- **SC-004**: 后端服务进度上报功能零回归
- **SC-005**: 现有全部构建（Windows/Linux/macOS 便携版）与安装流程不受影响（不新增依赖，版本 pin 无变化）

## Assumptions

- "pip 安装时那样彩色" 指 rich 默认渲染样式（与 pip 内嵌的进度渲染同源），不要求像素级复刻 pip 的具体配色
- GUI 网页端 gradio 进度条的外观本次不变更（仅保证其数据来源不受终端渲染改造影响）
- 回退开关以命令行参数形式提供；GUI 场景的终端渲染跟随全局默认（彩色），不在网页 UI 中单独增加开关
- babeldoc 的内置 rich 进度模式（`use_rich_pbar`）满足 fast/GUI 场景的彩色渲染需求，可直接复用
- precise 模式（pdf2zh 自研 high_level 管线）的彩色渲染在本仓库内实现
- CI 冒烟测试（GUI 启动 + 7860 端口轮询）继续通过；进度条改造不改变任何退出码与日志判据

## Open Questions

- 回退开关的具体参数命名（如 `--no-rich-progress` / `--progress-bar plain`）在 Phase 2 设计阶段确定
- precise 模式内部进度上报结构如何归一（当前向回调传递 tqdm 对象）在 Phase 2 设计阶段确定
