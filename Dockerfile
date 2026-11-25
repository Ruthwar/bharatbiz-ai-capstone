FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_MODE=mock \
    LLM_PROVIDER=none

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY data/synthetic ./data/synthetic
COPY data/knowledge_docs ./data/knowledge_docs
COPY data/knowledge_docs_track_b ./data/knowledge_docs_track_b
COPY data/eval ./data/eval
COPY vm05-ca.crt ./

RUN mkdir -p data/runtime && chown -R app:app /app

USER app

EXPOSE 8011

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8011/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011"]
