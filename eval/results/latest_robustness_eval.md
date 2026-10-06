# CourseBee Retrieval Robustness Evaluation

Generated: 2026-10-06 10:29:55 UTC

Scenarios cover OCR line-break noise, source conflicts, cross-document relations, distractors, and abstention.

| Metric | Result |
| --- | --- |
| Overall pass rate | 5 / 5 |
| Router accuracy | 5 / 5 |
| Source recall and precision checks | 5 / 5 |
| Graph evidence checks | 2 / 2 |
| Abstention checks | 1 / 1 |
| Ask latency p50 / p95 | 7.86 ms / 8.79 ms |
| Tokenizer warm-up (once per process, excluded above) | kiwi, 1589 ms |

| Scenario | Case | Route | Recall | Precision | Forbidden | Terms | Abstain | Graph | Latency | Status |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | ---: | --- |
| ocr_noise | `ocr_hyphenated_terms` | vector / vector | 1.00 | 1.00 | PASS | PASS | PASS | PASS | 7.74 ms | PASS |
| ocr_noise | `unsupported_question_abstains` | vector / vector | 1.00 | 1.00 | PASS | PASS | PASS | PASS | 2.13 ms | PASS |
| version_conflict | `conflicting_versions_keep_both_sources` | local_graph / local_graph | 1.00 | 1.00 | PASS | PASS | PASS | PASS | 8.69 ms | PASS |
| cross_document_trace | `ci_to_rollback_relation` | local_graph / local_graph | 1.00 | 1.00 | PASS | PASS | PASS | PASS | 8.79 ms | PASS |
| long_distractors | `relevant_source_among_distractors` | vector / vector | 1.00 | 1.00 | PASS | PASS | PASS | PASS | 7.86 ms | PASS |
