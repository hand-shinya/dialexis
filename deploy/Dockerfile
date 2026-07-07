# Alternative to the native systemd deployment (bootstrap_vps.sh is the
# primary, documented path). Build from repo root:
#   docker build -f deploy/Dockerfile -t dialexis .
#   docker run -p 8000:8000 -v dialexis-data:/app/data dialexis
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY GENESIS.md README.md LICENSE ./
VOLUME /app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
