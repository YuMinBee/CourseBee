# CourseBee Semantic Retrieval Evaluation

Generated: 2026-07-16 07:27:32 UTC

Public synthetic CourseBee semantic retrieval benchmark with Korean paraphrases and cross-lingual questions.

- Embedding model: `intfloat/multilingual-e5-small`
- Reranker model: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
- Evaluation depth: top-3
- Latency excludes model download and uses a warm in-process model/cache.

## Metrics

| Mode | Recall@k | MRR | Mean warm latency | Fallbacks |
| --- | ---: | ---: | ---: | ---: |
| `local_hybrid` | 0.17 | 0.167 | 2.29 ms | 0 |
| `semantic_hybrid` | 1.00 | 0.917 | 9.09 ms | 0 |
| `semantic_rerank` | 1.00 | 1.000 | 12.03 ms | 0 |

## Cases

| Case | Expected | local_hybrid rank | semantic_hybrid rank | semantic_rerank rank |
| --- | --- | ---: | ---: | ---: |
| `cross_lingual_subword` | tokenization.txt | MISS | 1 | 1 |
| `paraphrase_vocabulary_tradeoff` | tokenization.txt | MISS | 1 | 1 |
| `cross_lingual_long_memory` | sequence_models.txt | MISS | 1 | 1 |
| `paraphrase_vanishing_gradient` | sequence_models.txt | MISS | 2 | 1 |
| `cross_lingual_local_patterns` | text_cnn.txt | 1 | 1 | 1 |
| `paraphrase_provenance` | grounding.txt | MISS | 1 | 1 |

## Notes

- This synthetic suite measures retrieval ranking, not generated-answer quality.
- Cross-lingual and paraphrased questions reduce dependence on exact keyword overlap.
- A semantic fallback is counted as a failure so missing models are not reported as AI success.
- Model selection should be revisited with real, permission-safe lecture material before production use.
