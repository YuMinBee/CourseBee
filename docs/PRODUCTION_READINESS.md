# Production Readiness

CourseBee v2 is currently a local-first portfolio demo with clear production upgrade boundaries. The local path is implemented intentionally so the project can run without paid services or private infrastructure. The production path is separated behind provider interfaces and documented as planned work.

## Current Local Demo

Implemented locally:

- Korean-aware local hybrid retrieval with lexical and character-level signals
- Mock/rule LLM fallback
- Optional OpenAI summary refinement when `OPENAI_API_KEY` is set
- File-system artifact store
- Local `outputs/` directory for generated artifacts
- Local Course Pack metadata JSON
- Concept graph-assisted retrieval over Course Pack concept edges
- Hierarchical summary retrieval over course structure
- Evaluation harnesses for route, source recall/precision, graph evidence, OCR noise, conflicts, distractors, and abstention
- File-backed Course Pack job API for ingestion status
- Browser upload API with extension, signature, per-file size, batch size, count, identifier, and path validation
- Atomic JSON/artifact writes and in-process duplicate job protection
- Optional `X-API-Key` boundary plus HTTP request-id and timing headers
- Answer trace with request id, stage latency, and retrieval debug
- Separate liveness (`/health`) and storage/asset readiness (`/ready`) checks
- GitHub Actions checks for tests, three evaluation suites, isolated wheel install, and container smoke tests
- Package-owned demo UI and fixtures verified from a built wheel
- Dockerfile and Compose runtime with a non-root user and readiness health check

## Production Upgrade Path

Planned production replacements:

- Embedding retriever plus vector DB
- Persisted hybrid lexical + embedding retrieval and reranking
- Optional reranker with cross-encoder or LLM judge
- Async ingestion job queue / worker process for distributed production workloads
- Object storage for artifacts
- DB-backed Course Pack metadata
- Centralized observability: structured logs, metrics, traces, and token usage
- User identity, per-tenant authorization, quota/rate limits, and malware scanning
- Environment-specific deployment automation and secret management

## Status

```text
Status
- Local demo: implemented
- Source-grounded artifacts: implemented
- Citation / grounding check: implemented for API-refined summaries
- Course Pack job API: implemented locally
- Answer trace / retrieval debug: implemented
- Concept graph-assisted retrieval: implemented
- Hierarchical summary retrieval: implemented
- Query-type retrieval router: implemented
- Retrieval evaluation harness: implemented
- Multi-domain biology/economics/software evaluation: implemented
- Retrieval robustness evaluation: implemented for OCR noise, conflicts, cross-document evidence, distractors, and abstention
- Production vector DB: planned
- Async ingestion background task: implemented locally
- Object storage: planned
- DB-backed metadata: planned
- Observability: partially implemented through request headers, answer trace, and job state
- API key / upload signature, batch limit, and path validation: implemented locally
- User auth / quota / malware scanning: planned
- CI, isolated wheel install, and container runtime smoke checks: implemented
```

## Why This Is Not Hidden

The distinction between local demo and production path is explicit because it is an engineering trade-off. Hiding mock providers would make the project look less reliable. Naming them makes the architecture easier to evaluate.

Local demo priorities:

- reproducibility
- no paid dependencies
- deterministic tests
- explainable retrieval behavior
- source-grounded artifacts

Production priorities:

- semantic retrieval quality
- scalability
- background processing
- artifact durability
- observability and access control

## Observability

Course Pack answer responses include a `trace` field:

```json
{
  "trace": {
    "request_id": "req_abc123",
    "stages": [
      {"name": "classify_question", "latency_ms": 3},
      {"name": "retrieve_graph_context", "latency_ms": 18},
      {"name": "select_evidence_chunks", "latency_ms": 5},
      {"name": "compose_answer", "latency_ms": 11}
    ],
    "retrieval_debug": {
      "candidate_chunks": 12,
      "selected_chunks": 4,
      "candidate_graph_edges": 30,
      "selected_graph_edges": 2,
      "fallback_used": false
    }
  }
}
```

This makes router decisions and retrieval failures inspectable without adding a full tracing backend yet.

## Provider Replacement Map

| Local component | Production replacement |
| --- | --- |
| local `HybridRetriever` | persisted embedding/vector DB retriever plus reranker |
| `MockLLMProvider` | OpenAI-compatible provider, Clova Studio, hosted local model |
| `MockTTSProvider` | Clova Voice, Edge TTS service wrapper, local TTS service |
| local file system artifacts | object storage |
| JSON Course Pack metadata | relational DB or document DB |
| in-process ingestion | queue-based worker |
| local logs | structured tracing and metrics |

## Readiness Summary

CourseBee v2 is production-shaped but not production-deployed. The current repository proves the core retrieval and grounding behavior locally, while provider boundaries show how to replace local components with production infrastructure.
