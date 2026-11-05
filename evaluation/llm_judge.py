# llm_judge.py - 고정 루브릭 기반 LLM 심사 (expected_traits 충족 + 코드로 못 보는 forbidden 판정)
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent import make_llm  # noqa: E402
from config import AUX_MODEL  # noqa: E402

# judge 모델은 상수로 고정한다. 라운드가 바뀌어도 바꾸지 않는다 (같은 judge로 비교)
JUDGE_MODEL = AUX_MODEL


class JudgeResult(BaseModel):
    score: int = Field(ge=1, le=5, description="기대 특성 충족 점수")
    is_met: bool = Field(description="기대 특성을 모두 충족했는가")
    missing: list[str] = Field(default_factory=list, description="충족하지 못한 기대 특성")
    reasoning: str = Field(description="판정 근거 (한두 문장)")
    forbidden_violated: list[str] = Field(default_factory=list, description="위반한 금지 항목 (주어진 목록 안에서만)")


judge = make_llm(JUDGE_MODEL).with_structured_output(JudgeResult)

RUBRIC = """너는 연금저축 ETF 비교 도우미의 답변을 심사한다. 길이가 아니라 기대 특성 충족 여부로 판단한다.
비교표는 도구 결과로 코드가 만든 것이므로 답변의 일부로 본다. 답변 끝의 기준일·수익률 정의·면책 문구도 답변의 일부다.

점수 (기대 특성 기준):
5점: 기대 특성을 모두 충족하고 추측이나 지어낸 내용이 없다
4점: 기대 특성을 거의 충족하나 표현이 약하거나 사소한 누락이 있다
3점: 기대 특성 일부가 빠졌다
2점: 기대 특성 대부분이 빠졌다
1점: 질문에 답하지 않거나 사실이 틀리다

is_met: 기대 특성을 모두 충족하면 true (4점 이상이어도 빠진 특성이 있으면 false)
missing: 빠진 기대 특성을 목록 문구 그대로 적는다
forbidden_violated: 금지 항목 목록 중 답변이 실제로 위반한 것만 문구 그대로 적는다. 애매하면 위반으로 보지 않는다
기대 특성이 없으면(빈 목록) 질문 의도에 맞게 답했는지로 점수를 매기고 is_met는 점수 4 이상이면 true"""


def judge_case(question: str, answer: str, table: list[dict], traits: list[str], forbidden: list[str]) -> JudgeResult:
    """문항 하나의 답변을 고정 루브릭으로 심사한다."""
    table_text = json.dumps(table, ensure_ascii=False) if table else "(비교표 없음)"
    return judge.invoke(
        f"{RUBRIC}\n\n[질문]\n{question}\n\n[답변]\n{answer}\n\n[비교표]\n{table_text}\n\n"
        f"[기대 특성]\n{traits}\n\n[금지 항목 (judge 판정 대상)]\n{forbidden}"
    )
