# Disease Prediction GitOps

Private Kubernetes and cluster configuration for the Oracle k3s demo. Terraform and OCI resources are managed in `disease-prediction-infra`.

The cluster bootstrap and deployment workflow will be documented here. Domain and Cloudflare configuration are deferred until the application hostname is chosen. Never commit credentials, kubeconfigs, or unencrypted Kubernetes secrets.
