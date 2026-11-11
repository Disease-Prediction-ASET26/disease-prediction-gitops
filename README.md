# Disease Prediction GitOps

Kubernetes configuration for the independent single-node Oracle and local
Proxmox K3s clusters. Oracle hosts application workloads, public edge services,
and Grafana. Proxmox hosts local PostgreSQL, Vault, and the Prometheus backend.
The infrastructure repository owns OCI resources and Terraform. Application
source, images, and CI live in their respective repositories.

## Current scope

- Bootstrap and manage Oracle and Proxmox with Argo CD. Proxmox runs the local
  PostgreSQL database, Vault secret store, and Prometheus monitoring backend.
- Use Tailscale for private SSH and Kubernetes access.
- Keep the Kubernetes APIs private. On Oracle, protect the Argo CD UI with
  Authelia SSO.
- On Oracle, use the `pocket-doc.app` Cloudflare zone, Cloudflare Tunnel, Traefik, and
  ExternalDNS for reviewed public routes. Argo CD's route is enabled manually
  after its OIDC setup is ready; no workload application route is published.
- Never commit credentials, kubeconfigs, or unencrypted Kubernetes Secrets.

## Bootstrap

See [the bootstrap guide](docs/bootstrap.md). It installs a pinned Argo CD release with Helmfile and applies the Oracle root application. The root app reads this public repository over HTTPS. Bootstrap does not depend on the domain.

For the isolated Ubuntu VM, use the [local K3s guide](docs/operations/proxmox-k3s.md).
Its Ansible install and optional Argo CD bootstrap are separate from Oracle.

## Architecture and operations

See the [cross-repository DevOps overview](https://github.com/Disease-Prediction-ASET26/disease-prediction-docs/blob/main/devops/README.md)
for resource ownership, administration and secrets, and public traffic. Use the
[operations index](docs/operations/README.md) to find the runbook for a task.

## Layout

Each cluster has its own directory:

- `clusters/oracle/`: the Oracle root Kustomization, Applications, projects,
  namespaces, and the components those Applications manage. The
  `k3s-host-manifests/` directory contains K3s-owned host add-ons.
- `clusters/proxmox/`: the local root Kustomization, Vault, External Secrets,
  CloudNativePG, PostgreSQL, and the Prometheus monitoring backend. It does not
  include application workloads or public routes.
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
manifests; workload apps are limited to the `disease-prediction` namespace and
an allowlist of resource kinds.

External Secrets Operator syncs selected OCI Vault values to Kubernetes
Secrets. See the [secrets guide](docs/operations/secrets.md) before changing
synced credentials.

GitHub Actions validates both cluster manifests and the Ansible playbooks, and runs
the shared secret scan on pull requests and pushes to `main`.

Pod Security Admission enforces Restricted in workload and platform
namespaces. Monitoring uses Baseline because Grafana's data-volume setup
adjusts ownership. Node exporter is isolated in a dedicated namespace with
Privileged enforcement because it reads host filesystems. See [Kubernetes
operations](docs/operations/kubernetes.md#pod-security-standards).

Read [operations by tool](docs/operations/README.md) before changing or deleting live resources. For OCI and Terraform, use the [infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md).
