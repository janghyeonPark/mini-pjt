# api.py - FastAPI 서버: POST /query → {answer, contexts, trace} (에이전트 로직은 agent.py, 여기서는 호출만)
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent import query
from guards import log_block

class UTF8JSONResponse(JSONResponse):
    """charset 을 명시한다. 없으면 Windows PowerShell 5.1 Invoke-RestMethod 가 한글을 깨뜨려 읽는다."""
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="연금저축 ETF 비교 분석 Agent", default_response_class=UTF8JSONResponse)

FAILURE_MESSAGE = "일시적인 오류로 조회하지 못했습니다. 잠시 후 다시 시도해 주세요. 수치를 추정해서 안내하지 않습니다."


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000, description="사용자 질문")


class Context(BaseModel):
    doc_id: str
    text: str


class TraceStep(BaseModel):
    step: str
    input: str
    output: str


class QueryResponse(BaseModel):
    answer: str
    contexts: list[Context]
    trace: list[TraceStep]


@app.post("/query", response_model=QueryResponse)
def post_query(req: QueryRequest):
    """질문 하나를 에이전트로 처리한다. 동기 함수라 FastAPI 스레드풀에서 실행된다."""
    try:
        out = query(req.question)
    except Exception as e:  # Bedrock 한도 초과 등: 지어내지 않고 실패를 안내한다. 사유는 로그에만
        log_block("api_error", f"{type(e).__name__}: {str(e)[:200]}")
        return UTF8JSONResponse(status_code=503, content={"answer": FAILURE_MESSAGE, "contexts": [], "trace": []})
    return {"answer": out["answer"], "contexts": out["contexts"], "trace": out["trace"]}


@app.get("/health")
def health():
    return {"status": "ok"}
