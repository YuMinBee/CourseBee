from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from v2.io_utils import atomic_write_json
from v2.rag.answering import _sources_from_chunks
from v2.schemas import Chunk

KNOWN_CONCEPTS = [
    "OCR",
    "PDF parsing",
    "source citation",
    "sha256 cache",
    "request_id",
    "failure tracking",
    "GraphRAG",
    "GraphRAG-lite",
    "concept map",
    "RAG",
    "chunk",
    "page",
    "TTS",
    "Object Storage",
    "BPE",
    "OOV",
    "Tokenizer",
    "subword tokenization",
    "subword",
    "RNN",
    "LSTM",
    "CNN",
    "sequence data",
    "long-term dependency",
    "local pattern",
    "text classification",
    "NLP pipeline",
]

RELATION_HINTS: dict[str, list[tuple[str, str]]] = {
    "OCR": [("PDF parsing", "supports")],
    "source citation": [("RAG", "grounds")],
    "sha256 cache": [("repeated processing cost", "reduces")],
    "request_id": [("failure tracking", "enables")],
    "GraphRAG-lite": [("concept map", "builds"), ("RAG", "augments")],
    "chunk": [("source citation", "preserves")],
    "page": [("source citation", "anchors")],
    "TTS": [("audio script", "renders")],
    "Tokenizer": [("BPE", "uses"), ("BPE", "prerequisite_of")],
    "subword tokenization": [("BPE", "prerequisite_of"), ("OOV", "reduces")],
    "subword": [("BPE", "prerequisite_of"), ("OOV", "reduces")],
    "BPE": [("OOV", "reduces"), ("subword tokenization", "is_a"), ("NLP pipeline", "used_in")],
    "RNN": [("sequence data", "handles"), ("NLP pipeline", "used_in")],
    "LSTM": [("RNN", "improves"), ("long-term dependency", "handles"), ("NLP pipeline", "used_in")],
    "CNN": [("local pattern", "captures"), ("text classification", "used_in"), ("NLP pipeline", "used_in")],
}

STRUCTURAL_RELATIONS = {"contains", "mentions", "introduces", "appears_in", "evidence_in"}
KOREAN_STOPWORDS = {
    "그리고", "그러나", "하지만", "따라서", "때문", "통해", "대한", "위한", "있는", "없는",
    "한다", "된다", "있다", "없다", "같다", "사용", "설명", "내용", "자료", "문서", "강의",
    "이번", "해당", "여러", "하나", "부분", "경우", "정도", "기반", "중심", "과정이며",
}
ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "was", "were",
    "has", "have", "using", "used", "course", "lecture", "week", "text", "data",
}
TECHNICAL_HEADS = {
    "모델", "학습", "처리", "관계", "에너지", "과정", "알고리즘", "데이터", "정보", "구조",
    "함수", "시스템", "이론", "법칙", "효과", "네트워크", "토큰", "분류", "분석", "표현",
}


