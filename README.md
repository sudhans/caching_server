# mycache

`mycache` is a small static-file caching server for a local `kind` Kubernetes cluster. It downloads a requested filename from a configured upstream base URL on cache miss, stores it on a persistent volume, and serves the cached file to clients.

Default upstream:

```text
https://placehold.co
```

Default public hostname:

```text
mycache.msd.com
```

## Layout

```text
app/
  Dockerfile
  main.py
  requirements.txt
k8s/
  namespace.yaml
  persistent-volume.yaml
  persistent-volume-claim.yaml
  deployment.yaml
  service.yaml
  ingress.yaml
kind/
  kind-config.yaml
```

## Cache Behavior

Clients request files through this route:

```text
/files/{filename}
```

Example:

```text
http://mycache.msd.com/files/600x400.png
```

The server only accepts filename-only requests. Subfolders and path traversal are rejected.

Allowed filename characters:

```text
A-Z a-z 0-9 . _ -
```

Allowed examples:

```text
600x400.png
artifact-1.0.bin
test_file.iso
```

Rejected examples:

```text
../secret
folder/file.iso
folder\file.iso
https://example.com/file.iso
```

On cache miss, `600x400.png` is downloaded from:

```text
https://placehold.co/600x400.png
```

The file is written to a temporary path first, then atomically renamed into the cache. After that, the cached file is served to the client. Future requests are served directly from disk.

## Prerequisites

Required tools:

```text
kind
kubectl
docker or podman-compatible docker command
```

Port `80` on the desktop must be available for the kind ingress mapping.

## Create The kind Cluster

From this directory:

```bash
mkdir -p /home/msd/opencode/caching/.cache-data
kind create cluster --name mycache --config kind/kind-config.yaml
```

The kind config mounts this host directory into the kind node:

```text
/home/msd/opencode/caching/.cache-data -> /cache-data
```

The Kubernetes persistent volume uses `/cache-data` inside the kind node.

## Install Ingress Controller

Install ingress-nginx for kind:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=Ready pod --selector=app.kubernetes.io/component=controller --timeout=180s
```

## Build And Load Image

Build the container image:

```bash
docker build -t mycache:latest app
```

Load it into the kind cluster:

```bash
kind load docker-image mycache:latest --name mycache
```

## Deploy

Apply the manifests:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/persistent-volume.yaml
kubectl apply -f k8s/persistent-volume-claim.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

Wait for the pod:

```bash
kubectl -n caching rollout status deployment/mycache
```

## Configure Hostname

For testing from the desktop itself, add this to `/etc/hosts`:

```text
127.0.0.1 mycache.msd.com
```

For LAN clients, add this on each client or in local DNS:

```text
<redhat-desktop-ip> mycache.msd.com
```

## Test

Health check:

```bash
curl http://mycache.msd.com/healthz
```

Request a file:

```bash
curl -O http://mycache.msd.com/files/600x400.png
```

Run the same request again to confirm cache-hit behavior:

```bash
curl -O http://mycache.msd.com/files/600x400.png
```

Check pod logs:

```bash
kubectl -n caching logs deployment/mycache
```

Check cached files on the host:

```bash
ls -lh /home/msd/opencode/caching/.cache-data
```

## Change Upstream URL

Edit `k8s/deployment.yaml`:

```yaml
- name: UPSTREAM_BASE_URL
  value: https://placehold.co
```

Then apply and restart:

```bash
kubectl apply -f k8s/deployment.yaml
kubectl -n caching rollout restart deployment/mycache
```

## Cleanup

Delete Kubernetes resources:

```bash
kubectl delete namespace caching
kubectl delete pv mycache-pv
```

Delete the kind cluster:

```bash
kind delete cluster --name mycache
```

The cached files remain on the host under:

```text
/home/msd/opencode/caching/.cache-data
```
