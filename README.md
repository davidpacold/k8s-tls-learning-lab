# k8s-tls-learning-lab

A hands-on learning project that mirrors a real multi-service Kubernetes architecture. Three independent API pods, each on its own subdomain, routed by an nginx ingress controller with automated TLS — all deployed via a single Helm chart.

Built to answer the question: *"How does TLS actually work between services inside a cluster?"*

---

## What You'll Learn

- How **host-based ingress routing** works (vs. path-based)
- How to use a **single Helm chart** to deploy multiple services from the same Docker image
- How to configure **TLS at the ingress layer** with three different cert strategies
- How to get **pods to trust your TLS cert** without touching the Docker image (init containers + system CA bundle)
- How **in-cluster DNS** resolves custom hostnames using `hostAliases`
- How to handle **WAF/SSL offloading** at the nginx ingress layer

---

## Architecture

```
Your Machine (localhost)
        |
   port 80 / 443
        |
[ nginx ingress controller ]  ← LoadBalancer service (Docker Desktop / AKS)
        |
   host-based routing
   ┌────┴────┬─────────────┐
   ▼         ▼             ▼
api1.local  api2.local  api3.local
   │         │             │
[api1 pod] [api2 pod] [api3 pod]
SERVICE_NAME=api1  =api2    =api3
```

**Key design decisions:**

- **1 Docker image** — the same FastAPI app is deployed 3 times. Each pod gets a different `SERVICE_NAME` env var so it can identify itself in responses. This is how most real multi-tenant systems work.
- **Host-based routing** — nginx routes traffic to the right pod based on the `Host` header, not the URL path. `api1.local/hello` and `api2.local/hello` go to different pods.
- **TLS terminates at the ingress** — backend pods receive plain HTTP on port 8080. The ingress controller handles TLS negotiation with the client.

---

## Prerequisites

