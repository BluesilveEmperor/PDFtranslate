"""GUI 命令元数据表：驱动表单自动生成与 argv 组装。

字段类型:
  pdf_in      单个输入 PDF（可拖入）
  pdfs_in     多个输入 PDF（可拖入，支持目录/通配符由 CLI 展开）
  images_in   多个图片文件
  file        任意单个文件
  save_file   输出文件路径
  out_dir     输出目录
  text        文本
  int / float 数值
  choice      下拉选择
  bool        开关（对应 store_true 参数）

字段键: 位置参数用 "inputs"/"input"/"images"/"input_a"/"input_b"，
        可选参数用 CLI flag（如 "-o", "--dpi"）。
"""

CATEGORIES = [
    ("页面操作", "cat_pages"),
    ("内容编辑", "cat_edit"),
    ("安全", "cat_security"),
    ("PDF 转换", "cat_convert"),
    ("Office 转换", "cat_office"),
]

PAGE_EXPR_HELP = "页码范围表达式,如 1-3,5,7-9"

COMMANDS = {
    # ---------- 页面操作 ----------
    "merge": {
        "cat": "页面操作", "label": "合并 PDF", "icon": "merge",
        "desc": "将多个 PDF 按顺序合并为一个文件",
        "fields": [
            {"key": "inputs", "label": "输入 PDF(可多个)", "type": "pdfs_in", "required": True},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True,
             "default": "merged.pdf"},
        ],
    },
    "split": {
        "cat": "页面操作", "label": "拆分 PDF", "icon": "split",
        "desc": "按页数或范围把 PDF 拆成多份(--every 与 --ranges 二选一)",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-o", "label": "输出目录", "type": "out_dir", "required": True,
             "default": "parts"},
            {"key": "--every", "label": "每 N 页一份", "type": "int"},
            {"key": "--ranges", "label": "按范围拆分", "type": "text",
             "help": "如 1-3,4-9,每个范围出一份"},
        ],
    },
    "extract": {
        "cat": "页面操作", "label": "提取页面", "icon": "extract",
        "desc": "提取指定页面生成新 PDF",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-p", "label": "页码", "type": "text", "required": True,
             "help": PAGE_EXPR_HELP},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "delete": {
        "cat": "页面操作", "label": "删除页面", "icon": "delete",
        "desc": "删除指定页面",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-p", "label": "删除页码", "type": "text", "required": True,
             "help": PAGE_EXPR_HELP},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "insert": {
        "cat": "页面操作", "label": "插入页面", "icon": "insert",
        "desc": "将另一 PDF 的全部页面插入指定位置",
        "fields": [
            {"key": "input", "label": "主 PDF", "type": "pdf_in", "required": True},
            {"key": "--file", "label": "被插入的 PDF", "type": "pdf_in", "required": True},
            {"key": "--pos", "label": "插入位置", "type": "int", "default": -1,
             "help": "0 起,-1 为末尾"},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "rotate": {
        "cat": "页面操作", "label": "旋转页面", "icon": "rotate",
        "desc": "旋转指定页面",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--angle", "label": "角度", "type": "choice",
             "choices": ["90", "180", "270"], "default": "90", "required": True},
            {"key": "-p", "label": "页码(空=全部)", "type": "text",
             "help": PAGE_EXPR_HELP},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "cut": {
        "cat": "页面操作", "label": "裁剪边距", "icon": "cut",
        "desc": "裁剪每页边距(单位 pt,1pt = 1/72 英寸)",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--left", "label": "左(pt)", "type": "float", "default": 0},
            {"key": "--right", "label": "右(pt)", "type": "float", "default": 0},
            {"key": "--top", "label": "上(pt)", "type": "float", "default": 0},
            {"key": "--bottom", "label": "下(pt)", "type": "float", "default": 0},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "pages-merger": {
        "cat": "页面操作", "label": "双份页面合并", "icon": "pages-merger",
        "desc": "两份 PDF 页面交错或追加合并",
        "fields": [
            {"key": "input_a", "label": "PDF A", "type": "pdf_in", "required": True},
            {"key": "input_b", "label": "PDF B", "type": "pdf_in", "required": True},
            {"key": "--mode", "label": "模式", "type": "choice",
             "choices": ["interleave", "append"], "default": "interleave",
             "help": "interleave=交错 A1B1A2B2 / append=追加"},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    # ---------- 内容编辑 ----------
    "page-number": {
        "cat": "内容编辑", "label": "添加页码", "icon": "page-number",
        "desc": "为每页添加页码",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--pos", "label": "位置", "type": "choice",
             "choices": ["top-left", "top-center", "top-right",
                          "bottom-left", "bottom-center", "bottom-right"],
             "default": "bottom-center"},
            {"key": "--start", "label": "起始页码", "type": "int", "default": 1},
            {"key": "--format", "label": "格式模板", "type": "text",
             "default": "{n}", "help": "{n} 为页码占位符,如 第 {n} 页"},
            {"key": "--size", "label": "字号", "type": "float", "default": 11},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "watermark-text": {
        "cat": "内容编辑", "label": "文字水印", "icon": "watermark-text",
        "desc": "添加平铺或居中的文字水印",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--text", "label": "水印文字", "type": "text", "required": True},
            {"key": "--angle", "label": "角度", "type": "float", "default": 45},
            {"key": "--opacity", "label": "不透明度(0-1)", "type": "float",
             "default": 0.15},
            {"key": "--size", "label": "字号", "type": "float", "default": 36},
            {"key": "--center", "label": "居中单个(默认平铺)", "type": "bool"},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "watermark-image": {
        "cat": "内容编辑", "label": "图片水印", "icon": "watermark-image",
        "desc": "添加图片水印(PNG 带 alpha 最佳)",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--image", "label": "水印图片", "type": "file", "required": True},
            {"key": "--opacity", "label": "不透明度(0-1)", "type": "float",
             "default": 0.5},
            {"key": "--scale", "label": "相对页宽比例", "type": "float",
             "default": 0.35},
            {"key": "--center", "label": "居中单个(默认平铺)", "type": "bool"},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "text-replace": {
        "cat": "内容编辑", "label": "替换文本", "icon": "text-replace",
        "desc": "全文检索并替换文本(红注遮盖 + 叠印新文本)",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--old", "label": "查找", "type": "text", "required": True},
            {"key": "--new", "label": "替换为", "type": "text", "default": ""},
            {"key": "-p", "label": "页码(空=全部)", "type": "text",
             "help": PAGE_EXPR_HELP},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "text-delete": {
        "cat": "内容编辑", "label": "删除文本", "icon": "text-delete",
        "desc": "删除指定文本(红注遮盖)",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--text", "label": "删除文本", "type": "text", "required": True},
            {"key": "-p", "label": "页码(空=全部)", "type": "text",
             "help": PAGE_EXPR_HELP},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "remove-links": {
        "cat": "内容编辑", "label": "删除链接", "icon": "remove-links",
        "desc": "删除 PDF 中全部链接",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    # ---------- 安全 ----------
    "encrypt": {
        "cat": "安全", "label": "加密 PDF", "icon": "encrypt",
        "desc": "AES-256 加密,可禁止打印/复制",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "--user-pw", "label": "打开密码", "type": "text",
             "required": True, "secret": True},
            {"key": "--owner-pw", "label": "权限密码(空=同打开密码)", "type": "text",
             "secret": True},
            {"key": "--no-print", "label": "禁止打印", "type": "bool"},
            {"key": "--no-copy", "label": "禁止复制", "type": "bool"},
            {"key": "-o", "label": "输出文件", "type": "save_file", "required": True},
        ],
    },
    "decrypt": {
        "cat": "安全", "label": "免密码解密", "icon": "decrypt",
        "desc": "无需密码:权限密码瞬时解除,未知打开密码自动多阶段恢复",
        "fields": [
            {"key": "input", "label": "加密 PDF", "type": "pdf_in", "required": True},
            {"key": "--wordlist", "label": "密码字典文件", "type": "file",
             "help": "每行一个密码,# 开头为注释"},
            {"key": "--charset", "label": "暴力字符集", "type": "text",
             "help": "默认小写字母+数字"},
            {"key": "--min-len", "label": "最小长度", "type": "int", "default": 1},
            {"key": "--max-len", "label": "最大长度", "type": "int", "default": 4},
            {"key": "--jobs", "label": "并行进程数(空=全核)", "type": "int"},
            {"key": "-o", "label": "保存位置", "type": "save_file",
             "help": "默认源目录,文件名自动加 Removed 前缀"},
        ],
    },
    # ---------- PDF 转换 ----------
    "pdf-to-image": {
        "cat": "PDF 转换", "label": "PDF 转图片", "icon": "pdf-to-image",
        "desc": "每页渲染为 PNG/JPG 等图片",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-o", "label": "输出目录", "type": "out_dir", "required": True},
            {"key": "--dpi", "label": "DPI", "type": "int", "default": 150},
            {"key": "--fmt", "label": "格式", "type": "choice",
             "choices": ["png", "jpg", "jpeg", "bmp", "tiff"], "default": "png"},
            {"key": "-p", "label": "页码(空=全部)", "type": "text",
             "help": PAGE_EXPR_HELP},
            {"key": "--quality", "label": "JPEG 质量", "type": "int", "default": 90},
        ],
    },
    "image-to-pdf": {
        "cat": "PDF 转换", "label": "图片转 PDF", "icon": "image-to-pdf",
        "desc": "多张图片合成 PDF",
        "fields": [
            {"key": "images", "label": "图片(可多个)", "type": "images_in",
             "required": True},
            {"key": "--page-size", "label": "页面尺寸", "type": "choice",
             "choices": ["auto", "a4", "a3", "letter"], "default": "auto"},
            {"key": "--margin", "label": "页边距(pt)", "type": "float", "default": 0},
            {"key": "-o", "label": "输出文件", "type": "save_file",
             "required": True},
        ],
    },
    "pdf-to-word": {
        "cat": "PDF 转换", "label": "PDF 转 Word", "icon": "pdf-to-word",
        "desc": "文本级重建为 .docx(保留字号/粗体/斜体)",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-o", "label": "输出文件(.docx)", "type": "save_file",
             "required": True},
            {"key": "-p", "label": "页码(空=全部)", "type": "text",
             "help": PAGE_EXPR_HELP},
        ],
    },
    "pdf-to-ppt": {
        "cat": "PDF 转换", "label": "PDF 转 PPT", "icon": "pdf-to-ppt",
        "desc": "转换为 .pptx(image 保真 / text 可编辑)",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-o", "label": "输出文件(.pptx)", "type": "save_file",
             "required": True},
            {"key": "--mode", "label": "模式", "type": "choice",
             "choices": ["image", "text"], "default": "image",
             "help": "image=整页图片保真 / text=每页一个文本框"},
            {"key": "--dpi", "label": "DPI(image 模式)", "type": "int",
             "default": 150},
            {"key": "-p", "label": "页码(空=全部)", "type": "text",
             "help": PAGE_EXPR_HELP},
        ],
    },
    "pdf-to-excel": {
        "cat": "PDF 转换", "label": "PDF 转 Excel", "icon": "pdf-to-excel",
        "desc": "每页一个工作表,优先表格识别",
        "fields": [
            {"key": "input", "label": "输入 PDF", "type": "pdf_in", "required": True},
            {"key": "-o", "label": "输出文件(.xlsx)", "type": "save_file",
             "required": True},
            {"key": "-p", "label": "页码(空=全部)", "type": "text",
             "help": PAGE_EXPR_HELP},
        ],
    },
    # ---------- Office 转换 ----------
    "word-to-pdf": {
        "cat": "Office 转换", "label": "Word 转 PDF", "icon": "word-to-pdf",
        "desc": ".docx → PDF,纯 Python 渲染,无需 Office",
        "fields": [
            {"key": "input", "label": "输入 .docx", "type": "file",
             "required": True},
            {"key": "-o", "label": "输出 PDF", "type": "save_file",
             "required": True},
        ],
    },
    "excel-to-pdf": {
        "cat": "Office 转换", "label": "Excel 转 PDF", "icon": "excel-to-pdf",
        "desc": ".xlsx/.xls → PDF,多 sheet 自适应列宽",
        "fields": [
            {"key": "input", "label": "输入 .xlsx/.xls", "type": "file",
             "required": True},
            {"key": "-o", "label": "输出 PDF", "type": "save_file",
             "required": True},
        ],
    },
    "ppt-to-pdf": {
        "cat": "Office 转换", "label": "PPT 转 PDF", "icon": "ppt-to-pdf",
        "desc": ".pptx → PDF,还原幻灯片尺寸与布局",
        "fields": [
            {"key": "input", "label": "输入 .pptx", "type": "file",
             "required": True},
            {"key": "-o", "label": "输出 PDF", "type": "save_file",
             "required": True},
        ],
    },
}

POSITIONAL_KEYS = {"inputs", "input", "images", "input_a", "input_b"}


def build_argv(cmd, values):
    """由表单值组装 CLI argv。values: {key: value},bool 为 bool,其余为 str/list。"""
    meta = COMMANDS[cmd]
    positional, optional = [], []
    for f in meta["fields"]:
        v = values.get(f["key"])
        if f["type"] == "bool":
            if v:
                optional.append(f["key"])
            continue
        if v is None or v == "" or v == []:
            continue
        if f["type"] in ("pdfs_in", "images_in"):
            items = v if isinstance(v, list) else [v]
            positional.extend(items)
            continue
        s = str(v)
        if f["key"] in POSITIONAL_KEYS:
            positional.append(s)
        else:
            optional.extend([f["key"], s])
    return [cmd] + positional + optional


def validate(cmd, values):
    """返回错误信息列表,空列表 = 通过。"""
    errors = []
    for f in COMMANDS[cmd]["fields"]:
        v = values.get(f["key"])
        empty = v is None or v == "" or v == []
        if f.get("required") and not (f["type"] == "bool") and empty:
            errors.append(f"缺少必填项: {f['label']}")
        if not empty and f["type"] == "int":
            try:
                int(str(v))
            except ValueError:
                errors.append(f"{f['label']} 须为整数")
        if not empty and f["type"] == "float":
            try:
                float(str(v))
            except ValueError:
                errors.append(f"{f['label']} 须为数字")
    if cmd == "split" and not values.get("--every") and not values.get("--ranges"):
        errors.append("拆分方式: 每 N 页一份 与 按范围拆分 至少填一个")
    return errors
