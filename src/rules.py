# rules.py - 연금저축 계좌 매수 가능 여부 판정 (파이썬 규칙)
import pandas as pd

from etf_data import load_etf_list

# 추적배수가 이 값이 아니면 레버리지·인버스 → 연금계좌 매수 불가
NORMAL_MULTIPLE = "일반"


def check_eligibility(row: pd.Series) -> tuple[bool, str]:
    """ETF 한 종목의 연금저축 매수 가능 여부와 사유를 반환한다.

    현재 규칙: 추적배수가 레버리지·인버스면 불가. (문서 기반 추가 규칙은 TASKS 3-4)
    """
    if row["multiple"] != NORMAL_MULTIPLE:
        return False, f"{row['multiple']} 상품은 연금저축 계좌에서 매수할 수 없음"
    return True, "매수 가능 (레버리지·인버스 아님)"


def add_eligibility(etfs: pd.DataFrame) -> pd.DataFrame:
    """ETF 목록에 eligible(bool), eligibility_reason 컬럼을 붙여 반환한다."""
    result = etfs.apply(check_eligibility, axis=1, result_type="expand")
    return etfs.assign(eligible=result[0], eligibility_reason=result[1])


if __name__ == "__main__":
    etfs = add_eligibility(load_etf_list())
    for code in ["122630", "360750"]:
        r = etfs.loc[code]
        print(f"{code} {r['name']}: {'가능' if r['eligible'] else '불가'} - {r['eligibility_reason']}")
    print(f"불가 종목 수: {(~etfs['eligible']).sum()}")
