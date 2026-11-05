# market.py - 시가총액·시세 수집 (재시도, 평가 모드 스냅샷 저장·재사용)
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests
from pykrx import stock

from config import BASE_DATE, CANDIDATE_CODES, SNAPSHOT_DIR

NAVER_ETF_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
MARKET_CAP_CSV = SNAPSHOT_DIR / f"market_cap_{BASE_DATE.replace('-', '')}.csv"
PRICES_DIR = SNAPSHOT_DIR / "prices"
# 3년 전 날짜가 휴장일이면 직전 거래일 종가가 필요하므로 며칠 더 앞에서부터 받는다
PRICE_YEARS, PRICE_BUFFER_DAYS = 3, 10


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


def fetch_prices(code: str) -> pd.Series:
    """pykrx로 기준일까지 약 3년치 일별 종가를 받아 날짜 인덱스 Series로 반환한다."""
    end = date.fromisoformat(BASE_DATE)
    start = end.replace(year=end.year - PRICE_YEARS) - timedelta(days=PRICE_BUFFER_DAYS)
    df = with_retry(lambda: stock.get_market_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code))
    if df.empty:
        raise ValueError(f"{code} 시세 없음")
    close = df["종가"].rename("close")
    close.index = close.index.date
    close.index.name = "date"
    return close


def load_prices(code: str) -> pd.Series | None:
    """저장된 시세 스냅샷을 읽는다. 후보 종목인데 파일이 없으면 받아 저장한다.

    후보가 아닌 종목은 None을 반환한다 (호출 쪽에서 "시세 미저장"으로 안내).
    """
    path = PRICES_DIR / f"{code}.csv"
    if not path.exists():
        if code not in CANDIDATE_CODES:
            return None
        PRICES_DIR.mkdir(parents=True, exist_ok=True)
        fetch_prices(code).to_csv(path, encoding="utf-8-sig")
    s = pd.read_csv(path, index_col="date", parse_dates=True)["close"]
    s.index = s.index.date
    return s


if __name__ == "__main__":
    if "--prices" in sys.argv:
        t = time.time()
        for code in CANDIDATE_CODES:
            s = load_prices(code)
            print(f"{code}: {len(s):4d}행 {s.index[0]} ~ {s.index[-1]}")
        print(f"후보 {len(CANDIDATE_CODES)}종목 완료 ({time.time() - t:.1f}초)")
        print(f"후보 밖 종목 122630: {'시세 미저장' if load_prices('122630') is None else '저장됨'}")
        sys.exit()

    t = time.time()
    cached = MARKET_CAP_CSV.exists()
    caps = load_market_cap()
    print(f"{'스냅샷 파일' if cached else '네이버 API'}에서 {len(caps):,}종목 로드 ({time.time() - t:.2f}초)")
    print(f"받은 시각: {caps['fetched_at'].iloc[0]}")
    r = caps.loc["069500"]
    print(f"069500 {r['name']}: 시가총액 {r['market_cap']:,}억원")
