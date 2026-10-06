# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:40 UTC

Split `test`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: v3 original code (commit cb6c658): v3 retrieval, v3 prompt, Ollama default thinking (on), no support check. (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 59.3% | 11.1% | 3.7% | 25.9% |
| multi_hop | 13 | 38.5% | 46.2% | 7.7% | 7.7% |
| numeric | 10 | 70.0% | 0.0% | 0.0% | 30.0% |
| paraphrase | 10 | 0.0% | 0.0% | 0.0% | 100.0% |
| procedure | 8 | 75.0% | 12.5% | 0.0% | 12.5% |
| version_conflict | 7 | 57.1% | 0.0% | 0.0% | 42.9% |
| answerable (all) | 75 | 50.7% | 13.3% | 2.7% | 33.3% |
| unanswerable | 15 | - | - | 0.0% (made up) | 100.0% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 57.3%
- Stated something wrong (incorrect on any question): 2 / 90 (2.2%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 73 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 55.6% | 7.4% | 14.8% | 22.2% |
| multi_hop | 13 | 53.8% | 23.1% | 15.4% | 7.7% |
| numeric | 10 | 70.0% | 0.0% | 10.0% | 20.0% |
| paraphrase | 10 | 0.0% | 10.0% | 50.0% | 40.0% |
| procedure | 8 | 62.5% | 25.0% | 0.0% | 12.5% |
| version_conflict | 7 | 42.9% | 14.3% | 0.0% | 42.9% |
| answerable (all) | 75 | 49.3% | 12.0% | 16.0% | 22.7% |
| unanswerable | 15 | - | - | 6.7% (made up) | 93.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 55.3%
- Stated something wrong (incorrect on any question): 13 / 90 (14.4%)

## Deterministic checks

- Empty answers (nothing retrieved): 11 / 75 answerable, 6 / 15 unanswerable
- Every reference number/unit present in the answer: 28 / 57 answers
- Documents shown as sources (all retrieved): precision 0.32 / recall 0.62
- Documents cited by answer sentences: precision 0.68 / recall 0.57
- Answers rewritten by the support check: 0 / 75 answerable, 0 / 15 unanswerable
- End-to-end latency p50 / p95: 4.4 s / 7.7 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
