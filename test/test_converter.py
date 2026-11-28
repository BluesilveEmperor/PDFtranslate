import unittest
from unittest.mock import Mock, patch, MagicMock
from pdfminer.layout import LTPage, LTChar, LTLine
from pdfminer.pdfinterp import PDFResourceManager
from pdf2zh.converter import (
    PDFConverterEx,
    TranslateConverter,
    get_cjk_size_scale,
)


class TestPDFConverterEx(unittest.TestCase):
    def setUp(self):
        self.rsrcmgr = PDFResourceManager()
        self.converter = PDFConverterEx(self.rsrcmgr)

    def test_begin_page(self):
        mock_page = Mock()
        mock_page.pageno = 1
        mock_page.cropbox = (0, 0, 100, 200)
        mock_ctm = [1, 0, 0, 1, 0, 0]
        self.converter.begin_page(mock_page, mock_ctm)
        self.assertIsNotNone(self.converter.cur_item)
        self.assertEqual(self.converter.cur_item.pageid, 1)

    def test_render_char(self):
        mock_matrix = (1, 2, 3, 4, 5, 6)
        mock_font = Mock()
        mock_font.to_unichr.return_value = "A"
        mock_font.char_width.return_value = 10
        mock_font.char_disp.return_value = (0, 0)
        graphic_state = Mock()
        self.converter.cur_item = Mock()
        result = self.converter.render_char(
            mock_matrix,
            mock_font,
            fontsize=12,
            scaling=1.0,
            rise=0,
            cid=65,
            ncs=None,
            graphicstate=graphic_state,
        )
        self.assertEqual(result, 120.0)  # Expected text width


class TestTranslateConverter(unittest.TestCase):
    def setUp(self):
        self.rsrcmgr = PDFResourceManager()
        self.layout = {1: Mock()}
        self.translator_class = Mock()
        self.converter = TranslateConverter(
            self.rsrcmgr,
            layout=self.layout,
            lang_in="en",
            lang_out="zh",
            service="google",
        )

    def test_translator_initialization(self):
        self.assertIsNotNone(self.converter.translator)
        self.assertEqual(self.converter.translator.lang_in, "en")
        self.assertEqual(self.converter.translator.lang_out, "zh-CN")

    @patch("pdf2zh.converter.TranslateConverter.receive_layout")
    def test_receive_layout(self, mock_receive_layout):
        mock_page = LTPage(1, (0, 0, 100, 200))
        mock_font = Mock()
        mock_font.fontname.return_value = "mock_font"
        mock_page.add(
            LTChar(
                matrix=(1, 2, 3, 4, 5, 6),
                font=mock_font,
                fontsize=12,
                scaling=1.0,
                rise=0,
                text="A",
                textwidth=10,
                textdisp=(1.0, 1.0),
                ncs=Mock(),
                graphicstate=Mock(),
            )
        )
        self.converter.receive_layout(mock_page)
        mock_receive_layout.assert_called_once_with(mock_page)

    def test_receive_layout_with_complex_formula(self):
        ltpage = LTPage(1, (0, 0, 500, 500))
        ltchar = Mock()
        ltchar.fontname.return_value = "mock_font"
        ltline = LTLine(0.1, (0, 0), (10, 20))
        ltpage.add(ltchar)
        ltpage.add(ltline)
        mock_layout = MagicMock()
        mock_layout.shape = (100, 100)
        mock_layout.__getitem__.return_value = -1
        self.converter.layout = [None, mock_layout]
        self.converter.thread = 1
        result = self.converter.receive_layout(ltpage)
        self.assertIsNotNone(result)

    def test_invalid_translation_service(self):
        with self.assertRaises(ValueError):
            TranslateConverter(
                self.rsrcmgr,
                layout=self.layout,
                lang_in="en",
                lang_out="zh",
                service="InvalidService",
            )


