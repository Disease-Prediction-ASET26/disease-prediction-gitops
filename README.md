# Disease Prediction GitOps

Private Kubernetes configuration for the single-node Oracle k3s demo. `disease-prediction-infra` owns OCI resources and Terraform. Application source, containers, and CI remain in their respective repositories.

## Current scope

- Bootstrap and manage the cluster with Argo CD.
- Keep the Kubernetes API and Argo CD UI private.
- Keep application services internal until a domain is chosen.
- Add Cloudflare Tunnel and DNS later; the registrar is Name.com.
- Never commit credentials, kubeconfigs, or unencrypted Kubernetes Secrets.

## Bootstrap

See [the bootstrap guide](docs/bootstrap.md). It installs a pinned Argo CD release, connects this private repository with a read-only deploy key, and applies the Oracle root application. No domain is needed.

## Layout

- `clusters/oracle/`: root Argo CD application and restricted application project.
- `apps/`: application manifests, added when the services and images are ready.
- `platform/`: cluster add-ons, added when needed.

The root app uses automated sync and self-healing, with pruning disabled. Removing a manifest from Git therefore does not automatically delete its live resource. Persistent data deletion remains an explicit operator action.
