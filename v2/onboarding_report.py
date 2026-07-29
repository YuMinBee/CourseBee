from __future__ import annotations

import hashlib
import html
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from v2.providers.ollama import OllamaProvider, OllamaProviderError
from v2.providers.openai import OpenAIProvider, OpenAIProviderError
from v2.rag.answering import _best_sentence, _keyword_terms, _sources_from_chunks
from v2.rag.citations import check_text_grounding
from v2.schemas import Chunk


def build_source_snapshot(chunks: list[Chunk]) -> dict:
    documents: list[dict] = []
    for group in _group_chunks_by_document(chunks).values():
        if not group:
            continue
        metadata = group[0].metadata or {}
        digest = hashlib.sha256()
        for chunk in group:
            digest.update(chunk.chunk_id.encode("utf-8"))
            digest.update(str(chunk.page).encode("ascii"))
            digest.update(chunk.text.encode("utf-8"))
        documents.append(
            {
                "doc_id": metadata.get("doc_id"),
                "filename": metadata.get("filename"),
                "chunk_count": len(group),
                "pages": sorted({chunk.page for chunk in group}),
                "fingerprint": digest.hexdigest(),
            }
        )

    pack_digest = hashlib.sha256()
    for document in sorted(documents, key=lambda item: _snapshot_key(item)):
        pack_digest.update(str(document.get("fingerprint") or "").encode("ascii"))
    return {
        "document_count": len(documents),
        "fingerprint": pack_digest.hexdigest(),
        "documents": documents,
    }


def compare_source_snapshots(
    previous: dict | None,
    current: dict,
    sections: list[dict] | None = None,
) -> dict:
    if not previous or not previous.get("documents"):
        return {
            "status": "report_not_generated",
            "requires_regeneration": True,
            "change_count": len(current.get("documents", [])),
            "added_sources": list(current.get("documents", [])),
            "updated_sources": [],
            "removed_sources": [],
            "unchanged_source_count": 0,
            "executive_summary_affected": True,
            "affected_sections": [],
        }

    previous_by_key = {_snapshot_key(item): item for item in previous.get("documents", [])}
    current_by_key = {_snapshot_key(item): item for item in current.get("documents", [])}
    added = [item for key, item in current_by_key.items() if key not in previous_by_key]
    removed = [item for key, item in previous_by_key.items() if key not in current_by_key]
    updated = [
        {"before": previous_by_key[key], "after": item}
        for key, item in current_by_key.items()
        if key in previous_by_key and item.get("fingerprint") != previous_by_key[key].get("fingerprint")
    ]
    unchanged = sum(
        1
        for key, item in current_by_key.items()
        if key in previous_by_key and item.get("fingerprint") == previous_by_key[key].get("fingerprint")
    )
    changed_keys = {
        *(_snapshot_key(item) for item in added),
        *(_snapshot_key(item) for item in removed),
        *(_snapshot_key(item["after"]) for item in updated),
    }
    affected_sections = []
    for section in sections or []:
        section_keys = {_snapshot_key(source) for source in section.get("sources", [])}
        matched = sorted(section_keys & changed_keys)
        if not matched:
            continue
        affected_sections.append(
            {
                "index": section.get("index"),
                "title": section.get("title"),
                "changed_sources": matched,
            }
        )

    change_count = len(added) + len(updated) + len(removed)
    return {
        "status": "changes_detected" if change_count else "current",
        "requires_regeneration": bool(change_count),
        "change_count": change_count,
        "added_sources": added,
        "updated_sources": updated,
        "removed_sources": removed,
        "unchanged_source_count": unchanged,
        "executive_summary_affected": bool(change_count),
        "affected_sections": affected_sections,
    }


