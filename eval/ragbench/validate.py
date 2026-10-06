"""Validate the Korean onboarding-assistant RAG benchmark.

Usage: python validate.py            (run from this directory)
Exit code 0 = all checks passed.
"""
import json, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
TYPES = {"fact", "paraphrase", "numeric", "multi_hop", "version_conflict", "procedure", "unanswerable"}
NOTE_QUOTE = re.compile(r"([A-Za-z0-9_]+\.md): «(.+?)»")

docs = {f: open(os.path.join(DOCS, f), encoding="utf-8").read()
        for f in sorted(os.listdir(DOCS)) if f.endswith(".md")}
errors = []
def err(qid, msg): errors.append(f"{qid}: {msg}")

rows = [json.loads(l) for l in open(os.path.join(HERE, "questions.jsonl"), encoding="utf-8") if l.strip()]
ids = [r.get("id") for r in rows]
for qid, n in Counter(ids).items():
    if n > 1: err(qid, f"duplicate id ({n}x)")

for r in rows:
    qid = r.get("id", "?")
    for k in ("id", "type", "question", "answer", "answerable", "evidence"):
        if k not in r: err(qid, f"missing key {k}")
    if not re.fullmatch(r"q\d{3}", str(qid)): err(qid, "bad id format")
    t = r.get("type")
    if t not in TYPES: err(qid, f"unknown type {t}")
    ev = r.get("evidence", [])
    if t == "unanswerable":
        if r.get("answerable") is not False: err(qid, "unanswerable must have answerable=false")
        if ev: err(qid, "unanswerable must have empty evidence")
        if r.get("answer") != "문서에 없음": err(qid, "unanswerable answer must be '문서에 없음'")
    else:
        if r.get("answerable") is not True: err(qid, "answerable question must have answerable=true")
        if not ev: err(qid, "answerable question needs evidence")
    for e in ev:
        d, q = e.get("doc"), e.get("quote", "")
        if d not in docs: err(qid, f"evidence doc not found: {d}"); continue
        if q not in docs[d]: err(qid, f"quote not an exact substring of {d}: {q[:60]}")
        if not 20 <= len(q) <= 200: err(qid, f"quote length {len(q)} outside 20-200")
    if t == "multi_hop" and len({e.get("doc") for e in ev}) < 2:
        err(qid, "multi_hop needs evidence from >=2 different docs")
    notes = r.get("notes", "") or ""
    if t == "version_conflict" and not NOTE_QUOTE.search(notes):
        err(qid, "version_conflict notes must cite the outdated rule as 'doc.md: «quote»'")
    for d, q in NOTE_QUOTE.findall(notes):
        if d not in docs: err(qid, f"notes cite unknown doc {d}")
        elif q not in docs[d]: err(qid, f"notes quote not found in {d}: {q[:60]}")

print(f"docs: {len(docs)}  total characters: {sum(len(s) for s in docs.values())}")
print(f"questions: {len(rows)}  by type: {dict(Counter(r.get('type') for r in rows))}")
print(f"answerable: {sum(1 for r in rows if r.get('answerable'))}  unanswerable: {sum(1 for r in rows if r.get('answerable') is False)}")
if errors:
    print(f"FAILED with {len(errors)} problem(s):")
    for e in errors: print("  -", e)
    sys.exit(1)
print("PASSED: all evidence quotes are exact substrings, ids unique, types/answerable consistent, multi_hop spans >=2 docs.")
