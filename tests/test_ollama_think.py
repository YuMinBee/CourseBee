from __future__ import annotations

import unittest

from v2.providers.ollama import OllamaProvider, _ThinkFilter, strip_think_blocks


class ThinkBlockTest(unittest.TestCase):
    def test_strip_removes_inline_reasoning(self) -> None:
        self.assertEqual(strip_think_blocks("<think>계산 중...</think>답은 3일입니다."), "답은 3일입니다.")
        self.assertEqual(strip_think_blocks("답<think>잘린 추론"), "답")

    def test_stream_filter_handles_tags_split_across_pieces(self) -> None:
        pieces = ["<thi", "nk>숨겨야 할 ", "추론</th", "ink>", "연차는 ", "1영업일 전", "까지 a<b"]
        think_filter = _ThinkFilter()
        streamed = "".join(think_filter.feed(piece) for piece in pieces) + think_filter.flush()

        self.assertEqual(streamed, "연차는 1영업일 전까지 a<b")

    def test_thinking_is_off_by_default(self) -> None:
        self.assertFalse(OllamaProvider(model="qwen3:14b").think)


if __name__ == "__main__":
    unittest.main()
