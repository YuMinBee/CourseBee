# 한빛데이터 온보딩 어시스턴트 RAG 벤치마크 (Korean, blind)

This is a blind retrieval-augmented-generation benchmark for an AI onboarding assistant. The assistant answers employees' questions from internal company documents and must cite its sources. The corpus and questions were written **without any knowledge of the retriever or system under test**, so the benchmark does not favour any chunking, embedding or ranking strategy.

- Company: **주식회사 한빛데이터** (Hanbit Data Inc.), a fictional mid-size Korean SaaS company. All people, numbers and contacts are synthetic.
- **Reference date ("today"): 2026-10-06.** Questions about what applies now are judged against this date.
- Language: Korean, with English technical terms (SSO, VPN, MFA, SLA, P1/P2, PR, on-call, canary, …).

```
ragbench/
├── docs/              32 Markdown documents (the file name is the document id)
├── questions.jsonl    180 questions with gold answers and evidence quotes
├── validate.py        integrity checker (run: python validate.py)
└── README.md
```

## 1. Corpus

There are 32 documents with 57,237 characters in total. Documents range from 1,080 to 3,180 characters. They mix headings, prose, numbered procedures, Markdown tables, FAQ and Q&A blocks, meeting notes, release notes and checklists. "Q cited" is the number of questions whose evidence cites the document.

| Document id | Title | Area | Chars | Q cited |
|---|---|---|---:|---:|
| `hr_leave_policy_2025.md` | 휴가 및 연차 규정 (2025년판) — **outdated** | HR | 1,712 | 0 |
| `hr_leave_policy_2026.md` | 휴가 및 연차 규정 (2026년 개정, 2026-07-01 시행) | HR | 1,785 | 6 |
| `hr_attendance.md` | 근태 관리 규정 | HR | 1,502 | 8 |
| `hr_remote_work_2024.md` | 재택근무 운영 지침 (2024-02-01) — **outdated** | HR | 1,152 | 0 |
| `hr_remote_work_2026.md` | 재택근무 운영 지침 (2026-03-01 시행) | HR | 1,288 | 5 |
| `hr_business_trip.md` | 국내·해외 출장 및 출장비 규정 | HR/Finance | 2,239 | 9 |
| `hr_benefits.md` | 2026년 복리후생 안내 | HR | 1,941 | 10 |
| `security_policy_v1_2025.md` | 정보보안 정책 v1.0 (2025-01-01) — **outdated** | Security | 1,080 | 0 |
| `security_policy_v2_2026.md` | 정보보안 정책 v2.0 (2026-04-01 시행) | Security | 2,536 | 11 |
| `security_laptop_export.md` | 전산장비 반출입 관리 지침 | Security | 1,579 | 7 |
| `security_privacy_handling.md` | 개인정보 처리 지침 | Security | 1,634 | 7 |
| `security_incident_report.md` | 보안사고 신고 및 대응 절차 | Security | 1,657 | 6 |
| `security_account_management.md` | 계정 및 접근권한 관리 지침 | Security | 1,476 | 8 |
| `eng_code_review.md` | 코드 리뷰 가이드라인 | Engineering | 1,571 | 7 |
| `eng_branch_strategy.md` | 브랜치 전략 및 커밋 규칙 | Engineering | 1,774 | 5 |
| `eng_deploy_rollback.md` | 운영 배포 및 롤백 가이드 | Engineering | 1,672 | 6 |
| `eng_incident_runbook.md` | 서비스 장애 대응 Runbook | Engineering | 3,080 | 4 |
| `eng_oncall.md` | On-call 운영 규정 | Engineering | 1,535 | 7 |
| `eng_monitoring_alerts.md` | 모니터링 및 알람 기준 (2026-01-15, partly stale) | Engineering | 1,753 | 6 |
| `eng_postmortem_20260612.md` | 포스트모템: 2026-06-12 API 전면 장애 (P1) | Engineering | 1,741 | 5 |
| `it_helpdesk_faq.md` | IT 헬프데스크 FAQ | IT | 3,107 | 9 |
| `finance_expense_settlement.md` | 경비 지출 및 정산 가이드 | Finance | 1,545 | 6 |
| `finance_purchasing.md` | 구매 요청 및 승인 절차 | Finance | 1,646 | 4 |
| `onboarding_checklist.md` | 신규 입사자 온보딩 체크리스트 | Onboarding | 2,070 | 4 |
| `training_program.md` | 2026년 교육 프로그램 안내 (스타트업 캠프 1~4주차) | Training | 1,720 | 7 |
| `org_team_rnr.md` | 조직도 및 팀별 R&R | Org | 1,829 | 1 |
| `manual_hanbitwork.md` | 한빛워크(사내 포털) 사용자 매뉴얼 | Internal tool | 3,180 | 7 |
| `release_notes_hanbitwork.md` | 한빛워크 릴리스 노트 | Internal tool | 1,440 | 1 |
| `meeting_notes_eng_weekly_20260826.md` | 엔지니어링 주간 회의록 (2026-08-26) | Meeting notes | 1,439 | 3 |
| `meeting_notes_allhands_2026q3.md` | 2026년 3분기 전사 타운홀 회의록 | Meeting notes | 1,400 | 4 |
| `facilities_meeting_rooms.md` | 회의실 이용 안내 | Facilities | 1,527 | 6 |
| `facilities_parking_access.md` | 주차 및 출입 안내 | Facilities | 1,627 | 8 |

