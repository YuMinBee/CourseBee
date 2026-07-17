from __future__ import annotations

import json
import re
from pathlib import Path

from v2.io_utils import atomic_write_json, atomic_write_text


def artifact_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9가-힣_.-]+", "-", text or "answer").strip("-_.")
    return (cleaned or "answer")[:80]


def save_artifact(output_dir: Path, name: str, payload: dict) -> Path:
    path = output_dir / name
    atomic_write_json(path, payload)
    return path


def artifact_preview(path: Path, include_content: bool) -> dict:
    exists = path.exists() and path.is_file()
    size_bytes = path.stat().st_size if exists else 0
    minimum_ready_size = 2 if path.suffix.lower() == ".json" else 0
    preview = {
        "name": path.name,
        "path": str(path),
        "exists": exists,
        "ready": exists and size_bytes > minimum_ready_size,
        "size_bytes": size_bytes,
    }
    if not exists or not include_content:
        return preview
    if path.suffix.lower() == ".json":
        try:
            preview["data"] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            preview["error"] = f"invalid json: {error}"
        return preview
    text = path.read_text(encoding="utf-8")
    preview["text"] = text[:12000]
    preview["truncated"] = len(text) > 12000
    return preview


def export_concept_map(graph: dict, output_dir: Path, max_nodes: int, max_edges: int) -> dict:
    max_nodes = max(1, max_nodes)
    max_edges = max(1, max_edges)
    nodes = graph.get("nodes", [])[:max_nodes]
    node_ids = {node.get("id") for node in nodes}
    edges = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("source") in node_ids and edge.get("target") in node_ids
    ][:max_edges]
    warnings: list[str] = []
    if len(graph.get("nodes", [])) > len(nodes):
        warnings.append(f"Concept map export limited nodes to {len(nodes)} of {len(graph.get('nodes', []))}.")
    if len(graph.get("edges", [])) > len(edges):
        warnings.append(f"Concept map export limited edges to {len(edges)} of {len(graph.get('edges', []))}.")

    mermaid = concept_map_mermaid(nodes, edges)
    html = concept_map_html(mermaid)
    mermaid_path = output_dir / "concept_map.mmd"
    html_path = output_dir / "concept_map.html"
    atomic_write_text(mermaid_path, mermaid)
    atomic_write_text(html_path, html)
    return {
        "format": "mermaid",
        "mermaid_path": str(mermaid_path),
        "html_path": str(html_path),
        "mermaid": mermaid,
        "exported_node_count": len(nodes),
        "exported_edge_count": len(edges),
        "warnings": warnings,
    }


def concept_map_mermaid(nodes: list[dict], edges: list[dict]) -> str:
    lines = ["flowchart LR"]
    id_map = {str(node.get("id")): f"n{index}" for index, node in enumerate(nodes)}
    for node in nodes:
        node_id = str(node.get("id"))
        mermaid_id = id_map[node_id]
        label = _mermaid_label(str(node.get("label") or node_id))
        shape = "{{{label}}}" if node.get("type") == "document" else "[{label}]"
        lines.append(f"  {mermaid_id}{shape.format(label=label)}")
    for edge in edges:
        source = id_map.get(str(edge.get("source")))
        target = id_map.get(str(edge.get("target")))
        if not source or not target:
            continue
        relation = _mermaid_label(str(edge.get("relation") or "related_to"))
        lines.append(f"  {source} -- {relation} --> {target}")
    return "\n".join(lines) + "\n"


def concept_map_html(mermaid: str) -> str:
    escaped = mermaid.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="ko">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>CourseBee Concept Map</title>",
            "  <style>body{font-family:Arial,sans-serif;margin:24px;background:#f7f7f8;color:#171717}.wrap{max-width:1200px;margin:auto;background:white;border:1px solid #ddd;border-radius:8px;padding:20px}pre{white-space:pre-wrap;background:#111;color:#eee;padding:16px;border-radius:6px;overflow:auto}</style>",
            "</head>",
            "<body>",
            '  <div class="wrap">',
            "    <h1>CourseBee Concept Map</h1>",
            "    <p>Mermaid diagram generated from source-grounded concept relationships.</p>",
            '    <div class="mermaid">',
            escaped,
            "    </div>",
            "    <h2>Mermaid Source</h2>",
            f"    <pre>{escaped}</pre>",
            "  </div>",
            "  <script type=\"module\">import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs'; mermaid.initialize({startOnLoad:true});</script>",
            "</body>",
            "</html>",
        ]
    )


def _mermaid_label(text: str) -> str:
    cleaned = " ".join(text.split())[:80]
    return '"' + cleaned.replace("\\", "\\\\").replace('"', '\\"') + '"'
