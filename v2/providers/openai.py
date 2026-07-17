from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from v2.schemas import AnswerWithSources, Chunk, RelationTriple, VectorSource


class OpenAIProviderError(RuntimeError):
    pass


class OpenAIProvider:
    DEFAULT_MODEL = "gpt-5.4-mini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        dotenv = _read_dotenv()
        self.api_key = api_key or _configured_value("OPENAI_API_KEY", dotenv)
        self.model = model or _configured_value("OPENAI_MODEL", dotenv, self.DEFAULT_MODEL)
        self.base_url = (base_url or _configured_value("OPENAI_BASE_URL", dotenv, "https://api.openai.com/v1")).rstrip("/")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def summarize(self, chunks: list[Chunk]) -> str:
        instructions = (
            "You generate Korean Course Pack summaries for CourseBee. "
            "Use only the provided source chunks. Do not add unsupported facts. "
            "Keep the summary concise and useful for study."
        )
        prompt = (
            "다음 강의자료 근거만 사용해서 전체 흐름을 한국어로 요약해줘. "
            "출처 파일/페이지를 암시할 수는 있지만, 없는 내용을 만들지 마.\n\n"
            f"{_context_block(chunks)}"
        )
        return self._responses_text(instructions=instructions, input_text=prompt, max_output_tokens=900)

    def answer(self, question: str, chunks: list[Chunk], graph_context: list[RelationTriple]) -> AnswerWithSources:
        instructions = (
            "Answer in Korean using only the provided chunks. "
            "If the chunks are insufficient, say that the sources are insufficient."
        )
        graph_lines = "\n".join(" - " + " / ".join(triple.as_list()) for triple in graph_context)
        prompt = (
            f"질문: {question}\n\n"
            f"문서 근거:\n{_context_block(chunks)}\n\n"
            f"그래프 맥락:\n{graph_lines or '- 없음'}"
        )
        text = self._responses_text(instructions=instructions, input_text=prompt, max_output_tokens=700)
        sources = [VectorSource(page=chunk.page, chunk_id=chunk.chunk_id, doc_id=chunk.metadata.get("doc_id"), filename=chunk.metadata.get("filename")) for chunk in chunks]
        return AnswerWithSources(answer=text, vector_sources=sources, graph_context=graph_context)

    def extract_relations(self, chunks: list[Chunk]) -> list[RelationTriple]:
        return []

    def generate_script(self, chunks: list[Chunk], minutes: int) -> str:
        instructions = (
            "Generate a Korean audio script from the provided source chunks only. "
            "Keep it natural, but do not add unsupported facts."
        )
        prompt = f"목표 길이: {minutes}분\n\n문서 근거:\n{_context_block(chunks)}"
        return self._responses_text(instructions=instructions, input_text=prompt, max_output_tokens=1200)

    def _responses_text(self, instructions: str, input_text: str, max_output_tokens: int = 800) -> str:
        if not self.api_key:
            raise OpenAIProviderError("OPENAI_API_KEY is not set.")

        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": max_output_tokens,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise OpenAIProviderError(f"OpenAI API request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise OpenAIProviderError(f"OpenAI API request failed: {exc.reason}") from exc

        text = _extract_response_text(data).strip()
        if not text:
            raise OpenAIProviderError("OpenAI API returned an empty response.")
        return text


def _context_block(chunks: list[Chunk], max_chars_per_chunk: int = 900) -> str:
    lines: list[str] = []
    for chunk in chunks:
        filename = chunk.metadata.get("filename") if chunk.metadata else None
        doc_id = chunk.metadata.get("doc_id") if chunk.metadata else None
        source_id = f"{filename or doc_id or 'document'} p{chunk.page}/{chunk.chunk_id}"
        text = " ".join(chunk.text.split())[:max_chars_per_chunk]
        lines.append(f"[{source_id}] {text}")
    return "\n".join(lines)


def _extract_response_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    parts: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "".join(parts)


def _read_dotenv(path: str = ".env") -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _configured_value(name: str, dotenv: dict[str, str], default: str | None = None) -> str | None:
    if name in os.environ:
        return os.environ.get(name) or default
    return dotenv.get(name) or default
