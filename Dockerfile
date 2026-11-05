# Dockerfile - 연금저축 ETF 비교 분석 Agent API 서버·대화형 화면 이미지
#   빌드: docker build -t etf-agent .
#   실행: docker run --rm -p 8000:8000 --env-file .env etf-agent   → http://localhost:8000
#   비밀 값(.env)은 이미지에 넣지 않고 실행할 때 --env-file 로 넘긴다
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 패키지 설치를 먼저 해 소스만 바뀔 때는 이 층을 재사용한다
COPY requirements.txt .
RUN pip install -r requirements.txt

# 실행에 필요한 폴더만 복사한다 (.env·.venv·ref/·logs/ 는 들어가지 않는다)
# data/ 에는 평가 모드 스냅샷이 있고, 문서 검색 인덱스(data/chroma_db)는 첫 질문 때 만들어진다
COPY src/ src/
COPY data/ data/
COPY evaluation/ evaluation/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
