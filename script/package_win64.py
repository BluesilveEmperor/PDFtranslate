#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 build/ 产物打包成 Windows 便携发布 zip。

纯 Python 实现（仅标准库），替代手动压缩。产物解压后双击 pdf2zh.exe 即用。

用法:
    python script/package_win64.py                 # build/ -> dist/pdf2zh-win64-v<版本>.zip
    python script/package_win64.py --output x.zip  # 指定输出路径
    python script/package_win64.py --fast          # 不压缩（打包更快，体积更大）
    python script/package_win64.py --source build  # 指定产物目录

校验规则（缺一不可，缺了就报错退出）:
    build/pdf2zh.exe
    build/_pystand_static.int
    build/runtime/python.exe
    build/runtime/Lib/site-packages/precise_kernel.pth   # precise 内核 shim
    build/site-packages/pdf2zh/kernel/_precise_packages/pdf2zh_next  # precise 捆绑依赖
    build/offline_assets_*.zip                           # babeldoc 离线资源
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
    "runtime/Lib/site-packages/precise_kernel.pth",
    "site-packages/pdf2zh/kernel/_precise_packages/pdf2zh_next",
]

REQUIRED_GLOB = ["offline_assets_*.zip"]


def read_version() -> str:
    """从 pyproject.toml 读版本号。"""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("错误: pyproject.toml 中找不到 version")
    return m.group(1)


def validate(source: Path) -> None:
    """打包前完整性校验。"""
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
    validate(source)

    version = read_version()
    output = Path(args.output) if args.output else REPO_ROOT / "dist" / f"pdf2zh-win64-v{version}.zip"
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
