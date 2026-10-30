# Disease Prediction GitOps

Kubernetes configuration for the single-node Oracle k3s demo. `disease-prediction-infra` owns OCI resources and Terraform. Application source, containers, and CI remain in their respective repositories.

## Current scope

- Bootstrap and manage the cluster with Argo CD.
- Use Tailscale for private SSH and Kubernetes access.
- Keep the Kubernetes API and Argo CD UI private.
- Keep application services internal until a domain is chosen.
- Never commit credentials, kubeconfigs, or unencrypted Kubernetes Secrets.

## Bootstrap

See [the bootstrap guide](docs/bootstrap.md). It installs a pinned Argo CD release with Helmfile and applies the Oracle root application. The root app reads this public repository over HTTPS. No domain is needed.

## Layout

- `clusters/oracle/applications/`: Argo CD root and platform applications.
- `clusters/oracle/namespaces/`: checked-in namespace manifests.
- `clusters/oracle/projects/`: restricted Argo CD projects.
- `clusters/oracle/k3s-host-manifests/`: versioned source for K3s-owned host add-ons; these files are not part of the Argo Kustomization.
- `apps/`: application manifests, added when the services and images are ready.
- `platform/argocd/`: Argo CD namespace and Helm values; the root `helmfile.yaml` pins its chart.
- `docs/operations/`: cluster access, deployment, secrets, and recovery runbooks.
- `automation/ansible/`: repeatable host setup for Tailscale.

The root app uses automated sync and self-healing, with pruning disabled. Removing a manifest from Git therefore does not automatically delete its live resource. Persistent data deletion remains an explicit operator action. The root project can manage approved Argo CD configuration and namespace manifests from the trusted root path; workload apps are limited to the `disease-prediction` namespace and an allowlist of resource kinds.

External Secrets Operator is a namespace-scoped platform app. Its OCI Vault
`SecretStore` is added only after the Vault exists and its OCID is available.
See the [secrets operations guide](docs/operations/secrets.md) before adding,
rotating, or removing synced secrets.

GitHub Actions validates the Oracle manifests and Ansible playbooks, and runs
the shared secret scan on pull requests and pushes to `main`.

Read [operations by tool](docs/operations/README.md) before changing or deleting live resources. For OCI and Terraform, use the [infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md).
