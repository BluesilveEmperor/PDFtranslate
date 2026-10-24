import os
import tempfile

import pymupdf as fitz

from ._util import ensure_parent, parse_pages, parse_ranges

PERM_ALL = (
    fitz.PDF_PERM_ACCESSIBILITY
    | fitz.PDF_PERM_PRINT
    | fitz.PDF_PERM_COPY
    | fitz.PDF_PERM_ANNOTATE
    | fitz.PDF_PERM_FORM
    | fitz.PDF_PERM_ASSEMBLE
    | fitz.PDF_PERM_PRINT_HQ
)


def _open(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    return fitz.open(path)


def merge(inputs, output):
    ensure_parent(output)
    doc = fitz.open()
    for path in inputs:
        with _open(path) as src:
            doc.insert_pdf(src)
    doc.save(output, garbage=3, deflate=True)
    doc.close()
    return output


def split_every(input, output_dir, every):
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input))[0]
    outputs = []
    with _open(input) as doc:
        total = doc.page_count
        start = 0
        part = 1
        while start < total:
            out = fitz.open()
            out.insert_pdf(doc, from_page=start, to_page=min(start + every, total) - 1)
            path = os.path.join(output_dir, f"{stem}_part{part:03d}.pdf")
            out.save(path, garbage=3, deflate=True)
            out.close()
            outputs.append(path)
            start += every
            part += 1
    return outputs


def split_ranges(input, output_dir, spec):
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input))[0]
    outputs = []
    with _open(input) as doc:
        for idx, (lo, hi) in enumerate(parse_ranges(spec, doc.page_count), 1):
            out = fitz.open()
            out.insert_pdf(doc, from_page=lo, to_page=hi)
            path = os.path.join(output_dir, f"{stem}_range{idx:02d}_{lo + 1}-{hi + 1}.pdf")
            out.save(path, garbage=3, deflate=True)
            out.close()
            outputs.append(path)
    return outputs


def extract_pages(input, output, pages):
    ensure_parent(output)
    with _open(input) as src:
        sel = parse_pages(pages, src.page_count)
        doc = fitz.open()
        for p in sel:
            doc.insert_pdf(src, from_page=p, to_page=p)
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output


def delete_pages(input, output, pages):
    ensure_parent(output)
    with _open(input) as src:
        sel = set(parse_pages(pages, src.page_count))
        doc = fitz.open()
        for p in range(src.page_count):
            if p not in sel:
                doc.insert_pdf(src, from_page=p, to_page=p)
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output


def insert_pages(input, other, output, position):
    ensure_parent(output)
    pos = position if position >= 0 else -1
    with _open(input) as base, _open(other) as src:
        doc = fitz.open()
        total = base.page_count
        at = total if pos < 0 else min(pos, total)
        if at > 0:
            doc.insert_pdf(base, from_page=0, to_page=at - 1)
        doc.insert_pdf(src)
        if at < total:
            doc.insert_pdf(base, from_page=at, to_page=total - 1)
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output


def rotate(input, output, angle, pages=None):
    ensure_parent(output)
    with _open(input) as src:
        sel = parse_pages(pages, src.page_count)
        doc = fitz.open()
        doc.insert_pdf(src)
        for p in sel:
            page = doc[p]
            page.set_rotation((page.rotation + angle) % 360)
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output


def cut_margins(input, output, left, right, top, bottom):
    ensure_parent(output)
    with _open(input) as src:
        doc = fitz.open()
        doc.insert_pdf(src)
        for page in doc:
            rect = page.cropbox
            new = fitz.Rect(
                rect.x0 + left,
                rect.y0 + bottom,
                rect.x1 - right,
                rect.y1 - top,
            )
            if new.is_empty or new.width <= 0 or new.height <= 0:
                raise ValueError("裁剪边距过大，裁剪后页面为空")
            page.set_cropbox(new)
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output


