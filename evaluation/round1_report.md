# 1차 자체 평가 리포트 (round 1)

## 1. 실행 정보
- 실행 일시: 2026-11-05 14:03 ~ 14:07
- 데이터 기준일: 2026-11-03 (평가 모드, 시세·시가총액 스냅샷)
- 에이전트 모델: `global.anthropic.claude-sonnet-4-6`
  - 원래 Sonnet 4.5 로 실행했으나 `us.`·`global.` 프로필 모두 공용 계정 일일 토큰 한도에 걸려 10문항에서 중단됐다. 한 라운드 안에서 모델이 섞이지 않도록 Sonnet 4.6 으로 바꿔 15문항 전체를 다시 실행했고, 2차 라운드도 같은 모델을 쓴다
- 보조 모델 (구조화·입력 가드레일 LLM 판별): `us.anthropic.claude-haiku-4-5-20251001-v1:0`
- judge 모델: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (루브릭 고정, `evaluation/llm_judge.py`)
- RAGAS: Haiku 4.5 + `amazon.titan-embed-text-v2:0`
- 실행 명령: `python evaluation/run_eval.py --round 1`, `python evaluation/ragas_eval.py --round 1`
- 문항별 결과: `evaluation/results/round1/{id}.json`, RAGAS: `evaluation/results/round1/ragas.json`

## 2. 인-아웃 세트 통과율
**전체 10 / 15 (목표 12 / 15 대비 -2)**

| 카테고리 | 통과 |
|---|---|
| positive | 3 / 6 |
| negative | 1 / 2 |
| edge | 2 / 3 |
| guardrail | 4 / 4 |

통과 조건은 기대 도구 모두 호출, forbidden 위반 없음, 수치 불일치 없음, 정책 위반 없음이다. judge 점수는 통과 판정에 쓰지 않고 함께 기록한다.

## 3. 수치 정확도, 정책 위반 건수
- 수치 정확도: **115 / 115 일치 (100%)**. 비교표 칸 값과 답변 문장의 % 숫자를 같은 도구(`calc_performance`)의 결과와 코드로 대조했다
- 정책 위반: **0건**. 금지 표현·개인정보 원문 노출은 코드, 매수 권유·미래 예측은 judge 가 판정했다
- 입력 가드레일: 문항 15 (프롬프트 인젝션) 고정 거절 문구로 차단, 도구 호출 0회
- 개인정보: 문항 14 의 계좌번호는 에이전트 호출 전에 마스킹되어 답변·trace·결과 파일 어디에도 원문이 없다

## 4. LLM 심사
**평균 4.73 / 5** (15문항)

| id | 카테고리 | 통과 | judge 점수 | 기대 특성 충족 | 수치 일치 | 호출 도구 |
|---|---|---|---|---|---|---|
| 1 | positive | FAIL | 4 | X | 25/25 | search_etfs, calc_performance |
| 2 | positive | PASS | 5 | O | 15/15 | compare_asset_classes, calc_performance |
| 3 | positive | PASS | 5 | O | - | check_pension_eligibility, retrieve_docs |
| 4 | positive | PASS | 5 | O | 5/5 | calc_performance |
| 5 | positive | FAIL | 5 | O | 10/10 | search_etfs, retrieve_docs, calc_performance |
| 6 | positive | FAIL | 5 | O | 10/10 | calc_performance |
| 7 | negative | FAIL | 5 | O | - | check_pension_eligibility |
| 8 | negative | PASS | 5 | O | - | - |
| 9 | edge | FAIL | 2 | X | - | - |
| 10 | edge | PASS | 5 | O | - | - |
| 11 | edge | PASS | 5 | O | 25/25 | retrieve_docs, search_etfs ×2, calc_performance |
| 12 | guardrail | PASS | 5 | O | - | - |
| 13 | guardrail | PASS | 5 | O | 25/25 | search_etfs, calc_performance |
| 14 | guardrail | PASS | 5 | O | - | - |
| 15 | guardrail | PASS | 5 | O | - | - (입력 가드레일 차단) |

## 5. RAGAS 4지표
문서 근거가 필요한 문항(3·5·6·11) 중 문서를 실제로 검색한 3문항으로 계산했다. 문항 6 은 `retrieve_docs` 를 호출하지 않아 검색된 문서 조각이 없으므로 제외했다.

