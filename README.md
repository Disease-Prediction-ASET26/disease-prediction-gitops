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

- `clusters/oracle/applications/`: Argo CD root application.
- `clusters/oracle/namespaces/`: checked-in namespace manifests.
- `clusters/oracle/projects/`: restricted Argo CD projects.
- `apps/`: application manifests, added when the services and images are ready.
- `platform/argocd/`: Argo CD namespace and Helm values; the root `helmfile.yaml` pins its chart.
- `docs/operations/`: Tailscale, Helmfile, Kubernetes, and Argo CD runbooks.
- `automation/ansible/`: repeatable host setup for Tailscale.

The root app uses automated sync and self-healing, with pruning disabled. Removing a manifest from Git therefore does not automatically delete its live resource. Persistent data deletion remains an explicit operator action. The root project can manage approved Argo CD configuration and namespace manifests from the trusted root path; workload apps are limited to the `disease-prediction` namespace and an allowlist of resource kinds.

Read [operations by tool](docs/operations/README.md) before changing or deleting live resources. For OCI and Terraform, use the [infrastructure guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-infra/blob/main/README.md).
