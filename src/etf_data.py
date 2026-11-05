# etf_data.py - KRX ETF 전종목 기본정보 CSV 로더와 자산군 매핑
import re

import pandas as pd

from config import ETF_LIST_CSV

# CSV 원본 컬럼 → 코드에서 쓸 이름
COLUMNS = {
    "단축코드": "code",
    "한글종목약명": "name",
    "한글종목명": "full_name",
    "상장일": "listed_date",
    "기초지수명": "index_name",
    "추적배수": "multiple",
    "복제방법": "replication",
    "기초시장분류": "market",
    "기초자산분류": "asset",
    "운용사": "manager",
    "총보수": "fee",
}


def load_etf_list() -> pd.DataFrame:
    """ETF 목록 CSV(cp949)를 읽어 필요한 컬럼만 영문 이름으로 정리해 반환한다.

    종목코드는 0으로 시작하거나 영문이 섞이므로 문자열로 읽는다.
    """
    df = pd.read_csv(ETF_LIST_CSV, encoding="cp949", dtype=str)
    df = df[list(COLUMNS)].rename(columns=COLUMNS)
    df["fee"] = df["fee"].astype(float)
    df["listed_date"] = pd.to_datetime(df["listed_date"], format="%Y/%m/%d").dt.date
    df["asset_class"] = df.apply(classify_asset, axis=1)
    return df.set_index("code", drop=False)


# 금리형 키워드 (기초지수명). CD는 CDMO 등과 구분하려고 뒤에 영문자가 오지 않을 때만
RATE_PATTERN = re.compile(r"CD(?![A-Za-z])|KOFR|SOFR|머니마켓|단기채")
# 미국 지수 키워드 (기초지수명, 단어 단위). S&P Global 등 미국 외 지수는 걸리지 않는다.
# 다우존스·러셀은 지수 산출사 이름이라 미국 외 지수(Dow Jones Taiwan 등)에도 쓰여 제외 (미국 상품은 종목명에 "미국"이 있다)
US_INDEX_PATTERN = re.compile(r"\bS&P ?500\b|\bNASDAQ\b|나스닥")


def classify_asset(row: pd.Series) -> str:
    """SERVICE.md 3번 자산군 매핑 규칙을 위에서부터 적용해 처음 맞는 자산군 하나를 반환한다.

    1. 채권·금리형 (기초자산분류 = 채권, 또는 주식·혼합자산이 아니면서 기초지수명에 금리형 키워드)
    2. 주식 (국내 / 미국 / 기타 해외 / 글로벌)
    3. 그 외: 기초자산분류 값 그대로
    """
    asset, market = row["asset"], row["market"]

    is_rate = asset not in ("주식", "혼합자산") and RATE_PATTERN.search(row["index_name"])
    if asset == "채권" or is_rate:
        return "국내 채권·금리형" if market == "국내" else "해외 채권·금리형"

    if asset == "주식":
        if market == "국내":
            return "국내 주식"
        if market == "국내&해외":
            return "글로벌 주식"
        if "미국" in row["full_name"] or "미국" in row["name"] or US_INDEX_PATTERN.search(row["index_name"]):
            return "미국 주식"
        return "기타 해외 주식"

    return asset


if __name__ == "__main__":
    etfs = load_etf_list()
    print(f"전체 {len(etfs):,}행")
    r = etfs.loc["360750"]
    print(f"{r['code']}: {r['name']} / {r['market']} / {r['asset']} / 총보수 {r['fee']}")

    counts = etfs["asset_class"].value_counts()
    print("\n[자산군별 종목 수]")
    print(counts.to_string())
    print(f"합계 {counts.sum():,} / 분류 안 됨 {etfs['asset_class'].isna().sum()}")
