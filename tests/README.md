# tests

The current test suite targets the CourseBee v3 local demo while retaining v2 API compatibility checks.

Covered behavior:

- local `.txt`, `.md`, `.pdf`, and `.pptx` ingest
- page-level chunk source preservation
- source-grounded `/v2/ask`
- Course Pack overview retrieval balanced across documents
- Course Pack Summary source preservation, OpenAI fallback behavior, and citation_check validation
- Study Kit source preservation
- Audio Script source preservation
- Audio segment grounding reports and unsupported concrete-claim repair
- Onboarding report grounding, JSON/Markdown/HTML exports, source-change impact, and incremental section reuse
- GraphRAG-lite concept map generation
- Course Pack artifact preview and Mermaid/HTML concept map export
- OCR fallback provider behavior
- provider interface availability
- v2/v3 FastAPI route registration
- Playwright desktop report/RAG/upload flow, printable report, and mobile overflow checks

Run:

```bash
python -m unittest discover -s tests

# optional browser workflow
python -m pip install -e ".[e2e]"
python -m playwright install chromium
python -m unittest tests.test_browser_demo -v
```






