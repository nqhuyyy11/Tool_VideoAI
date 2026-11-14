# Dùng khi đưa lên host (Render, Railway, VPS...).
# Build từ thư mục CHA (thư mục chứa cả "autovideo" và "Web"):
#   docker build -f Web/Dockerfile -t autovideo-web .
FROM python:3.12-slim

# ffmpeg để dựng video; fonts-liberation thay cho font Arial của phụ đề
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY Web/requirements.txt Web/requirements.txt
RUN pip install --no-cache-dir -r Web/requirements.txt

COPY autovideo/*.py autovideo/
COPY Web/backend Web/backend
COPY Web/frontend Web/frontend

WORKDIR /app/Web
ENV PORT=8000
CMD ["sh", "-c", "python -m uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
