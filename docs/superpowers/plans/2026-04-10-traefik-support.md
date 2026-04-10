# Traefik v3 Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Traefik v3 as a selectable alternative to nginx ingress, switchable via a single `ingress.controller` field in `values.yaml`, using Traefik's native `IngressRoute` and `Middleware` CRDs.

**Architecture:** Both controllers live as subchart dependencies in `Chart.yaml` with Helm `condition` fields. Template files are split by controller — existing nginx templates get a guard, two new Traefik-specific templates render only when Traefik is selected. The `deployment.yaml` hostAliases lookup branches on `ingress.controller` to find the correct service name. Both 80 and 443 work simultaneously by default (`sslRedirect: false`).

**Tech Stack:** Helm 3, Traefik v3 Helm chart (`traefik.io/v1alpha1` CRD API group), ingress-nginx 4.11.3

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `charts/test-app/Chart.yaml` | Modify | Add `condition: ingress-nginx.enabled` to existing dep; add `traefik` dep with `condition: traefik.enabled` |
| `charts/test-app/values.yaml` | Modify | Add `ingress.controller: nginx`; change `sslRedirect` default to `false`; add `ingress-nginx.enabled: true`; add `traefik:` block |
| `charts/test-app/templates/ingress.yaml` | Modify | Wrap entire file in `{{- if eq .Values.ingress.controller "nginx" }}` guard |
| `charts/test-app/templates/deployment.yaml` | Modify | Replace hardcoded nginx service name with ternary on `ingress.controller` |
| `charts/test-app/templates/ingressroute.yaml` | Create | Traefik HTTP + HTTPS `IngressRoute` CRDs |
| `charts/test-app/templates/traefik-middleware.yaml` | Create | Traefik `Middleware` for HTTP→HTTPS redirect (only when `sslRedirect: true`) |

---

## Task 1: Add Traefik dependency to Chart.yaml

**Files:**
- Modify: `charts/test-app/Chart.yaml`

The current `Chart.yaml` has no `condition` on the nginx dep and no traefik dep. We add both.

- [ ] **Step 1: Verify current Chart.yaml content**

Run:
```bash
cat charts/test-app/Chart.yaml
```
Expected output:
```yaml
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

- [ ] **Step 2: Look up the latest Traefik v3 chart version**

Run:
```bash
helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
helm repo update traefik
helm search repo traefik/traefik --versions | head -5
```
Note the latest version that ships Traefik v3 (APP VERSION starting with `v3`). Use that version in Step 3.

- [ ] **Step 3: Replace Chart.yaml with dual-dependency version**

Replace the entire file content with:
```yaml
# charts/test-app/Chart.yaml
apiVersion: v2
name: test-app
description: A learning Helm chart deploying 3 FastAPI service instances with nginx or traefik ingress
type: application
version: 0.1.0
appVersion: "1.0.0"

dependencies:
  - name: ingress-nginx
    version: "4.11.3"
    repository: "https://kubernetes.github.io/ingress-nginx"
    condition: ingress-nginx.enabled

  - name: traefik
    version: "39.0.7"        # verify with helm search repo traefik/traefik
    repository: "https://traefik.github.io/charts"
    condition: traefik.enabled
```

- [ ] **Step 4: Run dep update to download both subcharts**

Run:
```bash
helm dependency update charts/test-app
```
Expected: Both subcharts downloaded to `charts/test-app/charts/`. `Chart.lock` is updated with both entries. No errors.

- [ ] **Step 5: Verify Chart.lock has both entries**

Run:
```bash
grep "^- name:" charts/test-app/Chart.lock
```
Expected:
```
- name: ingress-nginx
- name: traefik
```

- [ ] **Step 6: Commit**

```bash
git add charts/test-app/Chart.yaml charts/test-app/Chart.lock
git commit -m "feat: add traefik v3 as conditional subchart dependency"
```

---

## Task 2: Update values.yaml

**Files:**
- Modify: `charts/test-app/values.yaml`

Add `ingress.controller`, change `sslRedirect` default to `false`, add `ingress-nginx.enabled`, add `traefik:` block.

- [ ] **Step 1: Add `ingress.controller` field**

In `charts/test-app/values.yaml`, add `controller: nginx` as the first line inside the `ingress:` block, directly above the existing `tls: true` line:

```yaml
ingress:
  controller: nginx   # "nginx" or "traefik"
                      # When switching: also flip ingress-nginx.enabled / traefik.enabled below
  tls: true
