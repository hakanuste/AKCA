FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AKCA_DB_PATH=/data/akca.db
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY web ./web
COPY docs ./docs
RUN python -m pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "akca.api:app", "--host", "0.0.0.0", "--port", "8000"]
