FROM node:24.21.0-bookworm-slim AS frontend
WORKDIR /build/frontend
RUN npm install --global npm@12.2.0
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim-bookworm AS python-build
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim-bookworm
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HUGINN_FRONTEND_ASSETS_PATH=/app/frontend/dist
RUN groupadd --gid 10001 huginn && useradd --uid 10001 --gid huginn --create-home huginn
COPY --from=python-build /app/.venv /app/.venv
COPY --from=frontend /build/frontend/dist /app/frontend/dist
COPY docker/seed-admin.py /app/docker/seed-admin.py
COPY db/schema/operational-bootstrap-admin.sql /app/db/schema/operational-bootstrap-admin.sql
USER huginn
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "huginn.management.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
