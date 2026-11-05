# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 성격

자기 도메인의 **Agentic RAG 어시스턴트**를 만드는 개인 미니 프로젝트. 주제는 자유이며 `SERVICE.md` 가 정한다.

| 문서 | 역할 |
|---|---|
| `SERVICE.md` | **무엇을 왜** 만드는가 (사용자·문제·가치·확장 관점·도구/데이터·정책·성공 기준). 판단 기준이 되는 유일한 문서 |
| `TASKS.md` | 작업 목록. 한 번에 하나씩 처리 |
| `CLAUDE.md` | **어떻게** 만드는가 (스택·구조·규약) |
| `ref/` | 이전에 만든 완성 코드. **읽기 전용 참고 자료**, 수정하지 않는다 |

## 작업 규칙

- 무엇을 만드는지는 `SERVICE.md` 가 기준이다. 애매하면 추측하지 말고 물어본다. 새로 정해진 결정은 `SERVICE.md` 에 반영을 제안한다.
- `TASKS.md` 는 `SERVICE.md` 를 구현 순서대로 쪼갠 작업 목록이다 (레포 루트). 작성 규칙:
  - 작업 하나는 30분~1시간 크기
  - 작업마다 "다 됐는지 확인하는 방법"을 한 줄씩 붙인다 (실행 명령과 기대 결과처럼 확인 가능한 형태)
  - 첫 묶음은 입력 → 최종 답변까지 **한 경로만** 돌아가는 최소 버전. 도구·가드레일·평가 등은 그 뒤 묶음에서 하나씩 붙인다
  - `TASKS.md` 를 만들거나 고칠 때는 코드를 쓰지 않는다
- 한 번에 `TASKS.md` 의 작업 하나만 한다. 끝나면 확인 방법을 실제로 실행해 결과를 보여주고 체크한다. 여러 파일에 걸친 작업은 먼저 계획(파일별 변경 내용)을 보여주고 승인받은 뒤 구현한다.
- 레퍼런스: `ref/` 에 같은 역할의 코드가 있으면 그 구조를 따르고, 없으면 괜찮은 GitHub 코드를 찾아 참고한다.
- **사용자 허락 없이 새 프레임워크나 라이브러리를 들이지 않는다** (`requirements.txt` 에 없는 패키지는 먼저 물어본다).
- 계산과 규칙 판정은 LLM이 아니라 **파이썬 코드**로 한다. LLM 판정은 필요할 때 그 위에 덧붙인다.
- 요청하지 않은 파일은 만들지 않는다. 기존 파일을 통째로 다시 쓰지 않고 바뀐 부분만 고친다.
- 비밀 값은 `.env` 에서 읽고 코드에 적지 않는다.

## 폴더 구조 (고정. 바꾸지 않는다)

```
src/agent.py         메인 에이전트 그래프 + 진입점
src/tools.py         도메인 도구
src/retriever.py     RAG 파이프라인 (적재, 검색)
src/...              그 외 역할별 모듈 (가드레일, 트레이서, API 서버 등). 파일 하나에 역할 하나
data/                사용한 문서와 데이터 (더미 생성 스크립트 포함 가능)
evaluation/test_queries.csv     인-아웃 세트 (아래 스키마)
evaluation/ragas_references.csv RAGAS 정답 문장 (id, reference). test_queries.csv 컬럼은 7개 고정이라 분리
evaluation/round{N}_report.md   N차 자체 평가 결과
SERVICE.md, README.md, requirements.txt
Dockerfile, run.sh   선택
```

## API 규약

```
POST /query   {"question": "..."}
→ {"answer": "근거 기반 응답",
   "contexts": [{"doc_id": "...", "text": "..."}],
   "trace":    [{"step": "retrieve", "input": "...", "output": "..."}]}
```

- `contexts` 는 실제로 검색된 문서 조각 (`doc_id` 는 문서 `metadata["source"]` 등 출처 식별자).
- `trace` 는 콜백 핸들러로 수집한다 (`ref/local_tracer.py` 의 `FileTracer` 방식으로 LLM·도구 호출을 단계별 기록).
- API 서버는 FastAPI + uvicorn (`src/` 안 별도 모듈). 에이전트 로직은 `src/agent.py` 에 두고 서버는 호출만 한다.

## 인-아웃 세트: `evaluation/test_queries.csv`

컬럼: `id,category,input,expected_traits,forbidden,expected_tools,note`

- `category`: `positive`(~40%) / `negative`(~20%, 없는 정보 → 지어내지 않고 안내) / `edge`(~25%) / `guardrail`(~15%, 정책 위반 유도·PII·프롬프트 인젝션)
- `expected_traits`, `forbidden`, `expected_tools` 안의 여러 값은 **세미콜론(`;`)** 으로 구분. 여러 줄 필드는 큰따옴표로 감싼다.
- 15~20건 권장 (최소 10건). 통과한 문항도 지우지 않는다 (회귀 감지용).
- guardrail 문항은 `SERVICE.md` 4번 정책과 1:1로 맞춘다.
- `expected_tools` 에 쓰는 도구 이름은 고정이다. `src/tools.py` 의 도구 이름도 이와 같아야 한다: `search_etfs`, `compare_asset_classes`, `calc_performance`, `check_pension_eligibility`, `retrieve_docs`

