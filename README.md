# CourseBee v2

CourseBee v2는 단일 PDF RAG 도구였던 BeePDF를 여러 강의자료 기반 Course Pack 학습 시스템으로 확장한 프로젝트입니다.

CourseBee는 여러 차시의 Learning Materials를 하나의 `Course Pack`으로 묶고, source metadata를 유지한 상태에서 Q&A, Study Kit, Concept Map, Podcast Script, TTS artifact를 생성하는 AI 학습 콘텐츠 생성 시스템입니다.

![CourseBee v2 Architecture](images/coursebee-v2-architecture.png)

## Why CourseBee?

기존 단일 PDF RAG는 문서 하나 안의 질문에는 대응하기 쉽지만, 실제 강의 복습처럼 여러 차시 자료를 하나의 학습 단위로 묶어 이해하는 데는 한계가 있습니다.

CourseBee v2는 여러 강의자료를 하나의 Course Pack으로 묶고, 각 chunk에 `doc_id`, `filename`, `week`, `lecture_no`, `page`, `chunk_id`를 보존합니다. 이를 통해 답변과 학습 자료가 어떤 강의자료의 어떤 부분을 근거로 했는지 추적할 수 있습니다.

CourseBee의 graph 기능은 Course Pack 내부의 concept graph와 evidence chunk를 활용해 관계형 질문의 검색 근거를 보강하는 Concept Graph-assisted Retrieval입니다. 고급 graph indexing 제품을 흉내 내기보다, 강의 개념 관계를 검색 context로 쓰는 좁고 설명 가능한 범위에 집중했습니다.

## Retrieval Strategy

CourseBee v2 separates the dependency-free local retriever from the optional semantic retrieval path.

Local demo에서는 `HybridRetriever`를 기본으로 사용합니다. TF-IDF 계열 lexical score에 한국어 조사 정규화와 한글 character n-gram 유사도를 결합하고, 영어는 정확한 어휘 일치만 사용해 철자가 비슷한 무관 용어의 거짓 양성을 줄였습니다. 이 경로는 embedding 모델 없이도 설명 가능하고 재현 가능합니다.

선택형 AI path에서는 multilingual E5 bi-encoder 검색, lexical+dense RRF 결합, 다국어 Cross-Encoder reranking을 실제 Course Pack API에서 실행할 수 있습니다. 모델은 semantic 모드를 처음 호출할 때만 로드되고 이후 요청에서는 모델과 document embedding cache를 재사용합니다.

```text
RetrieverProvider
├─ LexicalRetriever      # exact lexical baseline
├─ HybridRetriever       # current local default: lexical + Korean character features
├─ EmbeddingRetriever    # multilingual E5 dense retrieval
└─ SemanticHybridRetriever
   ├─ RRF                # lexical + dense rank fusion
   └─ Cross-Encoder      # optional top-candidate reranking
```

`mode="semantic"`, `mode="semantic_hybrid"`, `mode="semantic_rerank"`로 각 단계를 비교할 수 있습니다. 모델이 없거나 실행에 실패하면 기존 local hybrid로 돌아가고, 실제 실행 경로와 fallback 여부를 `retrieval_details`와 `trace.retrieval_debug`에 남깁니다.
## Key Features

- Multi-document Course Pack ingestion
- Source-grounded Q&A
- Grounded-first Web RAG fallback with cited Wikipedia extracts and URLs
- Multi-turn SSE chat with token streaming, cancellation, and source-aware follow-ups
- Korean-aware local hybrid retriever and optional E5 + RRF + Cross-Encoder path
- Browser file upload for PDF, PPTX, Markdown, and text Course Packs
- Query-type Retrieval Router via `mode="auto"`
- Multi-level Summary Retrieval for global overview questions
- Concept Graph-assisted Retrieval via `local_graph`
- Study Kit generation
- Concept Map generation
- Staged Podcast Script generation: `outline -> scene generation -> repair`
- Edge TTS artifact generation
- Evaluation harness for router accuracy, source recall, citation coverage, graph usefulness, and fallback behavior
- Robustness evaluation for OCR noise, source conflicts, cross-document evidence, distractors, and abstention
- Optional API-key boundary, request IDs, upload signatures and limits, and path validation
- GitHub Actions CI, isolated wheel verification, and non-root Docker/Compose runtime

