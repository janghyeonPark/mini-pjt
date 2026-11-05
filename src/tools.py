# tools.py - 연금저축 ETF 도메인 도구 (검색, 매수 가능 판정, 수익률·변동성 계산)
import json
import re

from langchain_core.tools import tool

from config import BASE_DATE
from etf_data import load_etf_list
from market import load_market_cap
from metrics import NOT_AVAILABLE, RETURN_DEFINITION, VOLATILITY_DEFINITION, calc_metrics
from rules import add_eligibility

# 모듈 로드 시 한 번만 읽는다 (CSV + 시가총액 스냅샷)
ETFS = add_eligibility(load_etf_list())
ETFS["market_cap"] = load_market_cap()["market_cap"]
ETFS["hedged"] = ETFS["name"].str.contains(r"\(.*H\)", regex=True)

TOP_N = 5
DISCLAIMER = "과거 수익률은 미래 수익을 보장하지 않습니다."


def _norm(text: str) -> str:
    """검색 비교용으로 공백을 없애고 소문자로 바꾼다 ("S&P 500" == "S&P500")."""
    return re.sub(r"\s+", "", str(text)).lower()


def _to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _resolve(code_or_name: str):
    """종목코드 또는 종목명으로 ETF 한 행을 찾는다. 없으면 (None, 비슷한 종목명 목록)."""
    key = code_or_name.strip()
    if key in ETFS.index:
        return ETFS.loc[key], []
    hits = ETFS[ETFS["name"].map(_norm) == _norm(key)]
    if len(hits):
        return hits.iloc[0], []
    similar = ETFS[ETFS["name"].map(_norm).str.contains(re.escape(_norm(key)[:6]), regex=True)]
    return None, similar["name"].head(10).tolist()


def _summary(row) -> dict:
    return {
        "code": row["code"], "name": row["name"], "asset_class": row["asset_class"],
        "index_name": row["index_name"], "fee": row["fee"], "hedged": bool(row["hedged"]),
        "market_cap_억원": int(row["market_cap"]), "listed_date": row["listed_date"],
    }


@tool
def search_etfs(query: str = "", asset_class: str = "") -> str:
    """연금저축 계좌에서 매수 가능한 ETF를 조건(추종지수·키워드·자산군)으로 검색한다.

    "S&P500 ETF 뭐 있어?", "KOFR 상품 보여줘"처럼 후보 목록이 필요할 때 사용한다.
    결과는 시가총액 순 상위 5개와 전체 개수이며, 레버리지·인버스, 커버드콜, 혼합자산은 기본 제외한다
    (query에 "커버드콜"·"혼합"이 있거나 asset_class='혼합자산'이면 포함).
    특정 종목 하나의 매수 가능 여부에는 사용하지 않는다 (check_pension_eligibility 사용).
    수익률·변동성 수치가 필요하면 결과의 code로 calc_performance를 호출한다.

    Args:
        query: 추종지수나 종목명 키워드 (예: 'S&P500', '나스닥100', 'KOFR', 'S&P500(H)'). 비우면 자산군만으로 검색
        asset_class: 자산군 필터 (예: '미국 주식', '국내 주식', '국내 채권·금리형'). 비우면 전체
    """
    df = ETFS[ETFS["eligible"]]
    if "커버드콜" not in query:
        df = df[~df["name"].str.contains("커버드콜")]
    if "혼합" not in query and asset_class != "혼합자산":
        df = df[df["asset_class"] != "혼합자산"]
    if asset_class:
        if asset_class not in set(ETFS["asset_class"]):
            return f"'{asset_class}' 자산군이 없습니다. 가능한 자산군: {sorted(set(ETFS['asset_class']))}"
        df = df[df["asset_class"] == asset_class]
    if query:
        q = re.escape(_norm(query))
        df = df[df["name"].map(_norm).str.contains(q) | df["index_name"].map(_norm).str.contains(q)]
    if not query and not asset_class:
        return "검색 조건이 없습니다. 자산군·추종지수·키워드 중 하나를 알려 주세요."
    if df.empty:
        return (f"'{query}' 조건에 맞는 연금저축 매수 가능 ETF가 없습니다. "
                f"가능한 자산군: {sorted(set(ETFS['asset_class']))}")

    top = df.sort_values("market_cap", ascending=False).head(TOP_N)
    return _to_json({
        "total": len(df),
        "shown": len(top),
        "note": f"연금저축 매수 가능 종목 총 {len(df)}개 중 시가총액 상위 {len(top)}개",
        "items": [_summary(r) for _, r in top.iterrows()],
    })


