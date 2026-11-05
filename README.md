# 미니 PJT: 연금저축 ETF 비교 분석 Agent

## 무엇을 푸나
연금저축 계좌로 ETF에 투자할 때 "무엇을 살 수 있고, 같은 기준으로 비교하면 어떤지"를 한곳에서 보기 어려워 한 번 판단에 약 2시간이 걸리는 문제를, 매수 가능 종목만 실제 시세로 계산한 비교표와 문서 근거로 수 분 안에 답한다.

## 활용한 패턴 (Day 1~7)
<!-- 작성 중: 구현이 끝난 항목부터 채운다 -->
- Day 1: 구조화 출력 — 최종 답변을 pydantic `FinalAnswer{answer, comparison_table, sources, base_date}` 로 받고, LLM은 설명 문장과 표에 넣을 종목코드만 고른다 (`with_structured_output`)
- Day 2: RAG — (TASKS 3-3 예정) 매매 규칙·지수 설명 문서 하이브리드 검색 (벡터 + BM25 `kiwipiepy`)
- Day 3: ReAct 에이전트 — 도구 3개(검색·매수 가능 판정·수익률 계산)를 에이전트가 골라 호출
- Day 4: 도구 설계 — 독스트링에 "언제 쓰고 언제 쓰지 않는지", 못 찾으면 비슷한 종목·가능한 자산군을 안내
- Day 4: 도구 에러 처리 — 시세 조회 실패도 예외 대신 "지어내지 말고 조회 실패로 안내" 메시지로 반환
- Day 5: `create_agent` + 미들웨어 — (TASKS 4 예정) 입력·출력 가드레일, 로깅. 개인정보 마스킹은 trace에 원문이 남지 않도록 호출 전에 적용
- Day 6: (적용 안 함) Supervisor — 도구 5개라 단일 에이전트로 충분. HITL(Day 5)도 매매 주문을 빼서 승인할 위험 작업이 없음
- Day 7: LLM-as-Judge·누적 평가셋 — 고정 루브릭 judge(Haiku) + 코드 판정 채점 스크립트

## 아키텍처
<!-- 작성 중 -->
```
질문 → ReAct 에이전트 (Sonnet 4.5)
         ├─ search_etfs               KRX ETF 목록 CSV + 자산군 매핑 + 매수 가능 판정 + 시가총액 정렬
         ├─ check_pension_eligibility 추적배수 규칙 (레버리지·인버스 불가)
         └─ calc_performance          pykrx 시세 스냅샷 → 1년·3년 가격수익률·연환산 변동성
      → 구조화 단계 (Haiku): 설명 문장 + 표에 넣을 종목코드
      → 비교표는 calc_performance 결과로 코드가 생성
      → {answer, comparison_table, sources, base_date}
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
```

```powershell
# 호출 예 (PowerShell). 한글이 깨지지 않게 본문을 UTF-8 바이트로 보낸다
$body = [Text.Encoding]::UTF8.GetBytes('{"question": "KODEX 레버리지 연금저축에서 살 수 있어?"}')
Invoke-RestMethod -Uri http://localhost:8000/query -Method Post -ContentType "application/json; charset=utf-8" -Body $body
```

## RAGAS 평가 결과
- context_recall: (6-2 예정)
- context_precision:
- faithfulness:
- answer_relevancy:

## 인-아웃 세트 통과율 (자체 평가)
- 1차 (Day 9 종료): XX / 15 통과
- 2차 (Day 10 개선 후): XX / 15 통과
- 개선폭: +XX 건 (주요 개선 사항: ...)

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
- `src/agent.py:92` — 메인 에이전트 (`create_agent`)
- `src/agent.py:127` — `run()`: 에이전트 → 구조화 → 코드 생성 비교표
- `src/tools.py` — 도메인 도구 (`search_etfs:52`, `check_pension_eligibility:93`, `calc_performance:112`)
- `src/retriever.py` — RAG 파이프라인 (예정)
- `src/etf_data.py:45` — 자산군 매핑 규칙
- `src/metrics.py:17` — 수익률·변동성 계산
- `evaluation/run_eval.py:80` — forbidden 코드 검사 대응표
