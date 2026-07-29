# COURSEBee v2 Course Pack 케이스 스터디

이 문서는 COURSEBee v2 Course Pack 데모를 포트폴리오/면접에서 설명하기 좋도록 정리한 한국어 버전이다. 단순히 어떤 기능을 만들었는지가 아니라, 기존 구조에서 어떤 문제가 있었고, 왜 Course Pack 구조가 필요했으며, GraphRAG-lite와 LLM orchestration을 어떤 범위에서 적용했는지를 중심으로 설명한다.

## 1. Architecture Diagram

![COURSEBee v2 Architecture](images/coursebee-v2-architecture.png)

핵심 변화는 COURSEBee가 더 이상 파일 하나를 독립적인 PDF로만 다루지 않는다는 점이다. 여러 강의자료를 하나의 `pack_id` 아래에 묶고, Q&A, 요약, Study Kit, Concept Map, Podcast Script, TTS 결과물이 모두 같은 Course Pack artifact로 관리되도록 확장했다.

## 2. 대표 입력

고정 데모 입력은 NLP 11주차 강의자료 3개다.

```text
NLP 11주차 1차시
NLP 11주차 2차시
NLP 11주차 3차시
```

로컬 데모에서는 아래 Course Pack으로 관리된다.

```text
outputs/course_packs/pack_static_nlp_11week_demo/
```

각 chunk는 단순 텍스트 조각이 아니라, 문서와 강의 단위의 source metadata를 함께 가진다.

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

이 메타데이터가 v2 설계의 핵심이다. 답변이 그럴듯하게 생성되는 것만으로는 부족하고, 어떤 강의자료의 어떤 페이지와 chunk가 근거였는지 추적할 수 있어야 한다.

## 3. 대표 출력

Demo Course Pack:

- pack_id: `pack_static_nlp_11week_demo`
- inputs: NLP 11주차 1~3차시
- artifacts: Q&A, Study Kit, Concept Map, Podcast Script, Edge TTS mp3

데모에서 보여줄 수 있는 대표 출력은 네 가지다. 단순히 파일 경로만 나열하기보다, 실제 결과가 어떤 형태로 나오는지 바로 확인할 수 있도록 샘플을 함께 정리했다.

### 3.1 Q&A

Course Pack 질문은 일반 vector retrieval 또는 graph-augmented `local_graph` 모드로 처리할 수 있다.

예시 요청:

```json
{
  "pack_id": "pack_static_nlp_11week_demo",
  "question": "BPE와 OOV는 어떤 관계야?",
  "mode": "local_graph"
}
```

예시 출력:

```json
{
  "answer": "BPE는 OOV 문제를 줄이기 위해 단어를 통째로 unknown 처리하지 않고 subword 조각으로 나누는 토큰화 방식입니다. 예를 들어 lower, lowest, newer 같은 단어는 low, er, est 같은 조각을 공유할 수 있고, 모델은 처음 보는 단어도 이미 알고 있는 조각의 조합으로 처리할 수 있습니다.",
  "sources": [
    {
      "doc_id": "doc_week11_1",
      "filename": "자연어처리_11주차_1차시.pptx",
      "week": 11,
      "lecture_no": 1,
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
  ]
}
```

동작 흐름은 다음과 같다.

1. 질문에서 `BPE`, `OOV` 같은 entity를 찾는다.
2. 해당 entity와 관련된 concept graph edge를 검색한다.
3. graph edge에 연결된 evidence chunk를 가져온다.
4. 가져온 근거를 바탕으로 source-grounded answer를 생성한다.

중요한 점은 concept graph가 단순히 보여주는 artifact에 머물지 않고 retrieval 과정에 직접 참여한다는 것이다.

### 3.2 Study Kit

Study Kit은 일반 요약문이 아니라 학습 보조 자료에 가깝게 구성했다.

예시 출력:

