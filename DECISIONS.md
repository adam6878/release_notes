# Decisions

## AI assistance
I used Claude Code (an AI assistant) while building this. I reviewed every change and can
explain every line.

## Assumptions
- "Internal tool" means no authentication; it would sit behind the company SSO or VPN.
- A release is identified by its version string, which must be unique.
- The local cluster is the target for Parts 2 and 4; the pipeline does not reach a real cluster.

## Service
- **One file per job.** `main.py` only builds the app. Routes live in `app/routers/`, API
  shapes in `schemas.py`, the table in `db.py`, settings in `config.py`, and logging,
  metrics and the request middleware in `logger.py`, `metrics.py` and `middleware.py`.
  Packages re-export their public names through `__init__.py` with `__all__`.
- **No `/v1` prefix.** The only consumer is the bundled UI, which ships in the same image.
  I would add `/api/v1` when a second consumer exists.
- **Separate request and response models** (`ReleaseIn`, `ReleaseOut`), so input is
  validated and the response shape is fixed and documented.
- **Duplicate versions return 409, enforced by a unique constraint** in the database, so the
  rule holds with several replicas writing at once.
- **SQLAlchemy Core, not the ORM.** There is one table and no relationships, so mapped
  classes and a `Session` would add a second definition of the data and a lifecycle to manage
  for nothing. I would move to the ORM when a related table appears.
- **PostgreSQL in the cluster, SQLite locally**, chosen by `DATABASE_URL`.
- **Tables are created on startup** (`create_all`). This is a shortcut: replicas starting
  together can race. In production I would run Alembic migrations as a Job before the rollout.
- **Config from environment variables** (pydantic-settings). `DATABASE_URL` has no default,
  so a missing Secret stops startup instead of silently writing to a throwaway SQLite file.
- **Minimal UI:** one static HTML file, no build step, served by the API container. It
  renders with `textContent`, so notes cannot inject script. Splitting it into its own image
  only pays off with a separate frontend team or release cadence.

## Health, metrics and logs
- **Liveness does not touch the database; readiness does.** A database outage then takes pods
  out of rotation instead of restarting all of them at once.
- **Prometheus pull model.** The app serves `/metrics`; pods carry the standard
  `prometheus.io/scrape` annotations. I did not deploy Prometheus: in a real cluster the
  platform runs it (with the Operator I would ship a `ServiceMonitor`).
- **Bounded label values.** The `path` label is the real path only for matched API routes;
  everything else is `other`, so random URLs cannot create unlimited time series. This rule
  must switch to route templates once a route has path parameters.
- **JSON logs to stdout**, one line per request; probes and scrapes are counted, not logged.

## Container and Kubernetes
- **Image:** multi-stage build on `python:3.11-slim`, numeric non-root user, exec-form `CMD` so
  SIGTERM reaches uvicorn. The build stage keeps the pip cache and build leftovers out of the
  final image. `.dockerignore` keeps `.env` and git history out.
- **Helm over plain manifests or Kustomize:** I have used it in production, and it gives one
  set of templates with small per-environment values files, `helm lint` for CI, and
  `helm rollback` as the one-command way back.
- **Secrets:** the chart only references a Secret by name. `make up` generates the database
  password once with `openssl` and stores it only in the cluster. Non-secret settings
  (`LOG_LEVEL`) go in a ConfigMap; a checksum annotation rolls the pods when it changes.
  The Secret holds only the password; host, user and database name are plain chart values,
  and the Deployment assembles `DATABASE_URL` from them.
- **Pods:** liveness and readiness probes, CPU and memory requests and limits, read-only root
  filesystem, all capabilities dropped, `RollingUpdate` with `maxUnavailable: 0`. An init
  container waits for PostgreSQL so the app does not crash-loop during a cold start.
- **Scaling:** fixed 2 replicas in dev; an HPA on CPU (2 to 4 pods) in prod. metrics-server
  is installed by `make up`.
- **PostgreSQL** runs as a single-replica StatefulSet with a PersistentVolume, written in the
  chart rather than pulled in as a third-party subchart.
- **kind** as the local cluster: it runs in Docker and loads local images without a registry.
  I first used minikube; on this machine both failed because Docker ran cgroup v1, which
  current Kubernetes refuses. The fix was switching WSL2 to cgroup v2 (see README).
  `kind.yaml` also raises kubeadm's timeouts, because the first control-plane start on a
  2-CPU VM took longer than kubeadm's 1-minute default.

## Tests
- **Tests drive the real app over HTTP** (FastAPI `TestClient`), including middleware, routing,
  validation and a real SQL database, rather than unit-testing functions in isolation.
- **The same suite runs twice in CI:** on SQLite (fast, no server) and on PostgreSQL 16 as a
  service container, so the production driver, the unique constraint and timestamps are covered.
  The test database comes from `TEST_DATABASE_URL`, never `DATABASE_URL`, because the fixture
  deletes all rows and must not touch a real database from someone's shell.
- **No separate tests against the deployed cluster:** the Part 4 rollout script sends real
  traffic to the running stack and is that end-to-end check.

## CI/CD (GitHub Actions, `.github/workflows/ci.yml`)
- **Every push and pull request:** `ruff` lint; tests on SQLite and PostgreSQL; `helm lint` plus
  `helm template | kubeconform -strict` for both environments; image build tagged with the commit
  SHA. The image job runs only after the other three pass.
- **Push to `main` only:** the image is pushed to GHCR, then CI commits the new repository and
  tag into `deploy/values-prod.yaml`.
- **GitOps over a direct deploy step.** CI never holds cluster credentials and never talks to a
  cluster. A GitOps agent in the cluster (Argo CD or Flux) watches `main` and applies what it
  says, so git is the record of what runs in prod, drift is corrected, and a rollback is a
  `git revert` of the bump commit. The cost is a bot commit per release and a short delay until
  the agent syncs. The agent itself is not part of this repo; the local cluster is deployed with
  `make up`, which overrides the image with the locally built one.
- **Known limits:** the bump commit needs `main` to accept pushes from `github-actions[bot]`
  (with branch protection, a bot pull request instead). Actions are pinned to major versions;
  in production I would pin them to commit SHAs.

## Cut for time
Zero-downtime rollout script and graceful-shutdown tuning (Part 4), PodDisruptionBudget,
NetworkPolicy, Ingress, database backups, Alembic migrations, a secret manager,
authentication, image signing and vulnerability scanning.

## For a real rollout across many clusters
- **Infrastructure with Terraform:** one cluster per environment and region, a managed
  PostgreSQL in place of the in-cluster StatefulSet, networking and IAM.
- **GitOps (Argo CD or Flux)** instead of `make up`: CI publishes the image and bumps the tag
  in a config repository; each cluster pulls its own desired state, and an
  ApplicationSet-style template avoids copying configuration per cluster.
- **Secrets from a secret manager** (External Secrets Operator or Sealed Secrets), not
  generated at deploy time.
- **Progressive delivery:** roll out to one cluster or a canary share first, gate on error rate
  and latency from Prometheus, then widen.
- **Schema changes** as expand/contract migrations run before the rollout, so old and new pods
  can share the database.
- **Images from a registry**, signed, scanned in CI, and referenced by digest.
