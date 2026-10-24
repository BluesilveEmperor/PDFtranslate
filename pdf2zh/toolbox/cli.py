"""pdf2zh 工具箱独立命令行入口。

设计要点：
    * 所有命令及其参数 **完全由** :mod:`pdf2zh.toolbox.meta` 的 ``COMMANDS``
      元数据自动生成，元数据是唯一事实来源，无需在此重复维护参数表。
    * 执行后端统一走 :func:`pdf2zh.toolbox.run_command`，它内部完成
      「校验 → 组装 argv → 无副作用分发」，绝不调用会 ``sys.exit`` 的
      原始 CLI，也不向真实 stdout 打印，便于作为库函数被 GUI/测试复用。
    * ``main`` 只负责「解析 argv → 收集字段值 → 校验 → 调用 run_command →
      打印日志/错误 → 返回退出码」，不抛异常、不 sys.exit。

用法::

    python -m pdf2zh.toolbox <命令> [参数...]
    python -m pdf2zh.toolbox --help
    pdf2zh-toolbox <命令> [参数...]          # 安装后由 project.scripts 提供
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Optional, Sequence

from pdf2zh import __version__

from . import CATEGORIES, COMMANDS, run_command
from .meta import POSITIONAL_KEYS, validate

# 位置参数中「可接收多个文件」的字段类型（对应 build_argv 中的展开逻辑）
_VARIADIC_TYPES = ("pdfs_in", "images_in")


def _flag_dest(key: str) -> str:
    """把 CLI flag key（如 ``-o`` / ``--no-print``）映射为合法的 argparse dest。

    argparse 的 dest 必须是合法标识符，不能含连字符，因此统一加 ``opt_`` 前缀
    并做 ``-`` → ``_`` 替换；前缀同时避免与位置参数 key（input/inputs/...）冲突。
    """
    return "opt_" + key.lstrip("-").replace("-", "_")


def _field_help(field: dict[str, Any]) -> str:
    """由字段元数据拼出 argparse 的 help 文本。"""
    parts = [field["label"]]
    if field.get("required"):
        parts.append("(必填)")
    if field.get("help"):
        parts.append(f"— {field['help']}")
    return " ".join(parts)


def _add_field(sub: argparse.ArgumentParser, field: dict[str, Any]) -> None:
    """按字段元数据为子命令添加一个位置参数或可选参数。"""
    key = field["key"]
    typ = field["type"]
    help_txt = _field_help(field)

    # ---- 位置参数：inputs / input / images / input_a / input_b ----
    # 占位符交由 argparse 用 key.upper()，描述文本已含中文 label，避免重复。
    if key in POSITIONAL_KEYS:
        if typ in _VARIADIC_TYPES:
            # 多值位置参数：缺省时置 None，交由 validate 报「缺少必填项」
            sub.add_argument(key, nargs="*", default=None, help=help_txt)
        else:
            sub.add_argument(key, nargs="?", default=None, help=help_txt)
        return

    # ---- 可选参数（CLI flag）----
    dest = _flag_dest(key)
    common: dict[str, Any] = {
        "dest": dest,
        "help": help_txt,
        "metavar": field["label"],
    }
    if typ == "bool":
        sub.add_argument(key, action="store_true", dest=dest, help=help_txt)
    elif typ == "choice":
        sub.add_argument(
            key, choices=field.get("choices"), default=field.get("default"), **common
        )
    elif typ == "int":
        sub.add_argument(key, type=int, default=field.get("default"), **common)
    elif typ == "float":
        sub.add_argument(key, type=float, default=field.get("default"), **common)
    else:
        # text / file / pdf_in / save_file / out_dir 等按字符串处理
        sub.add_argument(key, default=field.get("default"), **common)


def _build_epilog() -> str:
    """按分类列出全部命令，供顶层 ``--help`` 展示。"""
    lines = ["可用命令（按分类）:"]
    for cat, _key in CATEGORIES:
        names = [name for name, meta in COMMANDS.items() if meta.get("cat") == cat]
        if names:
            lines.append(f"* {cat}: " + ", ".join(names))
    lines.append("")
    lines.append("示例: python -m pdf2zh.toolbox merge a.pdf b.pdf -o merged.pdf")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """由 COMMANDS 元数据构建顶层解析器及其全部子命令。"""
    top = argparse.ArgumentParser(
        prog="pdf2zh-toolbox",
        description=(
            "pdf2zh 工具箱：页面操作 / 内容编辑 / 安全 / PDF 转换 / Office 转换。"
            "\n所有命令与参数均由 pdf2zh.toolbox.meta 元数据自动生成。"
        ),
        epilog=_build_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    top.add_argument(
        "--version", action="version", version=f"pdf2zh toolbox v{__version__}"
    )
    subparsers = top.add_subparsers(dest="command", metavar="<命令>")

    for cmd, meta in COMMANDS.items():
        cat = meta.get("cat", "")
        sub = subparsers.add_parser(
            cmd,
            help=f"[{cat}] {meta['label']} — {meta['desc']}",
            description=f"[{cat}] {meta['label']}: {meta['desc']}",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        for field in meta["fields"]:
            _add_field(sub, field)
    return top


def _collect_values(ns: argparse.Namespace, cmd: str) -> dict[str, Any]:
    """把 argparse 命名空间还原成 ``{字段键: 值}``，键名与元数据完全一致。"""
    values: dict[str, Any] = {}
    for field in COMMANDS[cmd]["fields"]:
        key = field["key"]
        attr = key if key in POSITIONAL_KEYS else _flag_dest(key)
        values[key] = getattr(ns, attr)
    return values


def main(argv: Optional[Sequence[str]] = None) -> int:
    """工具箱命令行主函数。

    :param argv: 不含程序名的参数序列；``None`` 时取 ``sys.argv[1:]``。
    :return: 退出码。0 成功；2 参数/校验错误；1 执行失败。
    """
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    try:
        ns = parser.parse_args(args)
    except SystemExit as exc:
        # argparse 对 --help/--version/未知命令/类型错误自行抛 SystemExit，
        # 这里统一转换为整数退出码，保证 main 始终「返回」而非「退出」。
        return int(exc.code) if exc.code else 0

    cmd = getattr(ns, "command", None)
    if not cmd:
        # 无子命令：展示帮助，退出码 0
        parser.print_help()
        return 0

    values = _collect_values(ns, cmd)

    # 先校验必填项/类型，失败逐条打印并返回非 0
    errors = validate(cmd, values)
    if errors:
        for err in errors:
            print(f"错误: {err}", file=sys.stderr)
        return 2

    result = run_command(cmd, values)
    if result.get("log"):
        print(result["log"])
    if not result.get("ok"):
        if result.get("error"):
            print(f"错误: {result['error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
