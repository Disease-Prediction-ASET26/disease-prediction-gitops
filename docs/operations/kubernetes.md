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

During initial bootstrap, apply the files after reviewing the diff:

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

## Destroy the GitOps-managed resources

Back up any application data first. Deleting the root Application cascades to the projects and the `disease-prediction` namespace. Deleting that namespace also deletes its PVCs and may delete their data.

```bash
kubectl -n argocd delete application oracle-root --wait=true
```

This removes the GitOps-managed resources and keeps Argo CD installed. Recreate them with `kubectl apply -k clusters/oracle` if needed. Use `helmfile destroy` only when you also want to remove Argo CD. For full VM and cluster teardown, use the Terraform destroy guide in the infrastructure repository.
