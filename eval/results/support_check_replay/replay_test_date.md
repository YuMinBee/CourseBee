# CourseBee support check replay

Generated: 2026-10-07 06:59:51 UTC

Drafts `eval/results/support_check_replay/test_5_drafts.json` (verdicts from `claude_verdict`), split `test`, checker `qwen3:14b`, COURSEBEE_RETRIEVAL=semantic, COURSEBEE_TODAY=2026-10-06.

date-aware check

| Draft group | n | Rewritten as not supported | Check failed (draft kept) |
| --- | ---: | ---: | ---: |
| correct draft (answerable) | 62 | 4 (6%) | 0 |
| partial draft (answerable) | 10 | 1 (10%) | 0 |
| wrong draft (answerable) | 1 | 0 (0%) | 0 |
| made-up draft (unanswerable) | 2 | 1 (50%) | 0 |
| refusal draft | 15 | 12 (80%) | 0 |

Rejected correct or partial drafts:

- q036 (fact): 질문은 '남편 건강검진'에 대한 지원 여부를 묻고 있으나, 근거 문서 [2]에서는 '배우자 검진 비용은 50%를 지원합니다'라고 명시되어 있어 '남편'에 대한 지원 여부는 명시되지 않았다.
- q069 (paraphrase): 질문은 코드 리뷰가 지연된 이유에 대해 묻고 있으나, 근거 문서에는 코드 리뷰 응답 시간에 대한 목표와 리마인드 설정이 언급되지만, 리뷰가 지연되는 구체적인 이유나 해결 방안에 대한 정보는 포함되어 있지 않다.
- q071 (paraphrase): 근거 문서 [6]에 따르면 퇴사자의 메일함은 퇴사일로부터 30일간 보존한 뒤 삭제하지만, '가입 끊은 사람 데이터'에 대한 보존 기간은 명시되어 있지 않다.
- q084 (paraphrase): 질문은 자녀의 입학 축하금에 대한 지원 여부를 묻고 있으나, 답변 초안은 초등학교 입학 시 30만원을 지급한다고 명시하지만, 질문의 대상(우리 애, 1학년)은 초등학교 입학에 해당하지 않아 근거에 직접적으로 나오지 않습니다.
- q115 (version_conflict): 근거 문서에 2026년 복지포인트 금액은 120만원으로 명시되어 있으나, 질문은 '올해' 복지포인트 금액을 묻고 있으므로 2026년에 해당하는 120만원이 답이어야 하나, 답변 초안은 2027년 인상 내용을 포함하여 질문에 대한 명확한 답을 제공하지 않았다.

Wrong or made-up drafts that passed:

- q128 (multi_hop): 질문이 묻는 대상(6월 12일 장애 때 처음 울린 알람)과 측면(등급, 등급 기준, 전달 경로)은 근거 문서에 명시되어 있으며, 답변 초안은 근거에 기반하여 정확히 답하고 있다.
- q159 (unanswerable): 질문이 묻는 대상(렌터카 비용)과 측면(비용 처리 여부)은 근거 문서에 명시된 출장비 정산 절차에 따라 답할 수 있다.