## 평가와 개선 루프

- 채점 스크립트(`ref/run_eval.py` 구조 참고)는 문항마다 에이전트를 실행하고 **코드로** 판정한다:
  - `expected_tools` → 콜백으로 수집한 실제 호출 도구와 비교
  - `forbidden` → 답변에 포함되면 실패
  - `expected_traits` → **LLM-as-Judge** 로 판정 (`ref/llm_judge.py` 구조: judge 모델·루브릭 상수 고정, pydantic 결과 `{score 1~5, is_met, missing, reasoning}`). judge 모델은 라운드가 바뀌어도 바꾸지 않는다. 사람은 실패·애매 문항만 확인한다
  - 카테고리별·전체 통과율을 출력하고 `evaluation/round{N}_report.md` 로 저장
- RAG 품질 지표: `context_recall`, `context_precision`, `faithfulness`, `answer_relevancy` 를 `ragas` 로 산출해 리포트와 README에 기록 (평가용 LLM·임베딩도 위 Bedrock 모델을 `LangchainLLMWrapper`/`LangchainEmbeddingsWrapper` 로 래핑해 쓴다).
  - 호환 이슈: ragas 0.4.3 은 `langchain_community.chat_models.vertexai.ChatVertexAI`, `langchain_community.llms.VertexAI` 를 import 하는데 설치된 langchain-community 0.4.x 에는 없다. `import ragas` **전에** 두 이름을 빈 클래스로 `sys.modules` / 모듈 속성에 주입하는 shim을 둔다 (VertexAI는 쓰지 않으므로 동작에 영향 없음).
- 라운드 리포트 `evaluation/round{N}_report.md` 양식 (매 라운드 같은 항목):
  1. 실행 정보: 실행 일시, 데이터 기준일, 에이전트 모델, judge 모델
  2. 인-아웃 세트 통과율: 전체, 카테고리별 (목표 15건 중 12건 대비)
  3. 수치 정확도, 정책 위반 건수
  4. LLM 심사: 평균 점수, 문항별 점수
  5. RAGAS 4지표 (목표값 대비)
  6. 실패 문항 목록과 원인 진단 (답변 문제 / 판정 기준 문제)
  7. 이번 라운드 수정 사항과 이전 라운드 대비 변화 (2차부터)
- 개선 루프: 채점 → 실패 문항 **하나** 선택 → 원인이 답변인지 판정 기준인지 진단 → **한 가지만** 수정 → 재채점. 전부 통과하거나 3회 반복하면 멈추고 무엇을 고쳤는지 정리한다. 라운드 간 개선폭을 리포트에 명시한다.
- 시도했다가 버린 접근과 그 이유는 README의 회고 섹션에 쓸 수 있도록 그때그때 메모해 둔다.

## README 구성 (제출 템플릿. 제목·순서 그대로)

```
# 미니 PJT: [프로젝트 이름]
## 무엇을 푸나              한 문장으로 사용자 문제
## 활용한 패턴 (Day 1~7)     "- Day X: 패턴 — 어떻게 활용" 형식
## 아키텍처                  간단 다이어그램 or 텍스트 설명
## 실행 방법
## RAGAS 평가 결과           context_recall · context_precision · faithfulness · answer_relevancy (0.XX)
## 인-아웃 세트 통과율 (자체 평가)   1차 (Day 9 종료) XX/XX · 2차 (Day 10 개선 후) XX/XX · 개선폭 +XX건 (주요 개선 사항)
## 트라이앤에러 회고          시도했지만 실패한 접근·왜 / 최종 채택한 접근·왜 / 남은 한계·향후 개선 방향
## 핵심 코드 위치            `src/agent.py:NN` — 메인 에이전트 그래프, `src/tools.py` — 도메인 도구, `src/retriever.py` — RAG 파이프라인
```

- Day별 패턴 대응 (`ref/README.txt` 기준): 2일차 RAG, 3일차 도구 호출, 4일차 MCP 서버, 5일차 입력 가드레일, 6일차 Supervisor 멀티 에이전트, 7일차 Plan-and-Execute·장기 기억·트레이스·LLM 심사·평가셋

## 적용할 패턴

필수: 구조화 출력(pydantic `with_structured_output`) · RAG · 트레이스 · 평가.
가능하면 아래 중 여러 개를 조합한다: ReAct 도구 선택, 다중 도구 결합, MCP 서버, 입력/출력 가드레일(PII·인젝션), HITL(`interrupt()` 로 위험 작업 승인), 미들웨어(요약·마스킹·재시도), Multi-Agent Supervisor, Plan-Execute, 장기 메모리(Store), 하이브리드 검색·리랭킹·쿼리 확장(`rank-bm25`, `kiwipiepy`).

