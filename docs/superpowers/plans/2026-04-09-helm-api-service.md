# Helm API Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy 3 independent FastAPI pods (api1, api2, api3) to Docker Desktop Kubernetes via a single Helm umbrella chart, with nginx ingress routing traffic by subdomain (api1.local, api2.local, api3.local) on both HTTP and HTTPS.

**Architecture:** A single Docker image reads a `SERVICE_NAME` env var to identify itself. A Helm umbrella chart defines a `services` list in values.yaml and uses `range` loops in templates to produce 3 Deployments, 3 Services, and one Ingress with host-based rules. The `ingress-nginx` chart is bundled as a subchart dependency.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Docker, Helm 3, Kubernetes (Docker Desktop), ingress-nginx 4.11.3, pytest, httpx

---

## File Map

| File | Responsibility |
|------|---------------|
| `app/main.py` | FastAPI app — reads SERVICE_NAME env var, 3 endpoints |
| `app/requirements.txt` | Runtime + test dependencies |
| `app/Dockerfile` | Container image build |
| `tests/test_main.py` | Pytest unit tests for all 3 endpoints (mocking SERVICE_NAME) |
| `charts/test-app/Chart.yaml` | Chart metadata + ingress-nginx dependency declaration |
| `charts/test-app/values.yaml` | services list, image, ingress TLS flag, subchart overrides |
| `charts/test-app/.helmignore` | Ignore patterns for helm packaging |
| `charts/test-app/templates/deployment.yaml` | range loop → 3 Deployments with SERVICE_NAME env var |
| `charts/test-app/templates/service.yaml` | range loop → 3 ClusterIP Services |
| `charts/test-app/templates/ingress.yaml` | Host-based Ingress with TLS (nginx fake cert) |
| `Makefile` | build, dep-update, install, uninstall, status, test targets |
| `.gitignore` | Already created in Task 1 |

---

### Task 1: Initialize repo structure and git ✅ COMPLETE

---

### Task 2: FastAPI app + unit tests (TDD)

**Note:** app/main.py was already created but needs to be updated to read `SERVICE_NAME` from the environment.

**Files:**
- Update: `app/main.py` — add SERVICE_NAME env var
- Update: `tests/test_main.py` — test SERVICE_NAME behavior
- Existing: `app/requirements.txt`, `app/__init__.py`, `tests/__init__.py` — no changes needed

- [ ] **Step 1: Update tests to cover SERVICE_NAME behavior**

Write to `tests/test_main.py` (replaces existing file):

```python
# tests/test_main.py
import os
import pytest
from fastapi.testclient import TestClient


def make_client(service_name: str):
    os.environ["SERVICE_NAME"] = service_name
    # Re-import to pick up new env var
    import importlib
    import app.main
    importlib.reload(app.main)
    from app.main import app
    return TestClient(app)


def test_hello_returns_200() -> None:
    client = make_client("api1")
    response = client.get("/hello")
    assert response.status_code == 200


def test_hello_includes_service_name() -> None:
    client = make_client("api1")
    response = client.get("/hello")
    assert response.json() == {"service": "api1", "message": "Hello, World!"}


def test_goodbye_returns_200() -> None:
    client = make_client("api2")
    response = client.get("/goodbye")
    assert response.status_code == 200


def test_goodbye_includes_service_name() -> None:
    client = make_client("api2")
    response = client.get("/goodbye")
    assert response.json() == {"service": "api2", "message": "Goodbye, World!"}


def test_test_returns_200() -> None:
    client = make_client("api3")
    response = client.get("/test")
    assert response.status_code == 200


def test_test_includes_service_name() -> None:
    client = make_client("api3")
    response = client.get("/test")
    assert response.json() == {"service": "api3", "message": "Test endpoint OK", "status": "healthy"}


def test_default_service_name() -> None:
    os.environ.pop("SERVICE_NAME", None)
    import importlib
    import app.main
    importlib.reload(app.main)
    from app.main import app
    client = TestClient(app)
    response = client.get("/hello")
    assert response.json()["service"] == "unknown"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/davidpacold/Github/test-app-cluster
pytest tests/test_main.py -v
```

Expected: tests fail because current `app/main.py` doesn't include `service` in responses.

