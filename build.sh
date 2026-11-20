#!/bin/bash
set -e

# ==== 平台检测（git-bash/Windows、Linux、macOS）====
OS="$(uname -s)"
case "$OS" in
    MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
    Linux*)               PLATFORM="linux"  ;;
    Darwin*)              PLATFORM="macos"  ;;
    *) echo "错误: 不支持的平台 $OS"; exit 1 ;;
esac
echo "==== 构建平台: $PLATFORM ===="

# 可选环境变量（对所有平台的第 7/6 步生效）:
#   ASSETS_CACHE_DIR=/path/to/babeldoc_cache   指定资产缓存目录
#       （WSL 里复用 Windows 侧缓存: /mnt/c/Users/<user>/.cache/babeldoc）
#   ASSETS_ALLOW_DOWNLOAD=1                    缓存缺失时联网 warmup 下载
#       （CI / 网络畅通环境使用）
#   BUNDLE_PRECISE=0                           不捆绑 precise 内核依赖
#       （包体积 -约450MB；打包版将不可用 precise 模式，默认 1 捆绑）
ASSETS_CACHE_DIR="${ASSETS_CACHE_DIR:-}"
ASSETS_ALLOW_DOWNLOAD="${ASSETS_ALLOW_DOWNLOAD:-0}"
BUNDLE_PRECISE="${BUNDLE_PRECISE:-1}"

build_offline_assets () {
    # $1: python 解释器  $2: 输出目录
    local extra=()
    [ -n "$ASSETS_CACHE_DIR" ] && extra+=(--cache-dir "$ASSETS_CACHE_DIR")
    [ "$ASSETS_ALLOW_DOWNLOAD" = "1" ] && extra+=(--allow-download)
    "$1" script/make_offline_assets.py "${extra[@]}" "$2"
}


if [ "$PLATFORM" = "windows" ]; then
    # ================ Windows: Python embed + PyStand（git-bash 环境） ================
    PY_VER="3.12.9"

    echo "==== 1/7 创建目录 ===="
    # 注意: 只清理 build; dep_build 存放已下载的 python.zip/PyStand.zip 等依赖, 保留复用
    rm -rf build
    mkdir -p build/runtime dep_build

    echo "==== 2/7 下载 Python $PY_VER embed ===="
    if [ ! -f dep_build/python.zip ]; then
        curl -L -o dep_build/python.zip "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-embed-amd64.zip"
    else
        echo "复用已下载的 dep_build/python.zip"
    fi
    unzip -q -o dep_build/python.zip -d build/runtime

    echo "==== 3/7 准备 PyStand v1.1.4 ===="
    if [ ! -f dep_build/PyStand/PyStand-x64-CLI/PyStand.exe ]; then
        curl -L -o dep_build/PyStand.zip "https://github.com/skywind3000/PyStand/releases/download/1.1.4/PyStand-v1.1.4-exe.zip"
        unzip -q -o dep_build/PyStand.zip -d dep_build/PyStand
    else
        echo "复用本地 dep_build/PyStand"
    fi
    cp dep_build/PyStand/PyStand-x64-CLI/PyStand.exe build/pdf2zh.exe

    echo "==== 4/7 uv 安装 Python 3.12 与依赖 ===="
    # 原方案复制 conda env (pdf2zh_build) 的 site-packages, 该环境已不存在;
    # 改用 uv 安装托管 CPython 3.12, 依赖装到 build/site-packages (win_amd64
    # wheel, 兼容 3.12.9 embed 运行时), 与 Linux/macOS 分支的 uv 方案一致
    uv python install 3.12
    PY_EXE="$(cygpath -u "$(uv python find 3.12)")"
    uv pip install --python "$PY_EXE" --target build/site-packages .

    if [ "$BUNDLE_PRECISE" = "1" ]; then
        echo "==== 4b/7 捆绑 precise 内核依赖 (pdf2zh_next) ===="
        # precise 内核在便携包内以"捆绑模式"运行: 依赖预装到
        # build/site-packages/pdf2zh/kernel/_precise_packages, 运行时由
        # precise.py 注入 sys.path, 无需 venv/pip (embed 运行时没有它们)
        if [ ! -f pdf2zh/kernel/PDFMathTranslate-next.git/pyproject.toml ]; then
            echo "错误: precise 内核 submodule 未初始化" >&2
            echo "请先执行: git submodule update --init pdf2zh/kernel/PDFMathTranslate-next.git" >&2
            exit 1
        fi
        uv pip install --python "$PY_EXE" \
            --target build/site-packages/pdf2zh/kernel/_precise_packages \
            ./pdf2zh/kernel/PDFMathTranslate-next.git
    else
        echo "==== 4b/7 跳过 precise 捆绑 (BUNDLE_PRECISE=0, 包体积更小) ===="
    fi

    echo "==== 5/7 写 sitecustomize.py (BitStream 兼容层) ===="
    cat > build/site-packages/sitecustomize.py << 'EOF'
try:
    from bitstring import BitStream