def build_concept_map(chunks: list[Chunk], output_dir: str | None = None) -> dict:
    warnings: list[str] = []
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str, str | None, str]] = set()

    for chunk in chunks:
        metadata = chunk.metadata or {}
        concepts = _concepts_from_text(chunk.text)
        doc_id = metadata.get("doc_id")
        filename = metadata.get("filename")
        doc_node_id = _document_node_id(doc_id, filename)
        lecture_node_id = _lecture_node_id(metadata, doc_node_id)
        page_node_id = _page_node_id(metadata, doc_node_id, chunk.page)
        chunk_node_id = _chunk_node_id(metadata, doc_node_id, chunk.page, chunk.chunk_id)

        if doc_node_id:
            nodes.setdefault(
                doc_node_id,
                {
                    "id": doc_node_id,
                    "label": filename or doc_id or "document",
                    "type": "document",
                    "doc_id": doc_id,
                    "filename": filename,
                },
            )

        if lecture_node_id:
            nodes.setdefault(
                lecture_node_id,
                {
                    "id": lecture_node_id,
                    "label": _lecture_label(metadata, filename),
                    "type": "lecture",
                    "doc_id": doc_id,
                    "filename": filename,
                    "week": metadata.get("week"),
                    "lecture_no": metadata.get("lecture_no"),
                },
            )
            if doc_node_id:
                _append_edge(edges, seen_edges, doc_node_id, lecture_node_id, "contains", chunk, doc_id)

        if page_node_id:
            nodes.setdefault(
                page_node_id,
                {
                    "id": page_node_id,
                    "label": f"page {chunk.page}",
                    "type": "page",
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": chunk.page,
                },
            )
            parent = lecture_node_id or doc_node_id
            if parent:
                _append_edge(edges, seen_edges, parent, page_node_id, "contains", chunk, doc_id)

        nodes.setdefault(
            chunk_node_id,
            {
                "id": chunk_node_id,
                "label": chunk.chunk_id,
                "type": "chunk",
                "doc_id": doc_id,
                "filename": filename,
                "page": chunk.page,
                "chunk_id": chunk.chunk_id,
            },
        )
        if page_node_id:
            _append_edge(edges, seen_edges, page_node_id, chunk_node_id, "contains", chunk, doc_id)

        for concept in concepts:
            node = nodes.setdefault(concept, {"id": concept, "label": concept, "type": "concept", "documents": []})
            _add_document_to_node(node, doc_id=doc_id, filename=filename)
            _append_edge(edges, seen_edges, chunk_node_id, concept, "mentions", chunk, doc_id)
            _append_edge(edges, seen_edges, concept, chunk_node_id, "evidence_in", chunk, doc_id)
            if lecture_node_id:
                _append_edge(edges, seen_edges, lecture_node_id, concept, "introduces", chunk, doc_id)
            elif doc_node_id:
                _append_edge(edges, seen_edges, doc_node_id, concept, "introduces", chunk, doc_id)
            if doc_node_id:
                _append_edge(edges, seen_edges, concept, doc_node_id, "appears_in", chunk, doc_id)

        for source, target, relation in _edges_from_concepts(concepts, chunk.text):
            source_node = nodes.setdefault(source, {"id": source, "label": source, "type": "concept", "documents": []})
            target_node = nodes.setdefault(target, {"id": target, "label": target, "type": "concept", "documents": []})
            _add_document_to_node(source_node, doc_id=doc_id, filename=filename)
            _add_document_to_node(target_node, doc_id=doc_id, filename=filename)
            _append_edge(edges, seen_edges, source, target, relation, chunk, doc_id)

    concept_node_count = sum(1 for node in nodes.values() if node.get("type") == "concept")
    if concept_node_count == 0:
        warnings.append("No course graph could be built from the provided chunks.")

    graph = {"nodes": list(nodes.values()), "edges": edges, "warnings": warnings}
    if output_dir:
        path = Path(output_dir) / "graph.json"
        atomic_write_json(path, graph)
    return graph


def extract_concepts(text: str, limit: int = 14) -> list[str]:
    return _concepts_from_text(text)[: max(0, limit)]


def _append_edge(
    edges: list[dict],
    seen_edges: set[tuple[str, str, str, str | None, str]],
    source: str,
    target: str,
    relation: str,
    chunk: Chunk,
    evidence_doc_id: str | None,
) -> None:
    key = (source, target, relation, evidence_doc_id, chunk.chunk_id)
    if key in seen_edges:
        return
    seen_edges.add(key)
    edges.append(
        {
            "source": source,
            "target": target,
            "relation": relation,
            "edge_type": "structural" if relation in STRUCTURAL_RELATIONS else "conceptual",
            "evidence": [source_ref.to_dict() for source_ref in _sources_from_chunks([chunk])],
        }
    )


def _document_node_id(doc_id: str | None, filename: str | None) -> str | None:
    value = doc_id or filename
    return f"doc:{value}" if value else None