- [ ] **Step 3: Update app/main.py to read SERVICE_NAME**

Write to `app/main.py` (replaces existing file):

```python
# app/main.py
import os
from fastapi import FastAPI

SERVICE_NAME: str = os.getenv("SERVICE_NAME", "unknown")

app = FastAPI(title="Test App", version="1.0.0")


@app.get("/hello")
def hello() -> dict:
    return {"service": SERVICE_NAME, "message": "Hello, World!"}


@app.get("/goodbye")
def goodbye() -> dict:
    return {"service": SERVICE_NAME, "message": "Goodbye, World!"}


@app.get("/test")
def test_endpoint() -> dict:
    return {"service": SERVICE_NAME, "message": "Test endpoint OK", "status": "healthy"}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/davidpacold/Github/test-app-cluster
pytest tests/test_main.py -v
```

Expected: 7 tests all PASSED.

- [ ] **Step 5: Commit**

```bash
cd /Users/davidpacold/Github/test-app-cluster
git add app/main.py tests/test_main.py
git commit -m "feat: parameterize FastAPI app with SERVICE_NAME env var"
```

---

### Task 3: Dockerfile + verify build

**Files:**
- Create: `app/Dockerfile`

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# app/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Save to `app/Dockerfile`.

- [ ] **Step 2: Build the image**

```bash
docker build -t test-app:latest ./app
```

Expected: `Successfully built <image-id>` and `Successfully tagged test-app:latest`.

- [ ] **Step 3: Verify the image runs with env var**

```bash
docker run --rm -d -p 8080:8080 -e SERVICE_NAME=api1 --name test-app-verify test-app:latest
sleep 2
curl -s http://localhost:8080/hello
docker stop test-app-verify
```

Expected curl output: `{"service":"api1","message":"Hello, World!"}`

- [ ] **Step 4: Commit**

```bash
git add app/Dockerfile
git commit -m "feat: add Dockerfile for FastAPI service"
```

---

### Task 4: Helm chart skeleton (Chart.yaml + values.yaml + .helmignore)

**Files:**
- Create: `charts/test-app/Chart.yaml`
- Create: `charts/test-app/values.yaml`
- Create: `charts/test-app/.helmignore`

- [ ] **Step 1: Write Chart.yaml**

```yaml
# charts/test-app/Chart.yaml
apiVersion: v2
name: test-app
description: A learning Helm chart deploying 3 FastAPI service instances with nginx ingress
type: application
version: 0.1.0
appVersion: "1.0.0"

dependencies:
  - name: ingress-nginx
    version: "4.11.3"
    repository: "https://kubernetes.github.io/ingress-nginx"
```

Save to `charts/test-app/Chart.yaml`.

- [ ] **Step 2: Write values.yaml**

```yaml
# charts/test-app/values.yaml

# List of API services to deploy — each gets its own Deployment, Service, and Ingress rule
services:
  - name: api1
    host: api1.local
  - name: api2
    host: api2.local
  - name: api3
    host: api3.local

# Application image (same image for all services, differentiated by SERVICE_NAME env var)
image:
  repository: test-app
  tag: latest
  pullPolicy: IfNotPresent

# Number of pod replicas per service
replicaCount: 1

# Service configuration
service:
  type: ClusterIP
  port: 80
  targetPort: 8080

# Ingress configuration
ingress:
  tls: true              # uses nginx default fake cert (no secretName needed)

# ingress-nginx subchart overrides
# Full values reference: https://github.com/kubernetes/ingress-nginx/blob/main/charts/ingress-nginx/values.yaml
ingress-nginx:
  controller:
    service:
      type: LoadBalancer
```

Save to `charts/test-app/values.yaml`.

- [ ] **Step 3: Write .helmignore**

```
# Patterns to ignore when building packages.
.DS_Store
.git/
.gitignore
.vscode/
*.swp
*.bak
```

Save to `charts/test-app/.helmignore`.

- [ ] **Step 4: Commit**

```bash
git add charts/test-app/Chart.yaml charts/test-app/values.yaml charts/test-app/.helmignore
git commit -m "feat: add Helm chart skeleton with ingress-nginx dependency and services list"
```

---

### Task 5: Deployment template

