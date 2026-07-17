# CourseBee v2

This directory contains the current CourseBee application: multi-document Course Pack ingest, source-grounded retrieval, study artifacts, concept graph-assisted retrieval, and local-first provider adapters.

The default implementation is intentionally local and lightweight. Sentence Transformers is implemented as an explicit optional semantic profile, while heavier components such as Docling, FAISS, Chroma, external LLMs, and TTS APIs remain replaceable through providers without changing the workflow contract. `OpenAIProvider` is available as an optional API-backed LLM provider and falls back to rule/mock behavior when `OPENAI_API_KEY` is not configured. API-refined summaries are accepted only when `citation_check` confirms they are grounded in retrieved source chunks.

## Modules

- `ingest.py`: local `.pdf`, `.pptx`, `.txt`, and `.md` document ingest
- `documents.py`: local document/chunk loading helpers
- `course_packs.py`: multi-document Course Pack ingest and pack-level generation helpers
- `course_pack_store.py`: Course Pack metadata and chunk persistence
- `course_pack_artifacts.py`: artifact previews and Mermaid/HTML export
- `course_pack_jobs.py`: file-backed ingestion job lifecycle
- `course_summary.py`: Course Pack summary generation with source-preserving rule output and optional OpenAI refinement
- `schemas.py`: shared serializable models
- `api/schemas.py`: Pydantic request and response models
- `providers/`: storage, LLM, TTS, OCR, parser, index, and optional semantic retrieval providers
- `providers/semantic.py`: multilingual dense retrieval, RRF fusion, Cross-Encoder reranking, and model caches
- `rag/chunking.py`: page-level chunking with `page`, `chunk_id`, char offsets, `doc_id`, and `filename`
- `rag/retrieval.py`: local hybrid retrieval with lexical and Korean character-level signals
- `rag/answering.py`: source-grounded answer generation
- `study_kit.py`: rule/template based study-kit generation with sources
- `audio_script.py`: source-grounded audio script generation
- `graph/concept_map.py`: evidence-backed concept graph builder
- `workflows/`: state and node functions
- `api/routes.py`: FastAPI routes wired to local service functions

## Local Ingest

`ingest_local_document()` writes this artifact structure:

```text
outputs/{doc_id}/
- document.json
- pages.json
- chunks.json
- graph.json
- answers/
- study_kit.json
- audio_script.json
```

PDF ingest tries `pymupdf4llm` first and `PyMuPDF` second. If the text layer is empty, CourseBee tries local Tesseract OCR. PPTX ingest reads slide text from the `.pptx` zip/XML package with the Python standard library and maps each slide to the existing `page` field. If optional PDF libraries are unavailable, the app returns warnings instead of crashing. Text, Markdown, and PPTX ingest do not require extra dependencies.

## Chunk Schema

```json
{
  "chunk_id": "p3_c2",
  "page": 3,
  "text": "...",
  "char_start": 1200,
  "char_end": 1800,
  "metadata": {
    "doc_id": "sha256-doc-id",
    "filename": "sample.pdf",
    "pack_id": "pack_abc123"
  }
}
```

Empty pages are skipped during chunking, while `pages.json` can still preserve parsed page records.

## Course Pack Ingest

Course Packs aggregate multiple documents into one learning unit. Each input file still receives its own `doc_id`, while pack-level chunks preserve `doc_id`, `filename`, `page`, and `chunk_id` for source-grounded outputs.

```json
{
  "paths": ["week1.pdf", "week2.pdf", "week3.pdf"],
  "output_root": "outputs"
}
```

The pack artifact structure is:

```text
outputs/course_packs/{pack_id}/
- course_pack.json
- chunks.json
- graph.json
- answers/
- study_kit.json
- summary.json
- audio_script.json
- concept_map.mmd
- concept_map.html
```

Pack-level Q&A, Summary, Study Kit, Audio Script, Concept Map, artifact preview, and Mermaid/HTML concept map export use the aggregated chunks. A verified local walkthrough is documented in `docs/COURSE_PACK_DEMO.md`. Overview-style pack queries balance retrieval across documents so each lecture can contribute source evidence to the final answer. Concept Map adds document nodes and `appears_in` edges so shared concepts across lecture files are visible.

## Local Retrieval

The local retrieval path avoids embedding downloads and combines a TF-IDF-style lexical score with Korean suffix normalization, character features, and OCR line-break normalization. It returns only matched contexts.

Source-grounded answer generation returns an answer only when retrieval provides at least one source chunk. If no context is found, the answer is empty and a warning is returned.

