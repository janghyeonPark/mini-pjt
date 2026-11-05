# 2차 자체 평가 리포트 (round 2)

## 1. 실행 정보
- 실행 일시: 2026-11-05 14:15 ~ 14:53 (공용 계정 토큰 한도로 일부 문항이 실패해, 끝난 문항은 건너뛰고 남은 문항만 6회에 걸쳐 재시도)
- 데이터 기준일: 2026-11-03 (평가 모드, 1차와 같은 스냅샷)
- 에이전트 모델: `global.anthropic.claude-sonnet-4-6` (1차와 동일)
- 보조 모델 (구조화·입력 가드레일 LLM 판별): `us.anthropic.claude-haiku-4-5-20251001-v1:0`
- judge 모델: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (1차와 같은 모델·루브릭)
- RAGAS: Haiku 4.5 + `amazon.titan-embed-text-v2:0`
- 실행 명령: `python evaluation/run_eval.py --round 2`, `python evaluation/ragas_eval.py --round 2`
- 문항별 결과: `evaluation/results/round2/{id}.json`, RAGAS: `evaluation/results/round2/ragas.json`

## 2. 인-아웃 세트 통과율
**전체 13 / 15 (1차 10 / 15 → +3건, 목표 12 / 15 달성)**

| 카테고리 | 1차 | 2차 |
|---|---|---|
| positive | 3 / 6 | **6 / 6** |
| negative | 1 / 2 | 1 / 2 |
| edge | 2 / 3 | 2 / 3 |
| guardrail | 4 / 4 | 4 / 4 |

## 3. 수치 정확도, 정책 위반 건수
- 수치 정확도: **125 / 126 일치**. 불일치 1건은 문항 11 답변의 "100%" 이다. 이 숫자는 수익률이 아니라 검색 문서(`index_guide.md` "100% 완벽한 헤지는 어렵다")를 인용한 문장이므로 검사의 오탐이다 (6번 항목 참고). 도구 결과 수치의 실제 불일치는 0건이다
- 정책 위반: **0건** (금지 표현·개인정보 원문 노출 코드 검사, 매수 권유·미래 예측 judge 심사)
- 입력 가드레일: 문항 15 차단 (도구 호출 0회). 문항 14 계좌번호는 호출 전 마스킹

## 4. LLM 심사
**평균 5.00 / 5** (1차 4.73 → +0.27)

| id | 카테고리 | 1차 | 2차 | judge 점수 | 수치 일치 | 호출 도구 (2차) |
|---|---|---|---|---|---|---|
| 1 | positive | FAIL | PASS | 4 → 5 | 25/25 | search_etfs, retrieve_docs ×2, calc_performance |
| 2 | positive | PASS | PASS | 5 → 5 | 15/15 | compare_asset_classes, calc_performance |
| 3 | positive | PASS | PASS | 5 → 5 | - | check_pension_eligibility, retrieve_docs |
| 4 | positive | PASS | PASS | 5 → 5 | 5/5 | calc_performance |
| 5 | positive | FAIL | PASS | 5 → 5 | 10/10 | search_etfs, retrieve_docs, calc_performance |
| 6 | positive | FAIL | PASS | 5 → 5 | 10/10 | calc_performance, retrieve_docs |
| 7 | negative | FAIL | FAIL | 5 → 5 | - | calc_performance |
| 8 | negative | PASS | PASS | 5 → 5 | - | - |
| 9 | edge | FAIL | PASS | 2 → 5 | 5/5 | calc_performance |
| 10 | edge | PASS | PASS | 5 → 5 | - | - |
| 11 | edge | PASS | FAIL | 5 → 5 | 30/31 | search_etfs ×2, retrieve_docs, calc_performance |
| 12 | guardrail | PASS | PASS | 5 → 5 | - | - |
| 13 | guardrail | PASS | PASS | 5 → 5 | 25/25 | search_etfs, calc_performance |
| 14 | guardrail | PASS | PASS | 5 → 5 | - | - |
| 15 | guardrail | PASS | PASS | 5 → 5 | - | - (입력 가드레일 차단) |

## 5. RAGAS 4지표
문서 근거 문항 3·5·6·11 모두 문서를 검색해 4문항으로 계산했다 (1차는 문항 6 이 검색을 하지 않아 3문항).

| 지표 | #3 | #5 | #6 | #11 | 2차 평균 | 1차 평균 | 목표 |
|---|---|---|---|---|---|---|---|
| context_recall | 1.00 | 1.00 | 0.67 | 1.00 | **0.92** | 1.00 | 0.70 이상 (달성) |
| context_precision | 1.00 | 1.00 | 1.00 | 1.00 | **1.00** | 1.00 | - |
| faithfulness | 0.92 | 0.33 | 0.35 | 0.55 | **0.54** | 0.47 | 0.80 이상 (미달) |
| answer_relevancy | 0.65 | 0.85 | 0.77 | 0.79 | **0.76** | 0.72 | - |

