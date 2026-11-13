# Deploy the Disease Prediction dev stack

The Oracle workload manifests are prepared under
[`clusters/oracle/disease-prediction`](../../clusters/oracle/disease-prediction).
The Argo CD Application is staged in
[`applications/disease-prediction.yaml`](../../clusters/oracle/applications/disease-prediction.yaml)
but is not listed in `applications/kustomization.yaml`. Add it there only when
the required Vault secrets are synced and the backend-to-AI API boundary is
ready. This keeps Argo CD from starting an incomplete stack.

Use `dev.pocket-doc.app` for the dev stack and reserve
`health.pocket-doc.app` for production. Both names are in the existing
`pocket-doc.app` zone. The staged dev route targets only the frontend and uses
Authelia ForwardAuth. The backend and AI Services stay internal as `ClusterIP`
Services. The frontend proxies `/api/` to `http://backend:8080`. The AI Service
is `http://ai:8000`; the backend still needs its HTTP client and request/response
mapping before it uses that Service. The Argo Application is inactive until the
API boundary and Vault secrets are ready. Add the production route with the
production stack after its database, secrets, and image digests are prepared.
Follow the [domain and ingress guide](domain-ingress.md) when changing routes.

## Prepare the model image

Train and review the classifier outside k3s. Training does not happen in the
deployed service. Follow the AI repository's
[model training and release guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-ai#model-training-and-release).
Keep the dataset and trained model out of Git. After the team accepts the
training results, publish the model as an immutable image. The release workflow
trains from a pinned dataset, bundles the pinned ClinicalBERT and MiniLM files,
checks the artifact manifest, scans the image, and prints the digest to pin in
GitOps. The dev candidate from `model-runtime-dev-v0.1.2` is pinned in the AI
Deployment. Review representative predictions before accepting a model for
production; held-out scores alone do not validate clinical usefulness.

The backend and frontend deployments already use the published dev image
digests. The AI Deployment uses the immutable runtime digest. Do not deploy a
moving tag.

## Prepare Vault secrets

Before merging the ExternalSecret changes, create these OCI Vault secrets using
the [Secrets guide](secrets.md). Store JSON payloads with the listed properties:

| OCI Vault secret | JSON properties | Purpose |
|---|---|---|
| `disease-prediction-runtime-secrets` | `data_encryption_key` | Base64 AES-256 key required by the backend. |
| `disease-prediction-ghcr-pull` | `username`, `token` | GHCR username and a read-only package token. |

The existing PostgreSQL credentials and server CA are already synced in the
namespace. The backend configuration uses the PostgreSQL Service and verifies
its TLS certificate with the synced CA.

After the ExternalSecrets are synced, check their status without printing
Secret data:

```sh
kubectl --context oracle-k3s -n disease-prediction \
  get externalsecrets postgres-app-credentials postgres-server-ca \
  disease-prediction-runtime-secrets ghcr-pull
```

## Activate the Application

1. Confirm the backend has a real HTTP prediction client and that the AI request
   and response formats are mapped. The client should call `http://ai:8000`.
2. Confirm the AI Deployment points to the accepted model-runtime digest.
   Record the backend and frontend dev image digests from CI.
3. Update the three image references in `deployments.yaml` to those digests.
4. Add `disease-prediction.yaml` to `clusters/oracle/applications/kustomization.yaml`.
5. Render both Kustomize paths and review the Git diff:

   ```sh
   kubectl kustomize clusters/oracle
   kubectl kustomize clusters/oracle/disease-prediction
   ```

6. Merge the GitOps pull request. Argo CD creates the Application and syncs its
   workloads. Do not use `kubectl apply` for these managed resources.

The AI Deployment has separate process and readiness probes. Readiness loads
the trained classifier, manifest, and parser models before the pod receives
traffic. The model-runtime image contains pinned ClinicalBERT and MiniLM files
and runs in offline mode. It does not need Hugging Face egress or a cache PVC.
The measured local runtime peaked at about 2.03 GiB during warm-up, so the AI
container requests 2.25 GiB and can use up to 3 GiB. The namespace quota allows
the AI, backend, and frontend together. The Oracle node has only 2 CPU cores;
do not run dev and production copies there at the same time without reviewing
capacity first.

Check deployment state and access the frontend through a local port forward:

```sh
kubectl --context oracle-k3s -n disease-prediction \
  get deployments,pods,services,httproutes,externalsecrets
kubectl --context oracle-k3s -n disease-prediction \
  rollout status deployment/ai
kubectl --context oracle-k3s -n disease-prediction \
  port-forward service/frontend 8080:8080
```

Open `http://localhost:8080`. Until the backend integration is merged, its
assessment endpoint still returns the stub prediction.

## Update or remove the dev stack

For an application or model update, publish a new image, pin its digest in
GitOps, and merge the change. The AI model version and checksum are recorded in
the artifact manifest and image label.

To remove the stack, delete the Argo CD Application with cascading enabled:

```sh
argocd app delete disease-prediction-dev --cascade
```

Check that the three Deployments, Services, and HTTPRoute are gone before
removing the ExternalSecrets or their Vault values. The model and parser assets
are part of the immutable AI runtime image.
