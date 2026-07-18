FROM python:3.13.2-slim-bookworm@sha256:6b3223eb4d93718828223966ad316909c39813dee3ee9395204940500792b740

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-runtime.lock ./
RUN python -m pip install --requirement requirements-runtime.lock \
    && useradd --create-home --uid 10001 appuser

COPY app ./app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
