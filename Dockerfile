FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app ./app
COPY alembic ./alembic
COPY data ./data
COPY alembic.ini ./
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test

RUN pip install --no-cache-dir pytest pytest-asyncio httpx ruff
COPY tests ./tests

CMD ["pytest"]
