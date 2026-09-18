# Slim, multi-stage to keep image < 200MB.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for cryptography (PyJWT[crypto] needs them)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# App package
COPY . ./gex_pf_engine/

# Non-root user
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

# Cloud Run sets PORT; fall back to 8001 for local
ENV PORT=8001
EXPOSE 8001

CMD ["sh", "-c", "uvicorn gex_pf_engine.main:app --host 0.0.0.0 --port ${PORT}"]
