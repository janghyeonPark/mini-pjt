# ragas_eval.py - 저장된 채점 결과(답변·contexts)로 RAGAS 4지표 계산 (Haiku·Titan 래핑)
import argparse
import csv
import json
import sys
import types
import warnings
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent / "src"))
warnings.filterwarnings("ignore")

# ragas 0.4.3 은 설치된 langchain-community 0.4.x 에 없는 VertexAI 클래스를 import 한다.
# 쓰지 않는 클래스이므로 import ragas 전에 빈 클래스로 채워 둔다 (동작 영향 없음)
import langchain_community.llms as _llms  # noqa: E402

_vertex = types.ModuleType("langchain_community.chat_models.vertexai")
_vertex.ChatVertexAI = type("ChatVertexAI", (), {})
sys.modules[_vertex.__name__] = _vertex
if not hasattr(_llms, "VertexAI"):
    _llms.VertexAI = type("VertexAI", (), {})

from langchain_aws import BedrockEmbeddings  # noqa: E402
from ragas import EvaluationDataset, evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness  # noqa: E402

from agent import make_llm  # noqa: E402
from config import AUX_MODEL, EMBED_MODEL, REGION  # noqa: E402

REFERENCES_CSV = EVAL_DIR / "ragas_references.csv"
METRICS = [context_recall, context_precision, faithfulness, answer_relevancy]
METRIC_NAMES = [m.name for m in METRICS]
# answer_relevancy 는 답변에서 질문을 역생성해 원 질문과 임베딩 유사도를 본다. 프롬프트 예시가 영어라 질문이 영어로 나오면
# 한국어 원 질문과 유사도가 낮게 나온다 (Titan: 같은 뜻 한국어 0.69 / 영어 0.36). 질문 언어만 답변에 맞추게 한 줄 덧붙인다
answer_relevancy.question_generation.instruction += (
    " Write the question in the same language as the answer (a Korean answer needs a Korean question)."
)
# 목표값 (SERVICE.md 성공 기준). context_precision·answer_relevancy 는 목표 없이 함께 기록만 한다
TARGETS = {"context_recall": 0.7, "faithfulness": 0.8}


def load_samples(round_dir: Path, ids: set[str] | None) -> list[dict]:
    """정답 문장이 있는 문항 중 채점 결과가 저장된 것만 RAGAS 입력으로 바꾼다. 검색 결과가 없으면 건너뛴다."""
    with open(REFERENCES_CSV, encoding="utf-8") as f:
        refs = {r["id"]: r["reference"] for r in csv.DictReader(f)}
    samples = []
    for cid, reference in refs.items():
        if ids and cid not in ids:
            continue
        path = round_dir / f"{cid}.json"
        if not path.exists():
            print(f"#{cid} 채점 결과 없음 → 건너뜀 (먼저 run_eval.py 실행)")
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        contexts = [c["text"] for c in r.get("contexts", [])]
        if not contexts:
            print(f"#{cid} 검색된 문서 조각 없음 → 건너뜀 (retrieve_docs 미호출 또는 5-1 이전에 저장된 결과)")
            continue
        samples.append({"id": cid, "user_input": r["input"], "retrieved_contexts": contexts,
                        "response": r["result"]["answer"], "reference": reference})
    return samples


def main():
    parser = argparse.ArgumentParser(description="RAGAS 4지표 계산 (저장된 채점 결과 사용)")
    parser.add_argument("--ids", help="계산할 문항 id (쉼표 구분). 비우면 정답 문장이 있는 전체")
    parser.add_argument("--round", type=int, default=0, help="라운드 번호 (results/round{N} 의 결과 사용)")
    args = parser.parse_args()

    round_dir = EVAL_DIR / "results" / f"round{args.round}"
    samples = load_samples(round_dir, set(args.ids.split(",")) if args.ids else None)
    if not samples:
        print("계산할 문항이 없습니다.")
        return

    llm = LangchainLLMWrapper(make_llm(AUX_MODEL))
    emb = LangchainEmbeddingsWrapper(BedrockEmbeddings(model_id=EMBED_MODEL, region_name=REGION))
    dataset = EvaluationDataset.from_list([{k: v for k, v in s.items() if k != "id"} for s in samples])
    df = evaluate(dataset, metrics=METRICS, llm=llm, embeddings=emb, show_progress=False).to_pandas()

    # 문항별 점수를 저장한다. 다른 문항을 따로 계산해도 기존 값은 유지한다
    out_path = round_dir / "ragas.json"
    saved = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    for s, (_, row) in zip(samples, df.iterrows()):
        saved[s["id"]] = {m: round(float(row[m]), 4) for m in METRIC_NAMES}
    out_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n===== RAGAS ({AUX_MODEL} · {EMBED_MODEL}) =====")
    print(f"{'id':<5}" + "".join(f"{m:>20}" for m in METRIC_NAMES))
    for cid, scores in saved.items():
        print(f"{'#' + cid:<5}" + "".join(f"{scores[m]:>20.2f}" for m in METRIC_NAMES))
    print(f"{'평균':<4}" + "".join(f"{sum(s[m] for s in saved.values()) / len(saved):>20.2f}" for m in METRIC_NAMES))
    print(f"{'목표':<4}" + "".join(f"{TARGETS[m]:>20.2f}" if m in TARGETS else f"{'-':>20}" for m in METRIC_NAMES))
    print(f"\n저장 위치: {out_path.relative_to(EVAL_DIR.parent)}")


if __name__ == "__main__":
    main()