@tool
def check_pension_eligibility(code_or_name: str) -> str:
    """ETF 한 종목이 연금저축 계좌에서 매수 가능한지와 그 사유를 판정한다.

    "KODEX 레버리지 연금저축으로 살 수 있어?"처럼 특정 종목의 가능 여부를 물을 때 사용한다.
    여러 후보를 찾을 때는 사용하지 않는다 (search_etfs는 이미 매수 가능 종목만 반환).

    Args:
        code_or_name: 종목코드(예: '122630') 또는 종목명(예: 'KODEX 레버리지')
    """
    row, similar = _resolve(code_or_name)
    if row is None:
        return f"'{code_or_name}' 종목을 찾을 수 없습니다. 비슷한 종목: {similar or '없음'}"
    return _to_json({
        "code": row["code"], "name": row["name"], "eligible": bool(row["eligible"]),
        "reason": row["eligibility_reason"], "multiple": row["multiple"],
    })


@tool
def calc_performance(codes: list[str]) -> str:
    """ETF들의 1년·3년 가격수익률과 연환산 변동성, 총보수를 계산한다.

    비교표에 들어갈 수치가 필요할 때 사용한다. 수치는 반드시 이 도구 결과만 쓴다.
    후보를 모를 때는 먼저 search_etfs로 종목코드를 찾는다.
    상장 기간이 부족하면 "산출 불가", 시세가 저장되지 않은 종목은 "시세 미저장"으로 표시된다.

    Args:
        codes: 종목코드 또는 종목명 목록 (예: ['360750', '379800'])
    """
    items = []
    for key in codes:
        row, similar = _resolve(key)
        if row is None:
            items.append({"query": key, "error": f"종목을 찾을 수 없음. 비슷한 종목: {similar or '없음'}"})
            continue
        try:
            m = calc_metrics(row["code"], row["listed_date"])
        except Exception as e:  # 시세 조회 실패도 그래프를 죽이지 않고 안내 메시지로 돌려준다
            m = {"code": row["code"], "error": f"시세 조회 실패 ({type(e).__name__}). 수치를 지어내지 말고 조회 실패로 안내할 것"}
        items.append({**_summary(row), **m})
    return _to_json({
        "base_date": BASE_DATE,
        "return_definition": RETURN_DEFINITION,
        "volatility_definition": VOLATILITY_DEFINITION,
        "not_available": NOT_AVAILABLE,
        "disclaimer": DISCLAIMER,
        "items": items,
    })


TOOLS = [search_etfs, check_pension_eligibility, calc_performance]


if __name__ == "__main__":
    print("[search_etfs] S&P500")
    r = json.loads(search_etfs.invoke({"query": "S&P500"}))
    print(r["note"])
    for it in r["items"]:
        print(f"  {it['code']} {it['name']} ({it['market_cap_억원']:,}억)")
    print("\n[search_etfs] TIGER 화성탐사 →", search_etfs.invoke({"query": "TIGER 화성탐사"})[:60])
    print("\n[check_pension_eligibility]")
    print(" ", check_pension_eligibility.invoke({"code_or_name": "KODEX 레버리지"}))
    print(" ", check_pension_eligibility.invoke({"code_or_name": "360750"}))
    print("\n[calc_performance] 360750, 0218K0, 122630")
    r = json.loads(calc_performance.invoke({"codes": ["360750", "0218K0", "122630"]}))
    for it in r["items"]:
        print(f"  {it['code']} {it['name']}: 1y {it.get('return_1y')} / 3y {it.get('return_3y')} {it.get('error', '')}")
