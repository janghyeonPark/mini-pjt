# market.py - 시가총액·시세 수집 (재시도, 평가 모드 스냅샷 저장·재사용)
import time
from datetime import datetime

import pandas as pd
import requests

from config import BASE_DATE, SNAPSHOT_DIR

NAVER_ETF_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
MARKET_CAP_CSV = SNAPSHOT_DIR / f"market_cap_{BASE_DATE.replace('-', '')}.csv"


def with_retry(fn, tries: int = 4, base_delay: float = 1.0):
    """fn()을 실행하고 실패하면 지수 백오프(1, 2, 4초…)로 재시도한다. 끝내 실패하면 마지막 예외를 올린다."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                raise
            delay = base_delay * 2**i
            print(f"[재시도 {i + 1}/{tries - 1}] {type(e).__name__}: {e} → {delay:.0f}초 후")
            time.sleep(delay)


def fetch_market_cap() -> pd.DataFrame:
    """네이버 금융 ETF 목록 API에서 종목코드별 시가총액(억원)을 받아 반환한다.

    기준일을 지정할 수 없는 API라 호출 시점 값이며, fetched_at 컬럼에 받은 시각을 남긴다.
    """
    def call():
        r = requests.get(NAVER_ETF_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        r.raise_for_status()
        return r.json()["result"]["etfItemList"]

    items = with_retry(call)
    df = pd.DataFrame(items)[["itemcode", "itemname", "marketSum"]]
    df.columns = ["code", "name", "market_cap"]
    df["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return df


def load_market_cap() -> pd.DataFrame:
    """시가총액 스냅샷을 읽는다. 파일이 없으면 한 번 받아 저장한 뒤 반환한다."""
    if not MARKET_CAP_CSV.exists():
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        fetch_market_cap().to_csv(MARKET_CAP_CSV, index=False, encoding="utf-8-sig")
    return pd.read_csv(MARKET_CAP_CSV, dtype={"code": str}).set_index("code", drop=False)


if __name__ == "__main__":
    t = time.time()
    cached = MARKET_CAP_CSV.exists()
    caps = load_market_cap()
    print(f"{'스냅샷 파일' if cached else '네이버 API'}에서 {len(caps):,}종목 로드 ({time.time() - t:.2f}초)")
    print(f"받은 시각: {caps['fetched_at'].iloc[0]}")
    r = caps.loc["069500"]
    print(f"069500 {r['name']}: 시가총액 {r['market_cap']:,}억원")
