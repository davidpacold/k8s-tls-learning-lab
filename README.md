# test-app-cluster

A learning project that mirrors a real multi-service Kubernetes architecture. Three independent API pods, each on its own subdomain, routed by an nginx ingress controller with automated TLS — all deployed via a single Helm chart.

---

## What We Built

```
Your Machine (localhost)
        |
   port 80 / 443
        |
[ nginx ingress controller ]  ← LoadBalancer service (Docker Desktop)
        |
   host-based routing
   ┌────┴────┬─────────────┐
   ▼         ▼             ▼
api1.local  api2.local  api3.local
   │         │             │
[api1 pod] [api2 pod] [api3 pod]
SERVICE_NAME=api1  =api2    =api3
```

- **1 Docker image** — same FastAPI code deployed 3 times, each pod identifies itself via `SERVICE_NAME` env var
- **Host-based routing** — nginx ingress routes traffic to the correct pod based on which subdomain the request arrives on
- **Flexible TLS** — three cert modes: auto-generate, kubectl pre-created, or paste PEM into values
- **Pod-level CA trust** — init container injects the CA root cert into every pod's system trust store at startup, works for both Python and .NET runtimes
- **In-cluster DNS** — `hostAliases` dynamically injected via Helm `lookup` so pods resolve the ingress subdomains correctly

---

## Implementation Checklist

### Repository Setup
- [x] Git repo initialized with `.gitignore` (Helm subcharts, Python artifacts, `.env` files)
- [x] Directory structure: `app/`, `tests/`, `charts/test-app/`, `docs/`

### Application
- [x] FastAPI app (`app/main.py`) with 3 endpoints:
  - `GET /hello` → `{"service": "<name>", "message": "Hello, World!"}`
  - `GET /goodbye` → `{"service": "<name>", "message": "Goodbye, World!"}`
  - `GET /test` → `{"service": "<name>", "message": "Test endpoint OK", "status": "healthy"}`
- [x] `SERVICE_NAME` environment variable drives the service identity in all responses
- [x] Unit tests (`tests/test_main.py`) — 7 tests covering all endpoints + default fallback
- [x] Dockerfile — `python:3.12-slim`, port 8080, uvicorn

### Helm Chart (`charts/test-app/`)
- [x] `Chart.yaml` — umbrella chart with `ingress-nginx 4.11.3` as subchart dependency
- [x] `values.yaml` — configurable services list, image settings, TLS options
- [x] `templates/deployment.yaml` — `range` loop produces 3 Deployments with `SERVICE_NAME` env var
- [x] `templates/service.yaml` — `range` loop produces 3 ClusterIP Services
- [x] `templates/ingress.yaml` — single Ingress with host-based rules, one per subdomain
- [x] `Chart.lock` — dependency lockfile committed

### TLS — Three Certificate Modes

- [x] **Mode 1 — Auto-generate** (`generateCert: true`): Helm generates a self-signed cert via `genSelfSignedCert` covering all 3 SANs. Stored as K8s Secret, reused on `helm upgrade` via `lookup` (no churn). Configurable validity via `ingress.certDays` (default 3650 days).
- [x] **Mode 2 — kubectl pre-created** (`generateCert: false`, empty `externalCert`): User runs `kubectl create secret tls test-app-tls --cert=... --key=...` before install. Helm renders no Secret template and leaves the externally-managed secret untouched.
- [x] **Mode 3 — Paste in values** (`generateCert: false`, `externalCert.crt/key` set): User pastes PEM content into `values.yaml`. Helm creates the K8s Secret from those values.
- [x] Ingress TLS block references `test-app-tls` secret — nginx serves the cert for all 3 subdomains
- [x] Valet MCP used to issue a CA-signed cert (`cert_request_self_signed`) with correct SANs — better than truly self-signed because the issuing Root CA can be distributed separately

### Pod Trust Store
- [x] `trust-ca` init container runs before each API pod starts
- [x] **When `generateCert: true`**: init container appends the TLS cert itself to the system CA bundle
- [x] **When `corporateCA` is set**: init container appends the Root CA cert (from `ingress.corporateCA` in values) — pods trust any cert signed by that CA, not just this one specific cert
- [x] Updated bundle mounted into the main container via shared `emptyDir` volume at `/etc/ssl/certs/ca-certificates.crt`
- [x] Works for both Python and .NET pods (system-level trust via OpenSSL, not language-specific)
- [x] `templates/ca-configmap.yaml` — ConfigMap holding the corporate CA PEM, rendered only when `corporateCA` is set
- [x] Verified: pod-to-pod HTTPS calls succeed without `-k` (full chain verified)

### In-Cluster DNS
- [x] `hostAliases` injected into each pod via Helm `lookup` (dynamically resolves ingress controller ClusterIP at render time)
- [x] `api1.local`, `api2.local`, `api3.local` resolve correctly from inside pods without any manual /etc/hosts changes in the cluster

