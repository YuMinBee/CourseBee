"""청크 묶음마다 한 번만 만드는 BM25 인덱스.

이전 구현은 질의마다 모든 청크를 네 번씩 다시 토큰화했다(문서 빈도, 점수, 문구 비교, 문자 n-gram).
청크 1,300개 팩에서 질의 하나에 약 5초가 걸렸다. 여기서는 청크 내용이 같으면 인덱스를 재사용하고,
질의 시점에는 질의만 토큰화한다.

한국어는 Kiwi 형태소 분석으로 조사·어미를 떼어 낸다("에너지가" → "에너지"). kiwipiepy가 없으면
정규식 + 조사 목록 방식으로 동작한다.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass
from functools import lru_cache

from v2.schemas import Chunk

BM25_K1 = 1.2
BM25_B = 0.75
INDEX_CACHE_SIZE = 16
MINIMUM_SCORE = 0.08
CHARACTER_WEIGHT = 0.75
MINIMUM_CHARACTER_SIMILARITY = 0.18
PHRASE_BONUS = 0.3

# 검색어로 쓰는 Kiwi 품사: 일반·고유·의존명사, 수사, 동사·형용사 어간, 어근, 외국어, 숫자, 한자
KIWI_INDEX_TAGS = frozenset({"NNG", "NNP", "NNB", "NR", "VV", "VA", "XR", "SL", "SN", "SH"})
ENGLISH_STOPWORDS = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the",
     "to", "with", "what", "how", "why", "when", "which", "does", "do"}
)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[가-힣]+")
_KOREAN_SUFFIXES = (
    "으로부터",
    "에서부터",
    "이라고",
    "이라는",
    "에서는",
    "에게서",
    "까지는",
    "부터는",
    "입니다",
    "인가요",
    "이라면",
    "처럼",
    "보다",
    "으로",
    "에서",
    "에게",
    "한테",
    "에는",
    "에도",
    "의",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "와",
    "과",
    "에",
    "로",
    "도",
    "만",
)

_KIWI_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()
_INDEX_CACHE: OrderedDict[str, LexicalIndex] = OrderedDict()


def normalize_retrieval_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").replace("­", "")
    normalized = re.sub(r"(?<=[A-Za-z])-[ \t]*\r?\n[ \t]*(?=[A-Za-z])", "", normalized)
    return re.sub(r"(?<=[A-Za-z])-[ \t]+(?=[A-Za-z])", "", normalized)


@lru_cache(maxsize=1)
def _kiwi():
    # COURSEBEE_TOKENIZER=regex: Kiwi 없이 동작 확인·비교 실험용
    if os.environ.get("COURSEBEE_TOKENIZER", "kiwi").lower() == "regex":
        return None
    try:
        from kiwipiepy import Kiwi  # type: ignore[import-not-found]
    except ImportError:
        return None
    return Kiwi()


def tokenizer_name() -> str:
    return "kiwi" if _kiwi() is not None else "regex"


def warm_up() -> str:
    """형태소 분석기 로딩(약 1초)을 첫 질문이 떠안지 않게 서버 시작·지연시간 측정 전에 부른다."""
    tokenize("검색 준비")
    return tokenizer_name()


def tokenize(text: str) -> list[str]:
    """색인·질의 공용 토큰화. 같은 단어가 여러 번 나오면 여러 번 돌려준다(BM25의 단어 빈도)."""
    normalized = normalize_retrieval_text(text)
    kiwi = _kiwi()
    if kiwi is None:
        return _regex_tokens(normalized)
    with _KIWI_LOCK:
        analyzed = kiwi.tokenize(normalized)
    tokens: list[str] = []
    for token in analyzed:
        if token.tag not in KIWI_INDEX_TAGS:
            continue
        form = token.form.lower()
        if token.tag == "SL" and (len(form) < 2 or form in ENGLISH_STOPWORDS):
            continue
        tokens.append(form)
    return tokens


def _regex_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        raw = match.group(0).lower()
        if not contains_hangul(raw):
            if len(raw) >= 2 and raw not in ENGLISH_STOPWORDS:
                tokens.append(raw)
            continue
        stem = _strip_korean_suffix(raw)
        if len(stem) >= 2:
            tokens.append(stem)
        if raw != stem and len(raw) >= 2:
            tokens.append(raw)
    return tokens


def _strip_korean_suffix(token: str) -> str:
    for suffix in _KOREAN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)]
    return token


def contains_hangul(text: str) -> bool:
    return any("가" <= char <= "힣" for char in text)


def character_features(text: str) -> frozenset[str]:
    """한국어 어절의 2·3글자 조각. 형태소 분석이 놓치는 복합어·띄어쓰기 차이를 보완한다."""
    features: set[str] = set()
    for match in _TOKEN_PATTERN.finditer(normalize_retrieval_text(text)):
        token = match.group(0).lower()
        if not contains_hangul(token) or len(token) < 2:
            continue
        features.add(token)
        for size in (2, 3):
            features.update(token[index : index + size] for index in range(max(0, len(token) - size + 1)))
    return frozenset(features)


def _compact(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", normalize_retrieval_text(text).lower())


def _feature_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    if not overlap:
        return 0.0
    return overlap / math.sqrt(len(left) * len(right))


@dataclass(slots=True)
class LexicalIndex:
    postings: dict[str, list[tuple[int, int]]]
    lengths: list[int]
    average_length: float
    character_features: list[frozenset[str]]
    compact_texts: list[str]
    tokenizer: str

    @classmethod
    def build(cls, chunks: list[Chunk]) -> LexicalIndex:
        postings: dict[str, list[tuple[int, int]]] = {}
        lengths: list[int] = []
        for index, chunk in enumerate(chunks):
            counts = Counter(tokenize(chunk.text))
            lengths.append(sum(counts.values()))
            for term, frequency in counts.items():
                postings.setdefault(term, []).append((index, frequency))
        average_length = (sum(lengths) / len(lengths)) if lengths else 0.0
        return cls(
            postings=postings,
            lengths=lengths,
            average_length=average_length or 1.0,
            character_features=[character_features(chunk.text) for chunk in chunks],
            compact_texts=[_compact(chunk.text) for chunk in chunks],
            tokenizer=tokenizer_name(),
        )

    @property
    def size(self) -> int:
        return len(self.lengths)

    def search(self, query: str, top_k: int, strategy: str = "hybrid") -> list[tuple[float, int]]:
        """(점수, 청크 위치)를 점수 내림차순으로 돌려준다. 점수가 같으면 원래 순서를 따른다."""
        if top_k <= 0 or not self.size:
            return []
        query_terms = list(dict.fromkeys(tokenize(query)))

        bm25: dict[int, float] = {}
        for term in query_terms:
            postings = self.postings.get(term)
            if not postings:
                continue
            frequency = len(postings)
            idf = math.log(1 + (self.size - frequency + 0.5) / (frequency + 0.5))
            for index, term_frequency in postings:
                length_norm = 1 - BM25_B + BM25_B * self.lengths[index] / self.average_length
                bm25[index] = bm25.get(index, 0.0) + idf * term_frequency * (BM25_K1 + 1) / (
                    term_frequency + BM25_K1 * length_norm
                )

        # BM25는 질의마다 척도가 달라 최고점으로 나눠 0~1로 맞춘 뒤 문자 n-gram 신호와 더한다.
        best = max(bm25.values(), default=0.0)
        scores = {index: value / best for index, value in bm25.items()} if best else {}

        if strategy == "hybrid" and contains_hangul(query):
            query_features = character_features(query)
            for index, features in enumerate(self.character_features):
                similarity = _feature_similarity(query_features, features)
                if not similarity:
                    continue
                if index not in scores and similarity < MINIMUM_CHARACTER_SIMILARITY:
                    continue
                scores[index] = scores.get(index, 0.0) + CHARACTER_WEIGHT * similarity

        compact_query = _compact(query)
        if len(compact_query) >= 2:
            for index in scores:
                if compact_query in self.compact_texts[index]:
                    scores[index] += PHRASE_BONUS

        ranked = sorted(
            ((score, index) for index, score in scores.items() if score >= MINIMUM_SCORE),
            key=lambda item: (-item[0], item[1]),
        )
        return ranked[:top_k]


def _fingerprint(chunks: list[Chunk]) -> str:
    digest = hashlib.blake2b(digest_size=16)
    digest.update(tokenizer_name().encode())
    for chunk in chunks:
        digest.update(b"\x1f")
        digest.update(str(chunk.chunk_id).encode("utf-8", "surrogatepass"))
        digest.update(b"\x1e")
        digest.update(str(chunk.page).encode())
        digest.update(b"\x1e")
        digest.update(chunk.text.encode("utf-8", "surrogatepass"))
    return digest.hexdigest()


def index_for(chunks: list[Chunk]) -> LexicalIndex:
    """같은 내용의 청크 묶음이면 캐시된 인덱스를 돌려준다."""
    key = _fingerprint(chunks)
    with _CACHE_LOCK:
        cached = _INDEX_CACHE.get(key)
        if cached is not None:
            _INDEX_CACHE.move_to_end(key)
            return cached
    index = LexicalIndex.build(chunks)
    with _CACHE_LOCK:
        _INDEX_CACHE[key] = index
        _INDEX_CACHE.move_to_end(key)
        while len(_INDEX_CACHE) > INDEX_CACHE_SIZE:
            _INDEX_CACHE.popitem(last=False)
    return index


def clear_index_cache() -> None:
    with _CACHE_LOCK:
        _INDEX_CACHE.clear()