except ImportError:
    from bitstring import BitArray
    import bitstring
    bitstring.BitStream = BitArray
EOF

    echo "==== 5b/7 运行时注入 BitStream shim (babeldoc 多进程子进程也需要) ===="
    # embed 运行时 python312._pth 默认不执行 site; babeldoc spawn 的子进程
    # 走裸 python.exe 初始化, 不经过 PyStand/worker bootstrap, 缺 BitStream
    # shim 会 ImportError 并导致 babeldoc 无限重试。
    # 启用 import site 后, runtime/Lib/site-packages 成为标准 site 目录:
    #   - precise_kernel.pth 把捆绑的 _precise_packages 追加进 sys.path
    #   - 并执行 import bitstream_shim 给当前进程打上 BitStream 兼容层
    # 对所有 python.exe 进程生效 (PyStand 父进程 / worker / spawn 子进程)。
    sed -i 's/^#import site/import site/' build/runtime/python312._pth
    mkdir -p build/runtime/Lib/site-packages
    cat > build/runtime/Lib/site-packages/precise_kernel.pth << 'EOF'
../../../site-packages/pdf2zh/kernel/_precise_packages
import bitstream_shim
EOF
    cat > build/runtime/Lib/site-packages/bitstream_shim.py << 'EOF'
try:
    from bitstring import BitStream
except ImportError:
    import bitstring
    bitstring.BitStream = bitstring.BitArray
EOF
    cat > build/runtime/sitecustomize.py << 'EOF'
# 防止用户机器上的 user site-packages 混入便携包 (依赖版本不可控)
import sys as _sys
for _p in [p for p in _sys.path if "Roaming\\Python" in p or "Roaming/Python" in p]:
    _sys.path.remove(_p)
EOF

    echo "==== 6/7 复制 _pystand_static.int ===="
    cp script/_pystand_static.int build/_pystand_static.int

    echo "==== 7/7 生成离线资源 ===="
    # 注: babeldoc --generate-offline-assets 需要联网校验(本机直连 HuggingFace 不通),
    # 改用本地缓存打包: 从缓存目录校验并打 zip, 缺失时可加 ASSETS_ALLOW_DOWNLOAD=1。
    # 依赖在 build/site-packages 里, 需显式加 PYTHONPATH
    PYTHONPATH="$PWD/build/site-packages" build_offline_assets "$PY_EXE" build

    echo ""
    echo "==== 构建完成！===="
    echo "输出目录: build/"
    echo "可执行文件: build/pdf2zh.exe"
    echo "启动: build/pdf2zh.exe --interactive"
    exit 0
fi


# ================ Linux / macOS: uv + python-build-standalone 便携运行时 ================
# 与 Windows 版产物结构对称: build/{runtime, site-packages, 离线zip} + 启动器
PY_VER="3.12"

# 可选环境变量 TARGET_ARCH（仅 Linux/macOS 分支生效, Windows 分支忽略）:
#   缺省/空  = 跟随本机架构（现状行为, 不变）
#   x86_64   = macOS 下交叉构建 Intel x86_64 便携包:
#              uv 架构限定请求安装 x86_64 python-build-standalone（失败时回退
#              GitHub Releases 直接下载 install_only 包）, 依赖安装显式指定
#              --python-platform x86_64-apple-darwin; 资产打包等步骤经 Rosetta 2
#              执行 x86_64 解释器, 与 arm64 产物结构完全同构
#   arm64    = macOS 下显式 arm64（与缺省在本机为 ARM 时等价）
TARGET_ARCH="${TARGET_ARCH:-}"

echo "==== 1/6 创建目录 ===="
rm -rf build dep_build
mkdir -p build dep_build

echo "==== 2/6 安装 uv, 下载 Python $PY_VER 便携版 (python-build-standalone) ===="
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$PWD/dep_build/uv" sh
export UV_PYTHON_INSTALL_DIR="$PWD/dep_build/uv-python"
UV="$PWD/dep_build/uv/uv"

# 交叉构建时依赖安装的目标平台覆盖（缺省为空数组 = 不覆盖, 行为不变）
UV_PIP_PLATFORM_ARGS=()

if [ "$PLATFORM" = "macos" ] && [ "$TARGET_ARCH" = "x86_64" ]; then
    # ==== Intel macOS (x86_64) 交叉构建 ====
    # 主/回退路径同为 Python 3.12.7 (x86_64-apple-darwin, install_only 布局)
    PY_VER_X64="3.12.7"
    PBS_TAG="20241016"
    PY_ROOT="$UV_PYTHON_INSTALL_DIR/cpython-$PY_VER_X64-macos-x86_64-none"
    if "$UV" python install "cpython-$PY_VER_X64-macos-x86_64-none" && [ -x "$PY_ROOT/install/bin/python3.12" ]; then
        PY_PREFIX="$PY_ROOT/install"
    elif [ -x "$PY_ROOT/bin/python3.12" ]; then
        PY_PREFIX="$PY_ROOT"
    else
        echo "uv 架构限定安装不可用, 回退 GitHub Releases 直接下载 (tag $PBS_TAG)"
        curl -L -o dep_build/cpython-x64.tar.gz \
            "https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_TAG/cpython-$PY_VER_X64+$PBS_TAG-x86_64-apple-darwin-install_only.tar.gz"
        mkdir -p dep_build/pbs-x64
        tar xzf dep_build/cpython-x64.tar.gz -C dep_build/pbs-x64
        PY_PREFIX="$PWD/dep_build/pbs-x64/python"
    fi
    PY_EXE="$PY_PREFIX/bin/python3.12"
    UV_PIP_PLATFORM_ARGS=(--python-platform x86_64-apple-darwin)
    echo "交叉构建 x86_64 便携 Python: $PY_EXE"
