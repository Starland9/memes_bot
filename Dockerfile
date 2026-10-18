# Build context: this directory.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY bot/ ./bot

RUN useradd --uid 1000 --create-home bot \
    && mkdir -p /data \
    && chown -R bot:bot /data

USER bot

ENV DATA_DIR=/data

# Dokploy schedule jobs use `docker exec`, so the container must stay alive.
# Run a cycle manually with: docker run --rm memes-bot python -m bot --once
CMD ["sleep", "infinity"]