```

- [ ] **Step 2: Change sslRedirect default to false**

Find the current line:
```yaml
  sslRedirect: true
```
Change it to:
```yaml
  sslRedirect: false  # false = port 80 and 443 both work simultaneously (default)
                      # true  = HTTP (80) redirects to HTTPS (443)
```

- [ ] **Step 3: Add enabled flag to ingress-nginx block**

Find the current `ingress-nginx:` block at the bottom of the file:
```yaml
# ingress-nginx subchart overrides
ingress-nginx:
  controller:
    service:
      type: LoadBalancer
```
Replace with:
```yaml
# ingress-nginx subchart — set enabled: false when switching to traefik
ingress-nginx:
  enabled: true
  controller:
    service:
      type: LoadBalancer
```

- [ ] **Step 4: Add traefik block**

Append to the end of `charts/test-app/values.yaml`:
```yaml

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

- [ ] **Step 5: Verify helm template still renders for nginx (default)**

Run:
```bash
helm template test-app charts/test-app | grep "kind:" | sort | uniq -c
```
Expected output includes `Ingress` (not `IngressRoute`), three `Deployment`, three `Service`. No error about missing values.

- [ ] **Step 6: Commit**

```bash
git add charts/test-app/values.yaml
git commit -m "feat: add ingress.controller selector and traefik values block"
```

---

## Task 3: Guard ingress.yaml for nginx only

**Files:**
- Modify: `charts/test-app/templates/ingress.yaml`

The existing file must only render when `ingress.controller` is `nginx`. Add a guard wrapping the entire file.

- [ ] **Step 1: Add opening guard at line 1**

The current first line is:
```yaml
# charts/test-app/templates/ingress.yaml
```
Prepend above it:
```yaml
{{- if eq .Values.ingress.controller "nginx" }}
```

- [ ] **Step 2: Add closing guard at end of file**

The current last line ends after the `{{- end }}` for the TLS block. Add a final `{{- end }}` on a new last line:
```yaml
{{- end }}
```

- [ ] **Step 3: Verify nginx controller still renders Ingress**

Run:
```bash
helm template test-app charts/test-app | grep "kind: Ingress"
```
Expected: `kind: Ingress` appears once (default values have `controller: nginx`).

- [ ] **Step 4: Verify traefik controller renders no Ingress**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  | grep "kind: Ingress" || echo "PASS: no Ingress rendered"
```
Expected: `PASS: no Ingress rendered`

- [ ] **Step 5: Commit**

```bash
git add charts/test-app/templates/ingress.yaml
git commit -m "feat: guard ingress.yaml to render only when controller=nginx"
```

---

## Task 4: Fix hostAliases lookup in deployment.yaml

**Files:**
- Modify: `charts/test-app/templates/deployment.yaml` (lines 1-4)

The current lookup hardcodes the nginx service name. Replace it with a ternary that selects the right name based on `ingress.controller`.

- [ ] **Step 1: Locate the current lookup line**

The current lines 1-4 of `deployment.yaml` are:
```yaml
# charts/test-app/templates/deployment.yaml
{{- $ingressSvc := lookup "v1" "Service" .Release.Namespace (printf "%s-ingress-nginx-controller" .Release.Name) }}
{{- $ingressIP := "" }}
{{- if $ingressSvc }}{{- $ingressIP = $ingressSvc.spec.clusterIP }}{{- end }}
```

- [ ] **Step 2: Replace the lookup with a controller-aware version**

Replace those four lines with:
```yaml
# charts/test-app/templates/deployment.yaml
{{- $svcName := ternary (printf "%s-traefik" .Release.Name) (printf "%s-ingress-nginx-controller" .Release.Name) (eq .Values.ingress.controller "traefik") }}
{{- $ingressSvc := lookup "v1" "Service" .Release.Namespace $svcName }}
{{- $ingressIP := "" }}
{{- if $ingressSvc }}{{- $ingressIP = $ingressSvc.spec.clusterIP }}{{- end }}
```

- [ ] **Step 3: Verify template renders cleanly for both controllers**

Run:
```bash
helm template test-app charts/test-app | grep -A3 "hostAliases" | head -10
```
Expected: `hostAliases` block is absent (lookup returns empty during dry-run — this is expected behavior; `hostAliases` only appears in a live cluster after the ingress controller service exists).

Run the same for traefik to confirm no template errors:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  | grep "kind: Deployment" | wc -l
```
Expected: `3`

