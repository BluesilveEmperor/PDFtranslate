"""支持 ``python -m pdf2zh.toolbox`` 调用工具箱命令行。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
