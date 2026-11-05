# retriever.py - RAG 파이프라인: 마크다운 문서 적재, 하이브리드 검색(벡터 + BM25), retrieve_docs 도구
import hashlib
from functools import lru_cache

from kiwipiepy import Kiwi
from langchain_aws import BedrockEmbeddings
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_text_splitters import MarkdownHeaderTextSplitter

from config import DATA_DIR, DOCS_DIR, EMBED_MODEL, REGION

CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION = "etf_docs"
HASH_FILE = CHROMA_DIR / "docs.sha256"  # 문서가 바뀌었을 때만 벡터 DB를 다시 만든다
TOP_K = 3
WEIGHTS = [0.3, 0.7]  # [BM25, 벡터] (ref/day2_practice/hybrid.py 시작값)

kiwi = Kiwi()


def korean_tokenizer(text: str) -> list[str]:
    """한국어 형태소 단위 토크나이저. 명사, 어간, 숫자, 외래어만 남긴다 (ref/day2_practice/hybrid.py)."""
    keep = {"NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "SL", "SN"}
    return [t.form for t in kiwi.tokenize(text) if t.tag in keep]


def load_chunks() -> list[Document]:
    """data/docs/*.md 를 마크다운 헤더(#, ##) 단위로 나누고 출처 파일명·섹션을 메타데이터로 붙인다."""
    splitter = MarkdownHeaderTextSplitter([("#", "title"), ("##", "section")], strip_headers=False)
    chunks = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        for c in splitter.split_text(path.read_text(encoding="utf-8")):
            c.metadata["source"] = path.name
            chunks.append(c)
    return chunks


def _docs_hash() -> str:
    h = hashlib.sha256()
    for path in sorted(DOCS_DIR.glob("*.md")):
        h.update(path.name.encode() + path.read_bytes())
    return h.hexdigest()


@lru_cache(maxsize=1)
def get_retriever() -> EnsembleRetriever:
    """하이브리드 검색기를 만든다. 첫 호출에만 만들고, 벡터 DB는 문서 해시가 같으면 디스크에서 재사용한다."""
    chunks = load_chunks()
    embeddings = BedrockEmbeddings(model_id=EMBED_MODEL, region_name=REGION)
    db = Chroma(collection_name=COLLECTION, embedding_function=embeddings, persist_directory=str(CHROMA_DIR))

    current = _docs_hash()
    if not HASH_FILE.exists() or HASH_FILE.read_text() != current:
        db.delete_collection()
        db = Chroma.from_documents(chunks, embeddings, collection_name=COLLECTION, persist_directory=str(CHROMA_DIR))
        HASH_FILE.write_text(current)
        print(f"[retriever] 벡터 DB 재생성: 청크 {len(chunks)}개")

    bm25 = BM25Retriever.from_documents(chunks, preprocess_func=korean_tokenizer)
    bm25.k = TOP_K
    vector = db.as_retriever(search_kwargs={"k": TOP_K})
    return EnsembleRetriever(retrievers=[bm25, vector], weights=WEIGHTS)


def search(query: str, k: int = TOP_K) -> list[Document]:
    """하이브리드 검색 상위 k개 문서 조각을 반환한다."""
    return get_retriever().invoke(query)[:k]


def _label(d: Document) -> str:
    section = d.metadata.get("section")
    return f"{d.metadata['source']} > {section}" if section else d.metadata["source"]


@tool
def retrieve_docs(query: str) -> str:
    """연금저축 ETF 매매 규칙과 기초지수 설명 문서에서 관련 내용을 검색한다.

    "레버리지 ETF를 연금저축에서 왜 못 사?", "KOFR가 뭐야?", "환헤지(H)는 뭐가 달라?"처럼
    규칙의 근거, 지수 정의, 위험 요인 설명이 필요할 때 사용한다.
    종목 검색·매수 가능 판정·수익률 계산에는 사용하지 않는다 (search_etfs, check_pension_eligibility, calc_performance 사용).

    Args:
        query: 찾을 내용 (예: '레버리지 연금저축', 'KOFR 정의', '환헤지 차이')
    """
    try:
        docs = search(query)
    except Exception as e:  # 검색 실패도 예외 대신 안내 메시지로 돌려준다
        return f"문서 검색 실패 ({type(e).__name__}). 문서 근거 없이 지어내지 말고 검색 실패로 안내할 것"
    if not docs:
        return "관련 문서를 찾지 못했습니다."
    return "\n\n".join(f"[출처: {_label(d)}]\n{d.page_content}" for d in docs)


if __name__ == "__main__":
    for q in ["KOFR", "레버리지 연금저축", "환헤지 차이", "S&P500 나스닥100 차이"]:
        hits = search(q)
        print(f"{q} → " + " | ".join(_label(d) for d in hits))