- Docker Desktop with Kubernetes enabled
- `helm` CLI (`brew install helm`)
- One-time `/etc/hosts` entry on your Mac:
  ```bash
  sudo sh -c 'echo "127.0.0.1  api1.local api2.local api3.local" >> /etc/hosts'
  ```
  > This only affects your Mac. DNS inside the cluster is handled differently — see [In-Cluster DNS](#in-cluster-dns) below.

---

## Quick Start

```bash
# 1. Clone this repo
git clone https://github.com/davidpacold/k8s-tls-learning-lab.git
cd k8s-tls-learning-lab

# 2. Build the Docker image (builds locally into Docker Desktop's registry)
make build

# 3. Install the chart (pulls ingress-nginx subchart + deploys everything)
make install

# 4. Check everything is running
make status

# 5. Hit the endpoints
curl -sk https://api1.local/hello
curl -sk https://api2.local/hello
curl -sk https://api3.local/hello
```

Expected response:
```json
{"service": "api1", "message": "Hello, World!"}
```

The `-sk` flags skip TLS verification. See [Certificate Modes](#certificate-modes) for how to use a trusted cert instead.

---

## Project Structure

```
.
├── app/
│   ├── main.py            # FastAPI app — reads SERVICE_NAME env var
│   ├── Dockerfile         # python:3.12-slim, port 8080
│   └── requirements.txt
├── charts/
│   └── test-app/
│       ├── Chart.yaml     # Umbrella chart — ingress-nginx is a subchart dependency
│       ├── values.yaml    # All configuration lives here
│       └── templates/
│           ├── deployment.yaml    # range loop → 3 Deployments
│           ├── service.yaml       # range loop → 3 ClusterIP Services
│           ├── ingress.yaml       # 1 Ingress with host-based rules
│           ├── tls-secret.yaml    # Cert secret — 3 modes supported
│           └── ca-configmap.yaml  # Root CA for pod trust store injection
├── tests/
│   └── test_main.py       # 7 pytest unit tests (no cluster needed)
└── Makefile               # build, install, uninstall, status, test
```

---

## How Helm Generates 3 Services From 1 Chart

The `values.yaml` has a `services` list:

```yaml
services:
  - name: api1
    host: api1.local
  - name: api2
    host: api2.local
  - name: api3
    host: api3.local
```

Each template uses `{{- range .Values.services }}` to loop over this list and produce one resource per entry. For example, `deployment.yaml` produces three separate `Deployment` manifests — one for each service — each with a different `SERVICE_NAME` env var.

To add a fourth service, add one line to the list. No template changes needed.

---

## Certificate Modes

The ingress supports four cert strategies. Pick whichever fits your situation.

### Mode 1 — Auto-generate (default for local dev)

```yaml
ingress:
  generateCert: true
  certDays: 3650
```

Helm uses `genSelfSignedCert` to create a self-signed cert that covers all 3 subdomains as SANs. The cert is stored as a Kubernetes Secret and **reused on every `helm upgrade`** — it won't regenerate a new cert each time you deploy (Helm checks with `lookup` first).

**Limitation:** It's truly self-signed (no CA chain), so browsers and `curl` will warn. Use `-sk` to skip verification.

---

### Mode 2 — kubectl pre-created secret

```yaml
ingress:
  generateCert: false
  corporateCA: |
    -----BEGIN CERTIFICATE-----
    <your root CA PEM>
    -----END CERTIFICATE-----
```

You create the TLS secret manually before running `helm install`:

```bash
kubectl create secret tls test-app-tls \
  --cert=path/to/your.crt \
  --key=path/to/your.key \
  -n default
```

Helm renders no Secret template and leaves your externally-managed secret alone.

> **Gotcha when switching from Mode 1:** Run `helm upgrade` *first* (to drop Helm's ownership of the old generated secret), *then* create the new secret with kubectl. If you create the kubectl secret before upgrading, Helm will delete it because it previously owned a secret with that name.

---

### Mode 3 — Paste cert into values

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

Helm creates the Kubernetes Secret from the pasted values. Useful when you have a cert issued by a corporate CA but don't want to run kubectl commands manually.

---

### Mode 4 — Auto-generate cert + corporate CA (combined trust)

```yaml
ingress:
  generateCert: true
  certDays: 3650
  corporateCA: |
    -----BEGIN CERTIFICATE-----
    <your root CA PEM>
    -----END CERTIFICATE-----
```

Helm generates the self-signed cert for the ingress (same as Mode 1), but pods get **both** the self-signed cert and the corporate CA appended to their trust stores. Use this when:

- Your cluster is in an environment where pods make outbound HTTPS calls to internal services signed by a corporate CA
- You still want Helm to manage the ingress cert automatically

The init container appends both CAs in order: corporate CA first, then the self-signed cert. Either trust relationship is honored by OpenSSL.

---

## Pod TLS Trust — How Pods Verify the Cert

TLS termination happens at the ingress, but pods still make HTTPS calls to each other (via the ingress — see [In-Cluster DNS](#in-cluster-dns)). For those calls to succeed without `-k`, pods need to trust the cert's issuer.

### The problem

Python's `urllib`, `requests`, and .NET's `HttpClient` all use the system CA bundle (`/etc/ssl/certs/ca-certificates.crt` on Linux). The base Docker image doesn't know about your corporate CA or your self-signed cert — so pod-to-pod HTTPS calls fail with certificate errors.

### The solution — init container + emptyDir volume

Each pod runs an init container before the main app starts:

```
init container "trust-ca"
  1. Copy system CA bundle → /updated-certs/ca-certificates.crt
  2. Append your CA cert        >> /updated-certs/ca-certificates.crt

main container "api"
  → mounts /updated-certs/ca-certificates.crt
    at /etc/ssl/certs/ca-certificates.crt  (overlays the system file)
```

The shared volume is an `emptyDir` — it exists only for the lifetime of the pod, which is fine because the init container repopulates it on every pod start.

**Why this works for both Python and .NET:** Both runtimes on Linux use OpenSSL, which reads the system CA bundle. This is a system-level fix, not a language-specific one.

**What gets injected:**
- When `generateCert: true` → the self-signed cert is appended (pods trust that specific cert)
- When `corporateCA` is set → the corporate CA PEM is appended (pods trust any cert signed by that CA)
- Both can be set simultaneously (Mode 4) — both are appended, pods trust both

---

## In-Cluster DNS

When a pod calls `https://api2.local/hello`, it needs to resolve `api2.local` to an IP. Inside the cluster, CoreDNS doesn't know about your local `.local` hostnames — they only exist in your Mac's `/etc/hosts`.

### The solution — hostAliases

The chart uses Helm's `lookup` function to find the ingress controller's ClusterIP at render time, then injects it into every pod's `/etc/hosts` via `hostAliases`:

```yaml
hostAliases:
  - ip: 10.102.166.250   # ingress controller ClusterIP (looked up dynamically)
    hostnames:
      - api1.local
      - api2.local
      - api3.local
```

So a pod-to-pod call to `https://api2.local/hello` resolves to the ingress ClusterIP, hits the nginx ingress controller, which routes based on the `Host: api2.local` header, and forwards to the api2 pod.

**Why `hostAliases` instead of editing CoreDNS?**
- `hostAliases` is scoped to just these pods — no cluster-wide side effects
- The IP is resolved dynamically by Helm at install time — no hardcoding
- CoreDNS edits affect all pods in the cluster and require manual configuration outside the chart

---

## WAF / SSL Offloading

Some environments terminate TLS at a WAF or load balancer before traffic reaches the cluster. In that case, the ingress receives plain HTTP — but nginx's default behavior redirects HTTP → HTTPS (308), causing a redirect loop.

Disable the redirect:

```yaml
ingress:
  sslRedirect: false
```

This adds `nginx.ingress.kubernetes.io/ssl-redirect: "false"` to the Ingress annotation. Default is `true` (redirect enabled), which is correct for direct HTTPS.

---

## Configuration Reference

| Field | Default | Purpose |
|-------|---------|---------|
| `services[].name` | api1/api2/api3 | Pod identity — used as `SERVICE_NAME` env var and DNS hostname prefix |
| `services[].host` | api1.local etc. | Ingress hostname and TLS SAN |
| `image.repository` | test-app | Docker image name |
| `image.tag` | latest | Docker image tag |
| `replicaCount` | 1 | Replicas per service |
| `ingress.tls` | true | Enable HTTPS on the ingress |
| `ingress.controller` | nginx | Ingress controller to use: `nginx` or `traefik`. Also flip the `enabled` flags below. |
| `ingress.sslRedirect` | false | Redirect HTTP → HTTPS. Default false = port 80 and 443 work simultaneously. |
| `ingress.generateCert` | true | Mode 1: Helm auto-generates cert. Set false for modes 2 or 3. |
| `ingress.certDays` | 3650 | Self-signed cert validity in days (Mode 1 only) |
| `ingress.externalCert.crt` | "" | PEM cert content for Mode 3 (paste here) |
| `ingress.externalCert.key` | "" | PEM private key content for Mode 3 |
| `ingress.corporateCA` | "" | Root/intermediate CA PEM — injected into all pod trust stores |

---

## Switching Controllers

The chart supports nginx and Traefik v3. Both are bundled as subchart dependencies — only the enabled one is installed.

> **Helm CRD limitation:** When switching from nginx to Traefik on an existing release, Helm does not automatically install Traefik's CRDs (Helm only installs CRDs on a fresh `helm install`, not on `helm upgrade`). Apply them first:
> ```bash
> kubectl apply --server-side -f https://raw.githubusercontent.com/traefik/traefik/v3.6.12/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
> ```
> This is a one-time step — once the CRDs are in the cluster, upgrades work normally.

### Switch to Traefik

```yaml
# values.yaml
ingress:
  controller: traefik

ingress-nginx:
  enabled: false

traefik:
  enabled: true
```

```bash
# Apply Traefik CRDs first (one-time, required when switching from nginx)
kubectl apply --server-side -f https://raw.githubusercontent.com/traefik/traefik/v3.6.12/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml

helm dep update charts/test-app
helm upgrade --install test-app charts/test-app --namespace default --wait
kubectl get ingressroute    # verify Traefik CRDs deployed
curl -s http://api1.local/hello    # port 80
curl -sk https://api1.local/hello  # port 443
```

### Switch back to nginx

```yaml
# values.yaml
ingress:
  controller: nginx

ingress-nginx:
  enabled: true

traefik:
  enabled: false
```

```bash
helm dep update charts/test-app
helm upgrade --install test-app charts/test-app --namespace default --wait
kubectl get ingress    # verify nginx Ingress deployed
curl -sk https://api1.local/hello
```

---

## Testing

```bash
# Unit tests (no cluster needed)
make test

# Smoke test all 3 endpoints
curl -sk https://api1.local/hello
curl -sk https://api2.local/goodbye
curl -sk https://api3.local/test

# Smoke test from inside a pod — proves pod-to-pod TLS trust (no -k flag needed)
POD=$(kubectl get pod -l app=test-app-api1 -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD -- python3 -c "
import urllib.request, json
for url in ['https://api1.local/hello', 'https://api2.local/goodbye', 'https://api3.local/test']:
    data = json.loads(urllib.request.urlopen(url).read())
    print(url, '->', data)
"
```

If the pod-to-pod test passes without `-k`, pod trust is working correctly.

---

## How the Full TLS Chain Works

```
cert issuance (one-time, any mode)
  → cert stored as K8s Secret "test-app-tls"
  → Root CA PEM added to values.yaml under ingress.corporateCA
  → helm install/upgrade creates ConfigMap "test-app-ca" from the Root CA PEM

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
3. For TLS: use Mode 2 or 3 with a real corporate cert, or add cert-manager + Let's Encrypt
4. Remove or change `ingress-nginx.controller.service.type` — AKS handles LoadBalancer differently
5. Optionally extract `ingress-nginx` into its own shared cluster chart

Steps 1–2 require no structural changes to the chart.

---

## Common Issues

**`helm install` fails — subchart not found**
```bash
make dep-update   # runs helm dependency update
```

**curl returns HTTP 308 redirect instead of response**
You're hitting HTTP and nginx is redirecting to HTTPS. Either use `https://` in your curl, or set `ingress.sslRedirect: false` if you're intentionally testing without TLS.

**Pod-to-pod HTTPS fails with certificate error**
The `corporateCA` field in values.yaml is empty, or the pod was started before the CA ConfigMap existed. Verify the ConfigMap is present: `kubectl get configmap test-app-ca`. If missing, re-run `helm upgrade`.

**Switched from Mode 1 to Mode 2 and Helm deleted the kubectl secret**
See the gotcha note in [Mode 2](#mode-2--kubectl-pre-created-secret). Run `helm upgrade` first (to drop Helm ownership), then create the kubectl secret.
