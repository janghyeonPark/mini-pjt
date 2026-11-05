# tracer.py - LLM·도구 호출을 단계별로 수집하는 콜백 핸들러 (메모리 + logs/trace.jsonl)
import json
import time

from langchain_core.callbacks import BaseCallbackHandler

from config import LOG_DIR

TRACE_LOG = LOG_DIR / "trace.jsonl"
PREVIEW = 500  # 입력·출력은 앞부분만 남긴다


def get_text(message) -> str:
    """ChatBedrockConverse는 content를 블록 리스트로 주기도 하므로 텍스트만 모아 반환한다."""
    content = message.content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return content


class Tracer(BaseCallbackHandler):
    """LLM 호출과 도구 호출을 {step, input, output, latency_s, tokens} 로 모은다 (ref/local_tracer.py FileTracer 구조).

    step 은 LLM 호출이면 "llm", 도구 호출이면 도구 이름이다. 시작·끝은 run_id 로 짝짓는다.
    """

    def __init__(self, trace_id: str = ""):
        self.trace_id = trace_id
        self.steps: list[dict] = []
        self._open: dict = {}  # run_id -> (step 레코드, 시작 시각)

    def _start(self, run_id, step: str, input_text: str):
        record = {"step": step, "input": input_text[:PREVIEW], "output": ""}
        self.steps.append(record)
        self._open[run_id] = (record, time.time())

    def _end(self, run_id, output_text: str, **extra):
        record, started = self._open.pop(run_id, (None, time.time()))
        if record is None:
            return
        record.update(output=output_text[:PREVIEW], latency_s=round(time.time() - started, 2), **extra)
        self._write(record)

    def _write(self, record: dict):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with TRACE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "trace_id": self.trace_id, **record},
                               ensure_ascii=False) + "\n")

    # ---- LLM ----
    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        last = messages[0][-1] if messages and messages[0] else None
        self._start(run_id, "llm", get_text(last) if last is not None else "")

    def on_llm_end(self, response, *, run_id, **kw):
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        usage = (getattr(msg, "usage_metadata", None) or {}) if msg is not None else {}
        calls = [t["name"] for t in getattr(msg, "tool_calls", None) or []]
        output = gen.text or (f"도구 호출 결정: {calls}" if calls else "")
        self._end(run_id, output, tokens=usage.get("total_tokens", 0))

    def on_llm_error(self, error, *, run_id, **kw):
        self._end(run_id, f"[오류] {error}")

    # ---- 도구 ----
    def on_tool_start(self, serialized, input_str, *, run_id, **kw):
        name = (serialized or {}).get("name") or kw.get("name", "tool")
        self._start(run_id, name, input_str)

    def on_tool_end(self, output, *, run_id, **kw):
        self._end(run_id, str(getattr(output, "content", output)))

    def on_tool_error(self, error, *, run_id, **kw):
        self._end(run_id, f"[오류] {error}")

    @property
    def tools(self) -> list[str]:
        """호출된 도구 이름을 순서대로 반환한다."""
        return [s["step"] for s in self.steps if s["step"] != "llm"]
