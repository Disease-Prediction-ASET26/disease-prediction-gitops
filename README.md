# Disease Prediction GitOps

Kubernetes configuration for the single-node Oracle k3s cluster. The
infrastructure repository owns OCI resources and Terraform. Application
source, images, and CI live in their respective repositories.

## Current scope

- Bootstrap and manage the cluster with Argo CD.
- Use Tailscale for private SSH and Kubernetes access.
- Keep the Kubernetes API private and protect the Argo CD UI with Authelia SSO.
- Use the `pocket-doc.app` Cloudflare zone, Cloudflare Tunnel, Traefik, and
  ExternalDNS for reviewed public routes. Argo CD's route is enabled manually
  after its OIDC setup is ready; no workload application route is published.
- Never commit credentials, kubeconfigs, or unencrypted Kubernetes Secrets.

## Bootstrap

See [the bootstrap guide](docs/bootstrap.md). It installs a pinned Argo CD release with Helmfile and applies the Oracle root application. The root app reads this public repository over HTTPS. Bootstrap does not depend on the domain.

## Architecture and operations

See the [cluster map](docs/architecture.md) for separate views of resource
ownership, administration and secrets, and public traffic. Use the
[operations index](docs/operations/README.md) to find the runbook for a task.

## Layout

- `clusters/oracle/applications/`: Argo CD root and child Applications.
- `clusters/oracle/projects/`: Argo CD source, destination, and resource allowlists.
- `clusters/oracle/namespaces/`: namespaces created by the root Application.
- `clusters/oracle/auth/`, `edge/`, `ingress/`, and `observability/`: local
  resources managed by child Applications.
- `clusters/oracle/external-secrets/<namespace>/`: namespace-scoped
  `SecretStore` and `ExternalSecret` resources that read OCI Vault. These files
  contain references, not secret values.
- `clusters/oracle/policies/`: workload quotas and related policies.
- `clusters/oracle/apps/`: product workloads, added when their API and
  publishable images are ready.
- `clusters/oracle/k3s-host-manifests/`: K3s-owned host add-ons; these files
  are not part of the Argo Kustomization.
- `platform/argocd/`: Argo CD namespace and Helm values; the root `helmfile.yaml` pins its chart.
- `docs/operations/`: cluster access, deployment, secrets, and recovery runbooks.
- `automation/ansible/`: repeatable host setup for Tailscale.

The root Kustomization groups its `applications/`, `namespaces/`, and
`projects/` resources by type. Each child Application points to a local
component path or a pinned Helm chart.

The root app uses automated sync and self-healing, with pruning disabled. Removing a manifest from Git therefore does not automatically delete its live resource. Persistent data deletion remains an explicit operator action. The root project can manage approved Argo CD configuration and namespace manifests from the trusted root path; workload apps are limited to the `disease-prediction` namespace and an allowlist of resource kinds.

External Secrets Operator syncs selected OCI Vault values to Kubernetes
Secrets. See the [secrets guide](docs/operations/secrets.md) before changing
synced credentials.

GitHub Actions validates the Oracle manifests and Ansible playbooks, and runs
the shared secret scan on pull requests and pushes to `main`.

Pod Security Admission enforces Restricted in workload and platform
namespaces. Monitoring uses Baseline because Grafana's data-volume setup
adjusts ownership. Node exporter is isolated in a dedicated namespace with
Privileged enforcement because it reads host filesystems. See [Kubernetes
operations](docs/operations/kubernetes.md#pod-security-standards).

Read [operations by tool](docs/operations/README.md) before changing or deleting live resources. For OCI and Terraform, use the [infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md).