### Built-in difficulty
- **Overlapping topics.** The same subject appears in several documents:
  - 비밀번호, MFA and 계정 잠금 appear in both security policies, the IT FAQ and the account guide.
  - 휴가 appears in both leave policies, the onboarding checklist, the HanbitWork manual and the release notes.
  - VPN appears in the IT FAQ, the remote-work guidelines and security policy v2.
  - 노트북 반출 appears in the export guide, the business-trip rules and the onboarding checklist.
- **Version conflicts with effective dates.** The outdated documents stay in the corpus as distractors:

  | Topic | Outdated | Current (gold) |
  |---|---|---|
  | 휴가 규정 | 2025-01-01: 이월 5일/3월 31일, 3영업일 전 신청, 리프레시 5년·50만원, 반반차 없음 | 2026-07-01: 이월 10일/6월 30일, 1영업일 전, 3년·70만원, 반반차(2시간) |
  | 재택근무 | 2024-02-01: 주 2회, 전주 목요일 마감, 지원금 3만원, 응답 30분 | 2026-03-01: 주 3회 + 화요일 팀 출근일, 전주 금요일 15시, 5만원, 15분 |
  | 정보보안 정책 | v1.0 2025-01-01: 비밀번호 90일·9자·5회 잠금, 화면 잠금 10분 | v2.0 2026-04-01: 180일·12자·10회(30분) 잠금, 5분, 전 SSO MFA |
  | p95 알람 기준 | `eng_monitoring_alerts.md` (2026-01-15): Warning 800ms | 주간 회의 결정, 2026-09-01부터 1,000ms (the alert document was never updated) |
  | 복지포인트 | — | 2026년 120만원. 타운홀에서 발표된 150만원은 2027-01-01 시행이라 아직 미적용 |

- **Homonym trap: 주차.** It means parking (주차장, 정기주차) in `facilities_parking_access.md` and the town-hall notes, and week number (1주차, 2주차) in `training_program.md` and `onboarding_checklist.md`.
- **Distractor numbers next to the answer.** Examples:
  - 회의 식대 1만 5천원 vs 야근 식대 1만 2천원
  - P1 15분 / P2 30분 / on-call ack 5분 / escalation 15분
  - 5xx 롤백 2% vs 알람 1%/5%
  - 개인정보 권한 90일 vs 운영 권한 6개월
  - 보상휴가 1개월 (on-call) vs 3개월 (근태)
  - 자기계발비 100만원 vs 교육 예산 200만원
- **Similar-looking schemes.** Security incident grades S1–S3 are separate from service incident grades P1–P4.
- **Exceptions to rules.** Examples include "단, 팀장 승인 시 수습 기간에도 주 1회", CTO-approved hotfixes during a deploy freeze, and the 150% hotel cap.

## 2. Questions

There are 180 questions in `questions.jsonl`. They are written as employees would type them: casual Korean, mixed English terms, and some deliberate typos and spacing errors (헬프대스크, 어떡게, 몇일).

| Type | Count | What it tests |
|---|---:|---|
| `fact` | 60 | Single-fact lookup. Mixes heavy lexical overlap with paraphrase (e.g. "남편 건강검진도 회사에서 지원돼요?"). |
| `paraphrase` | 25 | Little or no keyword overlap with the evidence (e.g. "입사할 때 받은 랩탑 퇴근하면서 들고 가서 집에서 써도 되는 거지?" → 노트북 상시 반출). |
| `numeric` | 20 | The answer is a number, date or amount, and distractor numbers sit nearby. |
| `multi_hop` | 20 | Needs 2 or more documents (e.g. 출장 중 노트북 분실 → 신고 대상·기한 + 비용 처리). |
| `version_conflict` | 10 | Asks what applies now. The gold answer is the newest effective rule, or the current rule when a change takes effect in the future. |
| `procedure` | 15 | Steps or order of a process. |
| `unanswerable` | 30 | Plausible questions whose answer is not in the corpus. Many are near-misses that share keywords with real documents (e.g. on-call 수당 인상 시기, 형제자매 결혼 경조금, H스퀘어 주차장 요금). |

