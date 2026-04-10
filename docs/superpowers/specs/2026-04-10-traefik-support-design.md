# Traefik Support Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Traefik v3 as a selectable alternative to nginx ingress, using Traefik's native CRDs (`IngressRoute`, `Middleware`), with a single `ingress.controller` field in `values.yaml` controlling which controller is active.

**Architecture:** Both ingress-nginx and traefik are declared as subchart dependencies in `Chart.yaml` with Helm `condition` fields. Template files are split by controller — existing nginx templates get a guard, new Traefik-specific templates render only when Traefik is selected. The `deployment.yaml` lookup for `hostAliases` branches on the controller value to find the right service name.

**Tech Stack:** Helm 3, Traefik v3 (`traefik.io/v1alpha1` API group), Traefik Helm chart `33.2.1`, ingress-nginx `4.11.3`

---

## Behavior Contract

Both controllers must support port 80 and port 443 **simultaneously** with no redirect between them by default. This supports WAF/SSL offloading scenarios where HTTP and HTTPS traffic arrive independently.

`sslRedirect: true` is opt-in — it adds a redirect from HTTP→HTTPS. Default is `false`.

| `tls` | `sslRedirect` | nginx renders | Traefik renders |
|-------|--------------|---------------|-----------------|
| true  | false (default) | Ingress (80 + 443 simultaneously) | IngressRoute on `web` + `websecure` |
| true  | true | Ingress (80 redirects to 443) | IngressRoute on `web` (with Middleware redirect) + `websecure` + Middleware |
| false | false | Ingress (80 only) | IngressRoute on `web` only |

---

## Files Modified

| File | Change |
|------|--------|
| `Chart.yaml` | Add `traefik` dependency with `condition: traefik.enabled`; add `condition: ingress-nginx.enabled` to existing nginx entry |
| `charts/test-app/values.yaml` | Add `ingress.controller: nginx`; change `sslRedirect` default to `false`; add `ingress-nginx.enabled: true`; add `traefik:` block with `enabled: false` |
| `charts/test-app/templates/ingress.yaml` | Wrap entire file in `{{- if eq .Values.ingress.controller "nginx" }}...{{- end }}` |
| `charts/test-app/templates/deployment.yaml` | Replace hardcoded nginx service name lookup with a ternary that selects the right service name based on `ingress.controller` |

## Files Created

| File | Purpose |
|------|---------|
| `charts/test-app/templates/ingressroute.yaml` | Traefik `IngressRoute` CRDs — HTTP route always present, HTTPS route when `tls: true` |
| `charts/test-app/templates/traefik-middleware.yaml` | Traefik `Middleware` for HTTP→HTTPS redirect — only rendered when `controller=traefik` AND `sslRedirect: true` |

---

## Detailed Design

### `Chart.yaml` dependencies

```yaml
dependencies:
  - name: ingress-nginx
    repository: https://kubernetes.github.io/ingress-nginx
    version: "4.11.3"
    condition: ingress-nginx.enabled

  - name: traefik
    repository: https://traefik.github.io/charts
    version: "33.2.1"
    condition: traefik.enabled
```

### `values.yaml` additions

```yaml
ingress:
  controller: nginx   # "nginx" or "traefik"
                      # When switching: also flip ingress-nginx.enabled / traefik.enabled below
  sslRedirect: false  # false = 80 and 443 work simultaneously (default)
                      # true  = HTTP (80) redirects to HTTPS (443)
  # ... all existing tls, generateCert, certDays, externalCert, corporateCA fields unchanged

# ingress-nginx subchart — set enabled: false when switching to traefik
ingress-nginx:
  enabled: true
  controller:
    service:
      type: LoadBalancer

# traefik subchart — set enabled: true when switching to traefik
traefik:
  enabled: false
  ports:
    web:
      port: 80
    websecure:
      port: 443
  service:
    type: LoadBalancer
```

### `deployment.yaml` lookup fix

Replace the current hardcoded lookup:
```yaml
{{- $ingressSvc := lookup "v1" "Service" .Release.Namespace (printf "%s-ingress-nginx-controller" .Release.Name) }}
```

With a controller-aware lookup:
```yaml
{{- $svcName := ternary (printf "%s-traefik" .Release.Name) (printf "%s-ingress-nginx-controller" .Release.Name) (eq .Values.ingress.controller "traefik") }}
{{- $ingressSvc := lookup "v1" "Service" .Release.Namespace $svcName }}
```

### `ingress.yaml` guard

Wrap the entire existing file:
```yaml
{{- if eq .Values.ingress.controller "nginx" }}
... existing content unchanged ...
{{- end }}
```

### `ingressroute.yaml` — full content

```yaml
{{- if eq .Values.ingress.controller "traefik" }}
# HTTP IngressRoute — always rendered; carries redirect middleware when sslRedirect: true
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: {{ .Release.Name }}-api-http
spec:
  entryPoints:
    - web
  routes:
    {{- range .Values.services }}
    - match: Host(`{{ .host }}`)
      kind: Rule
      {{- if and $.Values.ingress.tls $.Values.ingress.sslRedirect }}
      middlewares:
        - name: {{ $.Release.Name }}-redirect-https
      {{- end }}
      services:
        - name: {{ $.Release.Name }}-{{ .name }}
          port: {{ $.Values.service.port }}
    {{- end }}
{{- if .Values.ingress.tls }}
---
# HTTPS IngressRoute — rendered when tls: true
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: {{ .Release.Name }}-api-tls
spec:
  entryPoints:
    - websecure
  routes:
    {{- range .Values.services }}
    - match: Host(`{{ .host }}`)
      kind: Rule
      services:
        - name: {{ $.Release.Name }}-{{ .name }}
          port: {{ $.Values.service.port }}
    {{- end }}
  tls:
    secretName: {{ printf "%s-tls" .Release.Name }}
{{- end }}
{{- end }}
```

### `traefik-middleware.yaml` — full content

```yaml
{{- if and (eq .Values.ingress.controller "traefik") .Values.ingress.tls .Values.ingress.sslRedirect }}
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: {{ .Release.Name }}-redirect-https
spec:
  redirectScheme:
    scheme: https
    permanent: true
{{- end }}
```

---

## Switching Controllers — Operator Runbook

### nginx → traefik

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
helm dep update charts/test-app
helm upgrade --install test-app charts/test-app --wait
```

### traefik → nginx

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
helm upgrade --install test-app charts/test-app --wait
```

---

## What Does NOT Change

- `templates/deployment.yaml` — init container, CA injection, volumes, `hostAliases` structure
- `templates/service.yaml` — ClusterIP services are controller-agnostic
- `templates/tls-secret.yaml` — all three cert modes work identically for both controllers
- `templates/ca-configmap.yaml` — pod trust injection is independent of the ingress controller
- `tests/test_main.py` — unit tests have no cluster dependency
- All `ingress.tls`, `ingress.generateCert`, `ingress.corporateCA`, `ingress.externalCert` fields

---

## Validation

After switching to Traefik, verify with:

```bash
# Check IngressRoute resources exist
kubectl get ingressroute

# Check pods are running
make status

# Hit both ports (no redirect between them)
curl -sk https://api1.local/hello   # port 443
curl -s  http://api1.local/hello    # port 80 — should return JSON, not a redirect

# Pod-to-pod trust (unchanged)
POD=$(kubectl get pod -l app=test-app-api1 -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD -- python3 -c "
import urllib.request, json
data = json.loads(urllib.request.urlopen('https://api2.local/hello').read())
print(data)
"
```
