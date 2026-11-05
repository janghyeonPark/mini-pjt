# rules.py - 연금저축 계좌 매수 가능 여부 판정 (파이썬 규칙)
import pandas as pd

from etf_data import load_etf_list

# 추적배수가 이 값이 아니면 레버리지·인버스 → 연금계좌 매수 불가
NORMAL_MULTIPLE = "일반"
# 판정 근거 (data/docs/pension_rules.md). 연금저축은 레버리지·인버스 외 종목 제한이 없다
RULE_SOURCE = "pension_rules.md, 금융위원회 연금저축계좌 ETF 투자 업무지침(2017-11-21)"


def check_eligibility(row: pd.Series) -> tuple[bool, str]:
    """ETF 한 종목의 연금저축 매수 가능 여부와 출처가 붙은 사유를 반환한다.

    규칙: 추적배수가 레버리지·인버스면 불가. 선물·합성 ETF와 위험자산 한도는 제한 없음 (pension_rules.md)
    """
    if row["multiple"] != NORMAL_MULTIPLE:
        return False, f"{row['multiple']} 상품은 연금저축 계좌에서 매수할 수 없음 [출처: {RULE_SOURCE}]"
    return True, f"매수 가능 (레버리지·인버스 아님. 선물·합성 ETF도 가능) [출처: {RULE_SOURCE}]"


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