## Demo Course Pack

- `pack_id`: `pack_static_nlp_11week_demo`
- Input: bundled synthetic NLP 11주차 1~3차시 fixtures
- Output: Q&A, Study Kit, Concept Map, Podcast Script, Edge TTS mp3

`/demo`를 처음 열면 공개 가능한 합성 fixture로 이 Course Pack을 자동 생성합니다. 사용자는 화면의 `Add Source`에서 자신의 PDF, PPTX, Markdown, TXT 자료를 올려 별도 Course Pack으로 전환할 수 있습니다.

mp3 같은 생성 artifact는 Course Pack 범위의 파일 API를 통해 제공하며, 로컬 데이터 루트 밖의 경로는 노출하지 않습니다.

## Operations Surface

CourseBee exposes a small operations surface so long-running Course Pack ingestion and RAG decisions can be inspected.

```text
POST /v2/course-packs/jobs
POST /v2/course-packs/upload
GET  /v2/course-packs
GET  /v2/course-packs/jobs/{job_id}
GET  /v2/course-packs/{pack_id}
GET  /health
GET  /ready
```

Local jobs are file-backed. By default they can run inline for tests and demos, and with `run_async: true` they are scheduled through FastAPI background tasks while exposing production-shaped state:

```json
{
  "job_id": "job_20260629_001",
  "status": "queued | running | succeeded | failed",
  "stage": "completed",
  "progress": 1.0,
  "processed_documents": 3,
  "total_documents": 3,
  "warnings": []
}
```

Course Pack answers also include `trace` with `request_id`, stage latencies, and retrieval debug information such as candidate chunks, selected chunks, graph edges, and fallback usage.

## Reliability Layer

CourseBee does not simply generate study content. Every generated artifact keeps source metadata, and API-refined summaries must pass `citation_check`. If generated text introduces unsupported terms, the system falls back to rule-based grounded output.

Citation quality checks include:

- source coverage
- unsupported claim detection
- source/chunk hover preview through artifact metadata
- answer sentence to supporting chunk mapping through preserved `sources`

`check_text_grounding` compares generated claim terms with source chunk terms and returns `coverage`, `matched_terms`, `unsupported_terms`, and warnings. This keeps generated Q&A, Study Kit, Concept Map, Podcast Script, and Summary artifacts tied back to Course Pack evidence.

## Evaluation Snapshot

The evaluation harness uses a public synthetic NLP 11-week Course Pack fixture, so it can be run without private lecture materials.

```bash
python eval/run_eval.py
```

| Metric | Result |
| --- | --- |
| Overall pass rate | 10 / 10 |
| Router accuracy | 10 / 10 |
| Source recall@5 | 9 / 9 required-source cases |
| Citation coverage | 0.90 |
| No-context fallback pass | 1 / 1 |
| Graph route useful cases | 4 / 4 |

Latest report: [eval/results/latest_eval.md](eval/results/latest_eval.md)

The generalization suite also runs six fact/relation cases across biology, economics, and software engineering.

| Metric | Result |
| --- | --- |
| Overall pass rate | 6 / 6 |
| Router accuracy | 6 / 6 |
| Required source recall | 6 / 6 |
| Citation coverage | 6 / 6 |
| Graph evidence usefulness | 3 / 3 |

Latest report: [eval/results/latest_generalization_eval.md](eval/results/latest_generalization_eval.md)

The robustness suite covers OCR line-break noise, conflicting source versions, cross-document evidence, distractors, and unsupported questions.

| Metric | Result |
| --- | --- |
| Overall pass rate | 5 / 5 |
| Source recall and precision | 5 / 5 |
| Graph evidence checks | 2 / 2 |
| Abstention checks | 1 / 1 |

Latest report: [eval/results/latest_robustness_eval.md](eval/results/latest_robustness_eval.md)

The optional semantic benchmark compares paraphrased and cross-lingual retrieval against the local baseline.

```bash
pip install -e ".[semantic]"
python eval/run_semantic_retrieval_eval.py
```

| Mode | Recall@3 | MRR | Mean warm latency |
| --- | ---: | ---: | ---: |
| Local hybrid | 0.17 | 0.167 | 2.29 ms |
| E5 + RRF | 1.00 | 0.917 | 9.09 ms |
| E5 + RRF + Cross-Encoder | 1.00 | 1.000 | 12.03 ms |

