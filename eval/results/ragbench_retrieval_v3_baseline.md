# CourseBee RAG Benchmark — Retrieval (v3 baseline)

Baseline measured on commit cb6c658 (before the Kiwi + BM25 index) with the same script and data.

Generated: 2026-10-06 10:23:48 UTC

Retriever `balanced` over 32 documents / 82 chunks. A chunk counts as evidence when it
contains at least 50% of a gold evidence quote. Full@k requires every evidence item
(multi-hop questions need all of their documents).

| Type | n | Hit@1 | Hit@3 | Hit@5 | Full@5 | MRR@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 60 | 36.7% | 65.0% | 71.7% | 71.7% | 0.524 |
| multi_hop | 20 | 45.0% | 70.0% | 85.0% | 20.0% | 0.591 |
| numeric | 20 | 35.0% | 60.0% | 60.0% | 60.0% | 0.450 |
| paraphrase | 25 | 0.0% | 0.0% | 0.0% | 0.0% | 0.000 |
| procedure | 15 | 20.0% | 46.7% | 73.3% | 60.0% | 0.404 |
| version_conflict | 10 | 0.0% | 30.0% | 50.0% | 50.0% | 0.194 |
| all | 150 | 27.3% | 50.0% | 58.7% | 48.7% | 0.402 |

- Unanswerable questions: 30. Top-score AUC (answerable vs unanswerable): 0.611
- Retrieval latency p50 / p95: 284.8 ms / 291.9 ms; pack build 1.4 s

Misses at k=5 (answerable):

q004, q010, q020, q021, q022, q024, q027, q029, q030, q035, q039, q040, q047, q049, q050, q055, q060, q061, q062, q063, q064, q065, q066, q067, q068, q069, q070, q071, q072, q073, q074, q075, q076, q077, q078, q079, q080, q081, q082, q083, q084, q085, q086, q088, q089, q093, q096, q101, q103, q104, q106, q107, q108, q109, q112, q118, q124, q131, q136, q141, q143, q146
