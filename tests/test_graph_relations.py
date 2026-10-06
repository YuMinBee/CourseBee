from __future__ import annotations

import unittest

from v2 import course_packs


class GraphRelationNamesTest(unittest.TestCase):
    def test_contrast_edges_use_the_extractor_relation_name(self) -> None:
        # 추출기는 "contrasts_with"를 쓰는데 검색은 "contrasts"를 찾아서 대조 검색이 한 번도 걸리지 않았다.
        graph = {"edges": [{"source": "RNN", "target": "CNN", "relation": "contrasts_with"}]}

        edges = course_packs._contrast_edges(["RNN", "CNN"], graph)

        self.assertEqual([edge["relation"] for edge in edges], ["contrasts_with"])

    def test_paths_follow_every_conceptual_relation(self) -> None:
        graph = {
            "edges": [
                {"source": "tokenizer", "target": "subword", "relation": "transforms"},
                {"source": "subword", "target": "OOV", "relation": "affects"},
            ]
        }

        steps = course_packs._find_shortest_graph_path("tokenizer", "OOV", graph)

        self.assertEqual(len(steps), 2)

    def test_paths_skip_co_occurrence_and_structural_edges(self) -> None:
        graph = {
            "edges": [
                {"source": "A", "target": "B", "relation": "related_in_context"},
                {"source": "B", "target": "C", "relation": "mentions"},
            ]
        }

        self.assertEqual(course_packs._find_shortest_graph_path("A", "C", graph), [])


if __name__ == "__main__":
    unittest.main()
