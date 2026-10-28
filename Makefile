SHELL := bash

ENV   ?= dev
TAG   ?= $(shell git rev-parse --short HEAD)
IMAGE   := release-notes
CHART   := deploy
CLUSTER := release-notes
METRICS_SERVER := https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml

.PHONY: up down clean

# Clean machine to running stack: cluster, image, secret, chart. Safe to re-run.
up:
	kind get clusters | grep -qx $(CLUSTER) || kind create cluster --name $(CLUSTER) --config kind.yaml
	kubectl config use-context kind-$(CLUSTER)
	# metrics-server feeds the HPA. kind's kubelet certificates are self-signed, hence --kubelet-insecure-tls.
	kubectl apply -f $(METRICS_SERVER)
	kubectl -n kube-system patch deployment metrics-server --type=json \
		-p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
	docker build -t $(IMAGE):$(TAG) .
	kind load docker-image $(IMAGE):$(TAG) --name $(CLUSTER)
	kubectl create namespace $(ENV) --dry-run=client -o yaml | kubectl apply -f -
	# The password is generated here, once, and lives only in the cluster Secret.
	kubectl -n $(ENV) get secret release-notes-db >/dev/null 2>&1 || \
		kubectl -n $(ENV) create secret generic release-notes-db \
			--from-literal=POSTGRES_PASSWORD=$$(openssl rand -hex 16)
	helm upgrade --install release-notes $(CHART) -n $(ENV) \
		-f $(CHART)/values-$(ENV).yaml --set image.tag=$(TAG) --wait --timeout 180s
	@echo "Up. dev UI: http://localhost:8080  (other envs: kubectl -n $(ENV) port-forward svc/release-notes 8081:80)"

down:
	helm uninstall release-notes -n $(ENV)
	kubectl delete pvc --all -n $(ENV)
	kubectl delete namespace $(ENV)

clean:
	kind delete cluster --name $(CLUSTER)