```json
{
  "overview": "11주차 Course Pack은 BPE/OOV 문제에서 시작해 RNN, LSTM, CNN이 자연어처리 pipeline 안에서 어떤 역할을 하는지 연결해 설명합니다.",
  "lecture_summaries": [
    {
      "lecture_no": 1,
      "summary": "BPE와 OOV 문제, subword tokenization의 필요성을 다룹니다.",
      "sources": [{"filename": "자연어처리_11주차_1차시.pptx", "page": 3}]
    },
    {
      "lecture_no": 2,
      "summary": "RNN과 LSTM이 sequence를 처리하는 방식과 장기 의존성 문제를 설명합니다.",
      "sources": [{"filename": "자연어처리_11주차_2차시.pptx", "page": 2}]
    },
    {
      "lecture_no": 3,
      "summary": "CNN이 텍스트 분류에서 local pattern을 포착하는 방식을 설명합니다.",
      "sources": [{"filename": "자연어처리_11주차_3차시.pptx", "page": 1}]
    }
  ],
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

이 구조를 통해 사용자는 단순히 “요약”을 받는 것이 아니라, 여러 강의자료를 복습할 수 있는 Course Pack artifact를 받게 된다.

### 3.3 Concept Map

Concept Map은 document node, concept node, evidence-backed edge를 포함한다. NLP 데모에서 주요 개념은 다음과 같다.

```text
BPE, OOV, Tokenizer, subword, RNN, LSTM, CNN
```

예시 graph edge:

```json
{
  "source": "BPE",
  "target": "OOV",
  "relation": "reduces",
  "evidence": [
    {
      "doc_id": "doc_week11_1",
      "filename": "자연어처리_11주차_1차시.pptx",
      "week": 11,
      "lecture_no": 1,
      "page": 3,
      "chunk_id": "p3_c1"
    }
  ]
}
```

이 map은 두 가지 역할을 한다.

1. 강의 구조를 이해하기 위한 시각화 artifact
2. `local_graph` 질문에 사용할 graph retrieval context

따라서 concept map은 장식용 시각화가 아니라 retrieval에도 쓰이는 데이터 구조가 된다.

### 3.4 Podcast Script / TTS

가장 눈에 잘 보이는 데모 산출물은 팟캐스트 대본과 TTS 음성 파일이다.

Podcast script 샘플:

```text
HOST: 오늘 이야기의 출발점은 자료의 이 문장입니다. 자연어처리 pipeline은 원문을 토큰화하고 숫자 표현으로 바꾼 다음, 모델이 task에 맞는 패턴을 학습하는 흐름입니다.