def add_page_numbers(input, output, pos="bottom-center", start=1, fmt="{n}", size=11, color=(0, 0, 0)):
    ensure_parent(output)
    with _open(input) as src:
        doc = fitz.open()
        doc.insert_pdf(src)
        margin = 24
        for i, page in enumerate(doc):
            num = start + i
            text = fmt.replace("{n}", str(num))
            rect = page.rect
            w = fitz.get_text_length(text, fontname="helv", fontsize=size)
            if pos.startswith("top"):
                y = margin
            else:
                y = rect.height - margin
            if pos.endswith("left"):
                x = margin
                point = fitz.Point(x, y)
            elif pos.endswith("right"):
                point = fitz.Point(rect.width - margin - w, y)
            else:
                point = fitz.Point((rect.width - w) / 2, y)
            page.insert_text(point, text, fontsize=size, fontname="helv", color=color)
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output


def _stamp_text(page, text, point, size, color, opacity, angle):
    m = fitz.Matrix(angle)
    page.insert_text(
        point,
        text,
        fontsize=size,
        fontname="helv",
        color=color,
        fill_opacity=opacity,
        morph=(point, m),
    )


def watermark_text(input, output, text, angle=45, opacity=0.15, size=36, color=(0.7, 0.7, 0.7), tiled=True):
    ensure_parent(output)
    with _open(input) as src:
        doc = fitz.open()
        doc.insert_pdf(src)
        for page in doc:
            rect = page.rect
            if not tiled:
                w = fitz.get_text_length(text, fontname="helv", fontsize=size)
                _stamp_text(page, text, fitz.Point((rect.width - w) / 2, rect.height / 2), size, color, opacity, angle)
                continue
            step_x = max(220.0, size * len(text) * 0.5)
            step_y = max(160.0, size * 2.2)
            y = 0
            row = 0
            while y < rect.height + step_y:
                x = -(row % 2) * (step_x / 2)
                while x < rect.width + step_x:
                    _stamp_text(page, text, fitz.Point(x, y), size, color, opacity, angle)
                    x += step_x
                y += step_y
                row += 1
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output


def watermark_image(input, output, image, opacity=0.5, tiled=True, scale=0.35):
    from PIL import Image

    ensure_parent(output)
    img = Image.open(image)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    if opacity < 1.0:
        alpha = img.getchannel("A").point(lambda a: int(a * opacity))
        img.putalpha(alpha)
    buf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(buf, "PNG")
    buf.close()
    try:
        with _open(input) as src, open(buf.name, "rb") as f:
            stream = f.read()
            doc = fitz.open()
            doc.insert_pdf(src)
            for page in doc:
                rect = page.rect
                iw, ih = img.size
                target_w = rect.width * scale
                target_h = target_w * ih / iw
                if not tiled:
                    r = fitz.Rect(
                        (rect.width - target_w) / 2,
                        (rect.height - target_h) / 2,
                        (rect.width + target_w) / 2,
                        (rect.height + target_h) / 2,
                    )
                    page.insert_image(r, stream=stream, overlay=True, keep_proportion=True)
                    continue
                step_x = target_w * 1.4
                step_y = target_h * 1.5
                y = 0.0
                while y < rect.height + step_y:
                    x = 0.0
                    while x < rect.width + step_x:
                        r = fitz.Rect(x, y, x + target_w, y + target_h)
                        page.insert_image(r, stream=stream, overlay=True, keep_proportion=True)
                        x += step_x
                    y += step_y
            doc.save(output, garbage=3, deflate=True)
            doc.close()
    finally:
        os.unlink(buf.name)
    return output


def encrypt(input, output, user_pw, owner_pw, allow_print=True, allow_copy=True):
    ensure_parent(output)
    with _open(input) as src:
        if src.is_encrypted:
            raise ValueError("输入文件已加密，请先解密")
        perms = fitz.PDF_PERM_ACCESSIBILITY
        if allow_print:
            perms |= fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ
        if allow_copy:
            perms |= fitz.PDF_PERM_COPY
        src.save(
            output,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=user_pw or "",
            owner_pw=owner_pw or user_pw or "",
            permissions=perms,
        )
    return output


