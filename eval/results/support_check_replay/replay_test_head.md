# CourseBee support check replay

Generated: 2026-10-07 06:56:21 UTC

Drafts `eval/results/support_check_replay/test_5_drafts.json` (verdicts from `claude_verdict`), split `test`, checker `qwen3:14b`, COURSEBEE_RETRIEVAL=semantic, COURSEBEE_TODAY=2026-10-06.

committed check (no date)

| Draft group | n | Rewritten as not supported | Check failed (draft kept) |
| --- | ---: | ---: | ---: |
| correct draft (answerable) | 62 | 3 (5%) | 0 |
| partial draft (answerable) | 10 | 1 (10%) | 0 |
| wrong draft (answerable) | 1 | 0 (0%) | 0 |
| made-up draft (unanswerable) | 2 | 1 (50%) | 0 |
| refusal draft | 15 | 12 (80%) | 0 |

Rejected correct or partial drafts:

- q036 (fact): 질문은 '남편 건강검진'에 대한 지원 여부를 묻고 있으나, 근거 문서 [2]에서는 '배우자 검진 비용은 50%를 지원합니다'라고 명시되어 있어 '남편'이라는 대상에 대한 직접적인 언급이 없어 지원 여부가 명확하지 않습니다.
- q069 (paraphrase): 질문은 코드 리뷰가 지연된 이유에 대해 묻고 있으나, 근거 문서에는 코드 리뷰 응답 시간에 대한 목표와 리마인드 설정이 언급되지만, 리뷰가 지연되는 구체적인 원인에 대한 정보는 포함되어 있지 않다.
- q071 (paraphrase): 질문은 '가입 끊은 사람 데이터'의 보존 기간을 묻고 있지만, 근거 문서 [1]의 6번 항목에서 퇴사자 메일함은 30일간 보존된 후 삭제한다고 명시되어 있으나, '가입 끊은 사람 데이터'에 대한 직접적인 언급은 없으며, '데이터'의 범위가 명확하지 않아 근거에서 바로 따라 나오는 답이 아니다.
- q115 (version_conflict): 질문은 '복지포인트 올해 얼마야?'로, 2026년 복지포인트 금액을 묻고 있으나 근거 문서에서는 2026년 복지포인트가 120만원임을 명시하고 있으나, 답변 초안은 2026년 복지포인트가 120만원이 아닌 150만원이라고 잘못 인용하였다.

Wrong or made-up drafts that passed:

- q128 (multi_hop): 질문에서 묻는 대상(6월 12일 장애 때 처음 울린 알람)과 측면(등급, 등급 기준, 전달 경로)은 근거 문서에 명시되어 있으며, 답변 초안은 근거에 기반하여 정확히 답하고 있다.
- q159 (unanswerable): 질문에서 묻는 '렌터카 비용'은 근거 문서에 명시된 '교통비'와 관련되어 있으며, 출장비 정산 절차에 따라 처리될 수 있다는 내용이 근거에 명시되어 있어 질문에 대한 답이 근거에서 바로 따라 나온다.
