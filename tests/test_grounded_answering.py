from __future__ import annotations

import os
import unittest
from unittest import mock

from v2 import course_packs
from v2.providers.base import IndexProvider
from v2.providers.semantic import reciprocal_rank_fusion
from v2.rag.answering import generate_source_grounded_answer
from v2.rag.grounded_prompt import (
    cited_indices,
    grounded_answer_prompt,
    source_block,
    support_check_prompt,
    unsupported_answer,
)
from v2.schemas import AnswerWithSources, Chunk


def _chunk(filename: str, chunk_id: str, text: str, title: str | None = None) -> Chunk:
    metadata = {"doc_id": filename, "filename": filename}
    if title:
        metadata["title"] = title
    return Chunk(chunk_id=chunk_id, page=1, text=text, char_start=0, char_end=len(text), metadata=metadata)


LEAVE = _chunk("leave_2026.md", "p1_c1", "연차 신청\n- 사용일 1영업일 전까지 신청", "휴가 규정 (2026-07-01 시행)")
TRIP = _chunk("trip.md", "p1_c2", "출장비는 출장 종료 후 10영업일 이내 정산", "출장 규정")


class _PassThrough(IndexProvider):
    def search(self, question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
        return chunks[:top_k]


class _FakeLLM:
    def __init__(self, answer: str, verdict: str) -> None:
        self._answer = answer
        self._verdict = verdict
        self.checked = 0

    def answer(self, question, chunks, graph_context):
        return AnswerWithSources(answer=self._answer, vector_sources=[], graph_context=graph_context)

    def check_support(self, question, chunks, answer):
        self.checked += 1
        return self._verdict, "fake"


class GroundedPromptTest(unittest.TestCase):
    def test_sources_are_numbered_once_with_title_and_line_breaks(self) -> None:
        block = source_block([LEAVE, TRIP, LEAVE])

        self.assertIn("[1] 문서: 휴가 규정 (2026-07-01 시행) (leave_2026.md)\n연차 신청\n- 사용일", block)
        self.assertIn("[2] 문서: 출장 규정 (trip.md)", block)
        self.assertNotIn("[3]", block)

    def test_prompt_carries_reference_date(self) -> None:
        with mock.patch.dict(os.environ, {"COURSEBEE_TODAY": "2026-10-06"}):
            self.assertIn("오늘 날짜는 2026-10-06", grounded_answer_prompt("연차 언제 신청?", [LEAVE]))

    def test_support_check_knows_the_reference_date(self) -> None:
        # 날짜가 없으면 "올해" 질문에서 구·신 규정이 함께 보일 때 맞는 답도 근거 없음으로 판정했다.
        with mock.patch.dict(os.environ, {"COURSEBEE_TODAY": "2026-10-06"}):
            prompt = support_check_prompt("올해 연차 언제 신청?", [LEAVE], "1영업일 전까지 [1].")
        self.assertIn("오늘 날짜는 2026-10-06", prompt)
        self.assertIn("오늘 시행 중인 버전", prompt)

    def test_cited_indices(self) -> None:
        self.assertEqual(cited_indices("1영업일 전 [1]. 정산은 10영업일 [2, 1]."), [1, 2])

    def test_unsupported_answer_lists_related_documents_only(self) -> None:
        self.assertEqual(
            unsupported_answer([LEAVE, TRIP]),
            "문서에서 확인되지 않습니다. 질문과 관련 있을 수 있는 문서: [1] 휴가 규정 (2026-07-01 시행), [2] 출장 규정",
        )


class SupportCheckTest(unittest.TestCase):
    def test_unsupported_draft_is_replaced(self) -> None:
        llm = _FakeLLM("형 결혼에도 경조금 100만원이 나옵니다 [1].", "not_supported")

        result = generate_source_grounded_answer("형 결혼 경조금?", [LEAVE], _PassThrough(), llm)

        self.assertTrue(result.answer.startswith("문서에서 확인되지 않습니다."))
        self.assertTrue(result.support_check["revised"])
        self.assertEqual(result.support_check["draft_answer"], "형 결혼에도 경조금 100만원이 나옵니다 [1].")

    def test_supported_draft_is_kept(self) -> None:
        llm = _FakeLLM("사용일 1영업일 전까지 신청합니다 [1].", "supported")

        result = generate_source_grounded_answer("연차 언제 신청?", [LEAVE], _PassThrough(), llm)

        self.assertEqual(result.answer, "사용일 1영업일 전까지 신청합니다 [1].")
        self.assertFalse(result.support_check["revised"])

    def test_check_can_be_disabled(self) -> None:
        llm = _FakeLLM("초안 [1].", "not_supported")
        with mock.patch.dict(os.environ, {"COURSEBEE_SUPPORT_CHECK": "off"}):
            result = generate_source_grounded_answer("질문", [LEAVE], _PassThrough(), llm)

        self.assertEqual(result.answer, "초안 [1].")
        self.assertEqual(llm.checked, 0)


class CitationAndRetrievalConfigTest(unittest.TestCase):
    def test_marker_citations_map_to_sources(self) -> None:
        citations = course_packs._sentence_citations("연차는 1영업일 전 [1]. 정산은 10영업일 [2]. 끝.", [LEAVE, TRIP])

        self.assertEqual([item.get("source_index") for item in citations], [1, 2, None])
        self.assertEqual([item["grounded"] for item in citations], [True, True, False])
        # 화면이 문장 뒤에 출처 버튼을 붙이므로 본문에서는 [번호]를 뺀다.
        self.assertEqual(citations[0]["sentence"], "연차는 1영업일 전.")

    def test_dense_weight_changes_fusion_order(self) -> None:
        lexical = [TRIP, LEAVE]
        dense = [LEAVE, TRIP]

        equal = reciprocal_rank_fusion(("lexical", lexical), ("dense", dense))
        dense_first = reciprocal_rank_fusion(("lexical", lexical), ("dense", dense), weights={"dense": 2.0})

        self.assertEqual(dense_first[0].chunk_id, LEAVE.chunk_id)
        self.assertEqual(len(equal), 2)

    def test_retrieval_aliases(self) -> None:
        self.assertEqual(course_packs.VECTOR_RETRIEVAL_ALIASES["lexical"], "vector")
        self.assertEqual(course_packs.VECTOR_RETRIEVAL_ALIASES["dense"], "semantic")


if __name__ == "__main__":
    unittest.main()
