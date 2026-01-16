# 파이썬 환경 준비
FROM python:3.11-slim-bookworm

# 오라클 DB 연결을 위한 필수 도구 설치 (cx_Oracle용)
RUN apt-get update && apt-get install -y \
    libaio1 wget unzip gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# 오라클 클라이언트 설치 (기존 DB 환경 유지용)
WORKDIR /opt/oracle
RUN wget https://download.oracle.com/otn_software/linux/instantclient/211000/instantclient-basic-linux.x64-21.1.0.0.0.zip && \
    unzip instantclient-basic-linux.x64-21.1.0.0.0.zip && \
    rm -f instantclient-basic-linux.x64-21.1.0.0.0.zip
ENV LD_LIBRARY_PATH="/opt/oracle/instantclient_21_1"

# 내 프로젝트 파일들을 도커 안으로 복사
WORKDIR /app
COPY requirements.web.txt .
RUN pip install --no-cache-dir -r requirements.web.txt
COPY . .

# Flask 실행
EXPOSE 5000
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"]