# agent.py - 연금저축 ETF 비교 에이전트 (ReAct + 구조화 답변) 진입점
import json
import re
import sys
import uuid

from botocore.config import Config
from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from config import AGENT_MODEL, AUX_MODEL, BANNED_PHRASES, BASE_DATE, REGION
from langchain.agents.middleware import ToolCallLimitMiddleware

from guards import (
    BLOCKED_OUTPUT_MESSAGE, REFUSAL_MESSAGE, InputGuardrailMiddleware, LoggingMiddleware,
    OutputGuardrailMiddleware, find_banned, log_block, mask_pii,
)
from metrics import RETURN_DEFINITION, VOLATILITY_DEFINITION
from tools import DISCLAIMER, TOOLS
from tracer import Tracer

# Bedrock 호출은 botocore 적응형 재시도(지수 백오프)로 감싼다
BEDROCK_RETRY = Config(retries={"max_attempts": 6, "mode": "adaptive"})
PII_NOTICE = "※ 입력하신 개인정보(계좌번호·연락처 등)는 마스킹했으며 저장하거나 사용하지 않습니다."
DATA_SOURCES = [
    "KRX 정보데이터시스템 ETF 전종목 기본정보 (2026-11-04 다운로드)",
    "pykrx 일별 종가",
    "네이버 금융 ETF 시가총액 (정렬용)",
]

SYSTEM_PROMPT = f"""너는 연금저축 계좌로 ETF에 투자하는 사람을 돕는 'ETF 비교 도우미'다.
데이터 기준일은 {BASE_DATE} 이다.

규칙:
- 도구로 조회·계산한 결과만 근거로 답한다. 도구 결과에 없는 종목·수치는 지어내지 말고 없다고 안내한다.
- 후보를 비교할 때는 search_etfs 로 후보를 찾고, calc_performance 로 수치를 계산한다.
  비교하는 종목들의 추종지수가 서로 다르면 retrieve_docs 로 각 지수 설명을 찾아, 지수 차이는 그 문서 내용으로만 설명한다.
- 특정 종목의 연금저축 매수 가능 여부는 check_pension_eligibility 로 판정하고, 그 사유(왜 안 되는지·왜 되는지)는 retrieve_docs 로 매매 규칙 문서를 확인한 내용만 설명한다. 문서에 없는 제한(예: 커버드콜 제한)을 덧붙이지 않는다.
- 매매 규칙의 근거, 기초지수 정의, 환헤지·위험 요인 설명은 retrieve_docs 로 문서를 찾아 답하고, 답변에 [출처: 파일명] 을 밝힌다. 문서에 없는 규칙·세율·한도는 지어내지 말고 문서에 없다고 안내한다.
- 수익률·변동성·보수·시가총액 숫자는 답변 문장에 쓰지 않는다. 비교표는 도구 결과로 자동 생성되므로 "비교표 참고"로 가리키고, 문장에는 차이의 성격(환헤지 여부, 보수 높낮이, 상장 기간 등)만 설명한다.
- 특정 종목을 사라고 권하지 않는다("선택하시기 바랍니다" 같은 권유 표현 포함). 비교와 근거만 제공한다.
- 미래 수익률을 예측하지 않는다.
- 금지 표현 {BANNED_PHRASES} 는 부정문·인용으로도 쓰지 않는다 (예: "사세요라고 할 수 없다" 대신 "특정 종목을 권하지 않는다").

[질문 유형별 대응]
- 추천 요청("뭐 사야 돼?", "하나만 찍어줘"): 거절로 끝내지 않는다. 특정 종목을 권하지 않는다고 한 문장으로 밝히고,
  자산군·추종지수 등 조건을 되물으며, 조건을 주면 비교표를 만들어 줄 수 있다고 제안한다.
- 조건이 전혀 없는 질문("아무거나 비교해줘"): 도구를 부르지 말고 자산군·추종지수·키워드 중 하나를 되묻는다.
  자산군·추종지수·키워드 중 하나라도 있으면 되묻지 말고 바로 검색·계산한다.
- 종목명·종목코드가 들어 있는 질문: 처음 보는 이름이어도 ETF가 아니라고 단정하지 말고 먼저 도구(calc_performance 등)로 조회한다.
  도구가 찾지 못했을 때만 목록에 없다고 안내한다.
- 미래 수익률 예측 요청("내년에 몇 % 오를까?"): 예측하지 않는다고 밝힌 뒤, 질문한 대상의 과거 1년·3년 수익률을
  search_etfs 와 calc_performance 로 실제 계산해 비교표로 보여준다.
- 질문에 [MASKED_...] 가 있으면 개인정보가 마스킹된 것이다. 개인정보는 저장·사용하지 않는다고 안내하고, 계좌번호 등을 되묻지 않는다.
- 답변은 한국어로 간결하게 쓴다."""

