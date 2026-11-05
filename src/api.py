# api.py - FastAPI 서버: POST /query → {answer, contexts, trace} (에이전트 로직은 agent.py, 여기서는 호출만)
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from agent import TableRow, query
from guards import log_block

INDEX_HTML = Path(__file__).resolve().parent / "static" / "index.html"

class UTF8JSONResponse(JSONResponse):
    """charset 을 명시한다. 없으면 Windows PowerShell 5.1 Invoke-RestMethod 가 한글을 깨뜨려 읽는다."""
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="연금저축 ETF 비교 분석 Agent", default_response_class=UTF8JSONResponse)

FAILURE_MESSAGE = "일시적인 오류로 조회하지 못했습니다. 잠시 후 다시 시도해 주세요. 수치를 추정해서 안내하지 않습니다."


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000, description="사용자 질문")
    thread_id: str | None = Field(default=None, max_length=100, description="이어갈 대화 id. 없으면 새 대화")


class Context(BaseModel):
    doc_id: str
    text: str


class TraceStep(BaseModel):
    step: str
    input: str
    output: str
    latency_s: float | None = None
    tokens: int | None = None


class QueryResponse(BaseModel):
    """규약의 세 키(answer, contexts, trace)에 화면용 comparison_table·thread_id 를 덧붙인다."""
    answer: str
    contexts: list[Context]
    trace: list[TraceStep]
    comparison_table: list[TableRow] = []
    thread_id: str | None = None


@app.get("/", include_in_schema=False)
def index():
    """대화형 화면 (HTML 한 장)."""
    return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")


@app.post("/query", response_model=QueryResponse)
def post_query(req: QueryRequest):
    """질문 하나를 에이전트로 처리한다. 동기 함수라 FastAPI 스레드풀에서 실행된다."""
    try:
        out = query(req.question, req.thread_id)
    except Exception as e:  # Bedrock 한도 초과 등: 지어내지 않고 실패를 안내한다. 사유는 로그에만
        log_block("api_error", f"{type(e).__name__}: {str(e)[:200]}")
        return UTF8JSONResponse(status_code=503, content={"answer": FAILURE_MESSAGE, "contexts": [], "trace": [],
                                                          "thread_id": req.thread_id})
    return {"answer": out["answer"], "contexts": out["contexts"], "trace": out["trace"],
            "comparison_table": out["result"].comparison_table, "thread_id": out["thread_id"]}


@app.get("/health")
def health():
    return {"status": "ok"}
