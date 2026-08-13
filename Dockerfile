FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv --no-cache-dir
RUN uv sync --frozen --no-cache

COPY . .

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]