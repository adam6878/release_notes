FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
# Installed into /install so the final stage copies only the packages, not the pip cache.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim
# No .pyc files and unbuffered logs; with no bytecode writes the root filesystem can be read-only.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Numeric UID so Kubernetes can verify runAsNonRoot.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /srv
COPY --from=builder /install /usr/local
COPY app ./app

USER 10001
EXPOSE 8000

# Exec form: SIGTERM goes straight to uvicorn, which finishes in-flight requests before exiting.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
