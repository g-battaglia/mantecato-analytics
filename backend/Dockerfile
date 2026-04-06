FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY core/ /app/core/
COPY backend/pyproject.toml backend/uv.lock /app/backend/

WORKDIR /app/backend
RUN uv sync --frozen --no-dev

COPY backend/ /app/backend/

EXPOSE 8100

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
