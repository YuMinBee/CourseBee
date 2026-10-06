from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