### Developer Experience
- [x] `Makefile` with targets: `build`, `dep-update`, `install`, `uninstall`, `status`, `test`

---

## Prerequisites

- Docker Desktop with Kubernetes enabled
- `helm` CLI (`brew install helm`)
- `/etc/hosts` entry (one-time, on your Mac — not inside the cluster):
  ```bash
  sudo sh -c 'echo "127.0.0.1  api1.local api2.local api3.local" >> /etc/hosts'
  ```

---

## Quick Start

```bash
# 1. Build the Docker image
make build

# 2. Install the chart (pulls ingress-nginx subchart + deploys everything)
make install

# 3. Check everything is running
make status

# 4. Test the endpoints
curl -sk https://api1.local/hello
curl -sk https://api2.local/hello
curl -sk https://api3.local/hello
```

---

## Testing

```bash
# Unit tests (no cluster needed)
make test

# Smoke test from inside a pod (proves pod-to-pod TLS trust — no -k flag)
POD=$(kubectl get pod -l app=test-app-api1 -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD -- python3 -c "
import urllib.request, json
for url in ['https://api1.local/hello', 'https://api2.local/goodbye', 'https://api3.local/test']:
    data = json.loads(urllib.request.urlopen(url).read())
    print(url, '->', data)
"
```

---

## Key Configuration (`charts/test-app/values.yaml`)

| Field | Default | Purpose |
|-------|---------|---------|
| `services[].name` | api1/api2/api3 | Pod identity — used as `SERVICE_NAME` env var and DNS hostname prefix |
| `services[].host` | api1.local etc. | Ingress hostname and TLS SAN |
| `image.repository` | test-app | Docker image name |
| `image.tag` | latest | Docker image tag |
| `replicaCount` | 1 | Replicas per service |
| `ingress.tls` | true | Enable HTTPS |
| `ingress.generateCert` | true | Mode 1: Helm auto-generates cert. Set false for modes 2 or 3. |
| `ingress.certDays` | 3650 | Self-signed cert validity in days (Mode 1 only) |
| `ingress.externalCert.crt` | "" | PEM cert content for Mode 3 (paste here) |
| `ingress.externalCert.key` | "" | PEM private key content for Mode 3 |
| `ingress.corporateCA` | "" | Root/intermediate CA PEM — injected into all pod trust stores |

---

## Certificate Modes

### Mode 1 — Auto-generate (default)
```yaml
ingress:
  generateCert: true
  certDays: 3650
```
Helm generates a self-signed cert on first install, reuses it on upgrades.

### Mode 2 — kubectl pre-created
```bash
# Run this BEFORE helm install (or after helm upgrade if switching from Mode 1)
kubectl create secret tls test-app-tls --cert=your.crt --key=your.key -n default
```
```yaml
ingress:
  generateCert: false
  corporateCA: |
    -----BEGIN CERTIFICATE-----
    <your root CA PEM>
    -----END CERTIFICATE-----
```
> **Gotcha when switching from Mode 1:** Run `helm upgrade` first (drops Helm's ownership of the old secret), then create the new secret with kubectl. If you create the secret before upgrading, Helm will delete it.

### Mode 3 — Paste into values
```yaml
ingress:
  generateCert: false
  externalCert:
    crt: |
      -----BEGIN CERTIFICATE-----
      <cert PEM>
      -----END CERTIFICATE-----
    key: |
      -----BEGIN PRIVATE KEY-----
      <key PEM>
      -----END PRIVATE KEY-----
  corporateCA: |
    -----BEGIN CERTIFICATE-----
    <root CA PEM>
    -----END CERTIFICATE-----
```

---

## How the TLS Chain Works

```
cert issuance (one-time, any mode)
  → cert stored as K8s Secret "test-app-tls"
  → Root CA PEM added to values.yaml under ingress.corporateCA
  → helm upgrade creates ConfigMap "test-app-ca" from the Root CA PEM

pod startup (every pod, every restart)
  → init container "trust-ca":
      cp /etc/ssl/certs/ca-certificates.crt → emptyDir
      cat /corporate-ca/ca.crt             >> emptyDir
  → main container mounts emptyDir at /etc/ssl/certs/ca-certificates.crt

pod-to-pod call (e.g. api1 → https://api2.local/hello)
  → hostAliases resolves api2.local → ingress ClusterIP (10.x.x.x)
  → TLS handshake: nginx presents cert (CN=api2.local, issued by Root CA)
  → api1 verifies: Root CA is in its trust store ✓
  → ingress routes to api2 pod via Host header
  → {"service":"api2","message":"Hello, World!"}
```

---

## AKS Migration Path

1. Push image to ACR, update `image.repository` and `image.tag`
2. Change `host` values: `api1.local` → `api1.yourdomain.com` etc.
3. For TLS: either use Mode 2/3 with a real corp cert, or add cert-manager + Let's Encrypt
4. Optionally extract `ingress-nginx` into its own shared cluster chart

Steps 1–2 require no structural changes to the chart.
