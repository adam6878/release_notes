# Release Notes

A small internal tool to record what shipped in each release and view the history.
It is a FastAPI service with a minimal web UI, backed by PostgreSQL, packaged as one
container image and deployed to a local Kubernetes cluster (kind) with a Helm chart.

## Architecture

```
            localhost:8080
                  │  (kind port mapping → NodePort 30080, dev only)
                  ▼
        ┌──────────────────┐        ┌───────────────────────────┐
        │ Service          │        │ Deployment: release-notes │
        │ release-notes    │──────▶ │  2+ pods, one container:  │
        └──────────────────┘        │  FastAPI API + static UI  │
                                    └─────────────┬─────────────┘
                                                  │ DATABASE_URL
                                                  ▼
                                    ┌───────────────────────────┐
                                    │ StatefulSet: postgres     │
                                    │  1 pod + PersistentVolume │
                                    └───────────────────────────┘
```

- **One image serves the API and the UI.** FastAPI serves `app/static/index.html` and the
  JSON API on the same origin, so there is no CORS and no separate frontend deployment.
- **API:** `GET /api/releases` lists releases (newest first). `POST /api/releases` records
  one (`version`, `title`, `author`, `notes`). A duplicate version returns `409`.
- **Operations endpoints** sit outside `/api`:
  `/healthz` (liveness, no DB call), `/readyz` (readiness, checks the DB),
  `/metrics` (Prometheus format: request count and latency by method, path and status).
- **Logs** are JSON, one line per request, written to stdout.
- **Configuration** comes from environment variables (`DATABASE_URL`, `LOG_LEVEL`).
  In the cluster, non-secret values come from a ConfigMap and the database password from a
  Secret that is generated at deploy time and never stored in git.
- **Environments:** one Helm chart in `deploy/` with `values-dev.yaml` and `values-prod.yaml`
  on top of shared defaults. Each environment installs into its own namespace.

## Prerequisites

- Docker Desktop (or another Docker engine) running with **cgroup v2**.
  On Windows with the WSL2 backend, add this under `[wsl2]` in `%USERPROFILE%\.wslconfig`,
  then run `wsl --shutdown` and restart Docker Desktop:
  ```
  kernelCommandLine = cgroup_no_v1=all
  ```
  Current Kubernetes versions do not start on cgroup v1.
- `kind`, `kubectl`, `helm`, `make`, `openssl`
- `bash` on the PATH (on Windows: Git Bash). The Makefile runs its recipes with bash.

## Bring the stack up

From a clean machine (no cluster yet):

```
make up
```

This creates the kind cluster `release-notes`, installs metrics-server, builds the image
(tagged with the current git commit), loads it into the cluster, creates the namespace and
the database Secret, and installs the chart with `helm upgrade --install --wait`.
Running it again is safe: existing pieces are reused.

Then open **http://localhost:8080**.

Other commands:

| Command | What it does |
|---|---|
| `make up ENV=prod` | Installs the prod settings into namespace `prod` (HPA on, ClusterIP service). Reach it with `kubectl -n prod port-forward svc/release-notes 8081:80`. |
| `make down` | Uninstalls the release and deletes the namespace **and its database volume**. |
| `make clean` | Deletes the whole kind cluster. |

The first `make up` takes several minutes (node image pull and control-plane start).

## Run locally without Kubernetes

```
python -m venv venv
venv\Scripts\activate            # Windows; on Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # SQLite by default
uvicorn app.main:app --reload --no-access-log
```

Then open http://127.0.0.1:8000 (API docs at `/docs`).

## Tests

```
pip install -r requirements-dev.txt
pytest
```

Tests run the real app through FastAPI's `TestClient` against a temporary SQLite database,
so no server or PostgreSQL is needed. They cover the API (create, list order, duplicate
version, validation), the UI route, liveness and readiness (including a real database
failure), metric labels, and request logging.

To run the same suite against PostgreSQL, as CI does, point `TEST_DATABASE_URL` at a
**throwaway** database (the tests delete all rows):

```
docker run -d --rm --name rn-test-pg -p 55432:5432 -e POSTGRES_USER=release \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=releases postgres:16
TEST_DATABASE_URL=postgresql+psycopg://release:test@localhost:55432/releases pytest
docker stop rn-test-pg
```

## CI/CD

GitHub Actions, `.github/workflows/ci.yml`:

- **Every push and pull request:** `ruff` lint, tests on SQLite and PostgreSQL, `helm lint` and
  `kubeconform` schema checks for dev and prod, and an image build tagged with the commit SHA.
- **Push to `main`:** the image is pushed to `ghcr.io/<owner>/release-notes:<sha>`, and CI
  commits that image into `deploy/values-prod.yaml`. A GitOps agent (Argo CD or Flux) watching
  `main` deploys it; CI itself never connects to a cluster. See DECISIONS.md for why.

## Configuration

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | none | SQLAlchemy URL. The app refuses to start without it. |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` in dev, `INFO` in prod. |

## Repository layout

```
app/                 FastAPI service
  main.py            entrypoint: builds the app, wires routers and middleware
  routers/           releases, health, metrics endpoints
  config.py          settings from environment variables
  db.py              table definition and engine
  schemas.py         request and response models
  logger.py          JSON log formatter
  metrics.py         Prometheus metric definitions
  middleware.py      per-request metrics and logging
  static/index.html  the UI (single file, no build step)
tests/               pytest suite (API, health, metrics, logging)
deploy/              Helm chart (values.yaml, values-dev.yaml, values-prod.yaml, templates/)
.github/workflows/   CI/CD pipeline
requirements-dev.txt test and lint dependencies (kept out of the image)
Dockerfile           production image (multi-stage, non-root)
kind.yaml            local cluster definition
Makefile             make up / down / clean
DECISIONS.md         trade-offs and what was cut
```

## Troubleshooting

- **`kubeadm init` fails or the API server never starts:** check that Docker runs cgroup v2
  (`docker info --format '{{.CgroupVersion}}'` must print `2`), then `make clean && make up`.
- **Slow first start:** `kind.yaml` already gives kubeadm 5 minutes. Giving Docker more CPUs
  (`processors=` in `.wslconfig`) shortens it.
- **Port 8080 already in use:** change `hostPort` in `kind.yaml`, then `make clean && make up`.