## 환경

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # 실행 정책 오류 시: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
```

- `.env`: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`. 모듈 상단에서 `load_dotenv()`.
- LLM은 AWS Bedrock만 사용한다. 기본형: `ChatBedrockConverse(model="us.anthropic.claude-sonnet-4-5-20250929-v1:0", region_name="us-east-1", temperature=0)`
- 사용 가능한 Bedrock 모델 ID (이 목록 밖의 모델은 쓰지 않는다):
  - Claude: `us.`/`global.anthropic.claude-sonnet-4-5-20250929-v1:0`, `us.`/`global.anthropic.claude-sonnet-4-6`, `us.`/`global.anthropic.claude-haiku-4-5-20251001-v1:0`
  - Nova: `us.amazon.nova-pro-v1:0`, `us.amazon.nova-lite-v1:0`, `us.`/`global.amazon.nova-2-lite-v1:0`
- 임베딩: `BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0", region_name="us-east-1")` (1024차원, 호출 확인됨)
- **Bedrock 일일 토큰 한도**(공용 계정, `ThrottlingException: Too many tokens per day`)에 실제로 걸린 적이 있다. 대응:
  - 모델 역할 분리: 에이전트 = Sonnet 4.5, 가드레일 LLM 판별·LLM-as-Judge·RAGAS = Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`). 모델 ID는 설정 상수 한곳에 둔다
  - Bedrock 호출은 지수 백오프로 재시도한다
  - 평가 스크립트는 문항별 결과를 즉시 파일에 저장하고, 재실행 시 끝난 문항은 건너뛴다
  - 개발 중 확인은 문항 1~2개만 돌리고, 15문항 전체 실행은 라운드 리포트를 낼 때만 한다
- 실행은 레포 루트에서 `python src/agent.py` 처럼 한다. 데이터 경로는 `__file__` 기준으로 잡아 실행 위치에 의존하지 않게 한다.

## ref 참고 대응표

| 만들려는 것 | 참고할 ref 파일 | 핵심 구조 |
|---|---|---|
| 더미 데이터 | `make_data.py` | 상수 리스트 → `BASE` 기준 JSON 생성 |
| 도구 / MCP 서버 | `mcp_server.py` | 독스트링에 "언제 쓰고 / 언제 쓰지 않는지(대신 쓸 도구)" + `Args:`. 결과는 `json.dumps(..., ensure_ascii=False)`, 못 찾으면 가능한 값 목록을 안내 |
| RAG 검색 | `final_scenario.py` `retrieve_docs` | `Chroma(...).as_retriever(k=3)` → `[출처: source]` 붙여 반환 |
| 멀티 에이전트 | `final_scenario.py` | `create_react_agent(llm, tools, prompt, name)` 하위 Agent + `create_supervisor(...).compile()`, `async def build_app()` |
| 단계형 워크플로 | `plan_and_execute.py` | `TypedDict` State + structured output + `StateGraph` (planner → execute → replan ⟲ → finalize) |
| 장기 기억 | `long_term_memory.py` | `InMemoryStore` 네임스페이스 `("users", user_id)` (라벨에 점 불가) |
| 입력 가드레일 | `guards_input.py`, `guards_refusal.py` | 정규식 1차 → LLM 2차, `input_guard(text) -> (blocked, reason)`, 고정 거절 문구 + 사유는 로그에만 |
| 트레이스 | `local_tracer.py` | `BaseCallbackHandler` 로 run_id별 시간·토큰 기록, `config["callbacks"]` 로 주입 |
| 평가 | `run_eval.py`, `llm_judge.py` | 콜백으로 하위 Agent 도구 호출 수집, 문항마다 새 `thread_id`, 고정 루브릭 judge |

## 코드 관례

- 비교표(`comparison_table`)는 **도구 결과로 코드가 직접 만든다**. LLM은 설명 문장(`answer`)만 쓰고 숫자를 옮겨 적지 않는다 (반올림·전사 오류로 수치 정확도가 깨지는 것을 막기 위함)
- `ChatBedrockConverse` 의 `content` 는 블록 리스트일 수 있으므로 항상 `get_text(message)` 헬퍼로 텍스트를 꺼낸다.
- Supervisor 그래프는 미들웨어를 받지 않는다 → 가드레일은 그래프 호출 **전에** 따로 실행한다.
- MCP 도구를 쓰면 앱 생성·호출 모두 async (`await build_app()`, `ainvoke`).
- 에이전트 프롬프트에는 "도구로 조회한 결과만 근거로 답하라, 없는 항목은 지어내지 말고 안내하라"를 넣는다.
- 거절 문구를 바꾸면 채점 스크립트의 차단 신호도 같이 바꾼다.
- 함수와 도구에는 한국어 docstring. 파일 첫 줄은 `# 파일명.py - 한 줄 설명`. 주석·프롬프트·출력 문구는 한국어.
