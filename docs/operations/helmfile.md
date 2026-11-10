# Helmfile and Helm Diff for Oracle

Helmfile manages the Oracle Argo CD chart from
`clusters/oracle/bootstrap/argocd/helmfile.yaml`, with values in the same
directory. For Proxmox, use the [local K3s guide](proxmox-k3s.md#optional-argo-cd-bootstrap).
Do not use Helmfile to manage workloads that Argo CD already owns. Run these
commands from the GitOps repository root and check the Kubernetes context.

## Install the tools

Install the versions listed in [pinned versions](README.md#pinned-versions).
For Helm 4, install Helm Diff from its signed release archive instead of
disabling signature checks:

```bash
curl -fsSLo databus23.asc https://github.com/databus23.gpg
gpg --import databus23.asc
gpg --fingerprint EA17A2A206AFF8CD
```

Check that the fingerprint is
`C564 5EF4 7482 257A 1F80 6D2B EA17 A2A2 06AF F8CD`. Then install the pinned
Linux amd64 archive. Helm verifies its provenance file during installation:

```bash
helm plugin install \
  https://github.com/databus23/helm-diff/releases/download/v3.15.15/helm-diff-linux-amd64.tgz
helm plugin list
```

For a different Linux architecture, choose the matching archive from the
[v3.15.15 release](https://github.com/databus23/helm-diff/releases/tag/v3.15.15).

## Preview, apply, and modify

Connect Tailscale and use the cluster-admin kubeconfig described in the
[Tailscale guide](tailscale.md). No SSH tunnel is needed. For a first install,
allow Helm Diff to render releases that are not installed yet. Keep Secret
values suppressed:

```bash
helmfile -f clusters/oracle/bootstrap/argocd/helmfile.yaml diff --diff-args "--allow-unreleased" --suppress-secrets
```

Apply after reviewing the diff. Add `--interactive` to require confirmation before changing the release:

```bash
helmfile -f clusters/oracle/bootstrap/argocd/helmfile.yaml apply --interactive --diff-args "--allow-unreleased" --suppress-secrets
```

Use `helmfile -f clusters/oracle/bootstrap/argocd/helmfile.yaml sync` only for
an already reviewed scripted run because it applies without a prompt. To change
Argo CD, edit the chart version or values in that directory, then preview the
diff above before applying.

Use Helmfile as the source of truth for applying this release.

## Remove the Argo CD release

First remove the root Argo CD Application using the steps in [Kubernetes operations](kubernetes.md#destroy-the-gitops-managed-resources). Then remove the Helm release:

```bash
helmfile -f clusters/oracle/bootstrap/argocd/helmfile.yaml destroy --interactive
```

The `argocd` namespace is a separate checked-in manifest. Remove it only after Helmfile has removed the release and the namespace is empty:

```bash
kubectl delete -f clusters/oracle/bootstrap/argocd/namespace.yaml
```

The chart keeps its CustomResourceDefinitions (CRDs) when the Helm release is
removed. Keep them if you may reinstall Argo CD. For a full removal, delete
them only after all Argo CD Applications and AppProjects are gone.
