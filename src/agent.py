# agent.py - 연금저축 ETF 비교 에이전트 (ReAct + 구조화 답변) 진입점
import json
import re
import sys

from botocore.config import Config
from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from config import AGENT_MODEL, AUX_MODEL, BASE_DATE, REGION
from metrics import RETURN_DEFINITION, VOLATILITY_DEFINITION
from tools import DISCLAIMER, TOOLS

# Bedrock 호출은 botocore 적응형 재시도(지수 백오프)로 감싼다
BEDROCK_RETRY = Config(retries={"max_attempts": 6, "mode": "adaptive"})
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
- 특정 종목의 연금저축 매수 가능 여부는 check_pension_eligibility 로 판정하고, 그 사유(왜 안 되는지·왜 되는지)는 retrieve_docs 로 매매 규칙 문서를 확인한 내용만 설명한다. 문서에 없는 제한(예: 커버드콜 제한)을 덧붙이지 않는다.
- 매매 규칙의 근거, 기초지수 정의, 환헤지·위험 요인 설명은 retrieve_docs 로 문서를 찾아 답하고, 답변에 [출처: 파일명] 을 밝힌다. 문서에 없는 규칙·세율·한도는 지어내지 말고 문서에 없다고 안내한다.
- 수익률·변동성·보수·시가총액 숫자는 답변 문장에 쓰지 않는다. 비교표는 도구 결과로 자동 생성되므로 "비교표 참고"로 가리키고, 문장에는 차이의 성격(환헤지 여부, 보수 높낮이, 상장 기간 등)만 설명한다.
- 특정 종목을 사라고 권하지 않는다("선택하시기 바랍니다" 같은 권유 표현 포함). 비교와 근거만 제공한다.
- 미래 수익률을 예측하지 않는다.
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


agent = create_agent(make_llm(AGENT_MODEL), TOOLS, system_prompt=SYSTEM_PROMPT, name="etf_agent")
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
            fee_pct=it["fee"], return_1y=it["return_1y"], return_3y=it["return_3y"],
            volatility_1y=it["volatility_1y"], volatility_3y=it["volatility_3y"],
            hedged=it["hedged"], listed_date=str(it["listed_date"]), base_date=str(it["base_date"]),
        ))
    return table


def run(question: str, config: dict | None = None) -> FinalAnswer:
    """질문 하나를 에이전트로 처리해 구조화된 최종 답변을 반환한다."""
    result = agent.invoke({"messages": [HumanMessage(question)]}, config=config)
    messages = result["messages"]
    draft = get_text(messages[-1])
    perf = collect_performance(messages)

    structured = structurer.invoke(STRUCTURE_PROMPT.format(question=question, draft=draft, codes=list(perf)))
    codes = [c for c in structured.table_codes if c in perf] or list(perf)
    table = build_table(codes, perf)

    answer = structured.answer
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
    return FinalAnswer(answer=answer, comparison_table=table, sources=sources, base_date=BASE_DATE)


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
