FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (PyMuPDF 빌드에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY main.py .
COPY src/ ./src/

# 출력 디렉토리 생성
RUN mkdir -p /app/output

ENTRYPOINT ["python", "main.py"]
