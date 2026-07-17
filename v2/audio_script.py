from __future__ import annotations

import re

from v2.providers.ollama import OllamaProvider, OllamaProviderError
from v2.rag.answering import _best_sentence, _keyword_terms, _sources_from_chunks
from v2.rag.retrieval import chunks_from_contexts, retrieve_contexts
from v2.schemas import Chunk

SUPPORTED_AUDIO_MODES = {"brief_1min", "briefing_3min", "briefing_5min", "lecture", "podcast"}
MODE_LIMITS = {
    "brief_1min": 1,
    "briefing_3min": 3,
    "briefing_5min": 5,
    "lecture": 8,
    "podcast": 10,
}
MODE_MINUTES = {
    "brief_1min": 1,
    "briefing_3min": 3,
    "briefing_5min": 5,
    "lecture": 8,
    "podcast": 6,
}


def generate_audio_script(
    chunks: list[Chunk],
    mode: str = "briefing_3min",
    llm_provider: str = "mock",
    llm_model: str | None = None,
    grounding: str = "creative",
    target_minutes: int | None = None,
    target_chars: int | None = None,
) -> dict:
    warnings: list[str] = []
    if grounding not in {"creative", "strict"}:
        warnings.append(f"unsupported grounding mode: {grounding}; using creative")
        grounding = "creative"
    if mode not in SUPPORTED_AUDIO_MODES:
        warnings.append(f"unsupported audio script mode: {mode}; using briefing_3min")
        mode = "briefing_3min"

    if not chunks:
        return _audio_payload(
            mode=mode,
            script=[],
            llm={"provider": llm_provider, "model": llm_model, "status": "skipped"},
            grounding=grounding,
            warnings=["No source chunks were provided. Audio script generation was skipped.", *warnings],
        )

    selected = chunks[: MODE_LIMITS[mode]]
    minutes = target_minutes if target_minutes and target_minutes > 0 else MODE_MINUTES[mode]
    if llm_provider in {"ollama", "qwen"}:
        llm_payload = _ollama_script(selected, mode=mode, model=llm_model, grounding=grounding, minutes=minutes, target_chars=target_chars)
        warnings.extend(llm_payload["warnings"])
        if llm_payload["script"]:
            return _audio_payload(
                mode=mode,
                script=llm_payload["script"],
                llm=llm_payload["llm"],
                grounding=grounding,
                warnings=warnings,
            )
    elif llm_provider not in {"mock", "rule", "local"}:
        warnings.append(f"unsupported audio script llm_provider: {llm_provider}; using rule-based fallback")

    if mode == "podcast":
        script = _podcast_script(selected)
    else:
        script = _single_speaker_script(selected, mode)
    script = _expand_script_to_target_chars(script, selected, mode=mode, target_chars=target_chars)

    return _audio_payload(
        mode=mode,
        script=script,
        llm={"provider": llm_provider, "model": llm_model, "status": "mock", "target_chars": target_chars},
        grounding=grounding,
        warnings=warnings,
    )


def _ollama_script(chunks: list[Chunk], mode: str, model: str | None, grounding: str = "creative", minutes: int | None = None, target_chars: int | None = None) -> dict:
    provider = OllamaProvider(model=model)
    try:
        text = provider.generate_script(chunks, minutes=minutes or MODE_MINUTES[mode], style=mode, grounding=grounding, target_chars=target_chars)
    except OllamaProviderError as exc:
        return {
            "script": [],
            "llm": {"provider": "ollama", "model": provider.model, "status": "fallback"},
            "warnings": [f"OllamaProvider failed. Falling back to rule-based audio script: {exc}"],
        }

    return {
        "script": _script_segments_from_llm_text(text, chunks, mode=mode),
        "llm": {"provider": "ollama", "model": provider.model, "status": "used", "grounding": grounding, "target_minutes": minutes or MODE_MINUTES[mode], "target_chars": target_chars},
        "warnings": [],
    }


def _script_segments_from_llm_text(text: str, chunks: list[Chunk], mode: str = "briefing_3min") -> list[dict]:
    if mode == "podcast":
        podcast_segments = _podcast_segments_from_llm_text(text, chunks)
        if podcast_segments:
            return podcast_segments

    paragraphs = [paragraph.strip(" -\t") for paragraph in re.split(r"\n\s*\n+", text) if paragraph.strip(" -\t")]
    if len(paragraphs) <= 1:
        paragraphs = [paragraph.strip(" -\t") for paragraph in text.splitlines() if paragraph.strip(" -\t")]
    if not paragraphs:
        paragraphs = [text.strip()]
    segments: list[dict] = []
    source_pool = chunks or []
    for index, paragraph in enumerate(paragraphs[:12]):
        source_chunk = _source_chunk_for_text(paragraph, source_pool, fallback_index=index)
        sources = [source.to_dict() for source in _sources_from_chunks([source_chunk])] if source_chunk else []
        segments.append({"speaker": "narrator", "text": paragraph, "sources": sources})
    return segments


