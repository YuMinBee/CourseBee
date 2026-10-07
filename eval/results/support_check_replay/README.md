# Support check replay

`eval/run_support_check_replay.py` re-runs only the answer support check on fixed drafts whose correctness was judged in the blind review, so check prompts can be compared without generation noise. See docs/RAG_BENCHMARK.md, section 2.

| File | Drafts | Check prompt |
| --- | --- | --- |
| `replay_dev3_head.json` / `replay_dev3_date.json` | `ragbench_answers/dev_3_kure_prompt.json` (check off) | first version / with the reference date |
| `replay_dev5_head.json` / `replay_dev5_date.json` | `ragbench_answers/dev_5_kure_prompt_think.json` (check off) | first version / with the reference date |
| `replay_test_head.*` / `replay_test_date.*` | `test_5_drafts.json`: answers of `ragbench_answers/test_5_kure_prompt_dated_check.json`, with the original draft wherever the check rewrote it | first version / with the reference date |

Each row has the draft's blind verdict (`draft_verdict`), the check result (`check`) and the checker's reason.
