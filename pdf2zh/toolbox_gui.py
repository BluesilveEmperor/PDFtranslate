"""工具箱 Tab：复用 :mod:`pdf2zh.toolbox` 的命令元数据动态生成 Gradio 表单。

设计要点：
    * 分类下拉 + 命令下拉两级选择，覆盖 ``COMMANDS`` 中的全部命令。
    * 用 ``@gr.render`` 依据当前命令的 ``fields`` 动态渲染输入组件，并在
      渲染回调内绑定「执行」按钮；切换命令会自动重建整张表单，无需为
      24 个命令手工编写 UI。
    * Gradio 上传得到的是临时文件路径，直接交给 ``run_command`` 即可
      （工具内部用 pymupdf 读取）；``save_file`` / ``out_dir`` 的产物统一
      落在本次执行的临时工作目录，单文件直接下载、多文件/目录打包 zip。
    * 全程只调用 :func:`pdf2zh.toolbox.run_command`，不接触 ``sys.exit``
      与真实 stdout，保证不会杀死正在运行的 Gradio 服务进程。

模块对外仅暴露 :func:`build_toolbox_tab`，需在 ``gr.Tab`` 上下文中调用。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from typing import Any, Callable, Iterator

import gradio as gr

from pdf2zh.toolbox import CATEGORIES, COMMANDS, run_command
from pdf2zh.toolbox.pwcrack import MAX_BRUTE_LEN

__all__ = ["build_toolbox_tab"]

#: 需要整行独占的上传类字段（文件选择器较宽，单独占一行更紧凑美观）
_UPLOAD_TYPES = ("pdf_in", "pdfs_in", "images_in", "file")

#: 需要重定向到临时工作目录的输出类字段
_OUTPUT_TYPES = ("save_file", "out_dir")

#: 临时工作目录前缀；与 ``tempfile.mkdtemp(prefix=...)`` 保持一致。
_WORKDIR_PREFIX = "pdf2zh_toolbox_"

#: 每次执行前保留的最新历史工作目录数量（其余按修改时间清理）。
_WORKDIR_KEEP = 5


# --------------------------------------------------------------------------- #
# 数值字段边界
# --------------------------------------------------------------------------- #
def _numeric_bounds(command: str, field: dict[str, Any]) -> tuple[float | None, float | None]:
    """返回数值字段的 ``(最小值, 最大值)``，用于限制会指数级放大开销的参数。

    仅对安全性敏感的字段设界：

    * ``--jobs``（pwcrack 并行进程数）限制在 ``[1, os.cpu_count()]``，
      与 :func:`pdf2zh.toolbox.pwcrack.clamp_jobs` 的上界一致；
    * ``--min-len`` / ``--max-len``（暴力枚举长度）限制在
      ``[1, MAX_BRUTE_LEN]``，与 :data:`pdf2zh.toolbox.pwcrack.MAX_BRUTE_LEN`
      的硬上限一致，避免候选数爆炸。

    其余字段返回 ``(None, None)``，即不限制。
    """
    key = field.get("key")
    if key == "--jobs":
        return 1, os.cpu_count() or 4
    if key in ("--min-len", "--max-len"):
        return 1, MAX_BRUTE_LEN
    return None, None


# --------------------------------------------------------------------------- #
# 元数据处理
# --------------------------------------------------------------------------- #
def _commands_of(category: str) -> list[str]:
    """返回某分类下全部命令 key，保持元数据的声明顺序。"""
    return [key for key, meta in COMMANDS.items() if meta["cat"] == category]


def _group_fields(fields: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    """把字段分组为「上传类独占一行、其余两两一行」，提高空间利用率。

    生成器逐个产出行分组，调用方在每组内开启一个 ``gr.Row`` 即可。
    """
    pending: list[dict[str, Any]] = []
    for field in fields:
        if field["type"] in _UPLOAD_TYPES:
            if pending:
                yield pending
                pending = []
            yield [field]
            continue
        pending.append(field)
        if len(pending) == 2:
            yield pending
            pending = []
    if pending:
        yield pending


def _make_component(command: str, field: dict[str, Any]) -> Any:
    """依据字段元数据创建对应的 Gradio 输入组件。

    必填字段在 label 末尾追加 ``*`` 作为提示；``secret`` 字段渲染为密码框；
    ``help`` 文案挂到组件的 ``info`` 上，保持界面紧凑。

    :param command: 所属命令 key，用于查表确定数值字段的安全边界。
    """
    label = field["label"] + (" *" if field.get("required") else "")
    ftype = field["type"]
    hint = field.get("help")
    default = field.get("default", "")

    if ftype == "pdf_in":
        return gr.File(
            label=label, file_count="single", file_types=[".pdf"], type="filepath"
        )
    if ftype == "pdfs_in":
        return gr.File(
            label=label, file_count="multiple", file_types=[".pdf"], type="filepath"
        )
    if ftype == "images_in":
        return gr.File(
            label=label, file_count="multiple", file_types=["image"], type="filepath"
        )
    if ftype == "file":
        return gr.File(label=label, file_count="single", type="filepath")
    if ftype == "save_file":
        return gr.Textbox(
            label=label, value=default, placeholder="输出文件名（自动存入临时目录）"
        )
    if ftype == "out_dir":
        return gr.Textbox(
            label=label, value=default, placeholder="输出目录名（自动存入临时目录）"
        )
    if ftype == "text":
        if field.get("secret"):
            return gr.Textbox(label=label, type="password", value=default or "")
        return gr.Textbox(label=label, value=default or "", info=hint)
    if ftype == "int":
        minimum, maximum = _numeric_bounds(command, field)
        return gr.Number(
            label=label,
            value=field.get("default"),
            precision=0,
            info=hint,
            minimum=minimum,
            maximum=maximum,
        )
    if ftype == "float":
        return gr.Number(label=label, value=field.get("default"), info=hint)
    if ftype == "choice":
        return gr.Dropdown(
            label=label,
            choices=list(field.get("choices", [])),
            value=field.get("default"),
            info=hint,
        )
    if ftype == "bool":
        return gr.Checkbox(
            label=label, value=bool(field.get("default", False)), info=hint
        )
    # 兜底：未知类型按文本框处理，避免整块表单渲染失败
    return gr.Textbox(label=label, value=default or "", info=hint)


# --------------------------------------------------------------------------- #
# 执行 / 输出处理
# --------------------------------------------------------------------------- #
def _prepare_outputs(
    fields: list[dict[str, Any]], values: dict[str, Any], workdir: str
) -> None:
    """就地改写 ``save_file`` / ``out_dir`` 字段值为工作目录下的绝对路径。

    * 用户填写了名称 → 取 basename 后拼接工作目录（防止越出临时目录）。
    * 用户留空且字段必填 → 保持空值，交给 ``validate`` 报出必填提示。
    * 用户留空且字段可选 → 采用元数据 default，或自动生成占位名称。
    """
    for field in fields:
        if field["type"] not in _OUTPUT_TYPES:
            continue
        value = values.get(field["key"])
        if value:
            values[field["key"]] = os.path.join(
                workdir, os.path.basename(str(value))
            )
        elif field.get("required"):
            continue  # 保持空，交由 validate 提示
        else:
            fallback = field.get("default") or (
                "output" if field["type"] == "out_dir" else "output.pdf"
            )
            values[field["key"]] = os.path.join(
                workdir, os.path.basename(str(fallback))
            )


def _collect_outputs(output: Any, workdir: str) -> str | list[str] | None:
    """把 ``run_command`` 的产出归一为可下载路径。

    单个文件直接返回其路径；多个文件或目录则打包成 zip 后再返回。
    """
    items = list(output) if isinstance(output, (list, tuple)) else [output]
    files = [str(p) for p in items if p and os.path.exists(str(p))]
    if not files:
        return None
    if len(files) == 1 and os.path.isfile(files[0]):
        return files[0]

    staging = tempfile.mkdtemp(prefix="_pack_", dir=workdir)
    for path in files:
        if os.path.isdir(path):
            for name in os.listdir(path):
                src = os.path.join(path, name)
                if os.path.isfile(src):
                    shutil.copy2(src, staging)
            continue
        shutil.copy2(path, staging)
    archive_base = os.path.join(workdir, f"toolbox_{int(time.time())}")
    return shutil.make_archive(archive_base, "zip", staging)


# --------------------------------------------------------------------------- #
# 临时工作目录生命周期管理
# --------------------------------------------------------------------------- #
def _cleanup_stale_workdirs(
    keep: int = _WORKDIR_KEEP, base_dir: str | None = None
) -> list[str]:
    """清理历史临时工作目录，仅保留最近的 ``keep`` 个。

    每次执行都在系统临时目录下 ``mkdtemp(prefix="pdf2zh_toolbox_")``，产物下载
    完成后该目录即无用处；长期运行会持续堆积直到占满临时盘。这里在每次执行
    **开始前** 调用：按目录修改时间倒序保留最近 ``keep`` 个（覆盖「当前/最近
    正在供下载」的产物目录），删除其余同前缀目录。

    逐个 ``shutil.rmtree`` 并忽略异常（目录可能正被其他会话占用或已不存在），
    清理失败不影响本次执行。

    :param keep: 需要保留的最新目录数量。
    :param base_dir: 搜索目录，默认系统临时目录（便于测试注入）。
    :return: 实际被删除的目录路径列表（便于测试断言）。
    """
    base = base_dir or tempfile.gettempdir()
    try:
        names = os.listdir(base)
    except OSError:
        return []

    matched: list[tuple[float, str]] = []
    for name in names:
        if not name.startswith(_WORKDIR_PREFIX):
            continue
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            continue
        try:
            matched.append((os.path.getmtime(path), path))
        except OSError:
            continue  # 竞态下目录可能已被移除，跳过

    matched.sort(key=lambda item: item[0], reverse=True)
    removed: list[str] = []
    for _mtime, path in matched[max(keep, 0):]:
        try:
            shutil.rmtree(path)
            removed.append(path)
        except OSError:
            pass
    return removed


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def build_toolbox_tab(
    icon_loader: Callable[[str], str] | None = None,
) -> Any:
    """构建「工具箱」Tab 的 UI，需在 ``gr.Tab`` 上下文中调用。

    :param icon_loader: 可选的图标加载函数（如 ``pdf2zh.gui.load_icon``），
        用于复用既有图标风格；为 ``None`` 时仅使用纯文字标题。
    :return: 分类下拉组件，便于调用方/测试确认 UI 已成功构建。
    """
    categories = [name for name, _ in CATEGORIES]
    default_category = categories[0]
    default_commands = _commands_of(default_category)

    head_icon = icon_loader("ic_public_settings") if icon_loader else ""
    gr.Markdown(
        f"{head_icon} <span class='section-label'>PDF 工具箱</span>"
        " <span class='secondary-text'>— 页面操作 / 内容编辑 / 安全 / 格式转换</span>",
        elem_classes=["icon-heading"],
    )

    with gr.Row():
        category_dd = gr.Dropdown(
            choices=categories,
            value=default_category,
            label="分类",
            scale=1,
        )
        command_dd = gr.Dropdown(
            choices=default_commands,
            value=default_commands[0] if default_commands else None,
            label="命令",
            scale=3,
        )

    def _on_category_change(category: str):
        commands = _commands_of(category)
        return gr.update(choices=commands, value=commands[0] if commands else None)

    category_dd.change(
        _on_category_change, inputs=category_dd, outputs=command_dd
    )

    @gr.render(inputs=[category_dd, command_dd])
    def _render_form(category: str, command: str):  # noqa: ARG001 —— category 仅用于触发重渲染
        if not command or command not in COMMANDS:
            gr.Markdown("请选择命令后填写参数。")
            return

        meta = COMMANDS[command]
        gr.Markdown(f"**{meta['label']}** — {meta['desc']}")
        fields: list[dict[str, Any]] = meta["fields"]

        # 动态生成输入组件，并记录组件引用以便绑定回调
        components: dict[str, Any] = {}
        for row in _group_fields(fields):
            with gr.Row():
                for field in row:
                    components[field["key"]] = _make_component(command, field)

        with gr.Row():
            run_btn = gr.Button("执行", variant="primary", scale=4)

        with gr.Row():
            log_box = gr.Textbox(
                label="运行日志", lines=6, interactive=False, scale=1
            )
            with gr.Column(scale=1):
                error_box = gr.Textbox(
                    label="错误信息", lines=3, interactive=False
                )
                output_file = gr.File(label="下载结果", visible=False)

        def _on_run(*raw_values):
            values = {
                field["key"]: value
                for field, value in zip(fields, raw_values)
            }
            # 先回收历史工作目录（保留最近若干个），再创建本次目录，
            # 确保正在供下载的近期产物不会被删除。
            _cleanup_stale_workdirs()
            workdir = tempfile.mkdtemp(prefix=_WORKDIR_PREFIX)
            _prepare_outputs(fields, values, workdir)

            result = run_command(command, values)
            files = (
                _collect_outputs(result.get("output"), workdir)
                if result.get("ok")
                else None
            )
            if files:
                return (
                    result.get("log", ""),
                    result.get("error", ""),
                    gr.update(value=files, visible=True),
                )
            return (
                result.get("log", ""),
                result.get("error", ""),
                gr.update(value=None, visible=False),
            )

        run_btn.click(
            _on_run,
            inputs=list(components.values()),
            outputs=[log_box, error_box, output_file],
        )

    return category_dd