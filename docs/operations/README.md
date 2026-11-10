# Operations

Unless a guide says otherwise, run its commands from the GitOps repository root.
Check the Kubernetes context before making cluster changes.

For a quick map of the cluster and its trust boundaries, start with the
[cross-repository DevOps overview](https://github.com/Disease-Prediction-ASET26/disease-prediction-docs/blob/main/devops/README.md).

The local K3s guide covers Proxmox. The other cluster runbooks cover Oracle.
Workstation setup below applies to both clusters.

| Task | Guide |
|---|---|
| Install and manage the local Proxmox K3s node | [Local K3s](proxmox-k3s.md) |
| Private SSH, kubectl, and K9s access | [Tailscale](tailscale.md) |
| Install or update Argo CD | [Helmfile](helmfile.md) |
| Edit Kubernetes manifests | [Kubernetes](kubernetes.md) |
| Check Argo CD sync or access its UI | [Argo CD](argocd.md) |
| Sync secrets from OCI Vault | [Secrets](secrets.md) |
| Manage local PostgreSQL and Vault secrets | [Proxmox data services](proxmox-data-services.md) |
| Manage login and passkey authentication | [Authelia](authelia.md) |
| View cluster metrics and Grafana dashboards | [Observability](observability.md) |
| Check or change host log retention | [Log retention](log-retention.md) |
| Recover the single-node cluster | [Recovery](recovery.md) |
| Manage Cloudflare DNS and public app routes | [Domain and ingress](domain-ingress.md) |
| Create or change OCI resources | [Infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md) |

## Pinned versions

These are the workstation and Oracle cluster versions. The Oracle Argo CD chart
and values are pinned under `clusters/oracle/bootstrap/argocd/`; other versions
are in the relevant Application manifests. The Proxmox pins are under
`clusters/proxmox/`.

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
| HashiCorp Vault chart / server | 0.34.1 / 2.0.4 |
| CloudNativePG chart / operator | 0.29.1 / 1.30.1 |
| ExternalDNS chart and image | 1.23.0 / 0.23.0 |
| Authelia image | 4.39.28 |
| kube-prometheus-stack chart | 92.17.0 |

## Install workstation tools

These commands use Ubuntu or WSL with Zsh or Bash. Install Ansible in a
repository-local virtual environment with a supported Python version. The
pinned Ansible Core was checked with Python 3.14; it does not start with Python
3.15 in this environment.

```bash
sudo apt update
sudo apt install -y ca-certificates curl git gnupg openssh-client python3-venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-ansible.txt
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
