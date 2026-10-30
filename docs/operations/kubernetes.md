# kubectl and Kustomize

Kubernetes objects are stored as YAML under `clusters/oracle/` and, when app images are ready, `apps/`. The Kustomize files list the manifests that belong to each deployment.

## Render and preview

From the repository root, with the private cluster context active:

```powershell
kubectl kustomize clusters/oracle
kubectl diff -k clusters/oracle
```

`kubectl diff` previews changes and does not apply them. A non-zero exit code can mean that differences were found.

## Apply and modify

During initial bootstrap, apply the files after reviewing the diff:

```powershell
kubectl apply -k clusters/oracle
```

After the root Application is active, edit the YAML, open a pull request, and merge the reviewed change. Argo CD syncs `main` automatically. Avoid routine direct `kubectl apply` because Argo CD may replace the live change with the Git version.

## Destroy the GitOps-managed resources

Back up any application data first. Deleting the root Application cascades to the projects and the `disease-prediction` namespace. Deleting that namespace also deletes its PVCs and may delete their data.

```powershell
kubectl -n argocd delete application oracle-root --wait=true
```

This removes the GitOps-managed resources and keeps Argo CD installed. Recreate them with `kubectl apply -k clusters/oracle` if needed. Use `helmfile destroy` only when you also want to remove Argo CD. For full VM and cluster teardown, use the Terraform destroy guide in the infrastructure repository.
