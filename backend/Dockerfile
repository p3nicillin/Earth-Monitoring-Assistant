FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system earth && useradd --system --gid earth --create-home earth
WORKDIR /app

COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

USER earth
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
