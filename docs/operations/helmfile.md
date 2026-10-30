# Helmfile and Helm Diff

Helmfile manages the Argo CD chart from `helmfile.yaml`. Chart values live in `platform/argocd/values.yaml`. Do not use Helmfile to manage workloads that Argo CD already owns.

## Install the tools

Install the versions listed in [tool versions](README.md#tool-versions). Install Helmfile from the official release page and check its published SHA-256 before using the binary. Add the Helm Diff plugin once:

```powershell
helm plugin install https://github.com/databus23/helm-diff --version v3.15.15 --verify=false
helm plugin list
```

Helm 4 does not accept this plugin's metadata for built-in signature verification. Pin the version and install only from the official project release.

## Preview, apply, and modify

From the repository root, set `KUBECONFIG` and keep the SSH tunnel open. Review the planned release changes:

```powershell
helmfile diff
```

Apply after reviewing the diff. `apply` asks before changing the release:

```powershell
helmfile apply
```

For a reviewed CI or scripted run, use `helmfile sync` to apply without the prompt. To change Argo CD, edit its chart version in `helmfile.yaml` or its values file, then run `helmfile diff` before applying.

`helmfile diff` uses the Helm Diff plugin. To preview the release directly with Helm, first add the chart repository:

```powershell
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update argo
helm diff upgrade argocd argo/argo-cd --namespace argocd --version 10.11.6 --values platform/argocd/values.yaml
```

Use Helmfile as the source of truth for applying this release.

## Remove the Argo CD release

First remove the root Argo CD Application using the steps in [Kubernetes operations](kubernetes.md#destroy-the-gitops-managed-resources). Then remove the Helm release:

```powershell
helmfile destroy
```

The `argocd` namespace is a separate checked-in manifest. Remove it only after Helmfile has removed the release and the namespace is empty:

```powershell
kubectl delete -f platform/argocd/namespace.yaml
```