def _podcast_segments_from_llm_text(text: str, chunks: list[Chunk]) -> list[dict]:
    turns: list[tuple[str, str]] = []
    current_speaker: str | None = None
    current_lines: list[str] = []
    speaker_pattern = re.compile(r"^(HOST|GUEST|\uc9c4\ud589\uc790|\uac8c\uc2a4\ud2b8)\s*[:\uff1a]\s*(.*)$", re.IGNORECASE)
    inline_speaker_pattern = re.compile(r"\s+(HOST|GUEST|\uc9c4\ud589\uc790|\uac8c\uc2a4\ud2b8)\s*[:\uff1a]", re.IGNORECASE)
    normalized_text = inline_speaker_pattern.sub(r"\n\1: ", text.strip())

    for raw_line in normalized_text.splitlines():
        line = raw_line.strip().strip("*- ")
        if not line:
            continue
        match = speaker_pattern.match(line)
        if match:
            if current_speaker and current_lines:
                turns.append((current_speaker, " ".join(current_lines).strip()))
            label = match.group(1).lower()
            current_speaker = "host" if label in {"host", "\uc9c4\ud589\uc790"} else "guest"
            current_lines = [match.group(2).strip()] if match.group(2).strip() else []
        elif current_speaker:
            current_lines.append(line)

    if current_speaker and current_lines:
        turns.append((current_speaker, " ".join(current_lines).strip()))

    segments: list[dict] = []
    source_pool = chunks or []
    for index, (speaker, turn_text) in enumerate(turns[:40]):
        if not turn_text:
            continue
        source_chunk = _source_chunk_for_text(turn_text, source_pool, fallback_index=index // 2)
        sources = [source.to_dict() for source in _sources_from_chunks([source_chunk])] if source_chunk else []
        segments.append({"speaker": speaker, "text": turn_text, "sources": sources})
    return segments

def _single_speaker_script(chunks: list[Chunk], mode: str) -> list[dict]:
    opening = {
        "brief_1min": "지금부터 핵심 개념을 1분 브리핑으로 빠르게 정리합니다.",
        "briefing_3min": "지금부터 강의자료의 핵심 흐름을 3분 브리핑으로 정리합니다.",
        "briefing_5min": "지금부터 강의자료의 핵심 흐름을 5분 심화 브리핑으로 정리합니다.",
        "lecture": "이 강의형 대본은 핵심 개념을 차례대로 연결해서 설명합니다.",
    }[mode]
    script = [
        {
            "speaker": "narrator",
            "text": opening,
            "sources": [source.to_dict() for source in _sources_from_chunks([chunks[0]])],
        }
    ]
    for chunk in chunks:
        script.append(
            {
                "speaker": "narrator",
                "text": f"다음으로 살펴볼 내용은 {_script_sentence(chunk)} 입니다.",
                "sources": [source.to_dict() for source in _sources_from_chunks([chunk])],
            }
        )
    return script


def _podcast_script(chunks: list[Chunk]) -> list[dict]:
    opening_terms = _terms_for_audio(chunks[0])
    script: list[dict] = [
        {
            "speaker": "host",
            "text": f"오늘은 강의자료에서 다루는 {opening_terms}의 흐름을 함께 정리해볼게요. 각 개념을 따로 외우기보다 자료 속 설명이 어떻게 이어지는지에 집중해보겠습니다.",
            "sources": [source.to_dict() for source in _sources_from_chunks([chunks[0]])],
        }
    ]
    for index, chunk in enumerate(chunks, start=1):
        sentence = _script_sentence(chunk)
        if index % 2:
            speaker = "host"
            text = f"먼저 자료에서 짚은 내용은 {sentence} 이 부분입니다. 이 설명이 앞뒤 내용과 어떤 관계를 이루는지 살펴보겠습니다."
        else:
            speaker = "guest"
            text = f"맞아요. 이어지는 자료에서는 {sentence} 라고 설명합니다. 정의뿐 아니라 이 내용이 필요한 이유와 활용 맥락을 함께 보면 이해하기 쉽습니다."
        script.append(
            {
                "speaker": speaker,
                "text": text,
                "sources": [source.to_dict() for source in _sources_from_chunks([chunk])],
            }
        )
    script.append(
        {
            "speaker": "host",
            "text": f"정리하면 오늘은 {', '.join(dict.fromkeys(_terms_for_audio(chunk) for chunk in chunks[:3]))}를 중심으로 자료의 흐름을 살펴봤습니다. 마지막으로 각 개념의 정의, 필요한 이유, 서로의 연결 관계를 자료 근거와 함께 다시 확인해보세요.",
            "sources": [source.to_dict() for source in _sources_from_chunks([chunks[-1]])],
        }
    )
    return script


def _script_char_count(script: list[dict]) -> int:
    return sum(len(str(segment.get("text") or "")) for segment in script)


def _source_dicts(chunk: Chunk | None) -> list[dict]:
    return [source.to_dict() for source in _sources_from_chunks([chunk])] if chunk else []


def _source_chunk_for_text(text: str, chunks: list[Chunk], fallback_index: int = 0) -> Chunk | None:
    if not chunks:
        return None
    contexts = retrieve_contexts(query=text, chunks=chunks, top_k=1).contexts
    matched = chunks_from_contexts(contexts)
    if matched:
        return matched[0]
    return chunks[min(max(fallback_index, 0), len(chunks) - 1)]


def _script_sources(script: list[dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[tuple[object, ...]] = set()
    for segment in script:
        for source in segment.get("sources") or []:
            key = (source.get("doc_id"), source.get("filename"), source.get("page"), source.get("chunk_id"))
            if key in seen:
                continue
            sources.append(source)
            seen.add(key)
    return sources


def _audio_payload(mode: str, script: list[dict], llm: dict, grounding: str, warnings: list[str]) -> dict:
    char_count = _script_char_count(script)
    sources = _script_sources(script)
    return {
        "mode": mode,
        "script": script,
        "script_char_count": char_count,
        "segment_count": len(script),
        "source_count": len(sources),
        "sources": sources,
        "estimated_duration_seconds": round(char_count / 6) if char_count else 0,
        "tts_status": "mock",
        "audio_path": None,
        "llm": llm,
        "grounding": grounding,
        "warnings": warnings,
    }


def _terms_for_audio(chunk: Chunk | None) -> str:
    if not chunk:
        return "핵심 개념"
    terms = _keyword_terms(chunk.text)[:4]
    return ", ".join(terms) if terms else "핵심 개념"


def _expand_script_to_target_chars(script: list[dict], chunks: list[Chunk], mode: str, target_chars: int | None) -> list[dict]:
    if not target_chars or target_chars <= 0:
        return script
    minimum_chars = int(target_chars * 0.9)
    if _script_char_count(script) >= minimum_chars:
        return script
    if not chunks:
        return script

    expanded = list(script)
    podcast_templates = [
        "여기서 {terms}를 한 번 더 풀어보면, 자료는 {sentence} 라고 설명합니다. 용어만 외우기보다 이 설명이 어떤 질문에 답하는지 함께 확인하면 핵심을 더 정확히 잡을 수 있습니다.",
        "조금 더 구체적으로 살펴보죠. {sentence} 이 대목에서 중요한 것은 자료가 제시한 조건과 결과를 구분하는 일입니다. 두 요소를 나눠 읽으면 설명의 구조가 선명해집니다.",
        "학습자가 자주 놓치는 부분은 {terms}를 독립된 암기 항목처럼 보는 것입니다. 앞에서 다룬 내용과 비교하고 다음 설명으로 이어지는 지점을 찾으면 전체 흐름을 이해하는 데 도움이 됩니다.",
        "다시 말해 이번 근거의 중심 문장은 {sentence} 입니다. 이 문장을 자신의 말로 바꾸어 설명해보면 개념의 의미와 역할을 제대로 이해했는지 확인할 수 있습니다.",
        "복습할 때는 {terms}의 정의, 등장 배경, 관련 개념을 차례로 정리해보세요. 자료에 나온 표현을 기준으로 답을 구성하면 불필요한 추측을 줄일 수 있습니다.",
        "마지막으로 현재 부분을 요약하면 {sentence} 입니다. 이 근거가 앞뒤 강의 내용과 어떻게 연결되는지 한 문장으로 덧붙여보면 좋은 복습이 됩니다.",
    ]
    narrator_templates = [
        "다음 포인트는 {terms}입니다. {sentence} 이 내용은 앞뒤 개념과 함께 이해해야 하며, 단독 정의보다 학습 흐름 속 역할을 보는 것이 중요합니다.",
        "조금 더 풀어 설명하면, {sentence} 이 부분은 모델이 입력을 처리하고 특징을 만드는 과정에서 중요한 단서가 됩니다.",
    ]

    index = 0
    while _script_char_count(expanded) < minimum_chars and index < 40:
        chunk = chunks[index % len(chunks)]
        sentence = _script_sentence(chunk)
        terms = _terms_for_audio(chunk)
        if mode == "podcast":
            speaker = "guest" if index % 2 else "host"
            template_index = ((index // len(chunks)) + (index % len(chunks))) % len(podcast_templates)
            template = podcast_templates[template_index]
        else:
            speaker = "narrator"
            template_index = ((index // len(chunks)) + (index % len(chunks))) % len(narrator_templates)
            template = narrator_templates[template_index]
        expanded.append(
            {
                "speaker": speaker,
                "text": template.format(terms=terms, sentence=sentence),
                "sources": _source_dicts(chunk),
            }
        )
        index += 1
    return expanded


def _script_sentence(chunk: Chunk) -> str:
    terms = _keyword_terms(chunk.text)
    return _best_sentence(chunk.text, terms)[:320]
