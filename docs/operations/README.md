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

## Install local tools on Ubuntu

The commands below use Ubuntu 24.04 and Bash. The same commands work on most
Debian-based Linux distributions. Install Python and the tools used to download
the pinned CLIs:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git openssh-client python3 python3-venv
```

Install the pinned Ansible Core version in a virtual environment from the
repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r automation/ansible/requirements.txt
ansible-playbook --version
```

Keep the virtual environment active when you run Ansible. Ansible Core 2.21
needs Python 3.12-3.14 on the control host and Python 3.9 or newer on the
managed host.

Install `kubectl` v1.37.1. This selects the matching amd64 or arm64 binary and
checks its published SHA-256 checksum before installing it:

```bash
set -euo pipefail
version=v1.37.1
arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64|arm64) ;;
  *) echo "Unsupported Debian architecture: $arch" >&2; exit 1 ;;
esac
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
cd "$tmp_dir"
curl -fsSLO "https://dl.k8s.io/release/${version}/bin/linux/${arch}/kubectl"
curl -fsSLO "https://dl.k8s.io/release/${version}/bin/linux/${arch}/kubectl.sha256"
echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client
```

Install Helm v4.3.1 from its official binary release. The official SHA-256
file is checked before installing the CLI:

```bash
set -euo pipefail
version=v4.3.1
arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64|arm64) ;;
  *) echo "Unsupported Debian architecture: $arch" >&2; exit 1 ;;
esac
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
cd "$tmp_dir"
archive="helm-${version}-linux-${arch}.tar.gz"
curl -fsSLO "https://get.helm.sh/${archive}"
curl -fsSLO "https://get.helm.sh/${archive}.sha256sum"
sha256sum --check "${archive}.sha256sum"
tar -xzf "$archive"
sudo install -o root -g root -m 0755 "linux-${arch}/helm" /usr/local/bin/helm
helm version --short
```

Install Helmfile v1.8.2 for the same architecture. Download the release and
checksum file from the [official release](https://github.com/helmfile/helmfile/releases/tag/v1.8.2):

```bash
set -euo pipefail
version=1.8.2
arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64|arm64) ;;
  *) echo "Unsupported Debian architecture: $arch" >&2; exit 1 ;;
esac
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
cd "$tmp_dir"
archive="helmfile_${version}_linux_${arch}.tar.gz"
curl -fsSLO "https://github.com/helmfile/helmfile/releases/download/v${version}/${archive}"
curl -fsSLO "https://github.com/helmfile/helmfile/releases/download/v${version}/helmfile_${version}_checksums.txt"
grep -F "  ${archive}" "helmfile_${version}_checksums.txt" | sha256sum --check
tar -xzf "$archive"
sudo install -o root -g root -m 0755 helmfile /usr/local/bin/helmfile
helmfile --version
```

Install the pinned Helm Diff plugin using the command in the
[Helmfile guide](helmfile.md#install-the-tools).
