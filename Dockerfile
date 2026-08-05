FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/home/ados/.local/bin:${PATH}"

WORKDIR /app

# The API does not need a compiler at runtime. Keep the image small and run it
# as an unprivileged user; database migrations use the same immutable image.
RUN groupadd --system --gid 10001 ados \
    && useradd --system --uid 10001 --gid ados --home-dir /home/ados ados

COPY requirements.txt pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install --no-deps .

COPY alembic.ini ./
COPY migrations ./migrations

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"

CMD ["uvicorn", "agent_data_os.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
