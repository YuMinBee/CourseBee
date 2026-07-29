# COURSEBee v2 Course Pack Case Study

This note summarizes the work behind the COURSEBee v2 Course Pack demo. It is written as an engineering case study rather than a feature checklist: what problem existed, what changed, what tradeoffs appeared, and how the implementation was validated.

## 1. Architecture Diagram

![COURSEBee v2 Architecture](images/coursebee-v2-architecture.png)

The important shift is that COURSEBee no longer treats each file as an isolated PDF. Multiple lecture files are grouped under one `pack_id`, and each downstream artifact keeps enough metadata to explain where its content came from.

## 2. Representative Input

The fixed demo input is a small multi-document NLP lecture pack:

```text
NLP week 11, lecture 1
NLP week 11, lecture 2
NLP week 11, lecture 3
```

In the local demo, this is represented as:

```text
outputs/course_packs/pack_static_nlp_11week_demo/
```

The pack contains source chunks with document-level and lecture-level metadata such as:

```json
{
  "doc_id": "doc_week11_1",
  "filename": "natural_language_processing_week11_lecture1.pptx",
  "week": 11,
  "lecture_no": 1,
  "page": 3,
  "chunk_id": "p3_c1"
}
```

This metadata is central to the v2 design. The system should not only answer correctly; it should explain which lecture, page, and chunk supported the result.

## 3. Representative Outputs

The demo is designed around four visible outputs.

### 3.1 Q&A

A Course Pack question can use regular vector retrieval or the graph-augmented `local_graph` mode.

Example question:

```json
{
  "pack_id": "pack_static_nlp_11week_demo",
  "question": "How are BPE and OOV related?",
  "mode": "local_graph"
}
```

Expected behavior:

1. Detect entities such as `BPE` and `OOV` from the question.
2. Search concept graph edges related to those entities.
3. Retrieve the evidence chunks attached to the graph edge.
4. Generate a source-grounded answer.

The point is not only to show a graph. The graph participates in retrieval.

### 3.2 Study Kit

The study kit is structured like a learning artifact rather than a plain summary. It includes:

- overview
- lecture-level summaries
- cross-lecture connections
- key concepts
- expected questions
- flashcards
- sources

This makes the output closer to a course companion than a generic RAG answer.

### 3.3 Concept Map

The concept map captures document nodes, concept nodes, and evidence-backed edges. For the NLP demo, the meaningful concepts include:

```text
BPE, OOV, Tokenizer, subword, RNN, LSTM, CNN
```

The map is useful in two ways:

1. As a visual artifact for understanding lecture structure.
2. As retrieval context for `local_graph` questions.

### 3.4 Podcast Script / TTS

The most visible demo artifacts are the [speaker transcript](demo-assets/coursebee-audio-overview-transcript.txt), [grounding trace](demo-assets/coursebee-audio-overview-grounding.json), and [generated MP3](demo-assets/coursebee-audio-overview.mp3).

The public run used Qwen3 14B, expanded 4,878 raw characters to 6,003 grounded characters, and produced 38 turns. The strict lexical guard passed all 35 checked turns, repaired 16, and left zero unsupported turns. The generated Edge TTS file measured 13 minutes 9 seconds. This confirms that character count and real TTS duration do not map perfectly; exact duration needs a synthesize-and-measure feedback loop.

## 4. Comparison Table

| Area | v1 / Earlier approach | v2 Course Pack approach | Why it matters |
|---|---|---|---|
| Input unit | Single PDF | Multi-document Course Pack | Matches how students actually review several lectures together. |
| Source tracking | Page/chunk-level evidence in one document | `doc_id`, filename, week, lecture number, page, chunk | Makes answers auditable across multiple files. |
| Retrieval | Basic vector retrieval | Vector retrieval plus `local_graph` mode | Shows lightweight GraphRAG behavior without a heavy graph stack. |
| Concept map | Mostly visual | Visual plus evidence-backed graph retrieval | The graph becomes operational, not decorative. |
| Summary | Plain summary | Overview, lecture summaries, connections, concepts, questions, flashcards | Produces study-ready artifacts. |
| Podcast generation | One-shot prompt | Outline -> scene generation -> repair | Handles long-form generation failure modes better. |
| LLM setup | Rule/mock/local generation | Ollama provider with Qwen/Gemma model tests | Demonstrates local model tradeoff awareness. |
| TTS | Script only or manual test | Edge TTS artifact and subtitle output | Turns generated text into a user-facing audio artifact. |

