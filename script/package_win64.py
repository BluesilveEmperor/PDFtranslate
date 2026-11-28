#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 build/ 产物打包成 Windows 便携发布 zip。

纯 Python 实现（仅标准库），替代手动压缩。产物解压后双击 pdf2zh.exe 即用。

用法:
    python script/package_win64.py                 # build/ -> dist/pdf2zh-win64-v<版本>.zip
    python script/package_win64.py --output x.zip  # 指定输出路径
    python script/package_win64.py --fast          # 不压缩（打包更快，体积更大）
    python script/package_win64.py --source build  # 指定产物目录

校验规则:
    必需: build/pdf2zh.exe、_pystand_static.int、runtime/python.exe、
          build/site-packages/sitecustomize.py、offline_assets_*.zip
    可选 precise 捆绑组（BUNDLE_PRECISE=0 构建的轻量包则不要求）:
          site-packages/pdf2zh/kernel/_precise_packages/pdf2zh_next
    捆绑存在 -> dist/pdf2zh-win64-v<版本>.zip
    未捆绑   -> dist/pdf2zh-win64-v<版本>-fast.zip（仅 fast 模式）
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 打包时排除的运行时垃圾（build/ 正常情况下是纯净的，这里只做保险）
EXCLUDE_DIRS = {"__pycache__", "gradio_files", "pdf2zh_files", ".staging"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log")

# 完整性校验必需的条目
REQUIRED = [
    "pdf2zh.exe",
    "_pystand_static.int",
    "runtime/python.exe",
    "site-packages/sitecustomize.py",
]

REQUIRED_GLOB = ["offline_assets_*.zip"]

# precise 捆绑组：目录存在时这些条目必须齐全；目录不存在则为轻量包（fast-only）
# 注: runtime site/pth shim (precise_kernel.pth/bitstream_shim.py) 已废弃，
#     bitstring 固定 4.3.0 原生含 BitStream，spawn 子进程从 worker 继承 sys.path
PRECISE_DIR = "site-packages/pdf2zh/kernel/_precise_packages"
PRECISE_GROUP = [
    PRECISE_DIR + "/pdf2zh_next",
]


def read_version() -> str:
    """从 pyproject.toml 读版本号。"""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("错误: pyproject.toml 中找不到 version")
    return m.group(1)


def validate(source: Path) -> bool:
    """打包前完整性校验。返回是否为 precise 捆绑包。"""
    missing = [rel for rel in REQUIRED if not (source / rel).exists()]
    for pattern in REQUIRED_GLOB:
        if not list(source.glob(pattern)):
            missing.append(pattern)
    if missing:
        raise SystemExit(
            "错误: build 产物不完整，缺少:\n  "
            + "\n  ".join(missing)
            + "\n请先运行 build.sh 完成构建。"
        )

    bundled = (source / PRECISE_DIR).is_dir()
    if bundled:
        group_missing = [rel for rel in PRECISE_GROUP if not (source / rel).exists()]
        if group_missing:
            raise SystemExit(
                "错误: precise 捆绑不完整，缺少:\n  " + "\n  ".join(group_missing)
            )
    else:
        print("轻量包（未捆绑 precise 内核，打包版仅支持 fast 模式）")
    return bundled


def iter_files(source: Path):
    """遍历产物文件，yield (绝对路径, zip 内相对路径)。"""
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(source)
        parts = rel.parts
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        if rel.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        yield path, rel.as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default="build", help="产物目录（默认 build）")
    parser.add_argument("--output", default="", help="输出 zip 路径（默认 dist/pdf2zh-win64-v<版本>.zip）")
    parser.add_argument("--fast", action="store_true", help="不压缩（ZIP_STORED，打包更快）")
    args = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("错误: 此脚本仅用于 Windows 便携包打包")

    source = (REPO_ROOT / args.source).resolve()
    if not source.is_dir():
        raise SystemExit(f"错误: 产物目录不存在: {source}")
    bundled = validate(source)

    version = read_version()
    variant = "" if bundled else "-fast"
    output = (
        Path(args.output)
        if args.output
        else REPO_ROOT / "dist" / f"pdf2zh-win64-v{version}{variant}.zip"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    compression = zipfile.ZIP_STORED if args.fast else zipfile.ZIP_DEFLATED
    files = list(iter_files(source))
    total = len(files)
    if total == 0:
        raise SystemExit("错误: 产物目录为空")

    print(f"打包 {total} 个文件 -> {output}")
    print(f"压缩模式: {'STORED' if args.fast else 'DEFLATED'}")
    started = time.perf_counter()

    with zipfile.ZipFile(output, "w", compression=compression, allowZip64=True) as zf:
        for i, (path, arcname) in enumerate(files, 1):
            zf.write(path, arcname)
            if i % 2000 == 0 or i == total:
                pct = i * 100 // total
                print(f"  {i}/{total} ({pct}%)", flush=True)

    elapsed = time.perf_counter() - started
    size_mb = output.stat().st_size / 1024 / 1024
    print(f"\n完成: {output}")
    print(f"大小: {size_mb:.1f} MB, 耗时: {elapsed:.1f}s, 文件数: {total}")

    # 抽查关键条目
    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
        for rel in ["pdf2zh.exe", "_pystand_static.int", "runtime/python.exe"]:
            if rel not in names:
                raise SystemExit(f"错误: zip 中缺少 {rel}")
    print("关键条目抽查通过，可分发。")


if __name__ == "__main__":
    main()
