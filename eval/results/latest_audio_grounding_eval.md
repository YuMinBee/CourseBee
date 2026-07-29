# CourseBee Audio Grounding Evaluation

Generated: 2026-07-29 17:19:37 UTC

Deterministic cases verify supported claims, conversational transitions, invented model names, numeric claims, and strict Korean grounding.

| Metric | Result |
| --- | --- |
| Classification accuracy | 6 / 6 |
| Unsupported-claim detection | 3 / 3 |

| Case | Expected | Actual | Coverage | High-risk terms | Status |
| --- | --- | --- | ---: | --- | --- |
| `supported_bpe_claim` | grounded / pass | grounded / pass | 1.000 | - | PASS |
| `supported_lstm_claim` | grounded / pass | grounded / pass | 1.000 | - | PASS |
| `conversational_transition` | context / pass | context / pass | 0.000 | - | PASS |
| `unsupported_model_name` | unsupported / fail | unsupported / fail | 0.800 | `quantumtransformerx` | PASS |
| `unsupported_numeric_claim` | unsupported / fail | unsupported / fail | 0.429 | `reaches`, `97`, `percent`, `accuracy` | PASS |
| `unsupported_korean_claim_strict` | unsupported / fail | unsupported / fail | 0.000 | - | PASS |
