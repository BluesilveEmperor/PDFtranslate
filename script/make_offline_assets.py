# -*- coding: utf-8 -*-
"""从本地 babeldoc 缓存生成离线资产包（默认跳过联网 warmup）。

babeldoc --generate-offline-assets 需要联网校验/下载全部资产，在
HuggingFace 直连不通的环境（本机）会因 SSL/404 失败。本脚本直接校验
本地缓存并打包；缓存缺失时可选择联网 warmup 补齐。

用法:
    python script/make_offline_assets.py [output_dir] [选项]

选项:
    --cache-dir DIR      指定 babeldoc 缓存目录（默认 ~/.cache/babeldoc）。
                         WSL 里可传 /mnt/c/Users/<user>/.cache/babeldoc 复用
                         Windows 侧缓存。
    --allow-download     缓存缺失时不报错，先联网 warmup 下载再打包
                         （CI / 网络畅通环境使用）。

缓存缺失且不允许联网时，可从 hf-mirror 手动补齐，例如:
    curl -L -o ~/.cache/babeldoc/fonts/SourceHanSansCN-Bold.ttf \
      "https://hf-mirror.com/datasets/awwaawwa/BabelDOC-Assets/resolve/main/fonts/SourceHanSansCN-Bold.ttf?download=true"
"""
import argparse
import sys
import zipfile
from pathlib import Path

# conda run 下 stdout 可能是 GBK, 中文输出在 git-bash 里会乱码, 强制 UTF-8
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

from babeldoc import const as babeldoc_const
from babeldoc.assets import assets as A


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从本地 babeldoc 缓存生成离线资产包"
    )
    parser.add_argument(
        "output_dir", nargs="?", default="build", help="输出目录（默认 build）"
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="babeldoc 缓存目录（默认 ~/.cache/babeldoc）",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="缓存缺失时联网 warmup 下载（默认直接报错退出）",
    )
    args = parser.parse_args()

    if args.cache_dir:
        # get_cache_file_path 运行时读取 const.CACHE_FOLDER, patch 后即生效
        babeldoc_const.CACHE_FOLDER = Path(args.cache_dir).expanduser().resolve()

    out_dir = Path(args.output_dir)
    file_list = A.generate_all_assets_file_list()
    tag = A.get_offline_assets_tag(file_list)

    def find_bad():
        bad = []
        for file_type, descs in file_list.items():
            for d in descs:
                p = babeldoc_const.get_cache_file_path(d["name"], file_type)
                if not A.verify_file(p, d["sha3_256"]):
                    bad.append(f"{file_type}/{d['name']}")
        return bad

    bad = find_bad()
    if bad:
        if not args.allow_download:
            print("缓存中以下文件缺失或校验失败（缓存目录:"
                  f" {babeldoc_const.CACHE_FOLDER}）:")
            for b in bad:
                print("  ", b)
            print("补齐方式: 加 --allow-download 联网下载, 或从 hf-mirror 手动下载")
            sys.exit(1)
        print(f"缓存缺失 {len(bad)} 个文件, 联网 warmup 下载中…")
        A.warmup()
        bad = find_bad()
        if bad:
            print("warmup 后仍缺失, 放弃:")
            for b in bad:
                print("  ", b)
            sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"offline_assets_{tag}.zip"
    with zipfile.ZipFile(
        out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        for file_type, descs in file_list.items():
            for d in descs:
                p = babeldoc_const.get_cache_file_path(d["name"], file_type)
                with p.open("rb") as f:
                    zf.writestr(f"{file_type}/{d['name']}", f.read())
    print(f"离线资产包已生成: {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()