def generate_onboarding_report(
    chunks: list[Chunk],
    *,
    title: str,
    audience: str,
    objective: str,
    max_sections: int = 6,
    llm_provider: str = "mock",
    llm_model: str | None = None,
) -> dict:
    warnings: list[str] = []
    if not chunks:
        return {
            "report_type": "onboarding",
            "title": title,
            "audience": audience,
            "objective": objective,
            "executive_summary": {"text": "", "sources": []},
            "sections": [],
            "source_register": [],
            "quality": _quality_summary([], 0),
            "llm": {"provider": llm_provider, "model": llm_model, "status": "skipped"},
            "warnings": ["No source chunks were provided. Onboarding report generation was skipped."],
        }

    groups = _group_chunks_by_document(chunks)
    sections: list[dict] = []
    section_chunks: list[list[Chunk]] = []
    for index, group in enumerate(list(groups.values())[:max_sections], start=1):
        selected = _representative_chunks(group, limit=3)
        section = _section_from_chunks(index, selected)
        if not section["key_points"]:
            continue
        sections.append(section)
        section_chunks.append(selected)

    used_chunks = _dedupe_chunks([chunk for group in section_chunks for chunk in group])
    executive_text = "\n\n".join(
        section["key_points"][0]["text"][:420] for section in sections if section["key_points"]
    )
    executive_text = executive_text[:1400].strip()
    executive_check = check_text_grounding(executive_text, used_chunks)
    llm_status = "mock"
    model = llm_model

    if llm_provider in {"ollama", "qwen", "qwen3"}:
        provider = OllamaProvider(model=llm_model)
        model = provider.model
        try:
            candidate = provider.generate_report_overview(
                used_chunks,
                audience=audience,
                objective=objective,
            ).strip()
            candidate_check = check_text_grounding(candidate, used_chunks)
            if candidate and candidate_check.passed:
                executive_text = candidate
                executive_check = candidate_check
                llm_status = "used"
            else:
                llm_status = "fallback"
                warnings.extend(candidate_check.warnings)
                warnings.append("Ollama report overview failed grounding validation; source-based overview was retained.")
        except OllamaProviderError as exc:
            llm_status = "fallback"
            warnings.append(f"Ollama report generation failed; source-based overview was retained: {exc}")
    elif llm_provider == "openai":
        provider = OpenAIProvider(model=llm_model)
        model = provider.model
        if not provider.available:
            llm_status = "fallback"
            warnings.append("OPENAI_API_KEY is not set; source-based overview was retained.")
        else:
            try:
                candidate = provider.generate_report_overview(
                    used_chunks,
                    audience=audience,
                    objective=objective,
                ).strip()
                candidate_check = check_text_grounding(candidate, used_chunks)
                if candidate and candidate_check.passed:
                    executive_text = candidate
                    executive_check = candidate_check
                    llm_status = "used"
                else:
                    llm_status = "fallback"
                    warnings.extend(candidate_check.warnings)
                    warnings.append("OpenAI report overview failed grounding validation; source-based overview was retained.")
            except OpenAIProviderError as exc:
                llm_status = "fallback"
                warnings.append(f"OpenAI report generation failed; source-based overview was retained: {exc}")
    elif llm_provider not in {"mock", "rule", "local"}:
        llm_status = "fallback"
        warnings.append(f"Unsupported llm_provider '{llm_provider}'; source-based overview was retained.")

    source_register = _source_dicts(used_chunks)
    report = {
        "report_type": "onboarding",
        "title": title,
        "audience": audience,
        "objective": objective,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": {
            "text": executive_text,
            "sources": source_register,
            "grounding_check": executive_check.to_dict(),
        },
        "sections": sections,
        "source_register": source_register,
        "quality": _quality_summary(sections, len(groups)),
        "llm": {"provider": llm_provider, "model": model, "status": llm_status},
        "warnings": list(dict.fromkeys(warnings)),
    }
    return report