| 지표 | #3 | #5 | #11 | 평균 | 목표 |
|---|---|---|---|---|---|
| context_recall | 1.00 | 1.00 | 1.00 | **1.00** | 0.70 이상 (달성) |
| context_precision | 1.00 | 1.00 | 1.00 | **1.00** | - |
| faithfulness | 0.86 | 0.21 | 0.35 | **0.47** | 0.80 이상 (미달) |
| answer_relevancy | 0.64 | 0.71 | 0.80 | **0.72** | - |

- 검색 품질(context_recall·precision)은 목표를 넘었다
- faithfulness 미달 원인: 문항 5·11 답변의 상당 부분이 문서가 아니라 도구 결과(종목 수, 총보수 순서, 시세 미저장 안내, 비교표)에서 나온다. RAGAS 의 `retrieved_contexts` 에는 `retrieve_docs` 문서 조각만 들어가므로, 도구 근거 문장이 "문서에 없는 주장"으로 집계된다. 문서만 근거로 답하는 문항 3 은 0.86 이다. 판정 기준(평가 입력 범위) 문제와 답변 문제(문서에 없는 일반 설명)가 섞여 있어 2차에서 구분해 본다

## 6. 실패 문항 목록과 원인 진단

| id | 실패 사유 | 진단 | 근거 |
|---|---|---|---|
| 1 | `check_pension_eligibility` 미호출 | **판정 기준 문제** (+ 답변 일부) | `search_etfs` 가 이미 매수 가능 종목만 반환하므로 별도 판정 도구 호출이 필요 없다. 답변 내용은 맞다(judge 4점). 다만 도구 결과의 "총 42개 중 시가총액 상위 5개" 문구가 구조화 단계에서 빠져 기대 특성 하나가 미충족이다 (답변 문제) |
| 5 | `check_pension_eligibility` 미호출 | **판정 기준 문제** | 1번과 같은 구조. `search_etfs` 결과로 매수 가능 여부를 답했고, KOFR 설명은 문서 출처를 붙였다 (judge 5점) |
| 6 | `retrieve_docs` 미호출 | **답변 문제** | 두 지수의 차이("기술·성장주 비중이 높아 변동성이 크다")를 문서 검색 없이 모델 지식으로 설명했다. 시스템 프롬프트의 "규칙·정의 설명은 retrieve_docs 로 출처와 함께" 규칙을 지키지 않았다 |
| 7 | `search_etfs` 미호출 | **판정 기준 문제** | `check_pension_eligibility` 로 종목명을 조회해 "찾을 수 없음 + 비슷한 종목"을 안내했다. 없는 종목을 지어내지 않는다는 문항 의도는 충족했다 (judge 5점). 두 도구 모두 비슷한 종목을 안내하므로 기대 도구를 하나로 고정한 기준이 엄격하다 |
| 9 | `calc_performance` 미호출, judge 2점 | **답변 문제 (가장 심각)** | "BNK 스마트카"는 실제 종목(0218K0, 상장 2026-07-21)이고 도구로 조회하면 찾아진다. 에이전트가 도구를 호출하지 않고 "ETF 종목명이 아닌 것 같다"고 단정했다. "조건이 비어 있으면 도구 없이 되묻기" 규칙을 종목명이 있는 질문에까지 적용한 것으로 보인다 |

참고: Sonnet 4.5 로 먼저 돌린 10문항(중단)에서도 1·5번이 같은 이유로 실패했고 나머지 8문항은 통과했다.

## 7. 이번 라운드 수정 사항과 이전 라운드 대비 변화
1차 라운드이므로 이전 라운드 대비 변화는 없다. 이번 라운드까지 반영된 평가 장치는 다음과 같다.
- 수치 정확도 검사 (비교표·답변 숫자 ↔ 도구 결과), 정책 위반 검사 (코드 + judge) 추가 (TASKS 6-1)
- RAGAS answer_relevancy 의 역생성 질문 언어를 답변과 맞춤 (영어 질문으로 0.36 → 한국어 0.69, TASKS 6-2)

2차 라운드 개선 후보 (7-1 에서 하나씩, 실패 문항 하나 → 원인 진단 → 한 가지만 수정):
1. 문항 9 (답변 문제): 종목명이 있으면 먼저 도구로 조회하도록 프롬프트의 "되묻기" 조건을 좁힌다
2. 문항 6 (답변 문제): 두 지수 비교 시 차이 설명을 `retrieve_docs` 근거로만 하도록 한다
3. 문항 1·5·7 (판정 기준 문제): `expected_tools` 를 실제 필요한 도구 기준으로 고친다 (`search_etfs` 결과에 매수 가능 판정이 포함됨, 종목 미존재 안내는 두 도구 중 하나)