def _lecture_node_id(metadata: dict, doc_node_id: str | None) -> str | None:
    week = metadata.get("week")
    lecture_no = metadata.get("lecture_no")
    if week is None and lecture_no is None:
        return None
    suffix = f"week:{week or 'unknown'}:lecture:{lecture_no or 'unknown'}"
    return f"lecture:{doc_node_id}:{suffix}" if doc_node_id else f"lecture:{suffix}"


def _page_node_id(metadata: dict, doc_node_id: str | None, page: int) -> str | None:
    value = doc_node_id or metadata.get("filename") or metadata.get("doc_id")
    return f"page:{value}:{page}" if value else f"page:{page}"


def _chunk_node_id(metadata: dict, doc_node_id: str | None, page: int, chunk_id: str) -> str:
    value = doc_node_id or metadata.get("filename") or metadata.get("doc_id") or "document"
    return f"chunk:{value}:{page}:{chunk_id}"


def _lecture_label(metadata: dict, filename: str | None) -> str:
    week = metadata.get("week")
    lecture_no = metadata.get("lecture_no")
    if week is not None and lecture_no is not None:
        return f"Lecture {week}-{lecture_no}"
    if week is not None:
        return f"Week {week} lecture"
    if lecture_no is not None:
        return f"Lecture {lecture_no}"
    return filename or "lecture"


def _add_document_to_node(node: dict, doc_id: str | None, filename: str | None) -> None:
    if "documents" not in node:
        return
    value = {key: item for key, item in {"doc_id": doc_id, "filename": filename}.items() if item}
    if value and value not in node["documents"]:
        node["documents"].append(value)


def _concepts_from_text(text: str) -> list[str]:
    lowered = text.lower()
    concepts = [concept for concept in KNOWN_CONCEPTS if concept.lower() in lowered]

    for phrase in re.findall(r"\b[A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)?\b", text):
        if len(phrase) >= 3 and phrase not in concepts:
            concepts.append(phrase)

    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[가-힣]+", text)
    normalized_tokens = [_normalize_candidate(token) for token in raw_tokens]
    tokens = [token for token in normalized_tokens if _useful_candidate(token)]
    counts = Counter(tokens)
    positions = {token: tokens.index(token) for token in counts}

    bigrams: list[str] = []
    for left, right in zip(normalized_tokens, normalized_tokens[1:]):
        if _useful_modifier(left) and right in TECHNICAL_HEADS:
            phrase = f"{left} {right}"
            if phrase not in bigrams:
                bigrams.append(phrase)
        if _useful_english_phrase_pair(left, right):
            phrase = f"{left.lower()} {right.lower()}"
            if phrase not in bigrams:
                bigrams.append(phrase)

    ranked = sorted(
        counts,
        key=lambda token: (
            counts[token],
            1 if token in TECHNICAL_HEADS else 0,
            min(len(token), 12),
            -positions[token],
        ),
        reverse=True,
    )
    for candidate in [*bigrams, *ranked]:
        if candidate not in concepts:
            concepts.append(candidate)
        if len(concepts) >= 14:
            break
    return concepts[:14]


def _edges_from_concepts(concepts: list[str], text: str) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    for source in concepts:
        for target, relation in RELATION_HINTS.get(source, []):
            if target in concepts and source != target and (source, target, relation) not in edges:
                edges.append((source, target, relation))

    for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", text):
        present = _ordered_sentence_concepts(concepts, sentence)
        inferred = _inferred_relation_edge(present, sentence)
        if inferred and inferred not in edges:
            edges.append(inferred)
        for left, right in zip(present, present[1:]):
            edge = (left, right, "related_in_context")
            if left != right and edge not in edges:
                edges.append(edge)
    return edges


def _normalize_candidate(token: str) -> str:
    value = token.strip("_- ")
    if not _contains_hangul(value):
        return value
    for suffix in (
        "에서는", "으로", "에서", "에게", "이다", "이며", "하고", "하는", "되는", "한다", "된다",
        "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만",
    ):
        if value.endswith(suffix) and len(value) - len(suffix) >= 2:
            value = value[: -len(suffix)]
            break
    return value