**Files:**
- Create: `charts/test-app/templates/deployment.yaml`

- [ ] **Step 1: Write the Deployment template**

```yaml
# charts/test-app/templates/deployment.yaml
{{- range .Values.services }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $.Release.Name }}-{{ .name }}
  labels:
    app: {{ $.Release.Name }}-{{ .name }}
spec:
  replicas: {{ $.Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ $.Release.Name }}-{{ .name }}
  template:
    metadata:
      labels:
        app: {{ $.Release.Name }}-{{ .name }}
    spec:
      containers:
        - name: api
          image: "{{ $.Values.image.repository }}:{{ $.Values.image.tag }}"
          imagePullPolicy: {{ $.Values.image.pullPolicy }}
          ports:
            - containerPort: {{ $.Values.service.targetPort }}
          env:
            - name: SERVICE_NAME
              value: {{ .name | quote }}
{{- end }}
```

Save to `charts/test-app/templates/deployment.yaml`.

- [ ] **Step 2: Render and inspect with helm template**

```bash
helm template test-app charts/test-app 2>/dev/null | grep -c "kind: Deployment"
```

Expected output: `3`

```bash
helm template test-app charts/test-app 2>/dev/null | grep "SERVICE_NAME" -A 1
```

Expected: three `value:` lines showing `api1`, `api2`, `api3`.

- [ ] **Step 3: Commit**

```bash
git add charts/test-app/templates/deployment.yaml
git commit -m "feat: add Deployment template with range loop for 3 services"
```

---

### Task 6: Service template

**Files:**
- Create: `charts/test-app/templates/service.yaml`

- [ ] **Step 1: Write the Service template**

```yaml
# charts/test-app/templates/service.yaml
{{- range .Values.services }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $.Release.Name }}-{{ .name }}
  labels:
    app: {{ $.Release.Name }}-{{ .name }}
spec:
  type: {{ $.Values.service.type }}
  selector:
    app: {{ $.Release.Name }}-{{ .name }}
  ports:
    - port: {{ $.Values.service.port }}
      targetPort: {{ $.Values.service.targetPort }}
      protocol: TCP
{{- end }}
```

Save to `charts/test-app/templates/service.yaml`.

- [ ] **Step 2: Render and inspect**

```bash
helm template test-app charts/test-app 2>/dev/null | grep -c "kind: Service"
```

Expected output: `3` (not counting Services from the ingress-nginx subchart — if count is higher, check with `grep "kind: Service" -A 3` to confirm all 3 app services are present with correct names).

- [ ] **Step 3: Commit**

```bash
git add charts/test-app/templates/service.yaml
git commit -m "feat: add Service template with range loop for 3 services"
```

---

### Task 7: Ingress template

**Files:**
- Create: `charts/test-app/templates/ingress.yaml`

- [ ] **Step 1: Write the Ingress template**

```yaml
# charts/test-app/templates/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Release.Name }}-api
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    {{- range .Values.services }}
    - host: {{ .host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ $.Release.Name }}-{{ .name }}
                port:
                  number: {{ $.Values.service.port }}
    {{- end }}
  {{- if .Values.ingress.tls }}
  tls:
    {{- range .Values.services }}
    - hosts:
        - {{ .host }}
    {{- end }}
  {{- end }}
```

Save to `charts/test-app/templates/ingress.yaml`.

Note: Each service gets its own TLS entry with no `secretName` — nginx serves the built-in fake cert for all three hosts.

- [ ] **Step 2: Render and inspect**

```bash
helm template test-app charts/test-app 2>/dev/null | grep -A 50 "kind: Ingress" | head -60
```

Expected: One Ingress with 3 host rules (api1.local, api2.local, api3.local) and 3 TLS entries.

- [ ] **Step 3: Run helm lint**

```bash
helm lint charts/test-app
```

Expected: `1 chart(s) linted, 0 chart(s) failed`.

- [ ] **Step 4: Commit**

```bash
git add charts/test-app/templates/ingress.yaml
git commit -m "feat: add Ingress template with host-based routing for 3 subdomains"
```

---

### Task 8: Pull Helm dependencies

**Files:**
- Create: `charts/test-app/Chart.lock` (generated by helm — commit this as the lockfile)
- Populates: `charts/test-app/charts/` (gitignored .tgz files — not committed)

