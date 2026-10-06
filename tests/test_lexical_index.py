from __future__ import annotations

import unittest
from collections import Counter

from v2 import course_packs
from v2.rag.lexical_index import _regex_tokens, index_for, tokenize, tokenizer_name
from v2.rag.retrieval import retrieve_contexts
from v2.schemas import Chunk


def _chunk(doc: str, text: str, chunk_id: str = "p1_c1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        page=1,
        text=text,
        char_start=0,
        char_end=len(text),
        metadata={"doc_id": doc, "filename": doc},
    )


LEAVE_DOCS = [
    ("d1_handbook.md", "휴가는 팀 일정과 조율해서 사용합니다. 휴가 중에는 메신저 상태를 부재로 바꿉니다."),
    ("d2_welfare.md", "복지 포인트는 휴가 기간에도 사용할 수 있습니다. 연말에 남은 포인트는 소멸합니다."),
    ("d3_security.md", "휴가 중 회사 노트북을 외부로 가져갈 때는 보안팀 반출 신청이 필요합니다."),
    ("d4_onboarding.md", "입사 첫 주에는 휴가 제도와 근태 시스템 사용법 교육을 받습니다."),
    ("d5_leave_policy.md", "연차 휴가 신청은 사용일 3영업일 전까지 근태 시스템에서 팀장 승인을 받아야 합니다."),
]


class BalancedChunkSelectionTest(unittest.TestCase):
    def test_answer_in_last_uploaded_document_is_ranked_first(self) -> None:
        # 이전 구현은 문서마다 1등 청크를 업로드 순서로 넣고 잘라서 d1, d2, d3만 돌려줬다.
        chunks = [_chunk(name, text) for name, text in LEAVE_DOCS]

        selected = course_packs._balanced_chunks("휴가 신청은 며칠 전까지 해야 하나요?", chunks, top_k=3)

        self.assertEqual(selected[0].metadata["filename"], "d5_leave_policy.md")

    def test_one_document_cannot_take_every_slot_when_others_are_relevant(self) -> None:
        ranked = [_chunk("a.md", f"a{i}", f"c{i}") for i in range(4)] + [_chunk("b.md", "b0", "c9")]

        selected = course_packs._diversify_by_document(ranked, top_k=4)

        self.assertEqual([chunk.metadata["filename"] for chunk in selected], ["a.md", "a.md", "a.md", "b.md"])

    def test_single_document_is_not_capped(self) -> None:
        ranked = [_chunk("a.md", f"a{i}", f"c{i}") for i in range(5)]

        selected = course_packs._diversify_by_document(ranked, top_k=4)

        self.assertEqual(len(selected), 4)


class LexicalIndexTest(unittest.TestCase):
    def test_index_is_reused_for_same_content_and_rebuilt_on_change(self) -> None:
        chunks = [_chunk(name, text) for name, text in LEAVE_DOCS]
        same_content = [_chunk(name, text) for name, text in LEAVE_DOCS]
        changed = [*same_content[:-1], _chunk("d5_leave_policy.md", "연차 휴가 신청은 5영업일 전까지 합니다.")]

        self.assertIs(index_for(chunks), index_for(same_content))
        self.assertIsNot(index_for(chunks), index_for(changed))

    def test_term_frequency_is_kept(self) -> None:
        # 이전 토크나이저는 중복 단어를 지워서 TF가 항상 1이었다.
        counts = Counter(_regex_tokens("보안 보안은 보안 정책"))

        self.assertEqual(counts["보안"], 3)

    @unittest.skipUnless(tokenizer_name() == "kiwi", "kiwipiepy not installed")
    def test_kiwi_removes_particles_and_endings(self) -> None:
        self.assertEqual(tokenize("빛 에너지가 열 에너지로 바뀌나요?"), ["빛", "에너지", "열", "에너지", "바뀌"])

    def test_more_frequent_term_ranks_higher(self) -> None:
        chunks = [
            _chunk("a.md", "보안 교육은 연 1회 진행합니다. 일정은 공지합니다."),
            _chunk("b.md", "보안 사고는 즉시 보안팀에 신고합니다. 보안 담당자가 보안 점검을 합니다."),
        ]

        contexts = retrieve_contexts("보안 점검 담당자", chunks, top_k=2).contexts

        self.assertEqual(contexts[0].metadata["filename"], "b.md")


if __name__ == "__main__":
    unittest.main()