150 questions are answerable and 30 are unanswerable. Every non-outdated document is cited by at least one question. The three outdated documents are cited only in `notes`, because they are traps.

### Record format
```json
{"id": "q106", "type": "version_conflict", "question": "비번 몇 달마다 바꿔야 돼? 90일이었나?",
 "answer": "180일마다 (정보보안 정책 v2.0, 2026-04-01 시행)", "answerable": true,
 "evidence": [{"doc": "security_policy_v2_2026.md", "quote": "비밀번호 변경 주기는 180일로 한다. 만료 14일 전부터 SSO 로그인 화면과 메일로 변경 안내가 표시된다."}],
 "notes": "outdated (v2.0 시행으로 폐지): security_policy_v1_2025.md: «비밀번호는 90일마다 변경하여야 하며»"}
```

Questions are grouped by type in this id order:

| Type | Ids |
|---|---|
| fact | q001–q060 |
| paraphrase | q061–q085 |
| numeric | q086–q105 |
| version_conflict | q106–q115 |
| multi_hop | q116–q135 |
| procedure | q136–q150 |
| unanswerable | q151–q180 |

- `answer` is a short gold answer in Korean. For unanswerable questions it is exactly `문서에 없음`, with `"answerable": false` and `"evidence": []`.
- `evidence` lists the supporting spans:
  - `doc` is the file name in `docs/`.
  - `quote` is an exact, case- and whitespace-sensitive substring of that file's UTF-8 content. It is 20–200 characters and is the minimal span that proves (part of) the answer.
  - A question may have several quotes when the answer has several parts.
  - Every `multi_hop` question cites at least 2 different documents.
  - Quotes never span a line break. Table-row quotes keep the Markdown pipes (e.g. `| P2 | 30분 이내 | 8시간 이내 | 1시간마다 |`).
- `notes` (may be empty) explains the trap: the distractor numbers, the homonym, or why the question is unanswerable.
  - When `notes` cites another document, it uses the form `doc.md: «exact quote»`. `validate.py` checks these quotes too.
  - Every `version_conflict` item cites the outdated or not-yet-effective rule this way, while `evidence` holds only the current rule.

### Suggested scoring
- **Retrieval:**
  - Doc-level recall@k: an evidence doc appears in the top-k. For `multi_hop`, report how many of the evidence docs were retrieved and whether all of them were.
  - Span-level hit: a retrieved chunk contains the `quote`.
- **Answer:** correctness against `answer`, judged by a human or an LLM. Numbers and dates must match exactly.
- **Citation:** the cited source is one of the evidence docs. For `version_conflict`, citing only the outdated document, or answering with the outdated value, counts as wrong.
- **Abstention:** for `unanswerable`, credit is given only when the system says the information is not in the documents. It may mention related information it did find, but it must not invent an answer.

## 3. Validation

```
python validate.py
```

The script checks that:
- ids are unique and well formed
- the types are known
- `answerable` and `answer` are consistent with the type
- every evidence quote is an exact substring of its document and is 20–200 characters long
- `multi_hop` items cite 2 or more documents
- the `notes` quotes exist in the documents they cite

Current result: **PASSED** (32 docs, 180 questions, 0 problems).

## 4. How CourseBee uses this benchmark

- **Provenance.** The corpus and questions were written by a separate agent that had no access to the CourseBee code, so the retriever was not designed around them.
- **Dev / test split.** `eval/run_ragbench_retrieval.py --split dev|test` splits questions by the SHA-256 of their id into two halves of 90 questions (75 answerable + 15 unanswerable each). Tuning decisions such as the embedding model are made on `dev`; `test` is only used to report results.
- **Retrieval run.** `python eval/run_ragbench_retrieval.py` builds a course pack from `docs/`, asks every question and reports Hit@k, Full@k (all evidence documents retrieved) and MRR per question type, plus how well the top retrieval score separates answerable from unanswerable questions (AUC). CI runs it with a Hit@5 gate.
- **Integrity.** `tests/test_ragbench.py` re-checks evidence quotes, ids and the split on every test run.
