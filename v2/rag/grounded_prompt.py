"""문서 근거 답변용 프롬프트와 번호 인용.

근거마다 [번호]를 붙여 LLM이 문장 끝에 인용하게 하고, 그 번호로 실제로 쓴 출처만 표시한다.
번호는 answering._sources_from_chunks와 같은 기준으로 중복을 제거한 순서라서 sources[번호-1]과 맞는다.
"""

from __future__ import annotations

import os
import re
from datetime import date

from v2.schemas import Chunk

CITATION_RE = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
NOT_FOUND_SENTENCE = "문서에서 확인되지 않습니다"


def today() -> str:
    """평가 재현을 위해 COURSEBEE_TODAY로 기준일을 고정할 수 있다."""
    return os.environ.get("COURSEBEE_TODAY") or date.today().isoformat()


def numbered_sources(chunks: list[Chunk]) -> list[Chunk]:
    numbered: list[Chunk] = []
    seen: set[tuple] = set()
    for chunk in chunks:
        metadata = chunk.metadata or {}
        key = (metadata.get("doc_id"), metadata.get("filename"), chunk.page, chunk.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        numbered.append(chunk)
    return numbered


def source_block(chunks: list[Chunk], max_chars_per_chunk: int = 1300) -> str:
    """제목에 버전·시행일이 들어 있는 경우가 많아 청크마다 문서 제목을 붙이고, 표·목록이 깨지지 않게 줄바꿈을 유지한다."""
    blocks: list[str] = []
    for index, chunk in enumerate(numbered_sources(chunks), start=1):
        metadata = chunk.metadata or {}
        filename = metadata.get("filename") or metadata.get("doc_id") or "document"
        title = metadata.get("title")
        header = f"[{index}] 문서: {title} ({filename})" if title and title != filename else f"[{index}] 문서: {filename}"
        lines = [line.rstrip() for line in chunk.text.strip().splitlines() if line.strip()]
        text = "\n".join(lines)
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk].rstrip() + "…"
        blocks.append(f"{header}\n{text}")
    return "\n\n".join(blocks)


def grounded_answer_prompt(question: str, chunks: list[Chunk]) -> str:
    return (
        "당신은 회사 내부 문서를 근거로 직원의 질문에 답하는 도우미입니다. "
        f"오늘 날짜는 {today()}입니다.\n\n"
        "규칙:\n"
        "1. 아래 번호가 붙은 근거에 적힌 내용만 사용하세요. 일반 상식이나 추측을 더하지 마세요.\n"
        '2. 사실을 말하는 문장마다 끝에 근거 번호를 붙이세요. 예: "연차는 1영업일 전까지 신청합니다 [2]."\n'
        "3. 질문과 표현만 다른 내용(예: '팀장 새로 달면' = '팀장으로 새로 임명된')이나 근거에 적힌 규정에서 바로 따라 나오는 "
        "결론(예: 출근 시각을 7시 30분~10시 사이에서 고른다면 가장 늦은 출근 시각은 10시)은 답할 수 있는 내용입니다. "
        f'그런 내용도 근거에 없으면 "{NOT_FOUND_SENTENCE}"라고 먼저 말하세요. '
        "다른 대상·다른 경우의 규정(예: 본인 결혼 규정을 형제 결혼에)을 끌어다 답을 추측하지 마세요. "
        "관련된 사실을 덧붙일 때는 그것이 질문에 대한 답이 아니라는 점을 밝히세요.\n"
        "4. 같은 주제의 규정이 여러 버전이면 오늘 날짜에 시행 중인 가장 최신 규정을 따르고, 어느 문서·시행일 기준인지 밝히세요. "
        "아직 시행되지 않은 변경은 시행일과 함께 따로 알려 주세요.\n"
        "5. 숫자, 금액, 기간, 이름은 근거에 적힌 그대로 쓰세요.\n"
        "6. 질문이 여러 가지를 물으면 각각 답하세요.\n"
        "7. 한국어로 간결하게 답하되, 답에 영향을 주는 조건·예외·기한·승인권자·신청 방법은 빠뜨리지 마세요. "
        "대화 맥락이 함께 주어지면 지금 질문의 대상을 파악하는 데만 쓰세요.\n\n"
        f"질문: {question}\n\n"
        f"근거:\n{source_block(chunks)}"
    )


def support_check_prompt(question: str, chunks: list[Chunk], answer: str) -> str:
    """답변 초안이 질문의 핵심에 대한 근거를 갖췄는지 묻는다. 답이 없는 질문에 비슷한 규정을 끌어다 단정하는
    실패를 잡기 위한 단계다(eval/ragbench dev에서 이런 답이 답 없는 질문의 40%였다)."""
    return (
        f"회사 문서 근거와 질문, 그 근거로 쓴 답변 초안이 있습니다. 오늘 날짜는 {today()}입니다. "
        "다음 두 가지를 차례로 확인하세요.\n"
        "1. 질문이 묻는 대상(제도·물건·제품·사람·행사 등)이 근거에 직접 나오는가? "
        "질문과 표현만 다른 경우(예: '회사 컴퓨터' = '업무용 노트북')는 나오는 것으로 봅니다.\n"
        "2. 그렇다면 질문이 묻는 측면(예/아니오, 금액, 기한, 담당자, 장소, 방법 등)에 대한 답이 근거에 적혀 있거나 "
        "근거에서 바로 따라 나오는가? 같은 규정이 여러 버전이면 오늘 시행 중인 버전을 기준으로 봅니다. "
        "버전이 여러 개라는 이유만으로 \"아니오\"가 되지는 않습니다.\n"
        '둘 다 "예"이면 "supported", 하나라도 "아니오"이면 "not_supported"입니다. '
        "답변 초안이 다른 대상·다른 경우의 규정을 끌어다 썼거나, 근거에 없는 '안 된다', '지원하지 않는다' 같은 단정을 했다면 "
        '"not_supported"입니다. 질문이 여러 가지를 묻고 근거가 그중 일부에 답하면 "supported"로 봅니다.\n'
        'JSON으로만 답하세요: {"verdict": "supported|not_supported", "reason": "한 문장"}\n\n'
        f"질문: {question}\n\n"
        f"답변 초안:\n{answer}\n\n"
        f"근거:\n{source_block(chunks)}"
    )


def unsupported_answer(chunks: list[Chunk], max_documents: int = 3) -> str:
    """근거가 질문에 답하지 못할 때의 답변. LLM에 다시 쓰게 하면 관련 사실을 덧붙이다 또 단정해서 고정 문구로 둔다."""
    titles: list[str] = []
    for index, chunk in enumerate(numbered_sources(chunks), start=1):
        metadata = chunk.metadata or {}
        title = metadata.get("title") or metadata.get("filename") or "문서"
        if any(title in existing for existing in titles):
            continue
        titles.append(f"[{index}] {title}")
        if len(titles) >= max_documents:
            break
    if not titles:
        return f"{NOT_FOUND_SENTENCE}."
    return f"{NOT_FOUND_SENTENCE}. 질문과 관련 있을 수 있는 문서: {', '.join(titles)}"


def strip_citation_markers(text: str) -> str:
    """'합니다 [1].' → '합니다.'"""
    return re.sub(r"\s*" + CITATION_RE.pattern, "", text or "").strip()


def cited_indices(text: str) -> list[int]:
    indices: list[int] = []
    for group in CITATION_RE.findall(text or ""):
        for part in group.split(","):
            value = int(part.strip())
            if value not in indices:
                indices.append(value)
    return indices
