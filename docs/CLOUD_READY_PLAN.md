# Cloud-ready Plan

CourseBee v2 keeps local execution as the default path for reproducibility and zero-cost review. Cloud-facing concerns remain behind provider and storage boundaries so the same workflow can move to managed infrastructure later.

## Current Implementation Target

- FastAPI API layer
- Local file storage for inputs and generated outputs
- Local TF-IDF and Korean character-feature hybrid retrieval
- Local evidence-backed concept graph artifact
- In-process workflow execution
- JSON artifacts under `outputs/{doc_id}/`

## Cloud Migration Path

| Current | Cloud-ready replacement |
| --- | --- |
| `LocalStorageProvider` | Object Storage provider such as NCP Object Storage or S3-compatible storage |
| In-memory hybrid retrieval | Managed vector DB, pgvector, or hosted Chroma collection |
| In-process workflow | Queue-based worker execution |
| Local JSON metadata | Managed DB such as Cloud DB for MySQL |
| Local logs | Centralized logging and request tracing |

## Design Statement

v2는 비용 문제로 로컬 실행을 기본값으로 두었지만, Storage/LLM/TTS/Index 계층을 provider interface로 분리하여 클라우드 Object Storage, 외부 LLM API, managed vector DB로 교체 가능한 cloud-ready 구조로 설계했습니다.

## Migration Principles

- Keep request and document identifiers stable across providers.
- Store source page and chunk metadata with every answer.
- Treat OCR, LLM, TTS, storage, and indexing as replaceable adapters.
- Keep the LangGraph-style workflow state serializable so it can later move from local functions to worker tasks.
- Prefer explicit failure records with `request_id`, node name, error type, and retry status.
