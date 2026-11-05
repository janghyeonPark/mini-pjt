# etf_data.py - KRX ETF 전종목 기본정보 CSV 로더와 자산군 매핑
import re
import sys

import pandas as pd

from config import ETF_LIST_CSV, ROOT

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
        if "미국" in row["full_name"] or "미국" in row["name"]:
            return "미국 주식"
        # 종목명에 "글로벌"이 있으면 기초지수가 미국 지수여도 비교 기준일 뿐이라 미국 주식으로 보지 않는다
        if "글로벌" not in row["name"] and US_INDEX_PATTERN.search(row["index_name"]):
            return "미국 주식"
        return "기타 해외 주식"

    return asset


REVIEW_CSV = ROOT / "evaluation" / "asset_class_review.csv"
REVIEW_CLASSES = ("미국 주식", "국내 채권·금리형", "해외 채권·금리형")


def export_review(etfs: pd.DataFrame) -> pd.DataFrame:
    """미국 주식·채권·금리형 분류 결과를 사람 검토용 CSV로 내보낸다.

    분류 근거를 붙이고, 확인이 필요한 종목(이름에 "미국"이 없는데 미국 주식,
    기초자산분류가 채권이 아닌데 금리형)을 맨 위에 둔다.
    """
    df = etfs[etfs["asset_class"].isin(REVIEW_CLASSES)].copy()

    def basis(row):
        if row["asset_class"] == "미국 주식":
            return "종목명 '미국'" if "미국" in row["full_name"] or "미국" in row["name"] else "기초지수 키워드"
        return "기초자산분류 채권" if row["asset"] == "채권" else "금리형 키워드"

    df["basis"] = df.apply(basis, axis=1)
    df["check"] = df["basis"].isin(["기초지수 키워드", "금리형 키워드"]).map({True: "확인", False: ""})
    df = df.sort_values(["check", "asset_class", "name"], ascending=[False, True, True])
    cols = ["check", "asset_class", "basis", "code", "name", "index_name", "market", "asset"]
    df[cols].to_csv(REVIEW_CSV, index=False, encoding="utf-8-sig")
    return df


if __name__ == "__main__":
    etfs = load_etf_list()
    print(f"전체 {len(etfs):,}행")
    r = etfs.loc["360750"]
    print(f"{r['code']}: {r['name']} / {r['market']} / {r['asset']} / 총보수 {r['fee']}")

    counts = etfs["asset_class"].value_counts()
    print("\n[자산군별 종목 수]")
    print(counts.to_string())
    print(f"합계 {counts.sum():,} / 분류 안 됨 {etfs['asset_class'].isna().sum()}")

    if "--review" in sys.argv:
        review = export_review(etfs)
        print(f"\n검토 파일: {REVIEW_CSV.relative_to(ROOT)} ({len(review)}행, 확인 필요 {(review['check'] == '확인').sum()}행)")
