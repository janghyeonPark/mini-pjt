# 미니 PJT: 연금저축 ETF 비교 분석 Agent

## 무엇을 푸나
연금저축 계좌로 ETF에 투자할 때 "무엇을 살 수 있고, 같은 기준으로 비교하면 어떤지"를 한곳에서 보기 어려워 한 번 판단에 약 2시간이 걸리는 문제를, 매수 가능 종목만 실제 시세로 계산한 비교표와 문서 근거로 수 분 안에 답한다.

## 활용한 패턴 (Day 1~7)
- Day 1: 구조화 출력 — 최종 답변을 pydantic `FinalAnswer{answer, comparison_table, sources, base_date}` 로 받는다. LLM(Haiku)은 설명 문장과 표에 넣을 종목코드만 고르고(`with_structured_output`), 숫자는 코드가 도구 결과에서 옮긴다
- Day 2: RAG — 매매 규칙·기초지수 문서를 `MarkdownHeaderTextSplitter` 로 헤더 단위 분할하고, Chroma(Titan 임베딩) + BM25(`kiwipiepy` 형태소) 를 `EnsembleRetriever`(0.3/0.7) 로 결합한다. 검색 결과에 `[출처: 파일 > 섹션]` 을 붙여 반환한다
- Day 3: ReAct 에이전트 — 도구 5개(검색·매수 가능 판정·수익률 계산·자산군 대표 비교·문서 검색)를 에이전트가 질문에 맞게 골라 호출한다
- Day 4: 도구 설계·에러 처리·trace — 독스트링에 "언제 쓰고 언제 쓰지 않는지"를 적고, 시세·문서 조회 실패는 예외 대신 "지어내지 말고 실패로 안내" 메시지로 반환한다. LLM·도구 호출은 콜백 트레이서로 단계별 기록한다
- Day 5: `create_agent` + 미들웨어 — 입력 가드레일(정규식 → Haiku 인젝션 판별), 도구 호출 제한, 출력 가드레일(금지 표현 → 1회 재생성 → 고정 문구), 로깅. 개인정보 마스킹은 trace 에 원문이 남지 않도록 에이전트 호출 전에 적용하고, 체크포인터로 화면 대화를 이어간다
- Day 6: (적용 안 함) Supervisor — 도구 5개라 단일 에이전트로 충분하다. HITL(Day 5)도 매매 주문을 빼서 승인할 위험 작업이 없다
- Day 7: LLM 심사·누적 평가셋 — 고정 루브릭 judge(Haiku) 위에 코드 판정(도구 호출·금지 항목·수치 정확도·정책 위반)을 둔 채점 스크립트와 RAGAS 4지표

## 아키텍처
```
화면(index.html) / POST /query  ──  FastAPI (src/api.py)
  → 개인정보 마스킹 (계좌번호·주민번호·전화·이메일)
  → create_agent (Sonnet 4.6) + 미들웨어 [입력 가드레일 → 도구 호출 제한 → 출력 가드레일 → 로깅] + 체크포인터
       ├─ search_etfs               KRX ETF 목록 CSV + 자산군 매핑 + 매수 가능 판정 + 시가총액 정렬
       ├─ check_pension_eligibility 추적배수 규칙 (레버리지·인버스 불가) + 근거 출처
       ├─ calc_performance          pykrx 시세 스냅샷 → 1년·3년 가격수익률·연환산 변동성
       ├─ compare_asset_classes     자산군별 대표 ETF (매수 가능 종목 중 시가총액 1위)
       └─ retrieve_docs             하이브리드 검색 (Chroma + BM25) → [출처] 붙은 문서 조각
  → 구조화 단계 (Haiku): 설명 문장 + 표에 넣을 종목코드
  → 코드가 비교표 생성, 기준일·정의·면책·근거 문서 부착, 금지 표현 재검사
  → {answer, contexts, trace} (+ 화면용 comparison_table, thread_id)
트레이서 콜백: LLM·도구 호출을 단계별로 logs/trace.jsonl 에 기록
```

## 실행 방법
<!-- 작성 중 -->
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# .env 에 AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

python src/agent.py "미국 S&P500 추종 ETF 중에 연금저축으로 살 수 있는 거 비교해줘"
python evaluation/run_eval.py --ids 1,4          # 일부 문항 채점 (개발용 round0)
python evaluation/run_eval.py --round 1          # 라운드 전체 채점

