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

From the repository root, set `KUBECONFIG` and keep the SSH tunnel open. For a first install, allow Helm Diff to render releases that are not installed yet. Keep Secret values suppressed:

```powershell
helmfile diff --diff-args "--allow-unreleased" --suppress-secrets
```

Apply after reviewing the diff. Add `--interactive` to require confirmation before changing the release:

```powershell
helmfile apply --interactive --diff-args "--allow-unreleased" --suppress-secrets
```

Use `helmfile sync` only for an already reviewed scripted run because it applies without the prompt. To change Argo CD, edit its chart version in `helmfile.yaml` or its values file, then run `helmfile diff --diff-args "--allow-unreleased" --suppress-secrets` before applying.

`helmfile diff` uses the Helm Diff plugin. To preview the release directly with Helm, first add the chart repository:

```powershell
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update argo
helm diff upgrade --install --suppress-secrets argocd argo/argo-cd --namespace argocd --version 10.11.6 --values platform/argocd/values.yaml
```

Use Helmfile as the source of truth for applying this release.

## Remove the Argo CD release

First remove the root Argo CD Application using the steps in [Kubernetes operations](kubernetes.md#destroy-the-gitops-managed-resources). Then remove the Helm release:

```powershell
helmfile destroy --interactive
```

The `argocd` namespace is a separate checked-in manifest. Remove it only after Helmfile has removed the release and the namespace is empty:

```powershell
kubectl delete -f platform/argocd/namespace.yaml
```

The chart keeps its CustomResourceDefinitions (CRDs) when the Helm release is
removed. Keep them if you may reinstall Argo CD. For a full removal, delete
them only after all Argo CD Applications and AppProjects are gone.
