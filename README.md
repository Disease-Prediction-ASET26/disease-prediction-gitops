# Disease Prediction GitOps

This repository manages the independent Oracle and Proxmox K3s clusters.
Oracle runs the public edge, Grafana, and the dev and production frontends and
backends. Proxmox runs both model services, PostgreSQL, Vault, and the
Prometheus server. Terraform manages OCI resources in the
infrastructure repository; application source and images live in their own
repositories.

## Current scope

- Manage each cluster with Argo CD. Bootstrap Argo CD separately with Helmfile.
- Use Tailscale for private SSH and Kubernetes API access. Neither cluster's
  Kubernetes API is public.
- On Oracle, Cloudflare Tunnel and Traefik carry approved public routes.
  Authelia protects the dev and production product routes.
- Never commit credentials, kubeconfigs, or unencrypted Kubernetes Secrets.

## Start here

- [Oracle bootstrap guide](docs/bootstrap.md): install Argo CD and apply the
  Oracle root Application. It does not create OCI resources or depend on DNS.
- [Operations index](docs/operations/README.md): find a cluster runbook by task.
- [Local Proxmox K3s guide](docs/operations/proxmox-k3s.md): install or manage
  the isolated Ubuntu node and its optional Argo CD instance.
- [Proxmox data services guide](docs/operations/proxmox-data-services.md):
  manage local PostgreSQL, Vault, and cross-cluster access.
- [Disease Prediction operations](docs/operations/disease-prediction.md):
  deploy and check the two application environments.
- [DevOps overview](https://github.com/Disease-Prediction-ASET26/disease-prediction-docs/blob/main/devops/README.md):
  see cross-repository ownership, access, and traffic flows.

## Layout

Each cluster has its own directory:

- `clusters/oracle/`: the Oracle root Kustomization, Applications, projects,
  namespaces, and the components those Applications manage. The
  `k3s-host-manifests/` directory contains K3s-owned host add-ons.
- `clusters/proxmox/`: the local root Kustomization, model workloads, Vault,
  External Secrets, CloudNativePG, PostgreSQL, and the Prometheus monitoring
  backend. It does not publish public routes.
- `clusters/<cluster>/bootstrap/argocd/`: that cluster's Argo CD namespace,
  Helmfile, and values.
- `clusters/<cluster>/automation/ansible/`: that cluster's host automation.
- `requirements-ansible.txt`: the Ansible Core version used by both clusters.
- `docs/operations/`: cluster access, deployment, secrets, and recovery runbooks.

Oracle's component directories include `auth/`, `edge/`, `external-secrets/`,
`ingress/`, `observability/`, and `policies/`. External Secrets files contain
OCI Vault references, not secret values. Proxmox runs its own Vault and
External Secrets Operator; its policies and secret references live under
`clusters/proxmox/`.

The root Kustomizations list the Kubernetes resources Argo CD manages. Bootstrap
files, Ansible playbooks, and Oracle host manifests are applied separately;
placing a file in a cluster directory does not apply it. Oracle's root groups
its `applications/`, `namespaces/`, and `projects/` by type. Each child
Application points to a component path or a pinned Helm chart and has its own
sync policy.

Both root Applications use automated sync and self-healing, with pruning
disabled. Removing a manifest from Git does not automatically delete its live
resource. Persistent data deletion remains an explicit operator action. The
Oracle root project can manage approved Argo CD configuration and namespace
manifests; workload apps are limited to their dev and production namespaces and
an allowlist of resource kinds.

External Secrets Operator syncs selected OCI Vault values to Kubernetes
Secrets. See the [secrets guide](docs/operations/secrets.md) before changing
synced credentials.

GitHub Actions validates both cluster manifests and Ansible playbooks. It also
runs the shared secret scan on pull requests and pushes to `main`.

Pod Security Admission enforces Restricted in workload and platform
namespaces. Monitoring uses Baseline because Grafana's data-volume setup
adjusts ownership. Node exporter is isolated in a dedicated namespace with
Privileged enforcement because it reads host filesystems. See [Kubernetes
operations](docs/operations/kubernetes.md#pod-security-standards).

For OCI resources and Terraform changes, use the
[infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md).