class TestCjkSizeScale(unittest.TestCase):
    """CJK 译文字号放大逻辑测试"""

    def test_scale_table(self):
        self.assertEqual(get_cjk_size_scale("zh"), 1.2)
        self.assertEqual(get_cjk_size_scale("zh-cn"), 1.2)
        self.assertEqual(get_cjk_size_scale("ZH-CN"), 1.2)
        self.assertEqual(get_cjk_size_scale("zh-tw"), 1.2)
        self.assertEqual(get_cjk_size_scale("ja"), 1.1)
        self.assertEqual(get_cjk_size_scale("ko"), 1.1)
        self.assertEqual(get_cjk_size_scale("en"), 1.0)
        self.assertEqual(get_cjk_size_scale(""), 1.0)
        self.assertEqual(get_cjk_size_scale(None), 1.0)

    def _make_converter(self, lang_out="zh", translated="中文译文"):
        converter = TranslateConverter(
            self.rsrcmgr,
            layout={1: self.layout_mock},
            lang_in="en",
            lang_out=lang_out,
            service="google",
        )
        converter.translator = Mock()
        converter.translator.translate.return_value = translated
        converter.translator.lang_out = lang_out
        converter.noto_name = "noto"
        converter.noto = Mock()
        converter.noto.char_lengths.side_effect = lambda ch, sz: [sz]
        converter.noto.has_glyph.return_value = 1
        converter.thread = 1
        return converter

    def _add_line(self, ltpage, text, x, y, size=10.0):
        for i, ch in enumerate(text):
            font = Mock()
            font.fontname = "Times-Roman"
            font.is_vertical.return_value = False
            font.get_descent.return_value = 0.0
            ltpage.add(
                LTChar(
                    matrix=(1, 0, 0, 1, x + i * 5.5, y),
                    font=font,
                    fontsize=size,
                    scaling=1.0,
                    rise=0,
                    text=ch,
                    textwidth=0.55,
                    textdisp=(0.0, 0.0),
                    ncs=Mock(),
                    graphicstate=Mock(),
                )
            )

    def setUp(self):
        self.rsrcmgr = PDFResourceManager()
        layout_mock = MagicMock()
        layout_mock.shape = (500, 500)
        layout_mock.__getitem__.return_value = 1
        self.layout_mock = layout_mock

    def test_multiline_paragraph_scaled(self):
        # 多行段落（brk=True）→ 译文字号放大 1.2 倍：10pt → 12pt
        ltpage = LTPage(1, (0, 0, 500, 500))
        self._add_line(ltpage, "Hello world", 100, 100)
        self._add_line(ltpage, "second line", 100, 85)
        converter = self._make_converter()
        ops = converter.receive_layout(ltpage)
        self.assertIn("/noto 12.000000 Tf", ops)
        self.assertNotIn("/noto 10.000000 Tf", ops)

    def test_single_line_short_scaled(self):
        # 单行短段落且放大后不超宽 → 同样放大
        ltpage = LTPage(1, (0, 0, 500, 500))
        self._add_line(ltpage, "Short title", 100, 100)
        converter = self._make_converter(translated="中文")
        ops = converter.receive_layout(ltpage)
        self.assertIn("/noto 12.000000 Tf", ops)

    def test_single_line_overflow_kept(self):
        # 单行段落放大后超宽（模拟表格单元格溢出）→ 保持原字号
        ltpage = LTPage(1, (0, 0, 500, 500))
        # 行宽 5.5*20=110pt；译文 12 字 × 10pt = 120pt > 110pt，放大后更宽
        self._add_line(ltpage, "A cell of the table", 100, 100)
        converter = self._make_converter(translated="这个中文单元格比较长")
        ops = converter.receive_layout(ltpage)
        self.assertIn("/noto 10.000000 Tf", ops)
        self.assertNotIn("/noto 12.000000 Tf", ops)

    def test_latin_output_not_scaled(self):
        # 非中文目标语言不放大
        ltpage = LTPage(1, (0, 0, 500, 500))
        self._add_line(ltpage, "Hello world", 100, 100)
        self._add_line(ltpage, "second line", 100, 85)
        converter = self._make_converter(lang_out="en", translated="hola mundo")
        ops = converter.receive_layout(ltpage)
        self.assertNotIn("/noto 12.000000 Tf", ops)


if __name__ == "__main__":
    unittest.main()
