# CourseBee v2 Upgrade Summary

## What Changed

CourseBee v2 evolves the original single-document BeePDF prototype into a runnable, multi-document learning system. A Course Pack can ingest PDF, PPTX, Markdown, and text sources, then produce source-grounded answers, summaries, study kits, audio scripts, and concept-map artifacts.

The default path is local and deterministic so a reviewer can run the complete demo without paid APIs. OpenAI and Ollama remain optional providers, and generated refinements are accepted only when citation grounding checks pass.

## Current Stack

| Area | Implementation | Why it matters |
| --- | --- | --- |
| API | FastAPI application and typed request/response schemas | Exposes the workflow through a reviewable HTTP contract and OpenAPI docs. |
| Ingestion | PyMuPDF PDF parser, dependency-free PPTX parser, text/Markdown parser | Supports common lecture formats without requiring a cloud parser. |
| OCR | Local Tesseract fallback | Keeps scanned PDFs in the same ingestion and citation flow. |
| Chunking | Page/slide-aware chunks with stable source metadata | Preserves `doc_id`, filename, page, offsets, and `chunk_id` for provenance. |
| Retrieval | Local TF-IDF/character features plus optional multilingual E5, RRF, and Cross-Encoder | Keeps the default reproducible while allowing measured semantic retrieve-and-rerank experiments. |
| Routing | Fact, overview, relation, learning-path, and mixed question routes | Selects chunk, hierarchical-summary, or concept-graph evidence by question type. |
| Generation | Rule/mock baseline with optional OpenAI or Ollama refinement | Provides a reproducible free path while retaining replaceable LLM adapters. |
| Grounding | Source-only answer construction and citation validation | Prevents unsupported refinements from silently replacing grounded output. |
| Persistence | Atomic JSON artifact writes behind Course Pack store/artifact modules | Avoids partially written artifacts and keeps storage responsibilities isolated. |
| Runtime | CLI, packaged demo assets, readiness checks, upload limits, Docker | Makes local, wheel, and container execution follow the same application entrypoint. |
| Quality | Unit/API tests, three dependency-light suites, and one live-model semantic suite | Measures routing, source recall, graph evidence, abstention, noise, conflicts, and semantic ranking. |

## Implemented Surface

- `GET /health` and `GET /ready`
- `GET /demo` and `GET /demo-ko`
- document ingest, retrieval, study-kit, audio-script, and concept-map endpoints under `/v2`
- Course Pack create, upload, list, read, ask, summary, study-kit, audio-script, TTS, and concept-map endpoints
- background Course Pack job status endpoint for local asynchronous ingestion
- `.txt`, `.md`, `.pdf`, and `.pptx` ingestion with type/signature and batch-size validation
- page/slide-level provenance on retrieved sources and graph evidence
- Mermaid and standalone HTML concept-map exports
- request IDs, structured error responses, optional `X-API-Key` protection, and safe runtime paths
- installable `coursebee` CLI and wheel-contained demo fixtures/UI
- non-root Docker runtime with readiness-based health checks

## Evaluation

The repository includes three deterministic suites:

| Suite | Coverage | Latest checked result |
| --- | --- | --- |
| `eval/run_eval.py` | NLP routing, source recall, citation coverage, graph routes | 10 / 10 |
| `eval/run_generalization_eval.py` | Biology, economics, and software engineering | 6 / 6 |
| `eval/run_robustness_eval.py` | OCR noise, conflicts, cross-document relations, distractors, abstention | 5 / 5 |
| `eval/run_semantic_retrieval_eval.py` | Korean paraphrases and cross-lingual expected-source ranking | Recall@3 1.00 |

Run the complete local verification with:

```bash
python -m ruff check v2 eval tests
python -m unittest discover -s tests
python eval/run_eval.py
python eval/run_generalization_eval.py
python eval/run_robustness_eval.py
```

GitHub Actions repeats lint, tests, the three dependency-light evaluation suites, isolated wheel installation, and container smoke checks. The semantic suite is a separate reproducible command because it downloads two model artifacts.

## Cloud Migration Path

| Current local boundary | Production replacement |
| --- | --- |
| Local JSON and uploaded files | Object storage plus a managed metadata database |
| In-memory hybrid retrieval | pgvector, Chroma, or another managed vector index |
| In-process background task | Durable queue and worker service |
| Local Tesseract | Managed OCR provider where accuracy or scale requires it |
| Optional static API key | Identity-aware gateway, OAuth, or platform IAM |
| Local logs | Centralized logs, metrics, traces, and alerting |

## Honest Limits

- Storage is local JSON rather than a transactional database and object store.
- Background ingestion is process-local and is not durable across restarts.
- TTS defaults to a mock artifact; a real provider must be configured for audio output.
- Concept graph extraction is heuristic rather than model-based entity and relation extraction.
- The local retriever is designed for portfolio-sized Course Packs, not a large multi-tenant corpus.
- Authentication and rate limiting need an external production-grade layer before public multi-user deployment.

These limits are deliberate boundaries, not hidden claims: the current repository is a complete local portfolio demo and a tested foundation for later cloud deployment.
