# Mirrors gex_pf_engine/Dockerfile; serves on 8002.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for cryptography (PyJWT[crypto]); build tools also serve numpy/scipy
# once OpenPyTEA is unpinned.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# App package
COPY . ./tea_engine/

RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

ENV PORT=8002
EXPOSE 8002

CMD ["sh", "-c", "uvicorn tea_engine.main:app --host 0.0.0.0 --port ${PORT}"]
