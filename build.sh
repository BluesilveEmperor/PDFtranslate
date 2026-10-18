#!/bin/bash
set -e
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
# 改用本地缓存打包: 从 ~/.cache/babeldoc/ 校验并打 zip, 无需联网。
# 不用 conda run 转发输出(它会按 GBK 重编码导致中文乱码), 直接调 env 的 python.exe
"$PY_EXE" script/make_offline_assets.py build

echo ""
echo "==== 构建完成！===="
echo "输出目录: build/"
echo "可执行文件: build/pdf2zh.exe"
echo "启动: build/pdf2zh.exe --interactive"