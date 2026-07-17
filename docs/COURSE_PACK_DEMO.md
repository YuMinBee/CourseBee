# Course Pack Demo

This demo shows the CourseBee v2 direction: multiple lecture files are grouped into one Course Pack, then Q&A, Summary, Study Kit, Audio Script, and Concept Map outputs are generated with source metadata.

## Demo Dataset

Verified local sample files:

```text
test_data/lecture/자연어처리 강의자료/자연어처리_11주차 1차시.pptx
test_data/lecture/자연어처리 강의자료/자연어처리_11주차 2차시-2.pptx
test_data/lecture/자연어처리 강의자료/자연어처리_11주차 3차시.pptx
```

Current verified result:

```json
{
  "pack_id": "pack_d49edce9d8c487cd",
  "document_count": 3,
  "chunk_count": 112,
  "warnings": []
}
```

## Run

```bash
python -m uvicorn v2.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

## 1. Ingest Course Pack

Endpoint:

```text
POST /v2/course-packs
```

Request:

```json
{
  "paths": [
    "test_data/lecture/자연어처리 강의자료/자연어처리_11주차 1차시.pptx",
    "test_data/lecture/자연어처리 강의자료/자연어처리_11주차 2차시-2.pptx",
    "test_data/lecture/자연어처리 강의자료/자연어처리_11주차 3차시.pptx"
  ],
  "output_root": "outputs/manual_course_pack_11week_api",
  "max_chunk_chars": 900
}
```

Expected behavior:

- Creates one `pack_id` for the three lecture files.
- Preserves `doc_id`, `filename`, `page`, and `chunk_id` on every chunk.
- Writes Course Pack artifacts under `outputs/manual_course_pack_11week_api/course_packs/{pack_id}`.

## 2. Course Pack Summary

Endpoint:

```text
POST /v2/course-packs/summary
```

Request:

```json
{
  "pack_id": "pack_d49edce9d8c487cd",
  "query": "course pack overview summary",
  "output_root": "outputs/manual_course_pack_11week_api",
  "top_k": 8,
  "max_items": 5,
  "llm_provider": "mock"
}
```

Verified local result:

```json
{
  "lecture_summaries": 3,
  "key_concepts": ["LSTM", "OOV", "Tokenizer", "RNN", "CNN"],
  "connections": 5,
  "sources": 3,
  "llm": {"provider": "mock", "status": "mock"},
  "citation_check": {"checked": false, "passed": true}
}
```

If `llm_provider` is `openai`, CourseBee uses `OpenAIProvider` only when `OPENAI_API_KEY` is configured. API-refined text must pass `citation_check`; otherwise CourseBee falls back to the rule-based source-grounded summary.

## 3. Course Pack Q&A

Endpoint:

```text
POST /v2/course-packs/ask
```

Request:

```json
{
  "pack_id": "pack_d49edce9d8c487cd",
  "question": "BPE OOV 토크나이저 핵심 내용",
  "output_root": "outputs/manual_course_pack_11week_api",
  "top_k": 5
}
```

Verified local result:

```json
{
  "source_count": 5,
  "source_filenames": [
    "자연어처리_11주차 1차시.pptx",
    "자연어처리_11주차 2차시-2.pptx",
    "자연어처리_11주차 3차시.pptx"
  ],
  "warnings": []
}
```

The answer is generated only from retrieved chunks. Every source includes `filename`, `page`, and `chunk_id`.

## 4. Concept Map

Endpoint:

```text
POST /v2/course-packs/concept-map
```

Request:

```json
{
  "pack_id": "pack_d49edce9d8c487cd",
  "output_root": "outputs/manual_course_pack_11week_api"
}
```

Verified local result:

```json
{
  "nodes": 121,
  "edges": 1019,
  "document_nodes": 3,
  "warnings": []
}
```

Concept Map adds document nodes and `appears_in` edges so shared concepts can be traced back to specific lecture files.

## 5. Concept Map Export

Endpoint:

```text
POST /v2/course-packs/concept-map/export
```

Request:

```json
{
  "pack_id": "pack_d49edce9d8c487cd",
  "output_root": "outputs/manual_course_pack_11week_api",
  "max_nodes": 60,
  "max_edges": 120
}
```

Verified local result:

```json
{
  "node_count": 121,
  "edge_count": 1019,
  "exported_node_count": 60,
  "exported_edge_count": 120,
  "mermaid_path": "outputs/manual_course_pack_11week_api/course_packs/pack_d49edce9d8c487cd/concept_map.mmd",
  "html_path": "outputs/manual_course_pack_11week_api/course_packs/pack_d49edce9d8c487cd/concept_map.html"
}
```

The export keeps the full `graph.json` while limiting Mermaid/HTML output by default so the visual map stays readable.

## 6. Artifact Preview

Endpoint:

```text
GET /v2/course-packs/{pack_id}/artifacts
```

Query parameters:

```text
output_root=outputs/manual_course_pack_11week_api
include_content=false
```

Verified local result:

```json
{
  "artifact_keys": [
    "course_pack",
    "summary",
    "study_kit",
    "audio_script",
    "graph",
    "chunks",
    "concept_map_mermaid",
    "concept_map_html"
  ],
  "answers": 3,
  "warnings": []
}
```

Use `include_content=true` in Swagger when you want to inspect the JSON payloads directly.

## Output Artifacts

```text
outputs/manual_course_pack_11week_api/course_packs/pack_d49edce9d8c487cd/
- course_pack.json
- chunks.json
- graph.json
- summary.json
- study_kit.json
- audio_script.json
- answers/
```

## Portfolio Point

CourseBee v2 is not positioned as a generic GraphRAG clone. The main product is Course Pack based learning AI:

```text
multiple lecture files
-> Course Pack
-> source-grounded RAG
-> Summary / Q&A / Study Kit / Audio Script
-> GraphRAG-lite Concept Map
```

GraphRAG-lite is used as a supporting feature for concept relationships across lecture files, while source-grounded RAG and citation metadata remain the core reliability layer.

