FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CACHE_DIR=/cache

WORKDIR /app

RUN addgroup --system --gid 10001 mycache \
    && adduser --system --uid 10001 --ingroup mycache mycache

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /cache && chown -R mycache:mycache /cache /app

USER mycache

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
