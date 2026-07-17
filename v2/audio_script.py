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
    if llm_provider in {"ollama", "qwen", "qwen3"}:
        llm_payload = _ollama_script(selected, mode=mode, model=llm_model, grounding=grounding, minutes=minutes, target_chars=target_chars)
        warnings.extend(llm_payload["warnings"])
        if llm_payload["script"]:
            raw_char_count = _script_char_count(llm_payload["script"])
            minimum_chars = int(target_chars * 0.9) if target_chars else None
            script = _expand_script_to_target_chars(
                llm_payload["script"],
                selected,
                mode=mode,
                target_chars=target_chars,
            )
            final_char_count = _script_char_count(script)
            if minimum_chars is not None:
                llm_payload["llm"].update(
                    {
                        "raw_script_char_count": raw_char_count,
                        "minimum_target_chars": minimum_chars,
                        "length_status": "met" if raw_char_count >= minimum_chars else "source_expanded",
                    }
                )
                if raw_char_count < minimum_chars:
                    if final_char_count >= minimum_chars:
                        warnings.append(
                            f"Ollama script was {raw_char_count} characters, below the {minimum_chars} minimum; "
                            f"source-grounded expansion produced {final_char_count} characters."
                        )
                    else:
                        llm_payload["llm"]["length_status"] = "short"
                        warnings.append(
                            f"Ollama script remained short after source-grounded expansion: "
                            f"{final_char_count} / {minimum_chars} characters."
                        )
            return _audio_payload(
                mode=mode,
                script=script,
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
        turn_text = _remove_spoken_speaker_labels(turn_text)
        if not turn_text:
            continue
        source_chunk = _source_chunk_for_text(turn_text, source_pool, fallback_index=index // 2)
        sources = [source.to_dict() for source in _sources_from_chunks([source_chunk])] if source_chunk else []
        segments.append({"speaker": speaker, "text": turn_text, "sources": sources})
    return segments


def _remove_spoken_speaker_labels(text: str) -> str:
    cleaned = re.sub(r"(?i)(?:,\s*)?\b(?:HOST|GUEST)\b(?=[\s,.!?，。！？]|$)", "", text)
    cleaned = re.sub(r"\s+([,.!?，。！？])", r"\1", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


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
    closing: list[dict] = []
    if mode == "podcast" and len(expanded) > 1:
        closing = [expanded.pop()]
    host_podcast_templates = [
        "여기서 앞 내용을 연결해보면 좋겠네요. 자료의 핵심 문장은 “{sentence}”입니다. 이 지점을 기억하면 다음 개념도 훨씬 자연스럽게 이어집니다.",
        "잠깐 정리해볼게요. “{sentence}”라는 설명이 중요한 연결점이었어요. 이 부분을 자신의 말로 바꿔보면 이해한 범위도 확인할 수 있겠네요.",
        "용어를 따로 외우기보다 흐름을 보는 게 중요하겠어요. “{sentence}”라는 근거를 중심에 두고 앞뒤 개념의 역할을 비교해보죠.",
        "이 대목에서 한 번 멈춰볼까요. 자료의 “{sentence}”라는 설명을 기준으로 보면 왜 이 개념이 필요한지 더 분명해집니다.",
        "앞의 내용과 이어서 들으니 구조가 보이네요. “{sentence}”라는 설명이 다음 단계로 넘어가는 단서라고 볼 수 있겠습니다.",
        "학습자 입장에서는 이 연결을 놓치기 쉬울 것 같아요. “{sentence}”를 기억해두고 비슷한 개념과 차이를 확인해보죠.",
    ]
    guest_podcast_templates = [
        "맞아요. 자료에서는 “{sentence}”라고 설명합니다. 정의와 함께 등장 배경과 결과를 나눠 보면 개념의 역할을 더 정확하게 이해할 수 있어요.",
        "조금 더 풀어보면 “{sentence}”가 핵심입니다. 이 설명이 어떤 문제에 답하는지 생각하면 단순 암기보다 오래 기억할 수 있어요.",
        "복습할 때도 “{sentence}”를 기준으로 정리해보세요. 관련 개념과의 차이까지 한 문장으로 덧붙이면 전체 구조가 선명해집니다.",
        "그렇습니다. 자료의 표현을 따라가면 “{sentence}”가 중심 내용이에요. 원인과 결과를 나눠 말해보면 이해가 더 단단해집니다.",
        "이 부분은 “{sentence}”로 요약할 수 있습니다. 앞서 본 개념이 실제 처리 과정에서 어떤 역할을 하는지 연결해서 보면 좋아요.",
        "핵심 근거는 “{sentence}”입니다. 이 문장을 출발점으로 정의, 필요한 이유, 다음 개념과의 관계를 차례대로 복습해보세요.",
    ]
    narrator_templates = [
        "다음 포인트는 {terms}입니다. {sentence} 이 내용은 앞뒤 개념과 함께 이해해야 하며, 단독 정의보다 학습 흐름 속 역할을 보는 것이 중요합니다.",
        "조금 더 풀어 설명하면, {sentence} 이 부분은 모델이 입력을 처리하고 특징을 만드는 과정에서 중요한 단서가 됩니다.",
    ]

    index = 0
    while _script_char_count([*expanded, *closing]) < minimum_chars and index < 40:
        chunk = chunks[index % len(chunks)]
        sentence = _concise_source_sentence(chunk, variant=index // len(chunks), max_chars=150)
        if mode == "podcast":
            previous_speaker = str(expanded[-1].get("speaker") or "guest").lower() if expanded else "guest"
            speaker = "guest" if previous_speaker == "host" else "host"
            templates = guest_podcast_templates if speaker == "guest" else host_podcast_templates
            template_index = ((index // len(chunks)) + (index % len(chunks))) % len(templates)
            template = templates[template_index]
        else:
            speaker = "narrator"
            template_index = ((index // len(chunks)) + (index % len(chunks))) % len(narrator_templates)
            template = narrator_templates[template_index]
        rendered = template.format(sentence=sentence)
        existing_texts = {str(item.get("text") or "") for item in expanded}
        if mode == "podcast" and rendered in existing_texts:
            for offset in range(1, len(templates)):
                candidate = templates[(template_index + offset) % len(templates)].format(sentence=sentence)
                if candidate not in existing_texts:
                    rendered = candidate
                    break
        expanded.append({"speaker": speaker, "text": rendered, "sources": _source_dicts(chunk)})
        index += 1

    if closing and expanded and expanded[-1].get("speaker") == closing[0].get("speaker"):
        closing_speaker = str(closing[0].get("speaker") or "guest").lower()
        bridge_speaker = "host" if closing_speaker == "guest" else "guest"
        expanded.append(
            {
                "speaker": bridge_speaker,
                "text": "좋아요. 지금까지 연결한 핵심을 기억하면서 마지막 정리로 넘어가 보죠.",
                "sources": closing[0].get("sources", []),
            }
        )
    return [*expanded, *closing]


def _script_sentence(chunk: Chunk, max_chars: int = 320) -> str:
    terms = _keyword_terms(chunk.text)
    sentence = _best_sentence(chunk.text, terms)
    if len(sentence) <= max_chars:
        return sentence
    shortened = sentence[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return shortened or sentence[:max_chars].rstrip()


def _concise_source_sentence(chunk: Chunk, variant: int = 0, max_chars: int = 150) -> str:
    text = " ".join(chunk.text.split())
    text = re.sub(r"^[^.!?。！？]{0,80}:\s*", "", text)
    candidates = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]
    if not candidates:
        return _script_sentence(chunk, max_chars=max_chars).rstrip(" .")
    sentence = candidates[variant % len(candidates)]
    if len(sentence) > max_chars:
        sentence = sentence[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return sentence.rstrip(" .")