STRUCTURE_PROMPT = """아래는 사용자 질문과 ETF 비교 도우미의 답변이다. 이를 최종 응답 형식으로 정리하라.

- answer: 답변의 설명 문장. 수익률·변동성·보수 같은 숫자는 옮겨 적지 말고 "아래 비교표 참고"처럼 표를 가리킨다.
  매수 가능 여부, 차이점, 산출 불가·시세 미저장 같은 안내는 그대로 남긴다. 종목 추천·미래 예측 문장은 넣지 않는다.
- table_codes: 비교표에 넣을 종목코드. 계산된 종목코드 목록 안에서만 고른다. 비교표가 필요 없으면 빈 목록.

[질문]
{question}

[도우미 답변]
{draft}

[계산된 종목코드]
{codes}"""


class AnswerDraft(BaseModel):
    """LLM이 채우는 부분: 설명 문장과 비교표에 넣을 종목코드 (숫자는 쓰지 않는다)."""
    answer: str = Field(description="설명 문장 (숫자는 비교표에 맡긴다)")
    table_codes: list[str] = Field(description="비교표에 넣을 종목코드 목록")


class TableRow(BaseModel):
    """비교표 한 행. 도구 결과에서 코드가 그대로 옮긴다."""
    name: str
    code: str
    asset_class: str
    index_name: str
    fee_pct: float = Field(description="총보수 (%, 연)")
    return_1y: float | str
    return_3y: float | str
    volatility_1y: float | str
    volatility_3y: float | str
    hedged: bool
    listed_date: str
    base_date: str


class FinalAnswer(BaseModel):
    answer: str
    comparison_table: list[TableRow]
    sources: list[str]
    base_date: str


def get_text(message) -> str:
    """ChatBedrockConverse는 content를 블록 리스트로 주기도 하므로 텍스트만 모아 반환한다."""
    content = message.content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return content


def make_llm(model: str) -> ChatBedrockConverse:
    return ChatBedrockConverse(model=model, region_name=REGION, temperature=0, config=BEDROCK_RETRY)


agent = create_agent(
    make_llm(AGENT_MODEL), TOOLS, system_prompt=SYSTEM_PROMPT, name="etf_agent",
    middleware=[  # 순서는 ref/day5_practice/day5_final.py 를 따른다
        InputGuardrailMiddleware(),               # 1순위: 주입이면 모델 호출 없이 고정 문구로 거절
        ToolCallLimitMiddleware(run_limit=10),    # 도구 무한 호출 방지
        OutputGuardrailMiddleware(),              # 최종 응답 금지 표현 → 1회 재생성 → 고정 문구
        LoggingMiddleware(),                      # 마지막: 정제된 응답과 토큰 사용량만 기록
    ],
    checkpointer=InMemorySaver(),  # 같은 thread_id 면 이전 대화를 이어간다 (서버 메모리, 재시작 시 사라짐)
)
structurer = make_llm(AUX_MODEL).with_structured_output(AnswerDraft)


def collect_performance(messages) -> dict[str, dict]:
    """대화 기록에서 calc_performance 도구 결과를 찾아 종목코드별 계산 결과를 모은다 (나중 호출이 우선)."""
    rows = {}
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "calc_performance":
            try:
                data = json.loads(m.content)
            except json.JSONDecodeError:
                continue
            for item in data.get("items", []):
                if "code" in item and "error" not in item:
                    rows[item["code"]] = item
    return rows


def selection_rule(messages) -> str | None:
    """compare_asset_classes 결과에서 대표 ETF 선정 기준 문구를 꺼낸다."""
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "compare_asset_classes":
            try:
                return json.loads(m.content).get("selection_rule")
            except json.JSONDecodeError:
                return None
    return None


def collect_doc_sources(messages) -> list[str]:
    """retrieve_docs 결과에서 실제로 검색된 문서 조각의 출처를 순서대로 중복 없이 모은다."""
    found = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "retrieve_docs":
            for label in re.findall(r"\[출처: ([^\]]+)\]", m.content):
                if f"문서: {label}" not in found:
                    found.append(f"문서: {label}")
    return found


def build_table(codes: list[str], perf: dict[str, dict]) -> list[TableRow]:
    """도구 결과로 비교표를 만든다. LLM은 종목코드만 고르고 숫자는 여기서 그대로 옮긴다."""
    table = []
    for code in codes:
        it = perf.get(code)
        if it is None:
            continue
        table.append(TableRow(
            name=it["name"], code=it["code"], asset_class=it["asset_class"], index_name=it["index_name"],
            fee_pct=it["fee_pct"], return_1y=it["return_1y"], return_3y=it["return_3y"],
            volatility_1y=it["volatility_1y"], volatility_3y=it["volatility_3y"],
            hedged=it["hedged"], listed_date=str(it["listed_date"]), base_date=str(it["base_date"]),
        ))
    return table


def run(question: str, config: dict | None = None) -> FinalAnswer:
    """질문 하나를 에이전트로 처리해 구조화된 최종 답변을 반환한다."""
    return _run(question, config)[0]


def query(question: str, thread_id: str | None = None) -> dict:
    """API·평가용: 답변과 함께 실제 검색된 문서 조각(contexts)과 단계별 trace 를 반환한다.

    thread_id 를 주면 그 대화를 이어가고, 없으면 새 대화로 시작한다 (평가는 문항마다 새 대화).
    """
    thread_id = thread_id or str(uuid.uuid4())
    tracer = Tracer(trace_id=thread_id)
    fa, messages = _run(question, {"configurable": {"thread_id": thread_id}, "callbacks": [tracer]})
    return {"answer": fa.answer, "contexts": collect_contexts(messages), "trace": tracer.steps,
            "tools": tracer.tools, "result": fa, "thread_id": thread_id}


