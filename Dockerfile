# syntax=docker/dockerfile:1

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system --gid 10001 suanpan \
    && adduser --system --uid 10001 --ingroup suanpan --home /app suanpan

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=suanpan:suanpan main.py ./
COPY --chown=suanpan:suanpan core ./core
COPY --chown=suanpan:suanpan routes ./routes
COPY --chown=suanpan:suanpan utils ./utils
COPY --chown=suanpan:suanpan docs ./docs

USER suanpan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthcheck', timeout=3)); assert data.get('status') == 'healthy'"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