def _useful_candidate(token: str) -> bool:
    if len(token) < 2:
        return False
    lowered = token.lower()
    if lowered in ENGLISH_STOPWORDS or token in KOREAN_STOPWORDS:
        return False
    if token.isdigit():
        return False
    if token.endswith(("한다", "된다", "했다", "하는", "되는", "이다", "이며", "난다", "인다")):
        return False
    return not bool(re.fullmatch(r"(?:하|되|있|없|같|바꾸|일어나)[가-힣]*", token))


def _useful_modifier(token: str) -> bool:
    if not token or token in KOREAN_STOPWORDS:
        return False
    if len(token) == 1:
        return _contains_hangul(token)
    return _useful_candidate(token)


def _useful_english_phrase_pair(left: str, right: str) -> bool:
    predicate_words = {
        "affects", "allows", "builds", "causes", "creates", "explains", "generates",
        "handles", "improves", "includes", "increases", "lowers", "makes", "prevents",
        "reduces", "supports", "transforms", "uses",
    }
    if not left.isascii() or not right.isascii():
        return False
    if not _useful_candidate(left) or not _useful_candidate(right):
        return False
    return left.lower() not in predicate_words and right.lower() not in predicate_words


def _contains_hangul(text: str) -> bool:
    return any("가" <= char <= "힣" for char in text)


def _concept_appears(concept: str, sentence: str) -> bool:
    compact_concept = re.sub(r"\s+", "", concept).lower()
    compact_sentence = re.sub(r"\s+", "", sentence).lower()
    return compact_concept in compact_sentence


def _ordered_sentence_concepts(concepts: list[str], sentence: str) -> list[str]:
    compact_sentence = re.sub(r"\s+", "", sentence).lower()
    matches: list[tuple[int, int, str]] = []
    for concept in concepts:
        compact = re.sub(r"\s+", "", concept).lower()
        if not compact:
            continue
        start = compact_sentence.find(compact)
        if start >= 0:
            matches.append((start, start + len(compact), concept))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    ordered: list[str] = []
    occupied: list[tuple[int, int]] = []
    for start, end, concept in matches:
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        ordered.append(concept)
        occupied.append((start, end))
    return ordered


def _inferred_relation_edge(concepts: list[str], sentence: str) -> tuple[str, str, str] | None:
    relation = _relation_from_sentence(sentence)
    if relation == "related_in_context" or len(concepts) < 2:
        return None
    compact_sentence = re.sub(r"\s+", "", sentence).lower()
    marker_positions = [
        compact_sentence.find(marker)
        for marker in ("줄", "감소", "완화", "바꾸", "변환", "사용", "이용", "영향", "필요", "비교", "차이")
        if marker in compact_sentence
    ]
    marker = min(marker_positions) if marker_positions else len(compact_sentence)
    before = [
        concept
        for concept in concepts
        if compact_sentence.find(re.sub(r"\s+", "", concept).lower()) < marker
    ]
    selected = before[-2:] if len(before) >= 2 else concepts[:2]
    return (selected[0], selected[1], relation) if len(selected) == 2 else None


def _relation_from_sentence(sentence: str) -> str:
    lowered = sentence.lower()
    relation_patterns = [
        ({"줄인다", "감소", "완화", "reduces"}, "reduces"),
        ({"변환", "바꾼", "바꾸", "convert", "transform"}, "transforms"),
        ({"사용", "이용", "uses", "using"}, "uses"),
        ({"구성", "포함", "contains", "consists"}, "contains_concept"),
        ({"영향", "affect"}, "affects"),
        ({"필요", "선수", "prerequisite", "전에"}, "prerequisite_of"),
        ({"비교", "차이", "반면", "whereas"}, "contrasts_with"),
        ({"분류", "예측", "classif"}, "supports_task"),
    ]
    for terms, relation in relation_patterns:
        if any(term in lowered for term in terms):
            return relation
    return "related_in_context"
