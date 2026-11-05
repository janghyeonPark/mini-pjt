# config.py - 모델 ID, 데이터 경로, 기준일 모드 등 설정 상수
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 모델 (역할 분리: 에이전트 = Sonnet, 가드레일·judge·RAGAS = Haiku)
REGION = "us-east-1"
AGENT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
AUX_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"

# 경로 (실행 위치에 의존하지 않도록 이 파일 기준)
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ETF_LIST_CSV = DATA_DIR / "etf_list_20261104.csv"
SNAPSHOT_DIR = DATA_DIR / "snapshot"
DOCS_DIR = DATA_DIR / "docs"

# 기준일 모드: 첫 버전은 평가 모드 고정 (평소 모드는 TASKS 8-1)
MODE = "eval"
BASE_DATE = "2026-11-03"