- [ ] **Step 1: Add the ingress-nginx Helm repo**

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
```

Expected: repo added and updated successfully.

- [ ] **Step 2: Download the ingress-nginx subchart**

```bash
helm dependency update charts/test-app
```

Expected:
```
Saving 1 charts
Downloading ingress-nginx from repo https://kubernetes.github.io/ingress-nginx
Deleting outdated charts
```

- [ ] **Step 3: Commit Chart.lock**

```bash
git add charts/test-app/Chart.lock
git commit -m "chore: pin ingress-nginx subchart dependency (Chart.lock)"
```

- [ ] **Step 4: Verify the full chart renders cleanly**

```bash
helm template test-app charts/test-app | grep "^kind:" | sort | uniq -c
```

Expected: shows Deployment (3), Service (multiple — app + nginx), Ingress (1), and various nginx resources.

---

### Task 9: Local DNS + Docker image

**Files:** No new files.

- [ ] **Step 1: Add /etc/hosts entries**

```bash
sudo sh -c 'echo "127.0.0.1  api1.local api2.local api3.local" >> /etc/hosts'
```

Verify:
```bash
grep "api" /etc/hosts
```

Expected: `127.0.0.1  api1.local api2.local api3.local`

- [ ] **Step 2: Confirm Docker Desktop Kubernetes is running**

```bash
kubectl config current-context
kubectl get nodes
```

Expected: context is `docker-desktop`, one node in `Ready` state.

- [ ] **Step 3: Build the image**

```bash
docker build -t test-app:latest ./app
```

Expected: `Successfully tagged test-app:latest`.

- [ ] **Step 4: Verify image is available**

```bash
docker images test-app
```

Expected: `test-app   latest   <id>   <time>   <size>`

---

### Task 10: Install the Helm chart and smoke test

**Files:** No new files.

- [ ] **Step 1: Install the chart**

```bash
helm install test-app charts/test-app --namespace default --wait --timeout 3m
```

Expected: `NAME: test-app` and `STATUS: deployed`.

- [ ] **Step 2: Check pod and service status**

```bash
kubectl get pods,svc,ingress
```

Expected: 3 API pods Running (test-app-api1, test-app-api2, test-app-api3), 1 nginx ingress controller pod Running. Services and Ingress present.

- [ ] **Step 3: Smoke test HTTP endpoints**

```bash
curl -s http://api1.local/hello
curl -s http://api2.local/hello
curl -s http://api3.local/hello
```

Expected:
```
{"service":"api1","message":"Hello, World!"}
{"service":"api2","message":"Hello, World!"}
{"service":"api3","message":"Hello, World!"}
```

- [ ] **Step 4: Smoke test HTTPS endpoints**

```bash
curl -sk https://api1.local/hello
curl -sk https://api2.local/hello
curl -sk https://api3.local/hello
```

Expected: same JSON responses. `-k` skips cert verification (expected — fake cert).

- [ ] **Step 5: Verify host-based routing (cross-check)**

```bash
curl -sk https://api1.local/goodbye
curl -sk https://api2.local/goodbye
curl -sk https://api3.local/goodbye
```

Expected:
```
{"service":"api1","message":"Goodbye, World!"}
{"service":"api2","message":"Goodbye, World!"}
{"service":"api3","message":"Goodbye, World!"}
```

---

### Task 11: Makefile

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Write the Makefile**

```makefile
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
```

Save to `Makefile`.

- [ ] **Step 2: Verify make targets work**

```bash
make test
```

Expected: all 7 pytest tests pass.

```bash
make status
```

Expected: shows pods, services, and ingress.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "chore: add Makefile with build, install, uninstall, status, test targets"
```

---

### Task 12: Final commit — docs

**Files:** Already exist.

- [ ] **Step 1: Commit the docs**

```bash
cd /Users/davidpacold/Github/test-app-cluster
git add docs/
git commit -m "docs: add design spec and implementation plan"
```

- [ ] **Step 2: Verify final repo state**

```bash
git log --oneline
```

Expected: 10+ commits.

```bash
helm list
```

Expected: `test-app` release in `deployed` state.
