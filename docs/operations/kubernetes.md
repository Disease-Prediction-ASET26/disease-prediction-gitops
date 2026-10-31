# kubectl and Kustomize

Kubernetes objects are stored as YAML under `clusters/oracle/` and, when app images are ready, `apps/`. The Kustomize files list the manifests that belong to each deployment.

## Render and preview

From the repository root, with the private cluster context active:

```bash
kubectl kustomize clusters/oracle
kubectl diff -k clusters/oracle
```

`kubectl diff` previews changes and does not apply them. A non-zero exit code can mean that differences were found.

## Apply and modify

During initial bootstrap, establish the Gateway API and Traefik CRD bundle
CRDs first, then apply the files after reviewing the diff:

```bash
kubectl apply -k clusters/oracle
```

After the root Application is active, edit the YAML, open a pull request, and merge the reviewed change. Argo CD syncs `main` automatically. Avoid routine direct `kubectl apply` because Argo CD may replace the live change with the Git version.

## K3s host-managed Gateway API CRDs

The live `kube-system/gateway-api-crd` HelmChart is sourced from the checked-in
`clusters/oracle/k3s-host-manifests/gateway-api-crd.yaml`, copied to
`/var/lib/rancher/k3s/server/manifests/gateway-api-crd.yaml` on the VM. K3s
serves the chart package `gateway-api-crd-1.6.103.tgz`; the installed CRDs
report the standard Gateway API bundle version `v1.6.1`. K3s's Helm controller
manages this chart; the Argo root Kustomization does not include the host
manifest.

Do not add another Gateway API CRD chart when installing a future Gateway
controller. Keep the current K3s host manifest as the single owner unless a
reviewed change transfers ownership to Argo CD and removes the host manifest.

## Traefik CRD bundle

Traefik's Helm release skips CRDs. The checked-in
`clusters/oracle/k3s-host-manifests/traefik-crds.yaml` contains all ten Traefik
CRDs from v3.7.16, matching the pinned Traefik image. The CRD provider watches
all ten kinds and needs read access to each in `disease-prediction`. The static
CRD file is not part of the Argo root Kustomization. When upgrading Traefik,
update this manifest and its namespaced RBAC from the matching upstream release.

## Install K3s host manifests

Copy both host manifests before applying the root configuration on a new
cluster, or before merging a Git change that adds a Traefik CRD resource on an
existing cluster. From the repository root:

```bash
scp clusters/oracle/k3s-host-manifests/gateway-api-crd.yaml oracle-k3s:/tmp/gateway-api-crd.yaml
scp clusters/oracle/k3s-host-manifests/traefik-crds.yaml oracle-k3s:/tmp/traefik-crds.yaml
ssh oracle-k3s 'sudo install -o root -g root -m 0644 /tmp/gateway-api-crd.yaml /var/lib/rancher/k3s/server/manifests/gateway-api-crd.yaml && sudo install -o root -g root -m 0644 /tmp/traefik-crds.yaml /var/lib/rancher/k3s/server/manifests/traefik-crds.yaml && rm -f /tmp/gateway-api-crd.yaml /tmp/traefik-crds.yaml'
kubectl -n kube-system get helmchart gateway-api-crd
kubectl wait --for=condition=Established crd/gatewayclasses.gateway.networking.k8s.io crd/gateways.gateway.networking.k8s.io crd/httproutes.gateway.networking.k8s.io crd/ingressroutes.traefik.io crd/ingressroutetcps.traefik.io crd/ingressrouteudps.traefik.io crd/middlewares.traefik.io crd/middlewaretcps.traefik.io crd/serverstransports.traefik.io crd/serverstransporttcps.traefik.io crd/tlsoptions.traefik.io crd/tlsstores.traefik.io crd/traefikservices.traefik.io --timeout=180s
```

## Destroy the GitOps-managed resources

Back up any application data first. Deleting the root Application cascades to the projects and the `disease-prediction` namespace. Deleting that namespace also deletes its PVCs and may delete their data.

```bash
kubectl -n argocd delete application oracle-root --wait=true
```

This removes the GitOps-managed resources and keeps Argo CD installed. Recreate them with `kubectl apply -k clusters/oracle` if needed. Use `helmfile destroy` only when you also want to remove Argo CD. For full VM and cluster teardown, use the Terraform destroy guide in the infrastructure repository.
