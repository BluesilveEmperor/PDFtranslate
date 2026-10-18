# 强制 stdout/stderr 用 UTF-8：启动横幅等中文输出在非中文 Windows（cp1252）
# 且输出被重定向（CI、管道）时会 UnicodeEncodeError 直接崩溃
import sys as _sys

for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass

# 兼容 babeldoc：bitstring 4.x/5.x 移除了 BitStream，babeldoc 仍 import 它
try:
    from bitstring import BitStream  # noqa: F401
except ImportError:
    from bitstring import BitArray
    import bitstring
    bitstring.BitStream = BitArray

# babeldoc 在 site-packages 下 import 时会 print("not in git repo")，
# 该输出由 babeldoc.const 触发、被各子模块延迟加载。
# 这里在静音窗口内显式预加载，保持终端干净
import contextlib
import io

with contextlib.redirect_stdout(io.StringIO()):
    import babeldoc  # noqa: F401
    import babeldoc.const  # noqa: F401

import logging

log = logging.getLogger(__name__)

__version__ = "1.9.12"
__author__ = "Byaidu"
__all__ = ["translate", "translate_stream"]


def __getattr__(name):
    if name in {"translate", "translate_stream"}:
        from pdf2zh.high_level import translate, translate_stream

        return {"translate": translate, "translate_stream": translate_stream}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
