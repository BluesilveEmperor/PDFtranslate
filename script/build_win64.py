#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 便携包一键构建（纯 Python 实现，替代 build.sh 的 Windows 分支）。

流程: 准备 embed Python + PyStand → uv 安装主依赖 → 捆装 precise 内核依赖
(BUNDLE_PRECISE=0 可跳过) → 注入 BitStream shim → 生成离线资源 → (可选)打 zip。

用法:
    python script/build_win64.py                 # 全量构建到 build/
    python script/build_win64.py --package       # 构建后立即打发布 zip
    python script/build_win64.py --allow-download  # 离线资源缓存缺失时联网补齐
    python script/build_win64.py --clean         # 构建前彻底删除旧 build/
    # 默认不清删除: 旧 build/ 改名保留为 build_prev_<时间戳>

依赖: uv (构建机需已安装), git submodule pdf2zh/kernel/PDFMathTranslate-next.git
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEP_DIR = REPO_ROOT / "dep_build"
BUILD_DIR = REPO_ROOT / "build"

PY_VERSION = "3.12.9"
PYTHON_ZIP_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
PYSTAND_ZIP_URL = "https://github.com/skywind3000/PyStand/releases/download/1.1.4/PyStand-v1.1.4-exe.zip"
PYSTAND_EXE_IN_ZIP = "PyStand-x64-CLI/PyStand.exe"

SUBMODULE = REPO_ROOT / "pdf2zh" / "kernel" / "PDFMathTranslate-next.git"


def step(msg: str) -> None:
    print(f"\n==== {msg} ====", flush=True)


