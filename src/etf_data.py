# etf_data.py - KRX ETF 전종목 기본정보 CSV 로더
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
    return df.set_index("code", drop=False)


if __name__ == "__main__":
    etfs = load_etf_list()
    print(f"전체 {len(etfs):,}행")
    r = etfs.loc["360750"]
    print(f"{r['code']}: {r['name']} / {r['market']} / {r['asset']} / 총보수 {r['fee']}")