def onboarding_report_markdown(report: dict) -> str:
    sources = report.get("source_register", [])
    selection = report.get("selection", {})
    source_numbers = {_source_key(source): index for index, source in enumerate(sources, start=1)}
    lines = [
        f"# {report.get('title') or '온보딩 보고서'}",
        "",
        f"- 대상: {report.get('audience') or '-'}",
        f"- 목적: {report.get('objective') or '-'}",
        f"- 생성 시각: {report.get('generated_at') or '-'}",
        (
            f"- 선택 문서: {selection.get('selected_document_count', 0)}/"
            f"{selection.get('pack_document_count', 0)}"
            if selection.get("pack_document_count")
            else "- 선택 문서: -"
        ),
        "",
        "## 핵심 브리핑",
        "",
        str((report.get("executive_summary") or {}).get("text") or ""),
        "",
    ]
    for section in report.get("sections", []):
        lines.extend([f"## {section.get('title') or '문서 핵심 내용'}", ""])
        for point in section.get("key_points", []):
            citations = _citation_labels(point.get("sources", []), source_numbers)
            lines.append(f"- {point.get('text', '')}{citations}")
        lines.append("")

    lines.extend(["## 출처", ""])
    for index, source in enumerate(sources, start=1):
        lines.append(f"{index}. {_source_label(source)}")

    quality = report.get("quality", {})
    lines.extend(
        [
            "",
            "## 검증",
            "",
            f"- 섹션 근거 통과: {quality.get('grounded_section_count', 0)}/{quality.get('section_count', 0)}",
            f"- 인용 포함률: {quality.get('citation_coverage', 0):.0%}",
            f"- 문서 반영률: {quality.get('source_document_coverage', 0):.0%}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def onboarding_report_html(report: dict) -> str:
    sources = report.get("source_register", [])
    source_numbers = {_source_key(source): index for index, source in enumerate(sources, start=1)}
    sections_html = []
    for section in report.get("sections", []):
        points = []
        for point in section.get("key_points", []):
            citation = _citation_links(point.get("sources", []), source_numbers)
            points.append(f"<li>{html.escape(str(point.get('text') or ''))}{citation}</li>")
        sections_html.append(
            "<section class=\"report-section\">"
            f"<p class=\"eyebrow\">SOURCE {section.get('index', '')}</p>"
            f"<h2>{html.escape(str(section.get('title') or '문서 핵심 내용'))}</h2>"
            f"<ul>{''.join(points)}</ul>"
            "</section>"
        )

    source_rows = []
    for index, source in enumerate(sources, start=1):
        source_rows.append(
            f'<li id="source-{index}"><span>{index:02d}</span>{html.escape(_source_label(source))}</li>'
        )

    quality = report.get("quality", {})
    selection = report.get("selection", {})
    passed = bool(quality.get("passed"))
    status = "검증 통과" if passed else "검토 필요"
    selection_badge = (
        f"<span>선택 문서 {selection.get('selected_document_count', 0)}/"
        f"{selection.get('pack_document_count', 0)}</span>"
        if selection.get("pack_document_count")
        else ""
    )
    summary_paragraphs = [
        f"<p>{html.escape(paragraph.strip())}</p>"
        for paragraph in str((report.get("executive_summary") or {}).get("text") or "").split("\n\n")
        if paragraph.strip()
    ]
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(str(report.get("title") or "CourseBee 온보딩 보고서"))}</title>
  <style>
    :root{{--ink:#17212b;--muted:#63717c;--line:#dbe2e6;--blue:#275da8;--green:#0e766e;--paper:#fff;--wash:#f2f5f6}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--wash);color:var(--ink);font-family:Arial,"Noto Sans KR",sans-serif;line-height:1.65;letter-spacing:0}}
    main{{width:min(920px,calc(100% - 32px));margin:32px auto;background:var(--paper);border:1px solid var(--line)}}
    header{{padding:48px 52px 40px;border-top:7px solid var(--blue);border-bottom:1px solid var(--line)}}
    .brand,.eyebrow{{margin:0 0 10px;color:var(--blue);font-size:12px;font-weight:800;text-transform:uppercase}}
    h1{{margin:0;font-size:34px;line-height:1.25}} .meta{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:28px}}
    .meta div{{border-left:3px solid var(--green);padding-left:12px}} .meta b{{display:block;font-size:12px;color:var(--muted)}} .meta span{{display:block;margin-top:3px}}
    .summary{{padding:34px 52px;background:#f7fafb;border-bottom:1px solid var(--line)}} .summary h2,.report-section h2,.sources h2{{margin:0 0 12px;font-size:20px}}
    .summary p{{margin:0;font-size:16px}} .quality{{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}} .quality span{{border:1px solid var(--line);padding:5px 9px;font-size:12px}}
    .quality .pass{{border-color:#8bc9b8;color:#086253;background:#edf8f4}}
    .report-section{{padding:32px 52px;border-bottom:1px solid var(--line)}} ul{{margin:0;padding-left:20px}} li+li{{margin-top:10px}}
    sup a{{margin-left:4px;color:var(--blue);font-weight:800;text-decoration:none}}
    .sources{{padding:34px 52px}} .sources ol{{list-style:none;margin:0;padding:0}} .sources li{{display:grid;grid-template-columns:36px 1fr;gap:8px;padding:10px 0;border-bottom:1px solid var(--line);font-size:13px}}
    .sources li span{{color:var(--blue);font-weight:800}} footer{{padding:18px 52px;background:var(--ink);color:#dbe5e9;font-size:12px}}
    @media(max-width:640px){{header,.summary,.report-section,.sources{{padding-left:24px;padding-right:24px}}h1{{font-size:27px}}.meta{{grid-template-columns:1fr}}}}
    @media print{{body{{background:#fff}}main{{width:100%;margin:0;border:0}}.report-section{{break-inside:avoid}}}}
  </style>
</head>
<body>
<main>
  <header>
    <p class="brand">CourseBee v3 · Source-grounded onboarding</p>
    <h1>{html.escape(str(report.get("title") or "온보딩 보고서"))}</h1>
    <div class="meta">
      <div><b>대상</b><span>{html.escape(str(report.get("audience") or "-"))}</span></div>
      <div><b>목적</b><span>{html.escape(str(report.get("objective") or "-"))}</span></div>
    </div>
  </header>
  <section class="summary">
    <p class="eyebrow">Executive briefing</p>
    <h2>핵심 브리핑</h2>
    {''.join(summary_paragraphs)}
    <div class="quality">
      <span class="{"pass" if passed else ""}">{status}</span>
      <span>근거 섹션 {quality.get("grounded_section_count", 0)}/{quality.get("section_count", 0)}</span>
      <span>문서 반영률 {quality.get("source_document_coverage", 0):.0%}</span>
      {selection_badge}
    </div>
  </section>
  {''.join(sections_html)}
  <section class="sources">
    <p class="eyebrow">Source register</p>
    <h2>출처</h2>
    <ol>{''.join(source_rows)}</ol>
  </section>
  <footer>이 보고서는 Course Pack의 검색 근거만 사용하며, 각 항목은 파일·페이지·chunk 단위로 추적됩니다.</footer>
</main>
</body>
</html>
"""


def write_onboarding_report_artifacts(report: dict, output_dir: Path) -> dict:
    from v2.io_utils import atomic_write_json, atomic_write_text

    json_path = output_dir / "onboarding_report.json"
    markdown_path = output_dir / "onboarding_report.md"
    html_path = output_dir / "onboarding_report.html"
    atomic_write_text(markdown_path, onboarding_report_markdown(report))
    atomic_write_text(html_path, onboarding_report_html(report))
    atomic_write_json(json_path, report)
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
    }


def _section_from_chunks(index: int, chunks: list[Chunk]) -> dict:
    points: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks:
        candidates = [paragraph.strip() for paragraph in chunk.text.splitlines() if len(paragraph.strip()) >= 30]
        if not candidates:
            candidates = [chunk.text]
        for candidate in candidates:
            sentence = _best_sentence(candidate, _keyword_terms(candidate)).strip()
            normalized = " ".join(sentence.lower().split())
            if not sentence or normalized in seen:
                continue
            seen.add(normalized)
            points.append({"text": sentence[:520], "sources": _source_dicts([chunk])})
            if len(points) >= 4:
                break
        if len(points) >= 4:
            break

    filename = next(
        (str((chunk.metadata or {}).get("filename")) for chunk in chunks if (chunk.metadata or {}).get("filename")),
        f"document-{index}",
    )
    document_title = next(
        (
            line.strip()
            for chunk in chunks
            for line in chunk.text.splitlines()
            if 3 <= len(line.strip()) <= 100
        ),
        Path(filename).stem,
    )
    section_text = " ".join(point["text"] for point in points)
    grounding_check = check_text_grounding(section_text, chunks)
    return {
        "index": index,
        "title": document_title,
        "summary": section_text,
        "key_points": points,
        "sources": _source_dicts(chunks),
        "grounding_check": grounding_check.to_dict(),
    }


def _representative_chunks(chunks: list[Chunk], limit: int) -> list[Chunk]:
    meaningful = [chunk for chunk in chunks if len(chunk.text.strip()) >= 30] or list(chunks)
    if len(meaningful) <= limit:
        return meaningful
    if limit == 1:
        return [meaningful[0]]
    indexes = [round(index * (len(meaningful) - 1) / (limit - 1)) for index in range(limit)]
    return [meaningful[index] for index in indexes]


def _group_chunks_by_document(chunks: list[Chunk]) -> OrderedDict[str, list[Chunk]]:
    groups: OrderedDict[str, list[Chunk]] = OrderedDict()
    for chunk in chunks:
        metadata = chunk.metadata or {}
        key = str(metadata.get("doc_id") or metadata.get("filename") or "document")
        groups.setdefault(key, []).append(chunk)
    return groups


def _quality_summary(sections: list[dict], source_document_count: int) -> dict:
    section_count = len(sections)
    grounded = sum(1 for section in sections if (section.get("grounding_check") or {}).get("passed"))
    cited = sum(1 for section in sections if section.get("sources"))
    represented_documents = len(
        {
            source.get("doc_id") or source.get("filename")
            for section in sections
            for source in section.get("sources", [])
            if source.get("doc_id") or source.get("filename")
        }
    )
    citation_coverage = cited / section_count if section_count else 0.0
    document_coverage = represented_documents / source_document_count if source_document_count else 0.0
    return {
        "passed": bool(section_count) and grounded == section_count and cited == section_count,
        "section_count": section_count,
        "grounded_section_count": grounded,
        "unsupported_section_count": section_count - grounded,
        "citation_coverage": round(citation_coverage, 3),
        "source_document_count": source_document_count,
        "represented_document_count": represented_documents,
        "source_document_coverage": round(document_coverage, 3),
    }


def _source_dicts(chunks: list[Chunk]) -> list[dict]:
    return [source.to_dict() for source in _sources_from_chunks(_dedupe_chunks(chunks))]


def _dedupe_chunks(chunks: list[Chunk]) -> list[Chunk]:
    deduped: list[Chunk] = []
    seen: set[tuple[str, int, str]] = set()
    for chunk in chunks:
        metadata = chunk.metadata or {}
        key = (str(metadata.get("doc_id") or metadata.get("filename") or ""), chunk.page, chunk.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _source_key(source: dict) -> tuple[str, int, str]:
    return (
        str(source.get("doc_id") or source.get("filename") or ""),
        int(source.get("page") or 0),
        str(source.get("chunk_id") or ""),
    )


def _snapshot_key(source: dict) -> str:
    return str(source.get("filename") or source.get("doc_id") or "")


def _source_label(source: dict) -> str:
    filename = source.get("filename") or source.get("doc_id") or "document"
    page = source.get("page")
    chunk_id = source.get("chunk_id")
    location = f"{filename}"
    if page:
        location += f" · p.{page}"
    if chunk_id:
        location += f" · {chunk_id}"
    return location


def _citation_labels(sources: list[dict], source_numbers: dict[tuple[str, int, str], int]) -> str:
    labels = sorted({source_numbers.get(_source_key(source)) for source in sources} - {None})
    return "".join(f" [{label}]" for label in labels)


def _citation_links(sources: list[dict], source_numbers: dict[tuple[str, int, str], int]) -> str:
    labels = sorted({source_numbers.get(_source_key(source)) for source in sources} - {None})
    return "".join(f'<sup><a href="#source-{label}">[{label}]</a></sup>' for label in labels)
