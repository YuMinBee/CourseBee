# Providers

CourseBee v2 separates infrastructure concerns behind provider interfaces. Local implementations are used by default, while cloud services can be added without rewriting the workflow.

## StorageProvider

Local demo:

- `LocalStorageProvider`

Future replacements:

- `S3LikeStorageProvider`
- `NCPObjectStorageProvider`
- Object Storage provider

Responsibilities:

- Save uploaded PDFs.
- Save JSON artifacts.
- Save generated audio.
- Return stable paths or presigned URLs.

## ParserProvider

Local demo:

- `LocalParserProvider`

Future replacements:

- Managed parser worker
- OCR-backed parser
- Cloud document parser

Responsibilities:

- Parse `.pdf`, `.txt`, and `.md` documents.
- Preserve page-level markdown.
- Return graceful warnings when optional PDF parsers are unavailable.


## OCRProvider

Local demo:

- `MockOCRProvider`
- `LocalTesseractOCRProvider`

Future replacements:

- `ClovaOCRProvider`
- `GoogleVisionOCRProvider`
- `AzureDocumentIntelligenceProvider`
- OCR worker backed by PaddleOCR or another document OCR engine

Responsibilities:

- Extract page text from scanned or image-only PDFs.
- Return page-level markdown so the same chunk/RAG pipeline can continue.
- Preserve warnings when OCR is unavailable or produces no text.

The local Tesseract provider is a working CPU-based fallback for demo and tests. It is not a hard requirement for production; managed OCR providers can replace it behind the same interface.

## LLMProvider

Local demo:

- `MockLLMProvider`
- `OpenAIProvider` when `OPENAI_API_KEY` is configured
- `OllamaProvider` for local grounded answers, explicit general-knowledge fallback, and script generation; the demo chat requests `qwen3:14b`
- `OllamaProvider` can stream token fragments through a callback and checks a cancellation event between fragments.

Future replacements:

- `OllamaProvider`
- OpenAI-compatible managed LLM provider
- `ClovaStudioProvider`

Responsibilities:

- Generate source-grounded summaries and optional API-refined Course Pack overviews.
- Answer questions with context.
- Extract entities and relations.
- Generate study kits and audio scripts.
- For Course Pack audio scripts, `llm_provider: "ollama"` can call a local model and fall back to rule output if Ollama is unavailable.
- For Course Pack Q&A, `allow_general_fallback: true` uses Ollama only when retrieval finds no evidence. The response marks this as `answer_scope: "general_knowledge"`, sets `grounding_status: "ungrounded"`, and returns no source citations.
- Follow-up questions can include bounded `conversation_history`; independent questions do not inherit stale retrieval terms.

## WebSearchProvider

Local demo:

- `WikipediaSearchProvider` searches Korean Wikipedia first and English Wikipedia as a fallback.
- Results include a bounded plain-text extract, canonical URL, language, provider, and rank.
- Results are converted to normal `Chunk` objects so answer generation and sentence citations reuse the same grounded pipeline.

Course Pack Q&A enables this layer with `allow_web_fallback: true`. The response uses `answer_scope: "external_web"`, `grounding_status: "web_grounded"`, `web_search_used: true`, and URL-bearing sources. `allow_general_fallback` is evaluated only after this search returns no usable evidence or fails.

## TTSProvider

Local demo:

- `MockTTSProvider`

Future replacements:

- `LocalTTSProvider`
- `ClovaVoiceProvider`

Responsibilities:

- Convert generated scripts to audio.
- Return local file paths, object storage URLs, or `null` for mock TTS.

## RetrieverProvider

Local demo:

- `LexicalRetriever`
- `HybridRetriever`
- `SimpleRetriever` compatibility alias

Current implementation:

- Tokenizes query and chunk text.
- Computes term frequency and IDF-style scores.
- Returns top-k chunks while preserving `doc_id`, `filename`, `page`, `chunk_id`, and lecture metadata.
- `EmbeddingRetriever` performs optional multilingual E5 dense retrieval with model and embedding caches.
- `SemanticHybridRetriever` combines local and dense rankings with Reciprocal Rank Fusion.
- `semantic_rerank` applies a multilingual Cross-Encoder only to the fused candidate set.
- Model import/download/runtime failures fall back to local hybrid retrieval and remain visible in response metadata.

Production replacements:

- `VectorDBRetriever` backed by Chroma, FAISS, pgvector, or a managed vector DB
- Hosted embedding and reranking endpoints behind the same provider contract

This split is intentional. Default local mode favors reproducibility and explainability, while explicit semantic modes demonstrate real retrieve-and-rerank behavior without making heavyweight downloads part of startup.
## IndexProvider

Local demo:

- `LocalIndexProvider`
- `LexicalRetriever`
- `SimpleRetriever` compatibility alias

Future replacements:

- `ChromaProvider`
- `ManagedVectorDBProvider`
- `FutureVectorDBProvider`

Responsibilities:

- Build document indexes.
- Search relevant chunks.
- Preserve `page` and `chunk_id` in search results.

## Contract Rule

Every provider should return serializable data. This keeps workflow state portable between local execution, HTTP APIs, background workers, and cloud deployment.

## Replacement Path

```text
LocalStorageProvider -> ObjectStorageProvider
LocalParserProvider -> OCR/parser worker
MockOCRProvider/LocalTesseractOCRProvider -> ClovaOCRProvider/managed OCR
MockLLMProvider -> OpenAIProvider/ClovaStudioProvider/OllamaProvider
MockTTSProvider -> ClovaVoiceProvider/LocalTTSProvider
LexicalRetriever/LocalIndexProvider -> EmbeddingRetriever/HybridRetriever/ManagedVectorDBProvider
In-process workflow -> Queue-based worker execution
```
