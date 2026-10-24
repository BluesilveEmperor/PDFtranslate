"""程序根目录与配置 / 缓存目录的定位。

用户需求：不希望配置与缓存散落在用户主目录（例如
``C:\\Users\\***\\config\\PDFMathTranslate``），而是以隐藏文件形式保存到
「程序所在文件夹的根目录」下的 ``config/pdf-cache/``。

本模块提供三项能力：

- :func:`app_root` —— 推导程序根目录，兼容便携打包与源码两种布局，并允许
  通过环境变量 ``PDF2ZH_HOME`` 显式覆盖；
- :func:`cache_dir` —— 返回并准备好 ``<app_root>/config/pdf-cache`` 目录；
- :func:`ensure_hidden` —— 尽力把文件 / 目录标记为隐藏（Windows 打隐藏属性）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Union

logger = logging.getLogger(__name__)

#: 显式指定程序根目录的环境变量名（便携版启动器可用它覆盖自动推导）。
ENV_APP_HOME = "PDF2ZH_HOME"

#: 最终缓存 / 配置所在的两级子目录：``<app_root>/config/pdf-cache``。
_CONFIG_SUBDIR = "config"
_CACHE_SUBDIR = "pdf-cache"

#: Python 安装布局中标识「站点包」的目录名。
_SITE_PACKAGE_DIRS = frozenset({"site-packages", "dist-packages"})

#: 进程内缓存：避免每次调用都重复 mkdir / 设置属性。
#: 以 app_root 为 key，保证同一进程内不同根目录（含测试场景）互不串扰。
_cache_dir_cache: Dict[Path, Path] = {}


def app_root() -> Path:
    """返回「程序所在文件夹的根目录」。

    推导规则（优先级从高到低）：

    1. 若环境变量 ``PDF2ZH_HOME`` 已设置，返回其 ``expanduser`` 后的绝对路径。
       便携版启动器可借此显式指定运行目录。
    2. 若本文件位于 ``<root>/site-packages/pdf2zh/app_paths.py``（便携版布局），
       返回 ``<root>``，即 ``site-packages`` 的父目录。
    3. 否则（源码 / 开发模式），返回 ``pdf2zh`` 包的父目录，即仓库根。

    这里刻意不做缓存：``PDF2ZH_HOME`` 可能在运行期被修改（例如测试），而路径
    推导本身开销极小。
    """
    env_home = os.environ.get(ENV_APP_HOME)
    if env_home:
        return Path(env_home).expanduser().resolve()

    package_dir = Path(__file__).resolve().parent  # .../pdf2zh
    parent = package_dir.parent
    if parent.name.lower() in _SITE_PACKAGE_DIRS:
        # 便携版：把 site-packages 的父目录视为程序根。
        return parent.parent
    # 源码 / 开发模式：仓库根 = pdf2zh 包的父目录。
    return parent


def cache_dir() -> Path:
    """返回 ``<app_root>/config/pdf-cache``，确保目录存在且已设为隐藏。

    结果按 ``app_root`` 做进程内缓存，避免重复创建目录。
    """
    root = app_root()
    cached = _cache_dir_cache.get(root)
    if cached is not None:
        return cached

    target = root / _CONFIG_SUBDIR / _CACHE_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    # 需求要求最终落在隐藏目录中；对 config 与 pdf-cache 两级都尝试设置，
    # 使目录在文件管理器中默认不可见。
    ensure_hidden(target.parent)
    ensure_hidden(target)

    _cache_dir_cache[root] = target
    return target


def ensure_hidden(path: Union[str, os.PathLike]) -> None:
    """尽力把 ``path``（文件或目录）标记为隐藏，失败静默忽略。

    - Windows：用 ``ctypes`` 调用 ``kernel32.SetFileAttributesW``，在原有属性
      位上按位或上 ``FILE_ATTRIBUTE_HIDDEN``，不改动其它属性位；
    - 其它平台：Unix 无对应文件属性，保持 no-op（不使用点号前缀，以免改变用户
      指定的 ``config/pdf-cache`` 目录名）。

    任何异常都被吞掉：隐藏失败绝不能导致程序中断。
    """
    try:
        target = Path(path)
        if not target.exists():
            return
        if os.name != "nt":
            return

        import ctypes

        FILE_ATTRIBUTE_HIDDEN = 0x02
        INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

        kernel32 = ctypes.windll.kernel32
        attrs = kernel32.GetFileAttributesW(str(target))
        if attrs == INVALID_FILE_ATTRIBUTES:
            return
        if attrs & FILE_ATTRIBUTE_HIDDEN:
            return  # 已是隐藏，无需重复设置
        kernel32.SetFileAttributesW(str(target), attrs | FILE_ATTRIBUTE_HIDDEN)
    except Exception:  # noqa: BLE001 - best-effort，绝不因隐藏失败中断
        logger.debug("ensure_hidden failed for %s", path, exc_info=True)