def download(url: str, dest: Path) -> None:
    """下载文件（走系统代理），带百分比进度。"""
    if dest.exists():
        print(f"复用已下载: {dest}")
        return
    print(f"下载: {url}")
    started = time.perf_counter()

    def hook(blocks: int, block_size: int, total: int) -> None:
        if total > 0:
            pct = min(blocks * block_size * 100 // total, 100)
            print(f"\r  {pct}% ({blocks * block_size / 1024 / 1024:.1f} MB)", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print(f"  完成 ({time.perf_counter() - started:.1f}s)")


def unzip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def run(cmd: list[str], **kw) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def clear_build(clean: bool) -> None:
    """清理旧 build/: --clean 真删除, 默认改名保留备份。"""
    if not BUILD_DIR.exists():
        return
    if clean:
        print("彻底删除旧 build/ ...")
        shutil.rmtree(BUILD_DIR)
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = REPO_ROOT / f"build_prev_{stamp}"
    n = 0
    while backup.exists():
        n += 1
        backup = REPO_ROOT / f"build_prev_{stamp}_{n}"
    try:
        BUILD_DIR.rename(backup)
        print(f"旧 build/ 已保留为: {backup.name}")
    except PermissionError as e:
        raise SystemExit(
            f"错误: 无法重命名旧 build/（可能有 python 进程占用其内部目录）: {e}\n"
            "请结束相关 python 进程后重试, 或使用 --clean 彻底删除。"
        )


def ensure_uv() -> None:
    if shutil.which("uv") is None:
        raise SystemExit("错误: 未找到 uv, 请先安装: pip install uv")
    run(["uv", "python", "install", "3.12"])


def uv_python() -> str:
    out = subprocess.run(
        ["uv", "python", "find", "3.12"], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def write_runtime_shim(runtime_dir: Path) -> None:
    """已废弃: bitstring 固定 4.3.0 后原生含 BitStream, spawn 子进程从
    worker 父进程继承 sys.path (含捆绑目录), 无需 site/pth 机制。保留
    空实现仅为兼容调用点。"""
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", action="store_true", help="构建完成后立即打发布 zip")
    parser.add_argument("--clean", action="store_true", help="构建前彻底删除旧 build/（默认改名保留）")
    parser.add_argument("--allow-download", action="store_true", help="离线资源缓存缺失时联网下载")
    parser.add_argument("--no-precise", action="store_true", help="不捆绑 precise 内核（轻量包, fast-only）")
    args = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("错误: 此脚本仅用于 Windows 构建")
    if shutil.which("git") is None:
        raise SystemExit("错误: 未找到 git")
    ensure_uv()

    py_exe = uv_python()
    print(f"构建用 Python: {py_exe}")

    # ==== 1/7 清理 ====
    step("1/7 准备目录")
    clear_build(args.clean)
    (BUILD_DIR / "runtime").mkdir(parents=True, exist_ok=True)
    DEP_DIR.mkdir(parents=True, exist_ok=True)

    # ==== 2/7 Python embed ====
    step(f"2/7 下载 Python {PY_VERSION} embed")
    python_zip = DEP_DIR / "python.zip"
    download(PYTHON_ZIP_URL, python_zip)
    unzip(python_zip, BUILD_DIR / "runtime")

    # ==== 3/7 PyStand ====
    step("3/7 准备 PyStand v1.1.4")
    pystand_zip = DEP_DIR / "PyStand.zip"
    download(PYSTAND_ZIP_URL, pystand_zip)
    pystand_src = DEP_DIR / "PyStand"
    if not (pystand_src / PYSTAND_EXE_IN_ZIP).exists():
        unzip(pystand_zip, pystand_src)
    shutil.copy2(pystand_src / PYSTAND_EXE_IN_ZIP, BUILD_DIR / "pdf2zh.exe")

    # ==== 4/7 主依赖 ====
    step("4/7 uv 安装主依赖 -> build/site-packages")
    run(["uv", "pip", "install", "--python", py_exe, "--target", BUILD_DIR / "site-packages", "."])

    # ==== 4b/7 precise 捆装 ====
    if args.no_precise:
        step("4b/7 跳过 precise 捆装 (--no-precise, 轻量包)")
    else:
        step("4b/7 捆装 precise 内核依赖 (pdf2zh_next)")
        if not (SUBMODULE / "pyproject.toml").exists():
            raise SystemExit(
                "错误: precise 内核 submodule 未初始化\n"
                "请先执行: git submodule update --init pdf2zh/kernel/PDFMathTranslate-next.git"
            )
        # 先装进独立 staging 目录再复制: 直接 --target 到主 site-packages
        # 会把共享依赖(tencentcloud-sdk 等)升级污染主程序。
        # bitstring 固定 4.3.0: 原生含 BitStream, babeldoc 兼容, 免 shim。
        stage = DEP_DIR / "_precise_stage"
        if stage.exists():
            shutil.rmtree(stage)
        constraints = DEP_DIR / "_precise_constraints.txt"
        constraints.write_text("bitstring==4.3.0\n", encoding="utf-8")
        run([
            "uv", "pip", "install", "--python", py_exe,
            "--target", stage,
            SUBMODULE,
        ])
        dest = BUILD_DIR / "site-packages" / "pdf2zh" / "kernel" / "_precise_packages"
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, dest)

    # ==== 5/7 主 sitecustomize ====
    step("5/7 写 sitecustomize.py (BitStream 兼容层)")
    (BUILD_DIR / "site-packages" / "sitecustomize.py").write_text(
        "try:\n"
        "    from bitstring import BitStream\n"
        "except ImportError:\n"
        "    from bitstring import BitArray\n"
        "    import bitstring\n"
        "    bitstring.BitStream = BitArray\n",
        encoding="utf-8",
    )

    # ==== 5b/7 运行时 shim ====
    step("5b/7 注入运行时 shim (babeldoc spawn 子进程必需)")
    write_runtime_shim(BUILD_DIR / "runtime")

    # ==== 6/7 启动脚本 ====
    step("6/7 复制 _pystand_static.int")
    shutil.copy2(REPO_ROOT / "script" / "_pystand_static.int", BUILD_DIR / "_pystand_static.int")

    # ==== 7/7 离线资源 ====
    step("7/7 生成离线资源")
    extra = ["--allow-download"] if args.allow_download else []
    # 注意: 用裸 uv Python + PYTHONPATH 指向 build/site-packages,
    # 不能用 uv venv 的解释器 (两套依赖树混用会冲突)
    env = {**os.environ, "PYTHONPATH": str(BUILD_DIR / "site-packages")}
    run([py_exe, REPO_ROOT / "script" / "make_offline_assets.py", *extra, BUILD_DIR], env=env)

    print("\n==== 构建完成! ====")
    print(f"输出目录: {BUILD_DIR}")
    print(f"可执行文件: {BUILD_DIR / 'pdf2zh.exe'}")
    print("启动: build/pdf2zh.exe --interactive")

    if args.package:
        step("打包发布 zip")
        run([sys.executable, REPO_ROOT / "script" / "package_win64.py"])


if __name__ == "__main__":
    main()