GUEST: 자료에 따르면 BPE는 단어를 subword 조각으로 표현해 OOV 문제를 줄입니다. 이 설명을 기준으로 다음 모델 단계와의 연결을 살펴보겠습니다.
```

TTS 결과:

- podcast script: [coursebee-audio-overview-transcript.txt](demo-assets/coursebee-audio-overview-transcript.txt)
- Qwen 원본 / 최종 대본: 4,878자 / 6,003자
- 발화: 38개, grounding 검사 대상 35개
- 근거 검증: 35/35 통과, unsupported 0개, source-grounded repair 16개
- Edge TTS mp3: [coursebee-audio-overview.mp3](demo-assets/coursebee-audio-overview.mp3)
- segment별 검증 내역: [coursebee-audio-overview-grounding.json](demo-assets/coursebee-audio-overview-grounding.json)
- 실제 재생 길이: 13분 9초

<audio controls src="demo-assets/coursebee-audio-overview.mp3"></audio>

이 과정에서 문자 수와 실제 TTS 재생 시간이 정확히 일치하지 않는다는 점도 확인했다. 실제 제품에서 정확한 재생 시간을 맞추려면 TTS 결과를 측정하고 대본을 다시 줄이거나 늘리는 피드백 루프가 필요하다.

## 4. 비교표

| 영역 | v1 / 초기 방식 | v2 Course Pack 방식 | 의미 |
|---|---|---|---|
| 입력 단위 | 단일 PDF | 여러 문서를 묶은 Course Pack | 학생은 보통 여러 차시를 하나의 학습 단위로 복습한다. |
| 출처 추적 | 단일 문서의 page/chunk 근거 | `doc_id`, filename, week, lecture_no, page, chunk | 여러 파일을 참고한 답변도 추적 가능하다. |
| Retrieval | 기본 vector retrieval | vector retrieval + `local_graph` | 무거운 GraphRAG stack 없이 graph-augmented retrieval을 구현했다. |
| Concept Map | 주로 시각화 | 시각화 + evidence 기반 graph retrieval | graph가 장식이 아니라 검색에 참여한다. |
| Summary | 일반 요약 | overview, lecture summaries, connections, concepts, questions, flashcards | 학습용 artifact에 가까워졌다. |
| Podcast 생성 | one-shot prompt | outline -> scene generation -> repair | 긴 대본 생성의 실패 패턴을 줄였다. |
| LLM 구성 | mock/rule/local 중심 | Ollama provider + Qwen/Gemma 비교 | 로컬 모델의 품질/비용/제약을 직접 비교했다. |
| TTS | 대본 생성 또는 수동 테스트 | Edge TTS mp3/subtitle artifact | 텍스트 결과를 실제 오디오 산출물로 연결했다. |

## 5. 발견한 문제와 해결 과정

### 5.1 Multi-document RAG에는 더 강한 provenance가 필요했다

단일 PDF에서는 page와 chunk만 있어도 어느 정도 출처 추적이 가능하다. 하지만 Course Pack에서는 여러 강의파일이 섞이기 때문에, 답변이 어느 파일, 어느 주차, 어느 차시, 어느 페이지에서 왔는지 추적할 수 있어야 한다.

이를 해결하기 위해 ingestion 단계에서 chunk에 `doc_id`, `filename`, `week`, `lecture_no`, `page`, `chunk_id`를 보존하도록 했다. 이 메타데이터는 Q&A, summary, study kit, concept map, audio script artifact까지 이어진다.

### 5.2 Concept Map이 있다고 해서 바로 GraphRAG는 아니었다

초기 concept map은 개념 관계를 보여주는 시각화에 가까웠다. 하지만 GraphRAG라고 말하려면 graph가 retrieval 과정에 실제로 참여해야 한다고 판단했다.

그래서 `local_graph` 모드를 추가했다. 질문에서 entity를 찾고, graph edge를 검색하고, edge evidence chunk를 가져와 답변에 활용한다. 이 구조는 full Microsoft GraphRAG는 아니지만, 가볍고 설명 가능한 GraphRAG-lite라고 볼 수 있다.

의도적으로 GraphRAG-lite라고 부른다. full GraphRAG라고 과장하기보다, 현재 범위에서는 lightweight graph-augmented retrieval이라고 설명하는 편이 더 정확하고 신뢰감 있다.

### 5.3 긴 팟캐스트 대본 생성은 one-shot으로 잘 되지 않았다

가장 많은 시행착오가 있었던 부분은 팟캐스트 대본 생성이다. LLM에 한 번에 “5분 대본을 만들어줘”라고 요청했을 때 여러 문제가 생겼다.

- 요청한 시간보다 훨씬 짧게 끝남
- 요약문처럼 딱딱하게 나옴
- `질문 -> 답 -> 질문 -> 답` 형태의 면접식 대화로 수렴함
- 작은 모델은 템플릿 placeholder를 그대로 복사함
- 큰 모델도 정확도는 좋아졌지만 길이 제어는 여전히 불안정함

이 문제를 해결하기 위해 generation을 작은 orchestration pipeline으로 나눴다.

```text
outline -> scene generation -> length repair -> segment grounding repair -> TTS
```

각 단계의 역할을 분리하니 디버깅이 쉬워졌고, 대본의 길이와 구조도 더 안정화됐다.

### 5.4 모델 크기만 키운다고 해결되지는 않았다

같은 Course Pack task로 여러 로컬 모델을 비교했다.

| 모델 | 관찰 결과 |
|---|---|
| `gemma2:2b` | 너무 작아서 placeholder를 그대로 복사하거나 podcast 형식을 잘 지키지 못함 |
| `gemma2:9b` | 형식은 나아졌지만 짧고 딱딱한 교육문답 느낌 |
| `qwen3:8b` | 길이와 내용량은 괜찮았지만 짧은 Q&A turn이 너무 많음 |
| `qwen3:14b` | 정확도는 좋아졌지만 one-shot 생성은 여전히 짧게 끝남 |
| `qwen3:14b` staged | 현재 가장 좋은 균형: 길이, 구조, artifact 품질이 모두 개선됨 |

실제 교훈은 단순히 더 큰 모델을 쓰는 것보다, 모델의 실패 패턴을 관찰하고 workflow를 나누는 것이 더 중요하다는 점이다.

### 5.5 TTS 재생 시간은 문자 수만으로 예측하기 어려웠다

공개 최종 대본은 6,003자였지만 Edge TTS 실측 결과는 13분 9초였다. 즉 “6,000자면 몇 분” 같은 단순 계산은 실제 음성 합성과 맞지 않을 수 있다.

정확한 오디오 길이를 맞추려면 다음과 같은 루프가 필요하다.

```text
target duration -> script length estimate -> TTS synthesize -> subtitle end time 측정 -> shorten/expand
```

## 6. 솔직한 한계

현재 구현은 의도적으로 lightweight하다.

- full GraphRAG가 아니라 concept edge와 evidence chunk를 활용하는 graph-augmented local retrieval이다.
- background knowledge는 팟캐스트 흐름을 풍부하게 하지만, lecture source evidence와 분리해 표시할 필요가 있다.
- 로컬 모델 품질 편차가 크다. 모델 크기만으로 품질이 보장되지 않는다.
- lexical grounding guard는 출처 단어 중첩을 재현 가능하게 검사하지만 semantic entailment나 사람의 청취 품질을 대신하지는 않는다.
- source-grounded repair의 문형 반복은 줄였지만, 장편 전체의 concept repetition은 사람 평가와 추가 duplicate-removal로 더 개선할 수 있다.
- Edge TTS는 무료 데모에는 유용하지만, 실제 제품에서는 voice separation, retry, duration control이 더 필요하다.
- 전체 실행 산출물은 `outputs/`에 두되, 공개 synthetic 자료로 검증한 MP3·대본·grounding JSON만 `docs/demo-assets/`에 고정했다.

## 7. 포트폴리오용 한 줄 설명

> COURSEBee v2는 단일 PDF RAG 도구를 여러 강의자료 기반 Course Pack 학습 시스템으로 확장한 프로젝트입니다. 각 chunk의 출처 메타데이터를 유지해 source-grounded Q&A와 Study Kit을 생성하고, concept graph를 retrieval에 활용하는 GraphRAG-lite 모드와 staged podcast generation pipeline을 구현했습니다.

이 프로젝트에서 보여주고 싶은 역량은 세 가지다.

1. multi-document provenance를 고려한 source-grounded RAG 설계
2. full GraphRAG를 과장하지 않고, 필요한 범위에서 직접 구현한 lightweight graph-augmented retrieval
3. LLM의 실제 실패 패턴을 관찰하고 `outline -> scene generation -> repair -> TTS`로 분해한 generation orchestration 설계


