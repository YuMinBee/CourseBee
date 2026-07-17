# CourseBee v2 Evaluation Results

Generated: 2026-07-16 07:26:59 UTC

This evaluation uses a public synthetic NLP 11-week Course Pack fixture. It does not use private lecture materials.

## Evaluation Snapshot

| Metric | Result |
| --- | --- |
| Overall pass rate | 10 / 10 |
| Router accuracy | 10 / 10 |
| Source recall@5 | 9 / 9 |
| Citation coverage | 0.90 |
| No-context fallback pass | 1 / 1 |
| Graph route useful cases | 4 / 4 |

## Case Results

| ID | Expected | Actual | Sources | Concepts | Status |
| --- | --- | --- | --- | --- | --- |
| `relation_bpe_oov` | relation_question / local_graph / local_graph | relation_question / local_graph / local_graph | 자연어처리_11주차_1차시.txt | BPE, OOV, subword tokenization, NLP pipeline, Tokenizer, subword, oov through | PASS |
| `learning_path_bpe` | learning_path_question / local_graph / course_graph_path | learning_path_question / local_graph / course_graph_path | 자연어처리_11주차_1차시.txt | BPE, Tokenizer, subword tokenization, subword | PASS |
| `overview_week11` | overview_question / hierarchical / hierarchical_summary | overview_question / hierarchical / hierarchical_summary | 자연어처리_11주차_1차시.txt, 자연어처리_11주차_2차시.txt, 자연어처리_11주차_3차시.txt | - | PASS |
| `pipeline_relation` | relation_question / local_graph / course_graph_path | relation_question / local_graph / course_graph_path | 자연어처리_11주차_3차시.txt, 자연어처리_11주차_2차시.txt, 자연어처리_11주차_1차시.txt | CNN, LSTM, NLP, NLP pipeline, RNN, nlp pipeline | PASS |
| `fact_lstm` | fact_question / vector / vector | fact_question / vector / vector | 자연어처리_11주차_2차시.txt | - | PASS |
| `fact_cnn` | fact_question / vector / vector | fact_question / vector / vector | 자연어처리_11주차_3차시.txt | - | PASS |
| `mixed_overview_relation` | mixed_question / hierarchical / hierarchical_summary | mixed_question / hierarchical / hierarchical_summary | 자연어처리_11주차_1차시.txt, 자연어처리_11주차_2차시.txt, 자연어처리_11주차_3차시.txt | - | PASS |
| `no_context_fallback` | relation_question / local_graph / local_graph_fallback_vector | relation_question / local_graph / local_graph_fallback_vector | - | - | PASS |
| `graphrag_concept_map` | relation_question / local_graph / local_graph | relation_question / local_graph / local_graph | 자연어처리_11주차_3차시.txt | GraphRAG, GraphRAG-lite, RAG, concept map, source citation, text classification, page | PASS |
| `source_citation_fact` | fact_question / vector / vector | fact_question / vector / vector | 자연어처리_11주차_3차시.txt | - | PASS |

## Notes

- Router accuracy checks `question_type`, `routed_mode`, and final `retrieval_mode`.
- Source recall@5 checks whether required source filenames appear in answer sources, graph evidence, or hierarchical supporting chunks.
- Citation coverage measures whether each answer returned at least one source-like evidence reference.
- Graph route useful cases require graph context or graph paths plus expected concepts.
- No-context fallback checks that relation questions with no matching course graph concepts fall back with a warning.
