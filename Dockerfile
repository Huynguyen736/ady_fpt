FROM python:3.11-slim

WORKDIR /app

# Cài uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy file dependency trước để tận dụng cache
COPY pyproject.toml uv.lock ./

# Cài dependency vào system env trong container
RUN uv sync --frozen --no-dev

# Copy source code và model
COPY app ./app
COPY model_with_threshold.pkl ./model_with_threshold.pkl

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]