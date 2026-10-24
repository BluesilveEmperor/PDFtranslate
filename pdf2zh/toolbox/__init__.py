"""pdf2zh 工具箱子包：PDF 页面操作、内容编辑、安全、格式转换与 Office 转换。

对外统一 API：
    COMMANDS / CATEGORIES            —— 命令元数据（来自 :mod:`pdf2zh.toolbox.meta`）
    build_argv(cmd, values)          —— 由表单值组装命令行参数
    validate(cmd, values)            —— 校验表单值，返回错误信息列表
    run_command(cmd, values) -> dict —— 统一执行入口，返回结构化结果

设计要点：
    * 纯数据/纯函数的 ``meta`` 直接导入，其余重型模块（pdf_ops/converters/
      office/pwcrack）在 ``run_command`` 真正命中对应命令时才惰性导入，
      既不拖慢主程序启动，也避免未安装可选依赖时 import 失败。
    * ``run_command`` 绝不调用会 ``sys.exit()`` 的 ``_util.die``，
      也不向真实 stdout 打印，所有日志收集进返回值供 UI 展示。
"""

from __future__ import annotations

import glob
import os
from typing import Any, Callable

from .meta import CATEGORIES, COMMANDS, POSITIONAL_KEYS, build_argv, validate

__all__ = [
    "COMMANDS",
    "CATEGORIES",
    "build_argv",
    "validate",
    "run_command",
]


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _as_list(value: Any) -> list[str]:
    """把单个值/序列统一成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _expand(paths: list[str]) -> list[str]:
    """展开目录与通配符（对应原 CLI 的 ``_expand``，但不 ``sys.exit``）。"""
    out: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            pdfs = sorted(glob.glob(os.path.join(p, "*.pdf")))
            if not pdfs:
                raise ValueError(f"目录中没有 PDF 文件: {p}")
            out.extend(pdfs)
        elif "*" in p or "?" in p:
            matched = sorted(glob.glob(p))
            if not matched:
                raise ValueError(f"没有匹配的文件: {p}")
            out.extend(matched)
        else:
            out.append(p)
    return out


def _split_argv(cmd: str, argv: list[str]) -> dict[str, Any]:
    """把 :func:`build_argv` 产出的 argv 还原成 ``{字段键: 值}`` 字典。

    消歧策略（``build_argv`` 保证「位置参数在前、选项对在后」）：

    * 非变长位置参数（input / input_a / input_b ...）按元数据声明顺序 **优先**
      消费固定数量的 token，即使取值恰好等于某个 flag 名也不会被误判为开关；
    * 变长位置参数（inputs / images）从右端回收选项对，剩余前段即为位置取值，
      避免把文件名误当开关。
    """
    fields = COMMANDS[cmd]["fields"]
    bool_keys = {f["key"] for f in fields if f["type"] == "bool"}
    value_keys = {
        f["key"]
        for f in fields
        if f["type"] != "bool" and f["key"] not in POSITIONAL_KEYS
    }
    variadic = [f["key"] for f in fields if f["type"] in ("pdfs_in", "images_in")]
    single_pos = [
        f["key"]
        for f in fields
        if f["key"] in POSITIONAL_KEYS and f["type"] not in ("pdfs_in", "images_in")
    ]

    parsed: dict[str, Any] = {}
    tokens = list(argv[1:])  # 跳过 cmd 本身

    if variadic:
        # 从右端回收选项区（bool 开关或 flag+value 对），剩余前段即位置取值
        ptr = len(tokens) - 1
        option_tokens: list[str] = []
        while ptr >= 0:
            tok = tokens[ptr]
            if tok in bool_keys:
                option_tokens.append(tok)
                ptr -= 1
            elif ptr - 1 >= 0 and tokens[ptr - 1] in value_keys:
                option_tokens.extend([tok, tokens[ptr - 1]])  # value 在前，flag 在后
                ptr -= 2
            else:
                break
        positional_tokens = tokens[: ptr + 1]
        option_tokens.reverse()
        parsed[variadic[0]] = positional_tokens
    else:
        # 位置参数固定数量优先，其余为选项
        count = len(single_pos)
        for key, tok in zip(single_pos, tokens[:count]):
            parsed[key] = tok
        option_tokens = tokens[count:]

    _parse_option_tokens(option_tokens, bool_keys, value_keys, parsed)
    return parsed


def _parse_option_tokens(
    tokens: list[str],
    bool_keys: set[str],
    value_keys: set[str],
    parsed: dict[str, Any],
) -> None:
    """从左到右解析选项 token（bool 开关 / flag+value），结果写入 ``parsed``。"""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in bool_keys:
            parsed[tok] = True
            i += 1
        elif tok in value_keys:
            if i + 1 >= len(tokens):
                raise ValueError(f"参数 {tok} 缺少取值")
            parsed[tok] = tokens[i + 1]
            i += 2
        else:
            raise ValueError(f"无法解析的参数: {tok}")


def _dispatch(cmd: str, parsed: dict[str, Any], log: Callable[[str], None]) -> Any:
    """按命令分发到具体实现。重型模块在此处按需惰性导入。"""
    fields = COMMANDS[cmd]["fields"]
    vals: dict[str, Any] = {f["key"]: f["default"] for f in fields if "default" in f}
    vals.update(parsed)

    def s(key: str, default: Any = None) -> Any:
        v = vals.get(key, default)
        return default if v is None else v

    def as_str(key: str, default: Any = None) -> Any:
        v = vals.get(key, default)
        return default if v is None or v == "" else str(v)

    def as_int(key: str, default: Any = None) -> Any:
        v = vals.get(key, default)
        return default if v is None or v == "" else int(v)

    def as_float(key: str, default: Any = None) -> Any:
        v = vals.get(key, default)
        return default if v is None or v == "" else float(v)

    def as_bool(key: str) -> bool:
        return bool(vals.get(key, False))

    def finish(output: Any) -> Any:
        if isinstance(output, (list, tuple)):
            log(f"已生成 {len(output)} 个文件")
        else:
            log(f"完成: {output}")
        return output

    # ---------------- 页面操作 / 内容编辑 / 安全（pdf_ops） ----------------
    page_ops = {
        "merge", "split", "extract", "delete", "insert", "rotate", "cut",
        "pages-merger", "page-number", "watermark-text", "watermark-image",
        "text-replace", "text-delete", "remove-links", "encrypt", "decrypt",
    }
    if cmd in page_ops:
        from . import pdf_ops as ops

        if cmd == "merge":
            inputs = _expand(_as_list(vals.get("inputs")))
            return finish(ops.merge(inputs, as_str("-o")))
        if cmd == "split":
            every = as_int("--every")
            ranges = as_str("--ranges")
            if every:
                return finish(ops.split_every(as_str("input"), as_str("-o"), every))
            if ranges:
                return finish(ops.split_ranges(as_str("input"), as_str("-o"), ranges))
            raise ValueError("需要 --every 或 --ranges 之一")
        if cmd == "extract":
            return finish(ops.extract_pages(as_str("input"), as_str("-o"), as_str("-p")))
        if cmd == "delete":
            return finish(ops.delete_pages(as_str("input"), as_str("-o"), as_str("-p")))
        if cmd == "insert":
            return finish(
                ops.insert_pages(
                    as_str("input"), as_str("--file"), as_str("-o"), as_int("--pos", -1)
                )
            )
        if cmd == "rotate":
            return finish(
                ops.rotate(as_str("input"), as_str("-o"), as_int("--angle"), as_str("-p", None))
            )
        if cmd == "cut":
            return finish(
                ops.cut_margins(
                    as_str("input"),
                    as_str("-o"),
                    as_float("--left", 0.0),
                    as_float("--right", 0.0),
                    as_float("--top", 0.0),
                    as_float("--bottom", 0.0),
                )
            )
        if cmd == "pages-merger":
            return finish(
                ops.pages_merger(
                    as_str("input_a"),
                    as_str("input_b"),
                    as_str("-o"),
                    as_str("--mode", "interleave"),
                )
            )
        if cmd == "page-number":
            return finish(
                ops.add_page_numbers(
                    as_str("input"),
                    as_str("-o"),
                    as_str("--pos", "bottom-center"),
                    as_int("--start", 1),
                    as_str("--format", "{n}"),
                    as_float("--size", 11.0),
                )
            )
        if cmd == "watermark-text":
            return finish(
                ops.watermark_text(
                    as_str("input"),
                    as_str("-o"),
                    as_str("--text"),
                    as_float("--angle", 45.0),
                    as_float("--opacity", 0.15),
                    as_float("--size", 36.0),
                    tiled=not as_bool("--center"),
                )
            )
        if cmd == "watermark-image":
            return finish(
                ops.watermark_image(
                    as_str("input"),
                    as_str("-o"),
                    as_str("--image"),
                    as_float("--opacity", 0.5),
                    tiled=not as_bool("--center"),
                    scale=as_float("--scale", 0.35),
                )
            )
        if cmd == "text-replace":
            return finish(
                ops.text_replace(
                    as_str("input"),
                    as_str("-o"),
                    as_str("--old"),
                    as_str("--new", ""),
                    as_str("-p", None),
                )
            )
        if cmd == "text-delete":
            return finish(
                ops.text_delete(
                    as_str("input"), as_str("-o"), as_str("--text"), as_str("-p", None)
                )
            )
        if cmd == "remove-links":
            out, n = ops.remove_links(as_str("input"), as_str("-o"))
            log(f"已删除 {n} 个链接")
            return finish(out)
        if cmd == "encrypt":
            return finish(
                ops.encrypt(
                    as_str("input"),
                    as_str("-o"),
                    as_str("--user-pw"),
                    s("--owner-pw", None),
                    allow_print=not as_bool("--no-print"),
                    allow_copy=not as_bool("--no-copy"),
                )
            )
        if cmd == "decrypt":
            return finish(
                ops.decrypt(
                    as_str("input"),
                    as_str("-o"),
                    wordlist=s("--wordlist", None),
                    charset=s("--charset", None),
                    min_len=as_int("--min-len", 1),
                    max_len=as_int("--max-len", 4),
                    jobs=as_int("--jobs", None),
                    log=log,
                )
            )

    # ---------------- PDF 转换（converters） ----------------
    convert_ops = {
        "pdf-to-image", "image-to-pdf", "pdf-to-word", "pdf-to-ppt", "pdf-to-excel",
    }
    if cmd in convert_ops:
        from . import converters as cv

        if cmd == "pdf-to-image":
            return finish(
                cv.pdf_to_image(
                    as_str("input"),
                    as_str("-o"),
                    as_int("--dpi", 150),
                    as_str("--fmt", "png"),
                    as_str("-p", None),
                    as_int("--quality", 90),
                )
            )
        if cmd == "image-to-pdf":
            images = _expand(_as_list(vals.get("images")))
            return finish(
                cv.image_to_pdf(
                    images, as_str("-o"), as_str("--page-size", "auto"), as_float("--margin", 0.0)
                )
            )
        if cmd == "pdf-to-word":
            return finish(
                cv.pdf_to_word(as_str("input"), as_str("-o"), as_str("-p", None))
            )
        if cmd == "pdf-to-ppt":
            return finish(
                cv.pdf_to_ppt(
                    as_str("input"),
                    as_str("-o"),
                    as_str("--mode", "image"),
                    as_int("--dpi", 150),
                    as_str("-p", None),
                )
            )
        if cmd == "pdf-to-excel":
            return finish(
                cv.pdf_to_excel(as_str("input"), as_str("-o"), as_str("-p", None))
            )

    # ---------------- Office 转换（office） ----------------
    office_ops = {"word-to-pdf", "excel-to-pdf", "ppt-to-pdf"}
    if cmd in office_ops:
        from . import office

        if cmd == "word-to-pdf":
            return finish(office.word_to_pdf(as_str("input"), as_str("-o")))
        if cmd == "excel-to-pdf":
            return finish(office.excel_to_pdf(as_str("input"), as_str("-o")))
        if cmd == "ppt-to-pdf":
            return finish(office.ppt_to_pdf(as_str("input"), as_str("-o")))

    raise ValueError(f"未知命令: {cmd}")


# --------------------------------------------------------------------------- #
# 统一执行入口
# --------------------------------------------------------------------------- #
def run_command(cmd: str, values: dict[str, Any]) -> dict[str, Any]:
    """统一执行入口：校验 → 组装 argv → 无副作用分发 → 返回结构化结果。

    返回结构::

        {
            "ok": bool,          # 是否成功
            "output": <路径|路径列表|摘要>,   # 失败时为 None
            "log": str,          # 收集到的文本日志（供 UI 展示）
            "error": str,        # 错误信息，成功时为空串
        }

    实现上先经 ``build_argv`` 组装参数，再由 ``_split_argv`` 还原成字段字典，
    最终分发到 ``pdf_ops`` / ``converters`` / ``office`` 中的函数；
    全程不调用 ``_util.die``（避免 ``sys.exit`` 杀死 Gradio 进程），
    也不向真实 stdout 打印。
    """
    if cmd not in COMMANDS:
        return {"ok": False, "output": None, "log": "", "error": f"未知命令: {cmd}"}

    errors = validate(cmd, values)
    if errors:
        return {"ok": False, "output": None, "log": "", "error": "；".join(errors)}

    logs: list[str] = []
    try:
        argv = build_argv(cmd, values)
        parsed = _split_argv(cmd, argv)
        output = _dispatch(cmd, parsed, logs.append)
        return {"ok": True, "output": output, "log": "\n".join(logs), "error": ""}
    except Exception as exc:  # noqa: BLE001 —— 统一兜底为结构化错误
        detail = f"{type(exc).__name__}: {exc}"
        logs.append(detail)
        return {"ok": False, "output": None, "log": "\n".join(logs), "error": detail}