This six-case synthetic suite measures retrieval ranking rather than answer quality. Warm latency is machine-dependent; the versioned report records the latest local run. Latest report: [eval/results/latest_semantic_retrieval_eval.md](eval/results/latest_semantic_retrieval_eval.md)

Set `COURSEBEE_INSTALL_SEMANTIC=true` before `docker compose build` to include the optional CPU-only model runtime in a container. Model weights remain lazy downloads; the default image stays lightweight and uses visible local fallback for semantic requests.

## Representative Outputs

### Source-grounded Q&A

```json
{
  "question": "BPE와 OOV는 어떤 관계야?",
  "mode": "local_graph",
  "answer": "BPE는 OOV 문제를 줄이기 위해 단어를 통째로 unknown 처리하지 않고 subword 조각으로 나누는 토큰화 방식입니다.",
  "sources": [
    {
      "doc_id": "doc_week11_1",
      "filename": "자연어처리_11주차_1차시.pptx",
      "page": 3,
      "chunk_id": "p3_c1"
    }
  ],
  "graph_context": [
    {
      "source": "BPE",
      "target": "OOV",
      "relation": "reduces",
      "evidence_chunk_id": "p3_c1"
    }
  ],
  "matched_entities": ["BPE", "OOV"],
  "traversal_strategy": "edge"
}
```

### Query-type Retrieval Router

```json
{
  "question": "RNN, LSTM, CNN은 NLP pipeline에서 어떻게 연결돼?",
  "mode": "auto",
  "question_type": "relation_question",
  "routed_mode": "local_graph",
  "retrieval_plan": [
    {"level": "high", "strategy": "course_graph"},
    {"level": "low", "strategy": "evidence_chunks"}
  ]
}
```

### Concept Graph-assisted Retrieval

```json
{
  "question": "BPE를 이해하려면 먼저 뭘 알아야 해?",
  "retrieval_mode": "course_graph_path",
  "traversal_strategy": "prerequisite",
  "matched_entities": ["BPE"],
  "graph_paths": [
    {
      "nodes": ["subword tokenization", "BPE"],
      "edges": [{"relation": "prerequisite_of"}]
    }
  ]
}
```

### Multi-level Summary Retrieval

```json
{
  "question": "11주차 전체 흐름 설명해줘",
  "mode": "hierarchical",
  "retrieval_mode": "hierarchical_summary",
  "abstraction_level": "course_pack",
  "selected_summary_nodes": [
    {"type": "course_pack_summary"},
    {"type": "lecture_summary"}
  ],
  "supporting_chunks": [
    {"filename": "자연어처리_11주차_1차시.pptx", "chunk_id": "p3_c1"}
  ]
}
```

### Study Kit

```json
{
  "overview": "11주차 Course Pack은 BPE/OOV 문제에서 시작해 RNN, LSTM, CNN이 자연어처리 pipeline 안에서 어떤 역할을 하는지 연결해 설명합니다.",
  "flashcards": [
    {
      "front": "BPE는 OOV 문제를 어떻게 줄이는가?",
      "back": "단어를 subword 조각으로 나누어 처음 보는 단어도 기존 조각의 조합으로 처리하게 한다."
    }
  ],
  "expected_questions": [
    "BPE와 word-level tokenization의 차이는 무엇인가?",
    "RNN/LSTM과 CNN은 텍스트를 보는 방식이 어떻게 다른가?"
  ]
}
```

### Podcast Script

```text
HOST: 오늘은 NLP의 복잡한 용어들이 하나의 퍼즐처럼 연결되어 있다는 걸 알아보는 시간이에요.

GUEST: BPE, OOV, RNN, LSTM, CNN 같은 용어들이 각각 다른 분야처럼 보이지만, 사실은 AI가 텍스트를 읽는 과정에서 서로 연결된 단계를 이루고 있어요.
```

## Implementation Status

