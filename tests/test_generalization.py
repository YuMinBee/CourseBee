from __future__ import annotations

import unittest

from v2.course_packs import _mindmap_view_from_graph
from v2.graph.concept_map import build_concept_map
from v2.rag.chunking import chunk_pages
from v2.rag.retrieval import retrieve_contexts
from v2.schemas import PageMarkdown
from v2.study_kit import generate_study_kit


class MultiDomainGeneralizationTest(unittest.TestCase):
    def test_korean_hybrid_retrieval_handles_case_suffixes(self) -> None:
        chunks = chunk_pages(
            [
                PageMarkdown(
                    page_number=1,
                    markdown="광합성은 엽록체에서 빛 에너지를 화학 에너지로 전환합니다.",
                    parser="txt",
                ),
                PageMarkdown(
                    page_number=2,
                    markdown="세포 호흡은 포도당을 분해해 ATP를 생성합니다.",
                    parser="txt",
                ),
            ],
            filename="biology.txt",
        )

        result = retrieve_contexts("빛 에너지가 어떤 에너지로 바뀌나요?", chunks, top_k=1)

        self.assertEqual(len(result.contexts), 1)
        self.assertEqual(result.contexts[0].page, 1)
        self.assertIn("화학 에너지", result.contexts[0].text)

    def test_concept_graph_extracts_non_nlp_domains(self) -> None:
        pages = [
            PageMarkdown(
                page_number=1,
                markdown="광합성은 엽록체에서 빛 에너지를 화학 에너지로 전환합니다.",
                parser="txt",
            ),
            PageMarkdown(
                page_number=2,
                markdown="금리 인상은 대출 비용을 높여 총수요와 물가 상승 압력을 낮춥니다.",
                parser="txt",
            ),
            PageMarkdown(
                page_number=3,
                markdown="A circuit breaker prevents cascading failures and improves service resilience.",
                parser="txt",
            ),
        ]
        graph = build_concept_map(chunk_pages(pages, filename="mixed-domains.txt"))
        labels = {str(node["label"]).lower() for node in graph["nodes"] if node.get("type") == "concept"}

        self.assertTrue(any("광합성" in label for label in labels))
        self.assertTrue(any("금리" in label or "총수요" in label for label in labels))
        self.assertTrue(any("circuit breaker" in label or "cascading failures" in label for label in labels))
        self.assertTrue(all(edge.get("evidence") for edge in graph["edges"]))

    def test_chunking_prefers_sentence_boundaries_and_keeps_overlap(self) -> None:
        text = (
            "첫 번째 문장은 핵심 개념을 소개합니다. "
            "두 번째 문장은 이 개념의 작동 원리를 자세히 설명합니다. "
            "세 번째 문장은 실제 사례와 예외를 함께 다룹니다. "
        ) * 5
        chunks = chunk_pages(
            [PageMarkdown(page_number=1, markdown=text, parser="txt")],
            max_chars=240,
            filename="lecture.txt",
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.text) <= 240 for chunk in chunks))
        self.assertTrue(all(chunk.char_end > chunk.char_start for chunk in chunks))
        self.assertLess(chunks[1].char_start, chunks[0].char_end)

    def test_dynamic_quiz_answers_and_citations_are_consistent(self) -> None:
        pages = [
            PageMarkdown(page_number=1, markdown="수요가 증가하면 다른 조건이 같을 때 균형 가격이 상승합니다.", parser="txt"),
            PageMarkdown(page_number=2, markdown="공급이 증가하면 균형 수량은 늘고 가격은 하락할 수 있습니다.", parser="txt"),
            PageMarkdown(page_number=3, markdown="가격 탄력성은 가격 변화에 대한 수요량 반응을 측정합니다.", parser="txt"),
            PageMarkdown(page_number=4, markdown="기회비용은 선택 때문에 포기한 대안 중 가장 큰 가치입니다.", parser="txt"),
        ]
        kit = generate_study_kit(chunk_pages(pages, filename="economics.txt"), max_items=4)

        self.assertEqual(len(kit["quiz"]), 4)
        for item in kit["quiz"]:
            correct_index = "ABCD".index(item["answer"])
            self.assertEqual(item["choices"][correct_index], item["explanation"])
            self.assertTrue(item["sources"])
            self.assertEqual(item["sources"][0]["filename"], "economics.txt")
        self.assertTrue(any(item["term"] not in {"BPE", "RNN", "LSTM"} for item in kit["glossary"]))

    def test_mindmap_view_is_derived_from_the_current_domain(self) -> None:
        chunks = chunk_pages(
            [
                PageMarkdown(
                    page_number=1,
                    markdown="광합성은 엽록체에서 빛 에너지를 화학 에너지로 전환합니다.",
                    parser="txt",
                )
            ],
            filename="biology.txt",
        )
        view = _mindmap_view_from_graph("pack_biology", build_concept_map(chunks))
        rendered = str(view)

        self.assertEqual(view["title"], "Course Pack Mindmap")
        self.assertTrue(view["branches"])
        self.assertIn("광합성", rendered)
        self.assertNotIn("NLP Pipeline", rendered)


if __name__ == "__main__":
    unittest.main()