## 5. Engineering Problems Found

### 5.1 Multi-document RAG needs stronger provenance

A single PDF answer can cite a page and chunk. A Course Pack answer needs more: which lecture file, which week, which lecture number, and which page. Without this, the answer may be correct but hard to trust.

The fix was to enrich chunks with document and lecture metadata during ingestion and preserve those fields through Q&A, summary, study kit, concept map, and audio script artifacts.

### 5.2 A concept map is not automatically GraphRAG

At first, the concept map was closer to a visualization artifact. That is useful, but not enough to claim graph-augmented retrieval. The `local_graph` mode was added so a question can find entities, search graph edges, pull edge evidence, and use that evidence during answer generation.

This is intentionally called GraphRAG-lite. It is not a full Microsoft GraphRAG implementation. It is a lightweight graph-augmented retrieval path that is explainable and cheap to run locally.

### 5.3 Long podcast generation fails in predictable ways

One-shot LLM generation produced several failure modes:

- scripts were too short even when the prompt asked for 5 or 8 minutes
- the model drifted into summary-note style
- the conversation became repetitive Q&A
- smaller models copied template placeholders literally
- larger models were more accurate but still ended early

The fix was to turn generation into a small orchestration pipeline:

```text
outline -> scene generation -> length repair -> segment grounding repair -> TTS
```

Each step has a narrower job. This made the output longer, more structured, and easier to debug.

### 5.4 Model size alone did not solve quality

Local models were compared through the same Course Pack task:

| Model | Observed behavior |
|---|---|
| `gemma2:2b` | Too small; copied placeholders and failed podcast structure. |
| `gemma2:9b` | Better format, but short and interview-like. |
| `qwen3:8b` | Best early result for length, but produced many short Q&A turns. |
| `qwen3:14b` | More accurate, but one-shot generation still ended early. |
| `qwen3:14b` staged | Best current balance of length, structure, and artifact quality. |

The practical lesson was that prompt orchestration mattered more than simply increasing model size.

### 5.5 TTS duration must be measured, not guessed

The public script had 6,003 characters, but Edge TTS produced 13 minutes 9 seconds of audio. This showed that duration control needs a feedback loop, such as:

```text
target duration -> estimate script length -> synthesize -> measure subtitle end time -> shorten/expand if needed
```

## 6. Honest Limitations

The current implementation is intentionally lightweight.

- It is not full GraphRAG. It is a graph-augmented local retrieval mode using concept edges and evidence chunks.
- Background knowledge can improve podcast flow, but it must be clearly separated from lecture-source evidence.
- Local model quality varies heavily. More parameters do not guarantee better podcast structure.
- The lexical grounding guard is deterministic, but it is not semantic entailment or a human listening-quality score.
- Source-grounded repair reduces unsupported claims, while concept repetition still needs human evaluation and stronger duplicate removal.
- Edge TTS is useful for a free demo, but production use would need clearer voice separation, retry handling, and duration control.
- Full runtime artifacts stay under `outputs/`; only the synthetic, validated MP3, transcript, and grounding trace are versioned under `docs/demo-assets/`.

## 7. Portfolio Framing

The strongest way to describe this work is:

> COURSEBee v2 extends a single-document PDF RAG tool into a multi-document Course Pack system. It preserves source metadata across files, adds a lightweight GraphRAG-style `local_graph` retrieval path, and uses an LLM orchestration pipeline to generate long-form study podcast artifacts from lecture materials.

The implementation shows three practical skills:

1. Source-grounded RAG design with multi-document provenance.
2. Lightweight graph-augmented retrieval without overclaiming full GraphRAG.
3. LLM workflow orchestration for long-form generation and TTS artifacts.
