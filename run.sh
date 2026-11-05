#!/usr/bin/env bash
# run.sh - 가상환경 준비 → 패키지 설치 → API 서버·대화형 화면 실행 (Windows Git Bash / Linux / macOS)
#   사용법: bash run.sh            (기본 포트 8000)
#           PORT=8001 bash run.sh
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

# .env 가 없으면 Bedrock 을 호출할 수 없으므로 먼저 안내하고 멈춘다
if [ ! -f .env ]; then
  echo "[오류] .env 가 없습니다. AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION 을 적어 주세요." >&2
  exit 1
fi

# 가상환경: 없으면 만들고 패키지를 설치한다. Windows 는 Scripts/, 그 외는 bin/
if [ ! -d .venv ]; then
  echo "가상환경 생성 중..."
  python -m venv .venv 2>/dev/null || python3 -m venv .venv
  NEW_VENV=1
fi
if [ -f .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi
if [ "${NEW_VENV:-0}" = 1 ]; then
  echo "패키지 설치 중 (처음 한 번, 몇 분 걸립니다)..."
  "$PY" -m pip install -q -r requirements.txt
fi

echo "서버 시작: 화면 http://localhost:${PORT}  /  API POST http://localhost:${PORT}/query"
exec "$PY" -m uvicorn api:app --app-dir src --host 127.0.0.1 --port "$PORT"