# API 서버 (POST /query → {answer, contexts, trace})
uvicorn api:app --app-dir src --port 8000
# 대화형 화면: 브라우저에서 http://localhost:8000 (같은 대화 안에서 "그중 환헤지만" 처럼 이어 묻기 가능)
```

```powershell
# 호출 예 (PowerShell). 한글이 깨지지 않게 본문을 UTF-8 바이트로 보낸다
$body = [Text.Encoding]::UTF8.GetBytes('{"question": "KODEX 레버리지 연금저축에서 살 수 있어?"}')
Invoke-RestMethod -Uri http://localhost:8000/query -Method Post -ContentType "application/json; charset=utf-8" -Body $body
```

## RAGAS 평가 결과
2차 라운드 기준, 문서 근거 문항 4개(3·5·6·11) 평균. 평가 LLM Haiku 4.5, 임베딩 Titan v2
- context_recall: 0.92 (목표 0.70 이상)
- context_precision: 1.00
- faithfulness: 0.54 (목표 0.80 미달. RAGAS contexts 에 문서 조각만 들어가 도구 결과 근거 문장이 근거 없음으로 집계됨. 문서만으로 답하는 문항 3 은 0.92)
- answer_relevancy: 0.76

## 인-아웃 세트 통과율 (자체 평가)
- 1차 (Day 9 종료): 10 / 15 통과
- 2차 (Day 10 개선 후): 13 / 15 통과
- 개선폭: +3 건 (주요 개선 사항: 종목명이 있으면 먼저 도구로 조회 · 지수가 다른 비교는 문서로만 설명 → 답변 개선 +2, `search_etfs` 가 매수 가능 판정을 포함하므로 기대 도구 기준 수정 +2, 수치 검사 오탐 -1. 상세는 `evaluation/round2_report.md`)

## 트라이앤에러 회고
<!-- 작업 중 메모. 제출 전에 세 항목으로 정리한다 -->
- 시도했지만 실패한 접근 · 왜 실패했는가
  - pykrx 로 ETF 전종목 목록 조회 → KRX 로그인이 필요해 실패. 로그인 없이 쓰려고 KRX 정보데이터시스템 CSV 다운로드본으로 전환
  - 투자설명서 PDF를 전부 RAG에 넣는 안 → 보수 같은 수치는 CSV에 이미 있어 문서 검색이 할 일이 없음. 매매 규칙·지수 설명만 공개 자료로 정리
  - 미국 주식 판별에 "다우존스" 키워드 사용 → "Dow Jones Taiwan" 이 미국 주식으로 분류됨. 다우존스·러셀은 지수 산출사 이름이라 제외
  - "S&P500" 검색을 기초지수명만으로 → 커버드콜·주식채권 혼합 상품이 상위에 섞임. 구조가 달라 같은 표에서 비교하면 왜곡되므로 기본 제외
  - 답변 문장에 수치를 쓰게 둠 → 총보수 0.004% 를 0.04% 로 옮겨 적는 전사 오류 발생
  - 출처·대표 선정 기준·개인정보 안내를 프롬프트로만 요구 → 구조화 단계(LLM)가 매번 일부를 빠뜨림. 필수 문구는 코드가 답변에 붙이는 방식으로 전환
  - 도구 결과의 총보수를 단위 없는 숫자(`"fee": 0.006`)로 넘김 → LLM이 비율로 읽어 "0.6%"로 100배 틀리게 씀. 필드에 단위(`fee_pct`, "연 0.006%")를 붙여 해결
  - 금지 표현을 단순 문자열로 검사 → "사세요라고 할 수 없다" 같은 부정문도 걸려 정상 답변이 고정 문구로 대체됨. 프롬프트에 "부정문으로도 쓰지 않는다"를 넣어 완화 (문자열 검사의 한계는 남음)
  - 개인정보 정규식에 `\b` 사용 → 한글이 붙은 "678901이고" 를 못 잡음. 앞뒤 숫자 경계로 변경. 채점 스크립트가 judge 에 원문을 넘겨 판정 근거에 계좌번호가 남은 것도 발견해 수정
  - RAGAS answer_relevancy 를 기본 프롬프트로 계산 → 역생성 질문이 영어로 나와 한국어 원 질문과 임베딩 유사도가 낮게 나옴 (문항 3: 0.36). 질문을 답변과 같은 언어로 만들라는 지시 한 줄을 덧붙여 0.69 로 정상화 (Titan 기준 같은 뜻 한국어 문장 쌍 0.69, 한·영 쌍 0.36)
  - 매매 규칙 문서를 증권사(삼성증권) 홈페이지에서 수집 → 자바스크립트 렌더링이라 본문을 받지 못함. 레버리지·인버스 제한은 증권사 공통 규칙이라 금융위원회 보도자료·운용사 안내로 전환
- 최종 채택한 접근 · 왜 그것으로 갔는가
  - 비교표는 도구 결과로 코드가 생성하고 LLM은 설명 문장과 종목코드 선택만 → 수치 정확도를 구조적으로 보장
  - 평가 모드 기준일 고정(2026-11-03) + 시세·시가총액 스냅샷 → 1차·2차 평가에서 같은 질문에 같은 수치
  - 인-아웃 세트의 forbidden 이 설명문이라 문자열 검사가 안 됨 → 항목별 코드 검사 함수 대응표 + 나머지는 judge 판정
- 남은 한계 · 향후 개선 방향
  - 수익률이 분배금 미포함 가격수익률이라 배당형 상품은 불리하게 보임
  - 시가총액이 기준일 값이 아니라 수집 시점(2026-11-05 장중) 값
  - 평가 모드는 후보 19종목만 시세가 있음. 평소 모드(실시간 조회)는 TASKS 8-1

## 핵심 코드 위치
- `src/agent.py:114` — 메인 에이전트 그래프 (`create_agent` + 미들웨어 + 체크포인터)
- `src/agent.py:215` — `_run()`: 마스킹 → 에이전트 → 구조화 → 코드 생성 비교표
- `src/tools.py` — 도메인 도구 (`search_etfs:65`, `check_pension_eligibility:103`, `calc_performance:122`, `compare_asset_classes:154`)
- `src/retriever.py` — RAG 파이프라인 (`get_retriever:50` 하이브리드 검색, `retrieve_docs:80`)
- `src/guards.py` — 가드레일 (`input_guard:75`, `mask_pii:104`, 미들웨어 `:126`·`:163`·`:190`)
- `src/etf_data.py:45` — 자산군 매핑 규칙
- `src/metrics.py:17` — 수익률·변동성 계산
- `src/api.py:57` — `POST /query`, `src/static/index.html` — 대화형 화면
- `evaluation/run_eval.py:91` — 수치 정확도 검사, `:123` — forbidden 코드 검사 대응표
- `evaluation/ragas_eval.py` — RAGAS 4지표
