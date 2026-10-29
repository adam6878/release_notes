FROM python:3.15-slim AS builder
WORKDIR /build
COPY requirements.txt .
# Installed into /install so the final stage copies only the packages, not the pip cache.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.15-slim
# No .pyc files and unbuffered logs; with no bytecode writes the root filesystem can be read-only.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Numeric UID so Kubernetes can verify runAsNonRoot.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
# The app never runs pip; removing it drops the CVEs in its bundled urllib3, msgpack and setuptools.
RUN pip uninstall --yes --root-user-action=ignore pip

WORKDIR /srv
COPY --from=builder /install /usr/local
COPY app ./app
COPY run.py .

USER 10001
EXPOSE 8000

# Exec form: python is PID 1, so SIGTERM goes straight to uvicorn, which finishes in-flight
# requests before exiting.
# ENTRYPOINT, not CMD: arguments passed to `docker run` or a pod's `args` cannot replace it.
ENTRYPOINT ["python", "run.py"]