- [ ] **Step 4: Commit**

```bash
git add charts/test-app/templates/deployment.yaml
git commit -m "feat: update hostAliases lookup to support both nginx and traefik service names"
```

---

## Task 5: Create ingressroute.yaml

**Files:**
- Create: `charts/test-app/templates/ingressroute.yaml`

This is the main Traefik routing resource. It renders two `IngressRoute` objects when `controller=traefik`:
1. HTTP route on the `web` entrypoint (always) — carries a redirect middleware ref when `sslRedirect: true`
2. HTTPS route on the `websecure` entrypoint (only when `tls: true`)

- [ ] **Step 1: Create the file**

Create `charts/test-app/templates/ingressroute.yaml` with this exact content:

```yaml
# charts/test-app/templates/ingressroute.yaml
{{- if eq .Values.ingress.controller "traefik" }}
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

- [ ] **Step 2: Verify nginx controller renders no IngressRoute**

Run:
```bash
helm template test-app charts/test-app | grep "kind: IngressRoute" || echo "PASS: no IngressRoute for nginx"
```
Expected: `PASS: no IngressRoute for nginx`

- [ ] **Step 3: Verify traefik with tls=true, sslRedirect=false renders 2 IngressRoutes (no middleware)**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  --set ingress.tls=true \
  --set ingress.sslRedirect=false \
  | grep "kind: IngressRoute" | wc -l
```
Expected: `2`

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  --set ingress.tls=true \
  --set ingress.sslRedirect=false \
  | grep "middlewares" || echo "PASS: no middleware refs in sslRedirect=false mode"
```
Expected: `PASS: no middleware refs in sslRedirect=false mode`

- [ ] **Step 4: Verify traefik with tls=true, sslRedirect=true renders middleware ref on HTTP route**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  --set ingress.tls=true \
  --set ingress.sslRedirect=true \
  | grep -A2 "middlewares:"
```
Expected output includes:
```yaml
      middlewares:
        - name: test-app-redirect-https
```

- [ ] **Step 5: Verify traefik with tls=false renders only 1 IngressRoute (HTTP only)**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  --set ingress.tls=false \
  | grep "kind: IngressRoute" | wc -l
```
Expected: `1`

- [ ] **Step 6: Verify all 3 hosts appear in each IngressRoute**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  | grep "match: Host"
```
Expected (6 lines total — 3 hosts × 2 IngressRoutes):
```
    - match: Host(`api1.local`)
    - match: Host(`api2.local`)
    - match: Host(`api3.local`)
    - match: Host(`api1.local`)
    - match: Host(`api2.local`)
    - match: Host(`api3.local`)
```

- [ ] **Step 7: Verify TLS secret name in HTTPS IngressRoute**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  | grep "secretName:"
```
Expected:
```
    secretName: test-app-tls
```

- [ ] **Step 8: Commit**

```bash
git add charts/test-app/templates/ingressroute.yaml
git commit -m "feat: add Traefik IngressRoute template for HTTP and HTTPS routing"
```

---

## Task 6: Create traefik-middleware.yaml

**Files:**
- Create: `charts/test-app/templates/traefik-middleware.yaml`

The `Middleware` resource that performs HTTP→HTTPS redirect. Only rendered when `controller=traefik`, `tls=true`, and `sslRedirect=true`.

- [ ] **Step 1: Create the file**

Create `charts/test-app/templates/traefik-middleware.yaml` with this exact content:

```yaml
# charts/test-app/templates/traefik-middleware.yaml
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

- [ ] **Step 2: Verify Middleware renders when sslRedirect=true**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  --set ingress.tls=true \
  --set ingress.sslRedirect=true \
  | grep "kind: Middleware"
```
Expected:
```
kind: Middleware
```

- [ ] **Step 3: Verify Middleware does NOT render when sslRedirect=false (default)**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  | grep "kind: Middleware" || echo "PASS: no Middleware in default config"
```
Expected: `PASS: no Middleware in default config`

- [ ] **Step 4: Verify Middleware does NOT render when controller=nginx**

Run:
```bash
helm template test-app charts/test-app | grep "kind: Middleware" || echo "PASS: no Middleware for nginx"
```
Expected: `PASS: no Middleware for nginx`