```text
Status
- Local demo: implemented
- Source-grounded artifacts: implemented
- Citation / grounding check: implemented for API-refined summaries
- Course Pack job API: implemented locally
- Answer trace / retrieval debug: implemented
- Concept graph-assisted retrieval: implemented
- Retrieval evaluation harness: implemented
- Multi-domain generalization evaluation: implemented
- OCR/conflict/distractor robustness evaluation: implemented
- Upload validation, optional API key, and atomic artifact writes: implemented
- Packaged demo assets and isolated wheel install: implemented
- GitHub Actions CI and non-root Docker runtime smoke test: implemented
- Production vector DB: planned
- Async ingestion background task: implemented locally
- Production worker queue and durable database/object storage: planned
```

The current repository is intentionally local-first. Mock/rule providers make the demo reproducible without paid services, while provider interfaces define the production upgrade path.

## v1 vs v2

| Area | v1 BeePDF | CourseBee v2 |
| --- | --- | --- |
| Main unit | Single PDF | Multi-document Course Pack |
| Goal | PDF-to-audio / document QA | Learning content generation from multiple lecture materials |
| Retrieval | Single-document RAG | Auto-routed chunk, multi-level summary, and concept graph-assisted retrieval across Course Pack sources |
| Graph | None or visualization-focused | Concept graph-assisted retrieval using concept edges and evidence chunks |
| Output | Script / TTS centered | Q&A, Study Kit, Concept Map, Podcast Script, TTS artifact |
| Generation | Mostly one-shot | Staged orchestration: `outline -> scene generation -> repair` |
| Provenance | Page/chunk-level within one file | `doc_id`, filename, week, lecture_no, page, chunk_id across files |

## Quick Start

```bash
python -m venv .venv
pip install -e ".[pdf,tts,dev]"
coursebee --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/demo
http://127.0.0.1:8000/ready
```

The demo Course Pack is seeded automatically. Upload a new Course Pack with `Add Source`, or run the same app in a container:

```bash
docker compose up --build
```

Set `COURSEBEE_API_KEY` to require `X-API-Key` on `/v2/*`; leave it empty for the same-origin local browser demo. See [.env.example](.env.example) for data-root and upload limits.

Example API call:

```bash
curl -X POST http://127.0.0.1:8000/v2/course-packs/ask \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "pack_static_nlp_11week_demo",
    "question": "BPE와 OOV는 어떤 관계야?",
    "mode": "local_graph"
  }'
```

## Expected Endpoints

- `POST /v2/documents/ingest`
- `POST /v2/ask`
- `POST /v2/study-kit`
- `POST /v2/audio-script`
- `POST /v2/concept-map`
- `POST /v2/course-packs/jobs`
- `POST /v2/course-packs/upload`
- `GET /v2/course-packs`
- `GET /v2/course-packs/jobs/{job_id}`
- `GET /v2/course-packs/{pack_id}`
- `POST /v2/course-packs/ask`
- `POST /v2/course-packs/study-kit`
- `POST /v2/course-packs/summary`
- `POST /v2/course-packs/audio-script`
- `POST /v2/course-packs/tts`
- `POST /v2/course-packs/concept-map`
- `POST /v2/course-packs/mindmap`

## Docs

- [CourseBee v2 Case Study](docs/coursebee-v2-case-study.md)
- [CourseBee Demo UI](v2/assets/coursebee_demo_ui.html) - run the server and open `http://127.0.0.1:8000/demo`
- CourseBee demo alias: `http://127.0.0.1:8000/demo-ko` serves the same current UI
- [Architecture](docs/ARCHITECTURE.md)
- [Retrieval Router](docs/LIGHTRAG_ROUTER.md)
- [Multi-level Summary Retrieval](docs/HIERARCHICAL_RETRIEVAL.md)
- [Concept Graph-assisted Retrieval](docs/GRAPH_RAG.md)
- [Concept Graph Retrieval Evaluation](docs/GRAPH_RAG_EVALUATION.md)
- [Evaluation](docs/EVALUATION.md)
- [Citation and Grounding](docs/CITATION_GROUNDING.md)
- [Providers](docs/PROVIDERS.md)
- [Production Readiness](docs/PRODUCTION_READINESS.md)
- [v1 Legacy Overview](docs/V1_LEGACY.md)

More docs: [docs/README.md](docs/README.md)

## Tests

```bash
python -m unittest discover -s tests
python eval/run_eval.py
python eval/run_generalization_eval.py
python eval/run_robustness_eval.py
```
