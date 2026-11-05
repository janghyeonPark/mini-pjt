# metrics.py - 기간별 가격수익률·연환산 변동성 계산 (파이썬 계산)
import math
from datetime import date

import pandas as pd

from config import BASE_DATE
from market import load_prices

PERIODS = {"1y": 1, "3y": 3}
TRADING_DAYS = 252
RETURN_DEFINITION = "가격수익률(분배금 미포함), 기준일 종가 ÷ N년 전 직전 거래일 종가 - 1"
VOLATILITY_DEFINITION = "기간 내 일간 수익률 표준편차 × √252"
NOT_AVAILABLE = "산출 불가"


def period_metrics(prices: pd.Series, base: date, years: int) -> dict:
    """기준일부터 years년 전까지의 가격수익률(%)과 연환산 변동성(%)을 계산한다.

    시작일은 N년 전 날짜 또는 그 직전 거래일. 시세가 그보다 늦게 시작하면(상장 기간 부족) 산출 불가.
    """
    target = base.replace(year=base.year - years)
    before = prices[prices.index <= target]
    if before.empty:
        return {"return": NOT_AVAILABLE, "volatility": NOT_AVAILABLE, "start_date": None}

    start_date = before.index[-1]
    window = prices[(prices.index >= start_date) & (prices.index <= base)]
    ret = window.iloc[-1] / window.iloc[0] - 1
    vol = window.pct_change().dropna().std() * math.sqrt(TRADING_DAYS)
    return {"return": round(float(ret) * 100, 2), "volatility": round(float(vol) * 100, 2), "start_date": start_date}


def calc_metrics(code: str, listed_date: date | None = None) -> dict:
    """종목 하나의 1년·3년 수익률·변동성을 계산해 반환한다. 시세가 저장되지 않았으면 error를 담는다."""
    prices = load_prices(code)
    if prices is None:
        return {"code": code, "error": "시세 미저장 (평가 모드 후보 종목이 아님)"}

    base = date.fromisoformat(BASE_DATE)
    prices = prices[prices.index <= base]
    result = {"code": code, "base_date": prices.index[-1], "listed_date": listed_date}
    for key, years in PERIODS.items():
        m = period_metrics(prices, base, years)
        result[f"return_{key}"] = m["return"]
        result[f"volatility_{key}"] = m["volatility"]
        result[f"start_{key}"] = m["start_date"]
    return result


if __name__ == "__main__":
    from etf_data import load_etf_list

    etfs = load_etf_list()
    for code in ["360750", "0218K0", "122630"]:
        listed = etfs.loc[code, "listed_date"]
        print(code, etfs.loc[code, "name"], calc_metrics(code, listed))

    # 손계산 대조: 360750 1년 수익률 = 기준일 종가 ÷ 1년 전 직전 거래일 종가 - 1
    p = load_prices("360750")
    base = date.fromisoformat(BASE_DATE)
    start = p[p.index <= base.replace(year=base.year - 1)]
    print(f"\n[손계산] {start.index[-1]} 종가 {start.iloc[-1]:,} → {base} 종가 {p[base]:,}: "
          f"{(p[base] / start.iloc[-1] - 1) * 100:.2f}%")
