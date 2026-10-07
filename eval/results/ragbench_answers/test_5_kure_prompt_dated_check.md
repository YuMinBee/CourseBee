# CourseBee RAG Benchmark — Answers

Generated: 2026-10-07 07:02:02 UTC

Split `test`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=semantic, COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1, OLLAMA_THINK=false, COURSEBEE_SUPPORT_CHECK=on (check prompt with the reference date), COURSEBEE_TODAY=2026-10-06. Blind review in a separate session from test_1..4 (30 anchor answers re-reviewed: 28/30 same verdict).

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 88.9% | 3.7% | 0.0% | 7.4% |
| multi_hop | 13 | 46.2% | 46.2% | 7.7% | 0.0% |
| numeric | 10 | 90.0% | 0.0% | 0.0% | 10.0% |
| paraphrase | 10 | 60.0% | 10.0% | 0.0% | 30.0% |
| procedure | 8 | 87.5% | 12.5% | 0.0% | 0.0% |
| version_conflict | 7 | 85.7% | 0.0% | 0.0% | 14.3% |
| answerable (all) | 75 | 77.3% | 12.0% | 1.3% | 9.3% |
| unanswerable | 15 | - | - | 6.7% (made up) | 93.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 83.3%
- Stated something wrong (incorrect on any question): 2 / 90 (2.2%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 71 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 70.4% | 22.2% | 0.0% | 7.4% |
| multi_hop | 13 | 46.2% | 46.2% | 7.7% | 0.0% |
| numeric | 10 | 70.0% | 20.0% | 0.0% | 10.0% |
| paraphrase | 10 | 40.0% | 20.0% | 10.0% | 30.0% |
| procedure | 8 | 75.0% | 25.0% | 0.0% | 0.0% |
| version_conflict | 7 | 57.1% | 14.3% | 14.3% | 14.3% |
| answerable (all) | 75 | 61.3% | 25.3% | 4.0% | 9.3% |
| unanswerable | 15 | - | - | 13.3% (made up) | 86.7% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 74.0%
- Stated something wrong (incorrect on any question): 5 / 90 (5.6%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 33 / 57 answers
- Documents shown as sources (all retrieved): precision 0.33 / recall 0.91
- Documents cited by answer sentences: precision 0.73 / recall 0.79
- Answers rewritten by the support check: 7 / 75 answerable, 11 / 15 unanswerable
- End-to-end latency p50 / p95: 2.9 s / 5.5 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
