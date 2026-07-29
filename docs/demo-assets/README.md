# CourseBee Demo Assets

These files are generated only from the public synthetic fixtures in `v2/assets/demo_fixtures`. The v3 screenshots use enterprise onboarding fixtures; the preserved long-form audio bundle uses the NLP fixtures and the repository's built-in background knowledge.

| Asset | Description |
| --- | --- |
| `coursebee-v3-demo.png` | Playwright-verified enterprise onboarding workflow at 1440 x 900 |
| `coursebee-v3-demo-mobile.png` | Full-page v3 mobile layout at 390 x 844 |
| `coursebee-v3-onboarding-report.png` | Printable grounded onboarding report |
| `coursebee-v3-onboarding-report.html` | Standalone printable report artifact |
| `coursebee-v3-onboarding-report.md` | Markdown report artifact |
| `coursebee-v3-onboarding-report.json` | Structured report, source selection, quality, and generation metadata |
| `coursebee-demo.png` | Playwright-verified desktop RAG workflow at 1440 x 900 |
| `coursebee-demo-mobile.png` | Full-page mobile layout at 390 x 844 |
| `coursebee-audio-overview.mp3` | Qwen3 14B script with dual-voice Edge TTS, 13:09 |
| `coursebee-audio-overview-transcript.txt` | Exact speaker-ordered text used for TTS |
| `coursebee-audio-overview-grounding.json` | Script, sources, per-segment grounding results, and generation metadata |

Report snapshot:

- profile: development-team new joiner
- selected documents: 2 / 3, engineering workflow and security policy
- excluded document: employee handbook
- grounded sections: 2 / 2
- citation and selected-document coverage: 1.00 / 1.00
- formats: JSON, Markdown, standalone printable HTML

Audio snapshot:

- target / final script: 6,000 / 6,003 characters
- raw Qwen output: 4,878 characters
- segments: 38 total, 35 checked, 3 conversational context
- grounding: 35 / 35 checked segments passed, 0 unsupported, 16 repaired
- method: `lexical_claim_overlap_v1`, strict minimum coverage `0.35`
- measured duration: 789.0 seconds
- MP3 SHA-256: `7BB3B96EB0777371EF3576F95DA8A7CCF55B0085ADAEEA0C6457757A74661FBC`

The lexical check is a deterministic guardrail, not a semantic entailment score or a human listening-quality rating.
