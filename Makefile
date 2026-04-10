# Makefile
IMAGE_NAME := test-app
IMAGE_TAG  := latest
CHART_DIR  := charts/test-app
RELEASE    := test-app
NAMESPACE  := default

.PHONY: build install uninstall status test dep-update

## Build the Docker image
build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) ./app

## Download Helm chart dependencies
dep-update:
	helm dependency update $(CHART_DIR)

## Install (or upgrade) the Helm release
install: dep-update
	helm upgrade --install $(RELEASE) $(CHART_DIR) \
		--namespace $(NAMESPACE) \
		--wait --timeout 3m

## Uninstall the Helm release
uninstall:
	helm uninstall $(RELEASE) --namespace $(NAMESPACE)

## Show status of pods, services, and ingress
status:
	kubectl get pods,svc,ingress --namespace $(NAMESPACE)

## Run unit tests
test:
	pytest tests/ -v
