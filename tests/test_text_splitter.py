"""core.text_splitter 的最小测试覆盖。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import re
import unittest

from core.text_splitter import split_long_text


def _normalize(s: str) -> str:
    """去掉所有空白字符，用于内容完整性比较。"""
    return re.sub(r"\s+", "", s)


def _assert_integrity(testcase: unittest.TestCase, original: str, chunks: list[str]) -> None:
    """不丢失文本内容：片段拼接后与原文（忽略空白差异）一致。"""
    testcase.assertEqual(_normalize("".join(chunks)), _normalize(original))


class TestSplitLongText(unittest.TestCase):
    def test_plain_chinese(self):
        text = "今天天气很好。我们决定去公园散步。路上遇到了老朋友，大家都很开心！"
        chunks = split_long_text(text, max_chars=40)
        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 40)
        _assert_integrity(self, text, chunks)

    def test_multi_paragraph(self):
        text = "第一段的内容。它有两个句子。\n\n第二段从这里开始。也有自己的句子。\n\n\n第三段。"
        chunks = split_long_text(text, max_chars=50)
        self.assertTrue(chunks)
        _assert_integrity(self, text, chunks)
        # 段落边界保留：任何片段不会同时包含两个段落的内容
        for chunk in chunks:
            self.assertFalse("第一段" in chunk and "第二段" in chunk)

    def test_mixed_chinese_english(self):
        text = (
            "The weather is nice today. 今天天气很好。"
            "We decided to go for a walk in the park. 路上遇到了老朋友，大家都很开心！"
        )
        chunks = split_long_text(text, max_chars=60)
        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 60)
        _assert_integrity(self, text, chunks)
        # 英文单词不被空格粘连破坏：拼接后应能找回原句
        self.assertIn("The weather is nice today.", "".join(chunks))

    def test_long_text_without_punctuation(self):
        text = "这是一个没有标点符号的超长句子" * 30  # 450 字无标点
        chunks = split_long_text(text, max_chars=150)
        self.assertGreaterEqual(len(chunks), 3)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 150)  # 硬切兜底
        _assert_integrity(self, text, chunks)

    def test_empty_text(self):
        self.assertEqual(split_long_text(""), [])
        self.assertEqual(split_long_text("   \n\n  \t "), [])

    def test_content_integrity_with_secondary_breaks(self):
        # 只有次级断点的长句：先按 ，；：拆，再合并，内容不丢
        text = "春天来了，花儿开了；微风拂过，带来阵阵花香：一切都是那么美好，让人心旷神怡。" * 4
        chunks = split_long_text(text, max_chars=60)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 60)
        _assert_integrity(self, text, chunks)

    def test_short_sentences_merged_toward_target(self):
        text = "好。行。可以。没问题。就这样。明白了。好的。收到。"
        chunks = split_long_text(text, max_chars=50)
        # 8 个短句应被合并为更少的片段
        self.assertLess(len(chunks), 8)
        _assert_integrity(self, text, chunks)

    def test_max_chars_validation(self):
        with self.assertRaises(ValueError):
            split_long_text("文本", max_chars=10)
        with self.assertRaises(ValueError):
            split_long_text("文本", max_chars=600)

    def test_single_short_text(self):
        self.assertEqual(split_long_text("你好。"), ["你好。"])


if __name__ == "__main__":
    unittest.main()
