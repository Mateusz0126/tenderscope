
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim

WORKDIR /app

ENV UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONPATH=/app/src

COPY . .

RUN uv sync --locked --no-dev --no-editable

CMD ["/app/.venv/bin/python", "-m", "tenderscope.pipeline", "--max-pages", "2", "--allow-partial"]
