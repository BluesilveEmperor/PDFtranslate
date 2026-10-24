import os
import sys


def parse_pages(spec, count):
    if not spec or not spec.strip():
        return list(range(count))
    result = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                lo_i = int(lo)
                hi_i = int(hi)
            except ValueError:
                raise ValueError(f"无效页码范围: {part!r}")
            if lo_i < 1 or hi_i < lo_i:
                raise ValueError(f"无效页码范围: {part!r}")
            result.extend(range(lo_i - 1, min(hi_i, count)))
        else:
            try:
                n = int(part)
            except ValueError:
                raise ValueError(f"无效页码: {part!r}")
            if n < 1 or n > count:
                raise ValueError(f"页码超出范围: {n}")
            result.append(n - 1)
    result = sorted(set(result))
    if not result:
        raise ValueError("页码选择为空")
    return result


def parse_ranges(spec, count):
    """解析分卷页码范围（如 ``1-2,3-4``），返回 0 基闭区间 ``(lo, hi)`` 列表。

    边界校验与 :func:`parse_pages` 保持一致：

    * 区间下界须 ``>=1`` 且上界 ``>=`` 下界，否则报「无效页码范围」；
    * 单页须落在 ``[1, count]`` 内，否则报「页码超出范围」；
    * 区间上界超出总页数时截断到最后一页（与 :func:`parse_pages` 相同）；
    * 全部为空段时报「页码范围选择为空」。
    """
    ranges = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                lo_i = int(lo)
                hi_i = int(hi)
            except ValueError:
                raise ValueError(f"无效页码范围: {part!r}")
            if lo_i < 1 or hi_i < lo_i:
                raise ValueError(f"无效页码范围: {part!r}")
            ranges.append((lo_i - 1, min(hi_i, count) - 1))
        else:
            try:
                n = int(part)
            except ValueError:
                raise ValueError(f"无效页码: {part!r}")
            if n < 1 or n > count:
                raise ValueError(f"页码超出范围: {n}")
            ranges.append((n - 1, n - 1))
    if not ranges:
        raise ValueError("页码范围选择为空")
    return ranges


def ensure_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def die(msg, code=1):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(code)
