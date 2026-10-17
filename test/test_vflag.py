"""字体（公式）判定规则单元测试。

覆盖 pdf2zh.converter 中收紧后的默认公式字体正则 DEFAULT_VFONT_PATTERN，
确保普通正文（斜体/粗体/无衬线/罗马体）不会被误判为公式，
同时真正的数学/符号字体仍能被识别。
"""

import unittest

from pdf2zh.converter import DEFAULT_VFONT_PATTERN, _is_math_font


class TestDefaultVfontPattern(unittest.TestCase):
    """默认公式字体正则必须兼容原有逻辑，但排除正文常用字体。"""

    def test_dangerous_fragments_removed(self):
        # .*Ital 会命中普通正文斜体（Times-Italic / *-ItalicMT），必须移除
        self.assertNotIn(r".*Ital", DEFAULT_VFONT_PATTERN)
        # CM[^R] 会命中正文粗体 CMBX、正文斜体 CMTI、无衬线 CMSS，必须收窄
        self.assertNotIn(r"CM[^R]", DEFAULT_VFONT_PATTERN)


class TestIsMathFontBodyFonts(unittest.TestCase):
    """正文/普通字体不应被判定为公式字体。"""

    def _assert_body(self, font):
        self.assertFalse(
            _is_math_font(font),
            msg=f"正文/普通字体被误判为公式字体: {font!r}",
        )

    def test_times_italic(self):
        self._assert_body("Times-Italic")

    def test_italic_mt_variants(self):
        # *-ItalicMT（如 TimesNewRomanPS-ItalicMT、Arial-ItalicMT）
        self._assert_body("TimesNewRomanPS-ItalicMT")
        self._assert_body("Arial-ItalicMT")

    def test_subset_prefix_is_stripped(self):
        # PDF 子集前缀（ABCDEF+）应被截断后再判定
        self._assert_body("ABCDEF+Times-Italic")
        self._assert_body("ABCDEF+TimesNewRomanPS-ItalicMT")

    def test_latex_body_bold(self):
        self._assert_body("CMBX12")  # LaTeX 正文粗体（\textbf）

    def test_latex_body_italic(self):
        self._assert_body("CMTI10")  # LaTeX 正文斜体

    def test_latex_sans_serif(self):
        self._assert_body("CMSS10")  # LaTeX 无衬线

    def test_common_body_fonts(self):
        self._assert_body("Helvetica")
        self._assert_body("Times-Roman")
        self._assert_body("LMRoman12")


class TestIsMathFontMathFonts(unittest.TestCase):
    """真正的数学/符号字体仍应被判定为公式字体。"""

    def _assert_math(self, font):
        self.assertTrue(
            _is_math_font(font),
            msg=f"数学/符号字体未被判定为公式字体: {font!r}",
        )

    def test_latex_math_fonts(self):
        self._assert_math("CMMI12")  # 数学斜体
        self._assert_math("CMSY10")  # 数学符号
        self._assert_math("CMEX10")  # 大符号
        self._assert_math("CMBSY10")  # 粗体数学符号

    def test_ams_symbol_font(self):
        self._assert_math("MSBM10")
        self._assert_math("MSAM10")

    def test_symbol_fonts(self):
        self._assert_math("Symbol")
        self._assert_math("MathType")

    def test_other_math_fonts(self):
        self._assert_math("ABCDEF+CMMI12")  # 子集前缀不影响判定
        self._assert_math("DejaVuSansMono")  # .*Mono
        self._assert_math("TeX-typewriter")  # TeX-


class TestIsMathFontOverridesAndTypes(unittest.TestCase):
    """用户自定义 pattern 与 bytes 输入的兼容性。"""

    def test_custom_pattern_overrides_default(self):
        # 显式传入的 pattern 优先于默认规则
        self.assertTrue(_is_math_font("Helvetica", r".*Helvetica"))
        self.assertFalse(_is_math_font("CMMI12", r"^Helvetica$"))

    def test_empty_pattern_falls_back_to_default(self):
        self.assertTrue(_is_math_font("CMMI12", ""))
        self.assertFalse(_is_math_font("Times-Roman", ""))

    def test_bytes_fontname(self):
        self.assertTrue(_is_math_font(b"CMMI12"))
        self.assertFalse(_is_math_font(b"Times-Italic"))

    def test_undecodable_bytes(self):
        # 无法 UTF-8 解码的 bytes 退化为空字符串，不匹配任何公式字体
        self.assertFalse(_is_math_font(b"\xff\xfe"))


if __name__ == "__main__":
    unittest.main()