# Semantic Retrieval

CourseBee keeps its dependency-free local hybrid retriever as the default and exposes semantic retrieval as an explicit AI profile. Opening the demo or using `mode="auto"` never downloads a model.

## Pipeline

```text
question
|-- local hybrid ranking
|-- multilingual E5 dense ranking
`-- Reciprocal Rank Fusion
    `-- optional multilingual Cross-Encoder reranking
        `-- source-grounded answer
```

Available Course Pack query modes:

| Mode | Execution |
| --- | --- |
| `semantic` | Dense bi-encoder retrieval only |
| `semantic_hybrid` | Local hybrid + dense retrieval + RRF |
| `semantic_rerank` | Local hybrid + dense retrieval + RRF + Cross-Encoder |

## Models

- Embedding: [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small)
- Reranker: [`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1)
- Runtime: [`sentence-transformers`](https://www.sbert.net/)

E5 retrieval inputs use the model-required `query:` and `passage:` prefixes. Embeddings are normalized and ranked by cosine-equivalent dot product.

## Rank Fusion

Local and dense rankings are merged with Reciprocal Rank Fusion:

```text
RRF(document) = sum(1 / (60 + rank))
```

RRF avoids pretending that lexical and cosine scores share the same numeric scale. A document found by both retrievers receives contributions from both rankings. `semantic_rerank` then sends only this bounded candidate set to the slower Cross-Encoder.

## Runtime Behavior

- Sentence Transformer and Cross-Encoder instances are lazy-loaded and cached by model name.
- Query and document embeddings use a bounded in-memory LRU cache.
- `COURSEBEE_EMBEDDING_CACHE_SIZE` controls the cache entry limit.
- Embedding failure falls back to local hybrid retrieval.
- Reranker failure retains the fused ranking.
- Every fallback is returned in `warnings`, `retrieval_details`, and `trace.retrieval_debug`.

Example request:

```json
{
  "pack_id": "pack_static_nlp_11week_demo",
  "question": "Which model preserves information across long contexts?",
  "mode": "semantic_rerank",
  "top_k": 4
}
```

## Evaluation

```bash
pip install -e ".[semantic]"
python eval/run_semantic_retrieval_eval.py
```

To include the CPU-only Sentence Transformers runtime in the Docker image from PowerShell:

```powershell
$env:COURSEBEE_INSTALL_SEMANTIC = "true"
docker compose build
docker compose up
```

The Docker profile installs CPU-only PyTorch so a CPU cloud deployment does not carry unused CUDA libraries. Model weights are still downloaded lazily on the first semantic request rather than baked into the default image.

Latest six-case synthetic result:

| Mode | Recall@3 | MRR | Mean warm latency | Fallbacks |
| --- | ---: | ---: | ---: | ---: |
| Local hybrid | 0.17 | 0.167 | 2.29 ms | 0 |
| E5 + RRF | 1.00 | 0.917 | 9.09 ms | 0 |
| E5 + RRF + Cross-Encoder | 1.00 | 1.000 | 12.03 ms | 0 |

The suite intentionally contains Korean paraphrases and English questions over Korean documents. It measures expected-source ranking, not answer correctness. Model download time is excluded, and latency is measured after warm-up in one local process. Latency is a machine-dependent snapshot rather than a service-level objective.

See [`eval/results/latest_semantic_retrieval_eval.md`](../eval/results/latest_semantic_retrieval_eval.md) for case-level ranks.

## Limits

- The current embedding cache is process-local and is rebuilt after restart.
- Dense encoding still scans all Course Pack chunks because no vector database is used yet.
- The benchmark is synthetic and small; it demonstrates behavior but does not replace evaluation on permission-safe real lecture material.
- Model memory and first-download costs are intentionally excluded from the default Docker image and CI path.