## Optional Semantic Retrieval

Install the optional model dependency and select a semantic mode explicitly:

```bash
pip install -e ".[semantic]"
```

- `semantic`: multilingual E5 dense retrieval
- `semantic_hybrid`: local hybrid and dense retrieval combined with Reciprocal Rank Fusion
- `semantic_rerank`: fused candidates reordered by a multilingual Cross-Encoder

The default models can be changed with `COURSEBEE_EMBEDDING_MODEL` and `COURSEBEE_RERANKER_MODEL`. CourseBee adds the E5 `query:` and `passage:` prefixes, caches loaded models and document embeddings in memory, and returns a visible local fallback when a semantic stage fails.

## OCR Fallback

Image-only PDFs can flow through a real local OCR fallback when Tesseract is installed:

```text
empty PDF text layer -> LocalTesseractOCRProvider -> PageMarkdown -> chunks -> v2 services
```

`MockOCRProvider` is available for deterministic tests. `LocalTesseractOCRProvider` renders PDF pages with PyMuPDF and extracts text with Tesseract through `pytesseract`.

## Audio Script Modes

`generate_audio_script()` supports:

- `brief_1min`
- `briefing_3min`
- `lecture`
- `podcast`

The response keeps sources on every script segment and uses mock TTS by default:

```json
{
  "mode": "briefing_3min",
  "script": [
    {
      "speaker": "narrator",
      "text": "...",
      "sources": [{"doc_id": "...", "filename": "week1.pdf", "page": 1, "chunk_id": "p1_c1"}]
    }
  ],
  "tts_status": "mock",
  "audio_path": null
}
```

## Concept Graph-assisted Retrieval

`build_concept_map()` creates heuristic nodes and edges from chunk text. Every edge includes source evidence from the chunk that produced it. For Course Packs, document nodes and `appears_in` edges make cross-document concept links visible. If no graph can be built, it returns empty `nodes` and `edges` with a warning.

The concept graph remains a helper path and is not required for answer generation. Relation questions combine graph evidence with balanced lexical evidence so conflicting or cross-document sources are not dropped. Course Pack concept maps can also be exported to `concept_map.mmd` and `concept_map.html` for visual review.

## FastAPI v2 Endpoints

The route skeleton uses Pydantic request and response models for the main v2 API surface:

- `POST /v2/documents/ingest`
- `GET /v2/documents/{doc_id}`
- `POST /v2/ask`
- `POST /v2/study-kit`
- `POST /v2/audio-script`
- `POST /v2/concept-map`
- `POST /v2/course-packs`
- `GET /v2/course-packs/{pack_id}`
- `GET /v2/course-packs/{pack_id}/artifacts`
- `POST /v2/course-packs/ask`
- `POST /v2/course-packs/ask/stream`
- `POST /v2/course-packs/study-kit`
- `POST /v2/course-packs/summary`
- `POST /v2/course-packs/audio-script`
- `POST /v2/course-packs/concept-map`
- `POST /v2/course-packs/concept-map/export`

Compatibility aliases remain for `/v2/ingest`, `/v2/retrieve`, and `/v2/answer`.

`conversation_history` accepts up to 12 recent `user`/`assistant` messages. CourseBee uses that history only for follow-up language such as `그럼`, `그건`, or `예시는?`, preserving independent-question retrieval. The streaming endpoint emits `status`, `token`, and final `result` SSE events; disconnecting the client signals local Ollama generation to stop.

`allow_web_fallback: true` inserts a cited Wikipedia Web RAG stage after a Course Pack miss. `web_provider` defaults to `wikipedia` and `web_top_k` accepts 1-5 results. Successful web answers return `answer_scope: "external_web"`, `grounding_status: "web_grounded"`, `web_search` metadata, and source objects containing `title`, `url`, and `excerpt`. `allow_general_fallback` runs only if this stage fails or returns no usable results.

## Resource Policy

CourseBee does not run embedding models or paid LLM APIs by default. Generic API requests still default to source-grounded rule/mock output with external fallback disabled. The packaged demo chat explicitly requests local Ollama `qwen3:14b` and enables the no-key Wikipedia Web RAG layer; if both Course Pack and web evidence are unavailable, it returns a labeled general-knowledge answer with no citations. To try managed API refinement, set `OPENAI_API_KEY` and send `llm_provider: "openai"`; if citation validation fails, CourseBee returns the rule-based summary with a warning instead of using unsupported LLM text.







