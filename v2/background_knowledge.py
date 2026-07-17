from __future__ import annotations

from dataclasses import dataclass

from v2.schemas import Chunk


@dataclass(frozen=True)
class BackgroundItem:
    key: str
    title: str
    terms: tuple[str, ...]
    text: str


BACKGROUND_ITEMS = [
    BackgroundItem(
        key="bpe_oov",
        title="Background: BPE and OOV",
        terms=("bpe", "oov", "subword", "token", "tokenization", "vocabulary", "unknown"),
        text=(
            "BPE(Byte Pair Encoding)는 단어를 문자 또는 subword 단위에서 시작해 자주 함께 등장하는 쌍을 반복적으로 병합하는 토큰화 방법이다. "
            "word-level vocabulary만 쓰면 학습 데이터에 없던 단어가 unknown token으로 처리될 수 있는데, BPE는 단어를 여러 subword 조각으로 표현해 OOV 문제를 줄인다. "
            "예를 들어 lower, lowest, newer는 low, er, est 같은 조각을 공유할 수 있고, 모델은 처음 보는 단어도 이미 알고 있는 조각의 조합으로 다룰 수 있다. "
            "이 방식의 핵심 trade-off는 vocabulary 크기와 표현력이다. vocabulary가 너무 작으면 단어가 지나치게 잘게 쪼개져 의미 단위가 약해지고, 너무 크면 희귀 단어와 메모리 부담이 늘어난다. "
            "팟캐스트에서는 BPE를 '모르는 단어를 통째로 포기하지 않고, 아는 조각으로 다시 읽는 방법'이라고 풀어 설명하면 청자가 이해하기 쉽다."
        ),
    ),
    BackgroundItem(
        key="sequence_rnn_lstm",
        title="Background: RNN and LSTM",
        terms=("rnn", "lstm", "sequence", "hidden", "gate", "vanishing", "context"),
        text=(
            "RNN은 문장처럼 순서가 중요한 데이터를 앞에서 뒤로 읽으며 hidden state에 이전 정보를 담아 다음 step으로 넘기는 구조다. "
            "이 구조는 sequence modeling에 자연스럽지만, 문장이 길어질수록 앞쪽 정보가 뒤쪽까지 안정적으로 전달되지 않는 gradient vanishing 문제가 생길 수 있다. "
            "LSTM은 input gate, forget gate, output gate와 cell state를 사용해 어떤 정보는 보존하고 어떤 정보는 잊도록 설계된 RNN 계열 모델이다. "
            "그래서 기본 RNN보다 긴 의존 관계를 다루는 데 유리하며, 문장 앞부분의 단서가 뒤쪽 의미 해석에 영향을 주는 경우를 설명할 때 좋은 예시가 된다. "
            "BPE가 입력 단어를 안정적인 조각으로 만들어 준다면, RNN과 LSTM은 그 조각들이 시간 순서 속에서 어떤 흐름을 만드는지 따라가는 역할을 한다."
        ),
    ),
    BackgroundItem(
        key="cnn_text",
        title="Background: CNN for Text Classification",
        terms=("cnn", "convolution", "filter", "pooling", "n-gram", "classification", "pattern"),
        text=(
            "CNN은 이미지뿐 아니라 텍스트에서도 사용할 수 있다. 텍스트 CNN은 인접한 토큰 묶음, 즉 n-gram처럼 보이는 지역 패턴을 convolution filter로 포착한다. "
            "여러 filter는 서로 다른 길이와 종류의 표현을 잡아내고, pooling은 그중 중요한 특징을 압축해 분류기에 전달한다. "
            "RNN과 LSTM이 순차적 흐름을 따라가며 문맥을 모델링하는 데 강점이 있다면, CNN은 특정 표현이나 지역 패턴이 등장했는지를 빠르게 잡아내는 데 강점이 있다. "
            "텍스트 분류에서는 문장 전체를 한 단어씩 길게 따라가기보다, 분류에 중요한 표현 조합을 빠르게 찾는 것이 효과적일 때가 많다. "
            "따라서 BPE로 입력을 subword 단위로 안정화한 뒤 CNN이 지역 패턴을 추출하는 흐름은 NLP pipeline을 설명하기 좋은 연결 구조다."
        ),
    ),
    BackgroundItem(
        key="nlp_pipeline",
        title="Background: NLP Pipeline Flow",
        terms=("nlp", "pipeline", "embedding", "model", "task", "text classification", "sequence"),
        text=(
            "자연어처리 pipeline은 보통 원문 텍스트를 토큰화하고, 토큰을 숫자 표현으로 바꾼 다음, 모델이 task에 맞는 패턴을 학습하는 흐름으로 이해할 수 있다. "
            "이때 tokenization은 단순한 전처리가 아니라 모델이 세상을 어떤 단위로 읽을지 정하는 단계다. "
            "BPE는 입력 표현을 안정화하고 OOV를 줄이는 역할을 하며, RNN/LSTM/CNN은 그 입력을 사용해 sequence modeling이나 text classification 같은 작업을 수행한다. "
            "팟캐스트 대본에서는 이 흐름을 '글자를 읽을 단위 정하기, 순서를 따라가기, 중요한 패턴 찾기, 최종 task 풀기'로 나누면 자연스럽다. "
            "이 연결 관계를 잡아주면 BPE, RNN, LSTM, CNN이 따로 떨어진 용어가 아니라 하나의 학습 흐름으로 들린다."
        ),
    ),
]


BACKGROUND_SCOPE_VALUES = {"course_pack_plus_background", "external_rag", "background"}


def background_chunks_for_query(query: str, source_chunks: list[Chunk], max_items: int = 4) -> list[Chunk]:
    haystack = " ".join([query, *(chunk.text for chunk in source_chunks)]).lower()
    scored = []
    for item in BACKGROUND_ITEMS:
        score = sum(1 for term in item.terms if term.lower() in haystack)
        if score:
            scored.append((score, item))
    if not scored:
        scored = [(1, item) for item in BACKGROUND_ITEMS]
    scored.sort(key=lambda pair: (-pair[0], pair[1].key))
    return [_chunk_from_item(item, index + 1) for index, (_, item) in enumerate(scored[:max_items])]


def _chunk_from_item(item: BackgroundItem, index: int) -> Chunk:
    text = f"{item.title}\n{item.text}"
    return Chunk(
        chunk_id=f"bg_{item.key}",
        page=index,
        text=text,
        char_start=0,
        char_end=len(text),
        metadata={
            "parser": "background",
            "doc_id": f"background_{item.key}",
            "filename": "background_nlp_reference.md",
            "source_type": "background_knowledge",
            "title": item.title,
        },
    )
