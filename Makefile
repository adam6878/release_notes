SHELL := bash

# Override on the command line, e.g. make up ENV=prod, make rollout TAG=v2.
ENV    ?= dev
TAG    ?= $(shell git rev-parse --short HEAD)

CLUSTER := release-notes
RELEASE := release-notes
IMAGE   := release-notes
CHART   := deploy
METRICS_SERVER := https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
LOAD_TEST := python scripts/load_test.py

.PHONY: up cluster metrics-server image secret deploy rollout rollback down clean

# Clean machine to running stack. Every step is safe to re-run.
up: cluster metrics-server image secret deploy
	@echo "Up. dev UI: http://localhost:8080  (other envs: kubectl -n $(ENV) port-forward svc/$(RELEASE) 8081:80)"

cluster:
	kind get clusters | grep -qx $(CLUSTER) || kind create cluster --name $(CLUSTER) --config kind.yaml
	kubectl config use-context kind-$(CLUSTER)

# Feeds the HPA. kind's kubelet certificates are self-signed, hence --kubelet-insecure-tls.
metrics-server:
	kubectl apply -f $(METRICS_SERVER)
	kubectl -n kube-system patch deployment metrics-server --type=json \
		-p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

image:
	docker build -t $(IMAGE):$(TAG) .
	kind load docker-image $(IMAGE):$(TAG) --name $(CLUSTER)

# Creates the namespace, then the DB password: generated once, it lives only in the cluster Secret.
secret:
	kubectl create namespace $(ENV) --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n $(ENV) get secret release-notes-db >/dev/null 2>&1 || \
		kubectl -n $(ENV) create secret generic release-notes-db \
			--from-literal=POSTGRES_PASSWORD=$$(openssl rand -hex 16)

deploy:
	helm upgrade --install $(RELEASE) $(CHART) -n $(ENV) -f $(CHART)/values-$(ENV).yaml \
		--set image.repository=$(IMAGE) --set image.tag=$(TAG) --wait --timeout 180s

# rollout and rollback start the load test in the background (&), change the pods, then wait
# for the load test's report; its exit code is the result. If the change fails, make stops at once.

# Zero-downtime check: build and roll out TAG under steady traffic; expect 0 failed.
rollout:
	$(LOAD_TEST) & $(MAKE) image deploy TAG=$(TAG) && wait $$!

# One-command way back to the previous Helm revision, measured the same way.
rollback:
	$(LOAD_TEST) & helm rollback $(RELEASE) -n $(ENV) --wait && wait $$!

down:
	helm uninstall $(RELEASE) -n $(ENV)
	kubectl delete pvc --all -n $(ENV)
	kubectl delete namespace $(ENV)

clean:
	kind delete cluster --name $(CLUSTER)
