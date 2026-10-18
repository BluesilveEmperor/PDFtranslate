# -*- coding: utf-8 -*-
"""从本地 babeldoc 缓存生成离线资产包（跳过联网 warmup）。

babeldoc --generate-offline-assets 需要联网校验/下载全部资产，在
HuggingFace 直连不通的环境（本机）会因 SSL/404 失败。本脚本假设
缓存已补齐（见 build.sh 注释），直接校验本地缓存并打包。

用法:
    conda run -n pdf2zh_build python script/make_offline_assets.py [output_dir]

缓存缺失时先用 hf-mirror 手动补齐，例如:
    curl -L -o ~/.cache/babeldoc/fonts/SourceHanSansCN-Bold.ttf \
      "https://hf-mirror.com/datasets/awwaawwa/BabelDOC-Assets/resolve/main/fonts/SourceHanSansCN-Bold.ttf?download=true"
"""
import sys
import zipfile
from pathlib import Path

from babeldoc.assets import assets as A


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build")
    file_list = A.generate_all_assets_file_list()
    tag = A.get_offline_assets_tag(file_list)

    bad = []
    for file_type, descs in file_list.items():
        for d in descs:
            p = A.get_cache_file_path(d["name"], file_type)
            if not A.verify_file(p, d["sha3_256"]):
                bad.append(f"{file_type}/{d['name']}")
    if bad:
        print("缓存中以下文件缺失或校验失败，请先用 hf-mirror 补齐:")
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
                p = A.get_cache_file_path(d["name"], file_type)
                with p.open("rb") as f:
                    zf.writestr(f"{file_type}/{d['name']}", f.read())
    print(f"离线资产包已生成: {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()