def current_turn(messages: list) -> list:
    """대화 기록에서 마지막 사용자 질문부터의 메시지만 남긴다. 이전 턴의 비교표·근거가 섞이지 않게 하기 위함."""
    last = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    return messages[last:]


def collect_contexts(messages) -> list[dict]:
    """retrieve_docs 결과(artifact)에서 검색된 문서 조각 {doc_id, text} 를 중복 없이 모은다."""
    seen, contexts = set(), []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "retrieve_docs":
            for c in m.artifact or []:
                if (c["doc_id"], c["text"]) not in seen:
                    seen.add((c["doc_id"], c["text"]))
                    contexts.append(c)
    return contexts


def _run(question: str, config: dict | None) -> tuple[FinalAnswer, list]:
    """에이전트 실행 → 구조화 → 코드 생성 비교표. (최종 답변, 메시지 목록)을 반환한다."""
    # 개인정보는 미들웨어가 아니라 여기서 먼저 마스킹한다. 그래프 상태·trace 콜백에 원문이 들어가지 않게 하기 위함
    question = mask_pii(question)
    config = config or {}
    config.setdefault("configurable", {}).setdefault("thread_id", str(uuid.uuid4()))  # 체크포인터는 thread_id 가 필요하다
    result = agent.invoke({"messages": [HumanMessage(question)]}, config=config)
    messages = current_turn(result["messages"])
    draft = get_text(messages[-1])
    if draft in (REFUSAL_MESSAGE, BLOCKED_OUTPUT_MESSAGE):  # 가드레일 고정 문구는 구조화 단계에서 바꾸지 않고 그대로 낸다
        return FinalAnswer(answer=draft, comparison_table=[], sources=[], base_date=BASE_DATE), messages
    perf = collect_performance(messages)

    # 구조화 호출에도 config(콜백)를 넘겨 trace 에 남긴다
    structured = structurer.invoke(STRUCTURE_PROMPT.format(question=question, draft=draft, codes=list(perf)),
                                   config={"callbacks": (config or {}).get("callbacks", [])})
    codes = [c for c in structured.table_codes if c in perf] or list(perf)
    table = build_table(codes, perf)

    answer = structured.answer
    # 구조화 단계(Haiku)가 문장을 다시 쓰므로 내보내기 직전에 금지 표현을 한 번 더 코드로 검사한다
    hits = find_banned(answer)
    if hits:
        log_block("output_banned", f"구조화 답변 {hits} → 고정 문구")
        answer = BLOCKED_OUTPUT_MESSAGE
    if "[MASKED_" in question:  # 개인정보 안내는 구조화 단계에서 빠지지 않도록 코드가 붙인다
        answer = PII_NOTICE + "\n\n" + answer
    rule = selection_rule(messages)
    if rule:  # 대표 ETF 선정 기준은 구조화 단계에서 빠지지 않도록 코드가 붙인다
        answer += f"\n\n[대표 ETF 선정 기준] {rule}"
    if table:
        answer += (f"\n\n※ 데이터 기준일 {BASE_DATE}. 수익률: {RETURN_DEFINITION}. "
                   f"변동성: {VOLATILITY_DEFINITION}. {DISCLAIMER}")

    used_tools = sorted({m.name for m in messages if isinstance(m, ToolMessage)})
    sources = [f"도구: {', '.join(used_tools)}"] + DATA_SOURCES if used_tools else []
    doc_sources = collect_doc_sources(messages)
    sources += doc_sources
    if doc_sources:  # 근거 문서는 구조화 단계에서 빠지지 않도록 코드가 붙인다
        answer += "\n\n[근거 문서] " + " / ".join(s.removeprefix("문서: ") for s in doc_sources)
    return FinalAnswer(answer=answer, comparison_table=table, sources=sources, base_date=BASE_DATE), messages


def print_answer(fa: FinalAnswer) -> None:
    """최종 답변을 터미널에 보기 좋게 출력한다."""
    print(fa.answer)
    if fa.comparison_table:
        print("\n[비교표]")
        print(f"{'종목명':<22}{'코드':<8}{'보수%':>7}{'1년%':>8}{'3년%':>8}{'변동1y':>8}{'변동3y':>8}  환헤지  상장일")
        for r in fa.comparison_table:
            print(f"{r.name:<22}{r.code:<8}{r.fee_pct:>7}{r.return_1y!s:>8}{r.return_3y!s:>8}"
                  f"{r.volatility_1y!s:>8}{r.volatility_3y!s:>8}  {'O' if r.hedged else '-':^5}  {r.listed_date}")
    print(f"\n기준일: {fa.base_date}")
    print("출처:", " / ".join(fa.sources) or "없음")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "미국 S&P500 추종 ETF 중에 연금저축으로 살 수 있는 거 비교해줘"
    print_answer(run(q))
