# CourseBee RAG Benchmark — Retrieval

Generated: 2026-10-06 10:30:02 UTC

Retriever `balanced` over 32 documents / 82 chunks. A chunk counts as evidence when it
contains at least 50% of a gold evidence quote. Full@k requires every evidence item
(multi-hop questions need all of their documents).

| Type | n | Hit@1 | Hit@3 | Hit@5 | Full@5 | MRR@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 60 | 71.7% | 93.3% | 95.0% | 95.0% | 0.817 |
| multi_hop | 20 | 70.0% | 95.0% | 95.0% | 50.0% | 0.817 |
| numeric | 20 | 75.0% | 85.0% | 95.0% | 95.0% | 0.824 |
| paraphrase | 25 | 0.0% | 12.0% | 28.0% | 28.0% | 0.090 |
| procedure | 15 | 66.7% | 86.7% | 100.0% | 80.0% | 0.800 |
| version_conflict | 10 | 30.0% | 60.0% | 80.0% | 80.0% | 0.490 |
| all | 150 | 56.7% | 76.0% | 83.3% | 75.3% | 0.673 |

- Unanswerable questions: 30. Top-score AUC (answerable vs unanswerable): 0.640
- Retrieval latency p50 / p95: 0.8 ms / 1.1 ms; pack build 3.2 s

Misses at k=5 (answerable):

q027, q039, q047, q061, q062, q063, q065, q066, q067, q068, q069, q070, q071, q072, q073, q074, q078, q079, q081, q084, q085, q089, q106, q112, q118
