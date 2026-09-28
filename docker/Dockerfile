# API pme-risk — Cloud Run (SPEC §5.2)
# Credenciais: ADC no runtime via service account do Cloud Run (sem API key)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY agents/ agents/
COPY api/ api/
COPY model/ model/
COPY monitoring/ monitoring/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Sem root em runtime — o código só precisa ler /app
RUN useradd --system --no-create-home app
USER app

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
