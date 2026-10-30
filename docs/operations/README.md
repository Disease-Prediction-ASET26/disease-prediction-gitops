# Operations by tool

Use the tool that owns the resource. Keep changes in files and review the diff before applying them.

| Tool | Owns | Guide |
|---|---|---|
| Terraform | OCI VM, network, and cluster host | [Infrastructure README](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md) |
| Ansible and Tailscale | Tailscale package and private host access | [Tailscale](tailscale.md) |
| Helmfile and Helm Diff | Argo CD Helm release | [Helmfile](helmfile.md) |
| kubectl and Kustomize | Checked-in Kubernetes manifests | [Kubernetes](kubernetes.md) |
| Argo CD | Ongoing sync and private cluster UI | [Argo CD](argocd.md) |
| SSH tunnel and kubeconfig | Private administrative access | [Access](access.md) |

## Tool versions

Use these versions for this cluster setup:

| Tool | Version |
|---|---|
| Ansible Core | 2.21.5 |
| kubectl | v1.37.1 |
| Helm | v4.3.1 |
| Helmfile | v1.8.2 |
| helm-diff plugin | v3.15.15 |
| Argo CD Helm chart | 10.11.6 |
| Argo CD images | v3.5.6 |

The Helm chart version is separate from the Argo CD image version. The image tag is set in `platform/argocd/values.yaml`; the chart version is pinned in `helmfile.yaml`.

## Install local tools

- Run Ansible from Linux, macOS, or WSL. Install the pinned `ansible-core` in
  `automation/ansible/requirements.txt` inside a Python virtual environment.
  Version 2.21 needs Python 3.12-3.14 on the control host and Python 3.9+ on
  managed hosts.
- Install [kubectl for Windows](https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/) at v1.37.1.
- Install Helm 4.3.1 with `winget install --id Helm.Helm --exact --version 4.3.1`.
- Install PowerShell 7.6.9 with `winget install --id Microsoft.PowerShell --exact --version 7.6.9.0`; the Windows Helm Diff installer uses `pwsh`.
- Download Helmfile v1.8.2 for Windows from the [official release page](https://github.com/helmfile/helmfile/releases/tag/v1.8.2) and verify the archive with its published checksum before adding `helmfile.exe` to `PATH`.
- Install the Helm Diff plugin using the command in the [Helmfile guide](helmfile.md#install-the-tools).
