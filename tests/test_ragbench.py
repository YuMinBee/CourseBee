from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from eval import run_ragbench_answers
from eval.run_ragbench_retrieval import DEFAULT_BENCH_DIR, evidence_spans, load_bench, split_of


class RagbenchDataTest(unittest.TestCase):
    def test_questions_point_to_existing_evidence(self) -> None:
        _paths, doc_texts, questions = load_bench(DEFAULT_BENCH_DIR)

        self.assertEqual(len(questions), 180)
        self.assertEqual(len({question["id"] for question in questions}), 180)
        for question in questions:
            spans = evidence_spans(question, doc_texts)
            if question["answerable"]:
                self.assertTrue(spans, question["id"])
            else:
                self.assertEqual(spans, [], question["id"])
            if question["type"] == "multi_hop":
                self.assertGreaterEqual(len({doc for doc, _start, _end in spans}), 2, question["id"])

    def test_dev_test_split_is_stable_and_balanced(self) -> None:
        _paths, _texts, questions = load_bench(DEFAULT_BENCH_DIR)
        sizes = Counter(split_of(question["id"]) for question in questions)

        self.assertEqual(split_of("q001"), split_of("q001"))
        self.assertGreater(min(sizes.values()), 70)

    def test_corpus_has_every_document(self) -> None:
        self.assertEqual(len(list(Path(DEFAULT_BENCH_DIR, "docs").glob("*.md"))), 32)


class AnswerHarnessTest(unittest.TestCase):
    def test_empty_answer_is_an_abstention_without_asking_the_judge(self) -> None:
        # qwen 심판은 빈 답을 정답과 비교해 correct로 판정하곤 했다.
        question = {"question": "월급날?", "answer": "매월 25일", "answerable": True}
        with mock.patch.object(run_ragbench_answers, "ollama_json") as judge_call:
            verdict, _reason = run_ragbench_answers.judge(question, "  ", "qwen3:14b")

        self.assertEqual(verdict, "abstained")
        judge_call.assert_not_called()

    def test_won_amounts_are_normalized(self) -> None:
        self.assertEqual(run_ragbench_answers.numbers_with_units("1만 5천원, 15,000원"), ["15000원"])


if __name__ == "__main__":
    unittest.main()
