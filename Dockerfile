FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -U pip pdm

COPY pyproject.toml pdm.lock* README.md /app/

RUN pdm config python.use_venv false && \
    pdm install --prod --no-editable

RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch


COPY . /app

EXPOSE 8080

CMD ["pdm","run","python","app.py"]