def _default_decrypt_output(input):
    """未指定输出时，写到输入 PDF 同目录，文件名加 ``Removed_`` 前缀。"""
    directory = os.path.dirname(os.path.abspath(input)) or os.getcwd()
    return os.path.join(directory, "Removed_" + os.path.basename(input))


def decrypt(input, output, wordlist=None, charset=None, min_len=1, max_len=4, jobs=None, log=None):
    from . import pwcrack

    log = log or (lambda *a: None)
    if not output:
        output = _default_decrypt_output(input)
    ensure_parent(output)
    doc = _open(input)
    if doc.is_encrypted and not doc.authenticate(""):
        doc.close()
        log("需要打开密码，启动密码恢复...")
        pw = pwcrack.crack(
            input,
            wordlist=wordlist,
            charset=charset,
            min_len=min_len,
            max_len=max_len,
            jobs=jobs,
            log=log,
        )
        if pw is None:
            raise ValueError("密码恢复失败：请尝试提供字典文件或扩大枚举范围")
        log(f"已恢复密码: {pw!r}")
        doc = _open(input)
        if not doc.authenticate(pw):
            raise ValueError("内部错误：恢复密码验证失败")
    doc.save(output, garbage=3, deflate=True)
    doc.close()
    return output


def text_replace(input, output, old, new, pages=None):
    ensure_parent(output)
    with _open(input) as src:
        sel = parse_pages(pages, src.page_count)
        doc = fitz.open()
        doc.insert_pdf(src)
        total = 0
        for p in sel:
            page = doc[p]
            rects = page.search_for(old)
            for r in rects:
                fontsize = max(6.0, min(r.height * 0.85, 36.0))
                page.add_redact_annot(
                    r,
                    text=new,
                    fontname="helv",
                    fontsize=fontsize,
                    align=fitz.TEXT_ALIGN_LEFT,
                    fill=(1, 1, 1),
                    text_color=(0, 0, 0),
                )
                total += 1
            if rects:
                page.apply_redactions()
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    if total == 0:
        raise ValueError(f"未找到文本: {old!r}")
    return output


def text_delete(input, output, text, pages=None):
    ensure_parent(output)
    with _open(input) as src:
        sel = parse_pages(pages, src.page_count)
        doc = fitz.open()
        doc.insert_pdf(src)
        total = 0
        for p in sel:
            page = doc[p]
            rects = page.search_for(text)
            for r in rects:
                page.add_redact_annot(r, fill=(1, 1, 1))
                total += 1
            if rects:
                page.apply_redactions()
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    if total == 0:
        raise ValueError(f"未找到文本: {text!r}")
    return output


def remove_links(input, output):
    ensure_parent(output)
    with _open(input) as src:
        doc = fitz.open()
        doc.insert_pdf(src)
        total = 0
        for page in doc:
            for link in list(page.get_links()):
                page.delete_link(link)
                total += 1
        doc.save(output, garbage=3, deflate=True)
        doc.close()
    return output, total


def pages_merger(input_a, input_b, output, mode="interleave"):
    ensure_parent(output)
    doc = fitz.open()
    with _open(input_a) as a, _open(input_b) as b:
        if mode == "interleave":
            n = max(a.page_count, b.page_count)
            for i in range(n):
                if i < a.page_count:
                    doc.insert_pdf(a, from_page=i, to_page=i)
                if i < b.page_count:
                    doc.insert_pdf(b, from_page=i, to_page=i)
        else:
            doc.insert_pdf(a)
            doc.insert_pdf(b)
    doc.save(output, garbage=3, deflate=True)
    doc.close()
    return output
