import unittest
from unittest.mock import MagicMock

import pymupdf

from pdf2zh.high_level import (
    _bbox_iou,
    _dedup_layout_boxes,
    _split_table_cells,
    _xy_cut_cells,
)


class TestXyCutCells(unittest.TestCase):
    def test_grid_2x2(self):
        # 两列（列间距 12pt）两行（行间距 10pt）→ 4 个单元格
        rects = [
            (10, 10, 30, 19),    # A1
            (42, 10, 62, 19),    # B1（列间隔 12pt）
            (10, 29, 30, 38),    # A2（行间隔 10pt）
            (42, 29, 62, 38),    # B2
        ]
        clip = (5, 5, 70, 45)
        cells = _xy_cut_cells(rects, clip)
        self.assertEqual(len(cells), 4)
        # 每个叶子应只包含一个词
        for cell in cells:
            contained = [
                r
                for r in rects
                if cell[0] <= (r[0] + r[2]) / 2 <= cell[2]
                and cell[1] <= (r[1] + r[3]) / 2 <= cell[3]
            ]
            self.assertEqual(len(contained), 1)

    def test_wrapped_cell_stays_whole(self):
        # 单元格内换行的两行文字（行距小）不应被拆开
        rects = [
            (10, 10, 60, 19),   # 第一行
            (10, 21, 45, 30),   # 第二行（间隔 2pt）
            (120, 10, 140, 19),  # 右侧另一列
        ]
        clip = (5, 5, 150, 40)
        cells = _xy_cut_cells(rects, clip)
        # 应切成两列，左列包含两行（一个单元格）
        self.assertEqual(len(cells), 2)

    def test_empty_region(self):
        self.assertEqual(_xy_cut_cells([], (0, 0, 10, 10)), [(0, 0, 10, 10)])

    def test_depth_cap(self):
        # 无法切割时返回原区域
        rects = [(10, 10, 12, 14)]
        cells = _xy_cut_cells(rects, (0, 0, 20, 20))
        self.assertEqual(cells, [(0, 0, 20, 20)])


class TestSplitTableCells(unittest.TestCase):
    def setUp(self):
        self.doc = pymupdf.open()
        self.page = self.doc.new_page(width=595, height=842)
        # 模拟三线表：两列三行，列间距足够大
        rows = [
            [("Model", 60), ("F1", 260)],
            [("LCF", 60), ("41.42", 260)],
            [("Atom", 60), ("65.32", 260)],
        ]
        for row in rows:
            for text, x in row:
                self.page.insert_text((x, 100 + rows.index(row) * 20), text, fontsize=9)

    def test_split_basic_table(self):
        cells = _split_table_cells(self.page, (50, 88, 320, 150))
        # 两列三行 → 至少 2 个单元格（行距 20-9=11pt > 4.5 应切开）
        self.assertGreaterEqual(len(cells), 4)
        # 所有单元格都在给定区域内
        for cx0, cy0, cx1, cy1 in cells:
            self.assertGreaterEqual(cx0, 49)
            self.assertLessEqual(cx1, 321)
            self.assertGreaterEqual(cy0, 87)
            self.assertLessEqual(cy1, 151)

    def test_empty_region_returns_no_cells(self):
        self.assertEqual(_split_table_cells(self.page, (400, 400, 500, 500)), [])


class TestBboxIou(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(_bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)

    def test_disjoint(self):
        self.assertEqual(_bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)

    def test_partial(self):
        # 交集 5x10=50，并集 100+100-50=150
        self.assertAlmostEqual(_bbox_iou((0, 0, 10, 10), (5, 0, 15, 10)), 1 / 3)


def _make_layout(names_and_boxes):
    """构造带 names/boxes 的 mock 版式结果（xyxy 为 numpy 数组，与真实一致）。"""
    import numpy as np

    layout = MagicMock()
    layout.names = {i: n for i, (n, _) in enumerate(names_and_boxes)}
    boxes = []
    for i, (_, bb) in enumerate(names_and_boxes):
        d = MagicMock()
        d.cls = i
        d.xyxy.squeeze.return_value = np.array(bb, dtype=float)
        boxes.append(d)
    layout.boxes = boxes
    return layout


class TestDedupLayoutBoxes(unittest.TestCase):
    def test_merge_overlapping_captions(self):
        # 同一段表题命中 figure_caption + table_caption，应合并为一个框
        layout = _make_layout(
            [
                ("figure_caption", [35, 211, 558, 238]),
                ("table_caption", [35, 211, 558, 238]),
                ("table_caption", [58, 217, 554, 239]),
            ]
        )
        boxes = _dedup_layout_boxes(layout)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0][0], "figure_caption")
        self.assertEqual(boxes[0][1], [35, 211, 558, 239])

    def test_no_merge_different_categories(self):
        # caption 与 table 不合并
        layout = _make_layout(
            [
                ("table_caption", [35, 211, 558, 238]),
                ("table", [35, 239, 558, 384]),
            ]
        )
        self.assertEqual(len(_dedup_layout_boxes(layout)), 2)

    def test_no_merge_low_iou(self):
        layout = _make_layout(
            [
                ("text", [0, 0, 100, 20]),
                ("text", [0, 400, 100, 420]),
            ]
        )
        self.assertEqual(len(_dedup_layout_boxes(layout)), 2)

    def test_merge_same_class_overlap(self):
        layout = _make_layout(
            [
                ("table", [0, 0, 100, 100]),
                ("table", [10, 10, 110, 110]),  # IoU ≈ 0.68
            ]
        )
        boxes = _dedup_layout_boxes(layout)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0][1], [0, 0, 110, 110])


if __name__ == "__main__":
    unittest.main()
