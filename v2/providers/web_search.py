from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from v2.schemas import Chunk


class WebSearchProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class WebSearchResult:
    title: str
    url: str
    text: str
    language: str
    provider: str = "wikipedia"
    rank: int = 0
    page_id: int | None = None

    def to_chunk(self, index: int) -> Chunk:
        stable_id = str(self.page_id or index)
        chunk_id = f"web_{self.language}_{stable_id}"
        return Chunk(
            chunk_id=chunk_id,
            page=1,
            text=self.text,
            char_start=0,
            char_end=len(self.text),
            metadata={
                "doc_id": f"web:{self.language}:{stable_id}",
                "filename": self.title,
                "title": self.title,
                "url": self.url,
                "source_type": "external_web",
                "web_provider": self.provider,
                "language": self.language,
                "search_rank": self.rank,
            },
        )


class WikipediaSearchProvider:
    def __init__(
        self,
        timeout: int = 12,
        languages: tuple[str, ...] = ("ko", "en"),
        user_agent: str = "CourseBee/2.1 (local educational Web RAG)",
    ) -> None:
        self.timeout = timeout
        self.languages = languages
        self.user_agent = user_agent
        self.name = "wikipedia"

    def search(self, query: str, top_k: int = 3) -> list[WebSearchResult]:
        clean_query = _clean_query(query)
        if not clean_query:
            return []

        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()
        warnings: list[str] = []
        for language in self.languages:
            try:
                language_results = self._search_language(clean_query, language, top_k)
            except WebSearchProviderError as exc:
                warnings.append(str(exc))
                continue
            for result in language_results:
                if result.url in seen_urls:
                    continue
                result.rank = len(results) + 1
                results.append(result)
                seen_urls.add(result.url)
                if len(results) >= top_k:
                    return results
        if not results and warnings:
            raise WebSearchProviderError("; ".join(warnings))
        return results

    def _search_language(self, query: str, language: str, top_k: int) -> list[WebSearchResult]:
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 0,
                "gsrlimit": max(1, min(top_k, 10)),
                "prop": "extracts|info",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 1200,
                "inprop": "url",
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
            }
        )
        request = urllib.request.Request(
            f"https://{language}.wikipedia.org/w/api.php?{params}",
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise WebSearchProviderError(f"Wikipedia {language} search failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise WebSearchProviderError(f"Wikipedia {language} search failed: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebSearchProviderError(f"Wikipedia {language} returned an invalid response") from exc

        pages = payload.get("query", {}).get("pages", [])
        if isinstance(pages, dict):
            pages = list(pages.values())
        pages = sorted(pages, key=lambda page: page.get("index", 10_000))
        results: list[WebSearchResult] = []
        for page in pages:
            title = " ".join(str(page.get("title") or "").split()).strip()
            text = _clean_extract(page.get("extract"))
            if not title or len(text) < 40:
                continue
            url = str(page.get("fullurl") or "").strip()
            if not url:
                slug = urllib.parse.quote(title.replace(" ", "_"))
                url = f"https://{language}.wikipedia.org/wiki/{slug}"
            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    text=text,
                    language=language,
                    page_id=page.get("pageid"),
                )
            )
        return results


def web_results_to_chunks(results: list[WebSearchResult]) -> list[Chunk]:
    return [result.to_chunk(index) for index, result in enumerate(results, start=1)]


def _clean_query(query: str) -> str:
    query = re.sub(r"(?m)^(이전 질문|현재 후속 질문|최근 대화|현재 질문)\s*:\s*", "", str(query))
    return " ".join(query.split())[:500]


def _clean_extract(value: object) -> str:
    text = " ".join(str(value or "").replace("\u200b", " ").split())
    injection_markers = (
        "ignore previous instructions",
        "ignore all instructions",
        "system prompt",
        "developer message",
    )
    lowered = text.lower()
    if any(marker in lowered for marker in injection_markers):
        return ""
    return text[:1200]
