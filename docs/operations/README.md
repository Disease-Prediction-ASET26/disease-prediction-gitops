# Operations

Use the guide for the tool that owns the change:

| Task | Guide |
|---|---|
| Private SSH, kubectl, and K9s access | [Tailscale](tailscale.md) |
| Install or update Argo CD | [Helmfile](helmfile.md) |
| Edit Kubernetes manifests | [Kubernetes](kubernetes.md) |
| Check Argo CD sync or access its UI | [Argo CD](argocd.md) |
| Sync secrets from OCI Vault | [Secrets](secrets.md) |
| Recover the single-node cluster | [Recovery](recovery.md) |
| Delegate `pocket-doc.app` and plan public app routes | [Domain and ingress](domain-ingress.md) |
| Create or change OCI resources | [Infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md) |

## Pinned versions

Use these versions for this cluster. The chart and image versions are set in
`helmfile.yaml` and `platform/argocd/values.yaml`.

| Tool | Version |
|---|---|
| Ansible Core | 2.21.5 |
| kubectl | v1.37.1 |
| Helm | v4.3.1 |
| Helmfile | v1.8.2 |
| helm-diff | v3.15.15 |
| K9s | v0.51.0 |
| Argo CD chart | 10.11.6 |
| Argo CD image | v3.5.6 |
| External Secrets chart and image | 2.14.0 |

## Install workstation tools

These commands use Ubuntu or WSL with Zsh or Bash. Install Ansible in a
repository-local virtual environment:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git gnupg openssh-client python3-venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r automation/ansible/requirements.txt
```

Install the pinned `kubectl`, Helm, Helmfile, and K9s versions from the
[kubectl guide](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/),
[Helm releases](https://github.com/helm/helm/releases),
[Helmfile releases](https://github.com/helmfile/helmfile/releases), and
[K9s releases](https://github.com/derailed/k9s/releases). Verify the published
checksums or signatures before installing downloaded binaries. The K9s setup
command is in the [Tailscale guide](tailscale.md).

Install Helm Diff using the signed release procedure in the
[Helmfile guide](helmfile.md#install-the-tools).