else
    "$UV" python install "$PY_VER"
    PY_EXE="$("$UV" python find "$PY_VER")"
    PY_PREFIX="$(dirname "$(dirname "$PY_EXE")")"
    echo "便携 Python: $PY_EXE"
fi

echo "==== 3/6 复制便携 Python → build/runtime ===="
# -L 强制实体化: uv-python 下的 cpython-3.12-... 是指向 cpython-3.12.x-... 的
# 符号链接, 不加 -L 时 build/runtime 只是一个链接, 脱离本机(如 CI test job /
# 用户解压后)即失效; -L 同时把 bin/python3 等别名链接也实体化, 分发更稳
cp -rL "$PY_PREFIX" build/runtime

echo "==== 4/6 安装依赖 → build/site-packages ===="
"$UV" pip install --python "$PY_EXE" --target build/site-packages "${UV_PIP_PLATFORM_ARGS[@]}" .

echo "==== 4b/6 捆绑 precise 内核依赖 (pdf2zh_next) ===="
if [ ! -f pdf2zh/kernel/PDFMathTranslate-next.git/pyproject.toml ]; then
    echo "错误: precise 内核 submodule 未初始化" >&2
    echo "请先执行: git submodule update --init pdf2zh/kernel/PDFMathTranslate-next.git" >&2
    exit 1
fi
"$UV" pip install --python "$PY_EXE" "${UV_PIP_PLATFORM_ARGS[@]}" \
    --target build/site-packages/pdf2zh/kernel/_precise_packages \
    ./pdf2zh/kernel/PDFMathTranslate-next.git

echo "==== 5/6 写 sitecustomize.py + 启动器 ===="
cat > build/site-packages/sitecustomize.py << 'EOF'
try:
    from bitstring import BitStream
except ImportError:
    from bitstring import BitArray
    import bitstring
    bitstring.BitStream = BitArray
EOF

cat > build/launch_pdf2zh.py << 'EOF'
import sys
import pdf2zh.pdf2zh
import os
import babeldoc.assets.assets
import pathlib

WAIT_FOR_INPUT = False
if len(sys.argv) == 1:
    sys.argv.append("-i")  # 无参数时自动添加 -i 参数
    WAIT_FOR_INPUT = True

base = os.path.dirname(os.path.abspath(__file__))
files = os.listdir(base)
for file in files:
    if file.endswith(".zip") and file.startswith("offline_assets_"):
        print('find offline_assets_zip file: ', file, ' try restore...')
        babeldoc.assets.assets.restore_offline_assets_package(pathlib.Path(base))

try:
    code = pdf2zh.pdf2zh.main()
    print(f"pdf2zh.pdf2zh.main() return code: {code}")
    if WAIT_FOR_INPUT:
        input("Press Enter to continue...")
    sys.exit(code)
except Exception:
    import traceback
    traceback.print_exc()
    if WAIT_FOR_INPUT:
        input("Press Enter to continue...")
    sys.exit(1)
EOF

cat > build/pdf2zh << 'EOF'
#!/bin/sh
# pdf2zh 启动器: 使用内嵌 runtime + site-packages, 解压即可用
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export PYTHONPATH="$DIR/site-packages${PYTHONPATH:+:$PYTHONPATH}"
exec "$DIR/runtime/bin/python3" "$DIR/launch_pdf2zh.py" "$@"
EOF
chmod +x build/pdf2zh

echo "==== 6/6 生成离线资源 ===="
# 便携 Python 是裸解释器, 依赖在 build/site-packages 里, 需显式加 PYTHONPATH
PYTHONPATH="$PWD/build/site-packages" build_offline_assets "$PY_EXE" build

echo ""
echo "==== 构建完成！===="
echo "输出目录: build/"
echo "可执行文件: build/pdf2zh"
echo "启动: ./build/pdf2zh --interactive"
if [ "$PLATFORM" = "macos" ] && [ "$TARGET_ARCH" = "x86_64" ]; then
    echo "分发: tar czf pdf2zh-macos-x64.tar.gz build/"
else
    echo "分发: tar czf pdf2zh-$(uname -s | tr 'A-Z' 'a-z')-$(uname -m).tar.gz build/"
fi