SHELL := cmd.exe

ENV    ?= dev
TAG    ?= $(shell git rev-parse --short HEAD)

ifeq ($(ENV),prod)
TARGET ?= 127.0.0.1:8081
else
TARGET ?= 127.0.0.1:8080
endif

CLUSTER := release-notes
RELEASE := release-notes
IMAGE   := release-notes
CHART   := deploy
METRICS_SERVER := https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
LOAD_TEST := python scripts/load_test.py $(TARGET)

.PHONY: up cluster metrics-server image secret deploy rollout rollback down clean

up: cluster metrics-server image secret deploy
	@echo Up. $(ENV) UI: http://$(TARGET)

# export kubeconfig writes the cluster into ~/.kube/config and makes it current, even if another tool overwrote it.
cluster:
	kind get kubeconfig --name $(CLUSTER) >nul 2>&1 || kind create cluster --name $(CLUSTER) --config kind.yaml
	kind export kubeconfig --name $(CLUSTER)

# metrics-server feeds the HPA. kind's kubelet certificates are self-signed, hence --kubelet-insecure-tls.
metrics-server:
	kubectl apply -f $(METRICS_SERVER)
	kubectl -n kube-system patch deployment metrics-server --type=json -p "[{\"op\":\"add\",\"path\":\"/spec/template/spec/containers/0/args/-\",\"value\":\"--kubelet-insecure-tls\"}]"

image:
	docker build -t $(IMAGE):$(TAG) .
	kind load docker-image $(IMAGE):$(TAG) --name $(CLUSTER)

secret:
	kubectl create namespace $(ENV) --dry-run=client -o yaml | kubectl apply -f -
	@kubectl -n $(ENV) get secret release-notes-db >nul 2>&1 || kubectl -n $(ENV) create secret generic release-notes-db --from-literal=POSTGRES_PASSWORD=$(shell python -c "import secrets; print(secrets.token_hex(16))")

deploy:
	helm upgrade --install $(RELEASE) $(CHART) -n $(ENV) -f $(CHART)/values-$(ENV).yaml --set image.repository=$(IMAGE) --set image.tag=$(TAG) --wait --timeout 180s
	

rollout:
	cmd /c start /b $(MAKE) image deploy TAG=$(TAG)
	$(LOAD_TEST)

rollback:
	cmd /c start /b helm rollback $(RELEASE) -n $(ENV) --wait
	$(LOAD_TEST)

down:
	helm uninstall $(RELEASE) -n $(ENV)
	kubectl delete pvc --all -n $(ENV)
	kubectl delete namespace $(ENV)

clean:
	kind delete cluster --name $(CLUSTER)
