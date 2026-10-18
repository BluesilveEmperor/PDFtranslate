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
ASSETS_CACHE_DIR="${ASSETS_CACHE_DIR:-}"
ASSETS_ALLOW_DOWNLOAD="${ASSETS_ALLOW_DOWNLOAD:-0}"

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
    CONDA_SP="/c/Users/HW/miniconda3/envs/pdf2zh_build/Lib/site-packages"
    PY_EXE="/c/Users/HW/miniconda3/envs/pdf2zh_build/python.exe"

    echo "==== 1/7 创建目录 ===="
    rm -rf build dep_build
    mkdir -p build/runtime dep_build

    echo "==== 2/7 下载 Python $PY_VER embed ===="
    curl -L -o dep_build/python.zip "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-embed-amd64.zip"
    unzip -q -o dep_build/python.zip -d build/runtime

    echo "==== 3/7 下载 PyStand v1.1.4 ===="
    curl -L -o dep_build/PyStand.zip "https://github.com/skywind3000/PyStand/releases/download/1.1.4/PyStand-v1.1.4-exe.zip"
    unzip -q -o dep_build/PyStand.zip -d dep_build/PyStand
    cp dep_build/PyStand/PyStand-x64-CLI/PyStand.exe build/pdf2zh.exe

    echo "==== 4/7 复制 conda site-packages ===="
    cp -r "$CONDA_SP" build/site-packages

    echo "==== 5/7 写 sitecustomize.py (BitStream 兼容层) ===="
    cat > build/site-packages/sitecustomize.py << 'EOF'
try:
    from bitstring import BitStream
except ImportError:
    from bitstring import BitArray
    import bitstring
    bitstring.BitStream = BitArray
EOF

    echo "==== 6/7 复制 _pystand_static.int ===="
    cp script/_pystand_static.int build/_pystand_static.int

    echo "==== 7/7 生成离线资源 ===="
    # 注: babeldoc --generate-offline-assets 需要联网校验(本机直连 HuggingFace 不通),
    # 改用本地缓存打包: 从缓存目录校验并打 zip, 缺失时可加 ASSETS_ALLOW_DOWNLOAD=1。
    # 不用 conda run 转发输出(它会按 GBK 重编码导致中文乱码), 直接调 env 的 python.exe
    build_offline_assets "$PY_EXE" build

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

echo "==== 1/6 创建目录 ===="
rm -rf build dep_build
mkdir -p build dep_build

echo "==== 2/6 安装 uv, 下载 Python $PY_VER 便携版 (python-build-standalone) ===="
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$PWD/dep_build/uv" sh
export UV_PYTHON_INSTALL_DIR="$PWD/dep_build/uv-python"
UV="$PWD/dep_build/uv/uv"
"$UV" python install "$PY_VER"
PY_EXE="$("$UV" python find "$PY_VER")"
PY_PREFIX="$(dirname "$(dirname "$PY_EXE")")"
echo "便携 Python: $PY_EXE"

echo "==== 3/6 复制便携 Python → build/runtime ===="
cp -r "$PY_PREFIX" build/runtime

echo "==== 4/6 安装依赖 → build/site-packages ===="
"$UV" pip install --python "$PY_EXE" --target build/site-packages .

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
echo "分发: tar czf pdf2zh-$(uname -s | tr 'A-Z' 'a-z')-$(uname -m).tar.gz build/"