- [ ] **Step 5: Verify Middleware name matches IngressRoute reference**

Run:
```bash
helm template test-app charts/test-app \
  --set ingress.controller=traefik \
  --set ingress-nginx.enabled=false \
  --set traefik.enabled=true \
  --set ingress.tls=true \
  --set ingress.sslRedirect=true \
  | grep -E "name: test-app-redirect-https" | wc -l
```
Expected: `4` — the Middleware metadata name (1) plus one ref per host in the HTTP IngressRoute (3).

- [ ] **Step 6: Commit**

```bash
git add charts/test-app/templates/traefik-middleware.yaml
git commit -m "feat: add Traefik Middleware for optional HTTP to HTTPS redirect"
```

---

## Task 7: Update README

**Files:**
- Modify: `README.md`

Add a "Switching Controllers" section and update the Configuration Reference table.

- [ ] **Step 1: Update the Configuration Reference table**

Find the table row:
```markdown
| `ingress.sslRedirect` | true | Redirect HTTP → HTTPS. Set false for WAF/SSL offloading. |
```
Replace with:
```markdown
| `ingress.controller` | nginx | Ingress controller to use: `nginx` or `traefik`. Also flip the `enabled` flags below. |
| `ingress.sslRedirect` | false | Redirect HTTP → HTTPS. Default false = port 80 and 443 work simultaneously. |
```

- [ ] **Step 2: Add a Switching Controllers section**

Add the following section after the "Configuration Reference" table:

```markdown
## Switching Controllers

The chart supports nginx and Traefik v3. Both are bundled as subchart dependencies — only the enabled one is installed.

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
helm dep update charts/test-app
helm upgrade --install test-app charts/test-app --wait
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
helm upgrade --install test-app charts/test-app --wait
```
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add controller switching section and update config reference"
```

---

## Task 8: Full smoke test with Traefik (requires running cluster)

This task requires Docker Desktop Kubernetes to be running.

- [ ] **Step 1: Update values.yaml to use Traefik**

Edit `charts/test-app/values.yaml`:
```yaml
ingress:
  controller: traefik

ingress-nginx:
  enabled: false

traefik:
  enabled: true
```

- [ ] **Step 2: Run dep update and install**

```bash
helm dependency update charts/test-app
helm upgrade --install test-app charts/test-app --namespace default --wait --timeout 3m
```
Expected: all pods reach Running state.

- [ ] **Step 3: Verify IngressRoute resources**

```bash
kubectl get ingressroute
```
Expected:
```
NAME                AGE
test-app-api-http   Xs
test-app-api-tls    Xs
```

- [ ] **Step 4: Test both ports simultaneously**

```bash
curl -s http://api1.local/hello
```
Expected: `{"service":"api1","message":"Hello, World!"}` (not a redirect)

```bash
curl -sk https://api1.local/hello
```
Expected: `{"service":"api1","message":"Hello, World!"}`

```bash
curl -sk https://api2.local/goodbye && curl -sk https://api3.local/test
```
Expected: responses from api2 and api3 respectively.

- [ ] **Step 5: Verify pod-to-pod TLS trust is unchanged**

```bash
POD=$(kubectl get pod -l app=test-app-api1 -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD -- python3 -c "
import urllib.request, json
for url in ['https://api1.local/hello', 'https://api2.local/goodbye', 'https://api3.local/test']:
    data = json.loads(urllib.request.urlopen(url).read())
    print(url, '->', data)
"
```
Expected: all three URLs return JSON without errors (no `-k` flag — full TLS verification).

- [ ] **Step 6: Switch back to nginx and confirm it still works**

Edit `charts/test-app/values.yaml` to restore:
```yaml
ingress:
  controller: nginx

ingress-nginx:
  enabled: true

traefik:
  enabled: false
```

```bash
helm dep update charts/test-app
helm upgrade --install test-app charts/test-app --namespace default --wait --timeout 3m
curl -sk https://api1.local/hello
```
Expected: `{"service":"api1","message":"Hello, World!"}`

- [ ] **Step 7: Commit the final values.yaml state (nginx as default)**

Confirm `values.yaml` is back to `controller: nginx`, `ingress-nginx.enabled: true`, `traefik.enabled: false`.

```bash
git add charts/test-app/values.yaml
git commit -m "chore: restore default controller to nginx after smoke test"
```

- [ ] **Step 8: Push to GitHub**

```bash
git push origin main
```