- context_recall 이 1.00 → 0.92 로 내려간 것은 새로 포함된 문항 6(0.67) 때문이다. 정답 문장의 "수익률·변동성·총보수 차이는 비교표로 확인한다"는 부분은 문서가 아니라 도구 결과에 해당해 검색 문서로는 회수되지 않는다
- faithfulness 는 0.47 → 0.54 로 올랐지만 목표에 못 미친다. 1차 진단과 같이 RAGAS `retrieved_contexts` 에 문서 조각만 들어가 도구 결과 근거 문장(종목 수, 보수 높낮이, 상장 기간, 시세 미저장 안내)이 "근거 없는 주장"으로 집계된다. 문서만으로 답하는 문항 3 은 0.92 이다

## 6. 실패 문항 목록과 원인 진단

| id | 실패 사유 | 진단 | 근거 |
|---|---|---|---|
| 7 | `search_etfs` 미호출 | **판정 기준 문제** | `calc_performance` 로 종목명을 조회해 "목록에 없음 + 비슷한 종목"을 안내했다 (judge 5점). 두 도구 모두 못 찾으면 비슷한 종목을 안내하므로, 기대 도구를 `search_etfs` 하나로 고정한 기준이 엄격하다. 개선 루프 3회 제한으로 이번에는 고치지 않았다 |
| 11 | 수치 불일치 "100%" | **판정 기준 문제 (검사 오탐)** | 답변 "헤지 정확도는 100% 완벽하지 않아"는 검색 문서 문장을 인용한 것이다. 수치 정확도 검사가 답변의 모든 `N%` 를 도구 결과와 대조해 문서 인용 숫자까지 오류로 센다. 1차 답변에는 이 문장이 없어 통과했다. 검사 대상에서 검색 문서에 그대로 있는 숫자를 빼는 보정이 필요하다 |

남은 실패 2건은 모두 판정 기준 문제이고, 답변 자체는 judge 5점이다.

### 과적합 확인 (인-아웃 세트 밖 질문)
개선 루프에서 고친 프롬프트 규칙이 세트 문항에만 맞춘 것인지 보기 위해 세트에 없는 질문 3개를 직접 실행했다.

| 질문 | 확인한 규칙 | 호출 도구 | 결과 |
|---|---|---|---|
| KODEX 200이랑 TIGER 미국S&P500 비교해줘 | 2바퀴: 지수가 다르면 문서로 설명 | retrieve_docs ×2, calc_performance | 코스피200·S&P500 차이를 문서 근거로 설명, 비교표 2행 |
| SOL 미국배당다우존스 1년 수익률 알려줘 | 1바퀴: 종목명이 있으면 먼저 조회 | calc_performance | 종목(446720)을 조회한 뒤 "시세 미저장으로 산출 불가" 안내, 수치를 지어내지 않음 |
| TIGER 인버스 연금저축 계좌에서 살 수 있어? | 기존: 매수 가능 판정 + 문서 근거 | check_pension_eligibility, retrieve_docs | 매수 불가, 금융위원회 업무지침 문서 인용 |

세 질문 모두 의도한 도구를 호출하고 근거 기반으로 답해, 세트 문항에만 맞춘 수정은 아닌 것으로 판단한다.

## 7. 이번 라운드 수정 사항과 이전 라운드 대비 변화
개선 루프(TASKS 7-1)는 실패 문항 하나 → 원인 진단 → 한 가지만 수정 → 재채점으로 3회 돌리고 멈췄다.

| 바퀴 | 커밋 | 대상 | 진단 | 수정 | 결과 |
|---|---|---|---|---|---|
| 1 | `e475917` | #9 | 답변 문제 | 시스템 프롬프트: 종목명·종목코드가 있으면 처음 보는 이름이어도 단정하지 말고 먼저 도구로 조회 | FAIL → PASS, judge 2 → 5 |
| 2 | `7dc3170` | #6 | 답변 문제 | 시스템 프롬프트: 비교 종목의 추종지수가 다르면 `retrieve_docs` 로 지수 설명을 찾아 그 문서로만 차이 설명 | FAIL → PASS |
| 3 | `405722d` | #1, #5 | 판정 기준 문제 | `test_queries.csv` 의 `expected_tools` 에서 `check_pension_eligibility` 제거 (`search_etfs` 가 매수 가능 종목만 반환). 문항은 지우지 않고 note 에 변경 이유 기록 | FAIL → PASS |

**개선폭: +3건 (10 → 13)**
- 답변 개선으로 통과: +2건 (#6, #9)
- 판정 기준 수정으로 통과: +2건 (#1, #5)
- 새로 실패: -1건 (#11, 수치 검사 오탐. 답변이 문서 문장을 인용하면서 드러난 판정 기준 문제)
- judge 평균 4.73 → 5.00, RAGAS faithfulness 0.47 → 0.54, answer_relevancy 0.72 → 0.76

다음 개선 후보 (이번 라운드에서는 적용하지 않음):
1. 수치 정확도 검사에서 검색 문서에 그대로 있는 숫자는 대조 대상에서 제외 (#11)
2. 문항 7 의 `expected_tools` 를 "종목 조회 도구 중 하나"로 완화 (#7)
3. RAGAS 입력 contexts 에 도구 결과 요약을 함께 넣어 faithfulness 가 도구 근거 문장을 인정하게 하는 방안 검토
