# Design Spec: Helm-Based API Service with Nginx Ingress

**Date:** 2026-04-09  
**Status:** Approved (revised — multi-service subdomain architecture)

---

## Overview

A learning project that deploys three instances of a FastAPI service to a local Docker Desktop Kubernetes cluster via a single Helm umbrella chart. Each instance runs as its own pod, is differentiated by a `SERVICE_NAME` environment variable, and is accessed via a distinct subdomain (`api1.local`, `api2.local`, `api3.local`). The nginx ingress controller performs host-based routing. Designed to mirror real multi-service architectures and be portable to AKS with minimal changes.

---

## Goals

- Deploy 3 pods (one per API service) using the same Docker image, differentiated by `SERVICE_NAME` env var
- Route external traffic via nginx ingress using host-based routing (one subdomain per service)
- Support both HTTP (port 80) and HTTPS (port 443) — TLS via nginx's built-in fake self-signed certificate
- Everything installable in one command from a clean Docker Desktop cluster

---

## Non-Goals

- Real TLS certificates (cert-manager, Let's Encrypt)
- Authentication or authorization
- Database or persistent storage
- External container registry (local build only for now)

---

## Repo Structure

```
test-app-cluster/
├── app/
│   ├── main.py                 # FastAPI app — reads SERVICE_NAME env var, 3 endpoints
│   ├── requirements.txt        # fastapi, uvicorn, httpx, pytest
│   └── Dockerfile              # python:3.12-slim, runs uvicorn on port 8080
├── tests/
│   └── test_main.py            # Pytest tests for all 3 endpoints
├── charts/
│   └── test-app/               # Umbrella Helm chart
│       ├── Chart.yaml          # declares ingress-nginx as subchart dependency
│       ├── values.yaml         # services list, image, ingress TLS flag, subchart overrides
│       ├── charts/             # downloaded subchart (gitignored, populated by helm dep update)
│       └── templates/
│           ├── deployment.yaml # loops over .Values.services → 3 Deployments
│           ├── service.yaml    # loops over .Values.services → 3 Services
│           └── ingress.yaml    # host-based rules, one per service; TLS with nginx fake cert
├── Makefile                    # build, dep-update, install, uninstall, status, test targets
├── .gitignore
└── README.md
```

---

## Application

**Runtime:** Python 3.12, FastAPI, Uvicorn  
**Port:** 8080 (inside container)  
**Configuration:** `SERVICE_NAME` environment variable (default: `"unknown"`)

**Endpoints:**

| Path | Method | Response |
|------|--------|----------|
| `/hello` | GET | `{"service": "<SERVICE_NAME>", "message": "Hello, World!"}` |
| `/goodbye` | GET | `{"service": "<SERVICE_NAME>", "message": "Goodbye, World!"}` |
| `/test` | GET | `{"service": "<SERVICE_NAME>", "message": "Test endpoint OK", "status": "healthy"}` |

**Dockerfile:**
- Base: `python:3.12-slim`
- Copies `requirements.txt`, installs deps
- Copies `main.py`
- Entrypoint: `uvicorn main:app --host 0.0.0.0 --port 8080`

**Local image workflow:** Build with `docker build`, Docker Desktop Kubernetes shares the host Docker daemon — no push needed. `imagePullPolicy: IfNotPresent` ensures the locally built image is used.

---

## Helm Chart

### values.yaml (key fields)

```yaml
services:
  - name: api1
    host: api1.local
  - name: api2
    host: api2.local
  - name: api3
    host: api3.local

image:
  repository: test-app
  tag: latest
  pullPolicy: IfNotPresent

replicaCount: 1

service:
  type: ClusterIP
  port: 80
  targetPort: 8080

ingress:
  tls: true              # uses nginx default fake cert

ingress-nginx:
  controller:
    service:
      type: LoadBalancer
```

### Templates

**deployment.yaml** — iterates over `.Values.services` with `range`, creating one Deployment per service. Each Deployment sets `SERVICE_NAME` as an env var from the service's `name` field.

**service.yaml** — iterates over `.Values.services` with `range`, creating one ClusterIP Service per Deployment.

**ingress.yaml** — single Ingress resource with one host rule per service (host-based routing). TLS block lists all three hosts; no `secretName` → nginx serves its built-in fake certificate for all.

---

## Ingress & TLS

The `ingress-nginx` controller is deployed via subchart. On Docker Desktop, its LoadBalancer service binds to `localhost:80` and `localhost:443`.

Traffic routing:
```
api1.local → api1 Service:80 → api1 Pod (SERVICE_NAME=api1)
api2.local → api2 Service:80 → api2 Pod (SERVICE_NAME=api2)
api3.local → api3 Service:80 → api3 Pod (SERVICE_NAME=api3)
```

**TLS:** nginx serves its default fake self-signed cert (`O=Acme Co`) for all three hostnames. The cert has no SANs for these hosts so browsers warn — expected. Use `curl -sk` to skip verification.

**Local DNS:** User adds one `/etc/hosts` entry before testing:
```
127.0.0.1  api1.local api2.local api3.local
```

---

## Smoke Tests (after install)

```bash
# HTTP
curl -s http://api1.local/hello    # → {"service":"api1","message":"Hello, World!"}
curl -s http://api2.local/hello    # → {"service":"api2","message":"Hello, World!"}
curl -s http://api3.local/hello    # → {"service":"api3","message":"Hello, World!"}

# HTTPS (cert warning expected)
curl -sk https://api1.local/hello  # → same responses
curl -sk https://api2.local/hello
curl -sk https://api3.local/hello
```

---

## AKS Migration Path

When moving to AKS:
1. Push image to Azure Container Registry (ACR), update `image.repository` + `image.tag`
2. Change `host` values in `services` list: `api1.local` → `api1.davidpacold.com` etc.
3. Add cert-manager + Let's Encrypt annotation to ingress template for real TLS
4. Optionally extract `ingress-nginx` into its own shared chart

No structural changes to the Helm chart are required for steps 1–2.
