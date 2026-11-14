# Deploy the Disease Prediction dev stack

The Oracle workload manifests are under
[`clusters/oracle/disease-prediction`](../../clusters/oracle/disease-prediction).
The dev Argo CD Application is active through
[`applications/disease-prediction.yaml`](../../clusters/oracle/applications/disease-prediction.yaml)
and is listed in `applications/kustomization.yaml`. Argo CD syncs it from
`main`. The frontend and backend run on Oracle. The model runs on Proxmox,
managed by the `disease-prediction-ai-dev` Application. The backend calls
`http://proxmox-ai:8000/predict` through Tailscale, maps the response to its
public API shape, and returns an emergency result without calling the model.

Use `dev.pocket-doc.app` for the dev stack and reserve
`health.pocket-doc.app` for production. Both names are in the existing
`pocket-doc.app` zone. The dev route targets only the frontend and uses
Authelia ForwardAuth. The Authelia rule requires two-factor login. The backend
and model Services stay private. The frontend proxies
`/api/` to `http://backend:8080`; the backend calls the AI Service at
`http://proxmox-ai:8000`. The required Vault secrets were synced before
activation; keep all four ExternalSecrets Ready. Add the production route with the
production stack after its database, secrets, and image digests are prepared.
Follow the
[domain and ingress guide](domain-ingress.md) when changing routes.

## Prepare the model image

Train and review the classifier outside k3s. Training does not happen in the
deployed service. Follow the AI repository's
[model training and release guide](https://github.com/Disease-Prediction-ASET26/disease-prediction-ai#model-training-and-release).
Keep the dataset and trained model out of Git. After the team accepts the
training results, publish the model as an immutable image. The release workflow
copies the trained classifier, bundles the pinned ClinicalBERT and MiniLM files,
checks the artifact manifest, scans both platform images, and verifies offline
prediction. It does not train a model. Review representative predictions before
accepting a model for production; held-out scores alone do not validate clinical
usefulness.

The Deployments use immutable dev image digests. Do not deploy a moving tag.
After a successful `develop` image publish, backend and frontend CI open or
update a GitOps pull request with the new digest. Publishing a reviewed AI
model runtime does the same. CI merges the update after the GitOps checks pass,
then Argo CD syncs it. These workflows need a GitHub App installed only on
`disease-prediction-gitops`, with Contents and Pull requests write access. Set
`GITOPS_CLIENT_ID` to the app Client ID and `GITOPS_APP_PRIVATE_KEY` to the
complete PEM key in the backend, frontend, and AI Actions secrets before
merging application changes that publish dev images.

## Prepare Vault secrets

Before activating the Application, ensure these OCI Vault secrets exist using
the [Secrets guide](secrets.md). Store JSON payloads with the listed properties:

| OCI Vault secret | JSON properties | Purpose |
|---|---|---|
| `disease-prediction-runtime-secrets` | `data_encryption_key` | Base64 AES-256 key required by the backend. |
| `disease-prediction-ghcr-pull` | `username`, `token` | GHCR username and a read-only package token. |

Dev and production use separate databases, login roles, and passwords on the
same Proxmox PostgreSQL cluster: `disease_prediction_dev` and
`disease_prediction_prod`. They share the cluster's CPU, storage, and
availability. The dev app connects to `disease_prediction_dev`; production is
not deployed yet. Keep each password in its environment's Vault secret. The
dev and production credentials are synced to separate OCI Vault secrets. The
backend verifies the server certificate with the synced CA in either
environment. The old `disease_prediction` database and
role were removed after the dev connection was verified. Their data was not
migrated.

After the OCI secrets are present and the ExternalSecrets are synced, check
their status without printing Secret data:

```sh
kubectl --context oracle-k3s -n disease-prediction \
  get externalsecrets postgres-app-credentials postgres-server-ca \
  disease-prediction-runtime-secrets ghcr-pull
```

## Activate or recreate the Application

1. Confirm all four ExternalSecrets are Ready. Do not print Kubernetes Secret
   data.
2. Confirm the three Deployment images use immutable digests. The AI digest
   must come from a reviewed model-runtime release.
3. Keep `disease-prediction.yaml` in the Oracle applications Kustomization and
   `disease-prediction-ai-dev.yaml` in the Proxmox applications Kustomization.
4. Render both Kustomize paths and review the Git diff:

   ```sh
   kubectl kustomize clusters/oracle
   kubectl kustomize clusters/oracle/disease-prediction
   kubectl kustomize clusters/proxmox
   kubectl kustomize clusters/proxmox/disease-prediction-ai/dev
   ```

5. Merge the GitOps pull request. Argo CD creates or updates the Application
   and syncs its workloads. Do not use `kubectl apply` for these managed resources.

The AI Deployment has separate process and readiness probes. Readiness loads
the trained classifier, manifest, and parser models before the pod receives
traffic. The model-runtime image contains pinned ClinicalBERT and MiniLM files
and runs in offline mode. It does not need Hugging Face egress or a cache PVC.
The measured local runtime peaked at about 2.03 GiB during warm-up, so the AI
container requests 2.25 GiB and can use up to 3 GiB on Proxmox. A NetworkPolicy
denies model pod egress; its required assets are in the image.

Check deployment state and access the frontend through a local port forward:

```sh
kubectl --context oracle-k3s -n disease-prediction \
  get deployments,pods,services,httproutes,externalsecrets
kubectl --context proxmox-k3s -n disease-prediction-dev \
  rollout status deployment/ai
kubectl --context oracle-k3s -n disease-prediction \
  port-forward service/frontend 8080:8080
```

Open `https://dev.pocket-doc.app` in a private browser session. An unauthenticated
request must redirect to Authelia. After login, submit a free-text description
and a checklist-only assessment. The backend returns 422 when the AI service
cannot identify a symptom, 503 when it cannot connect, and 502 for other
upstream errors.

## Update or remove the dev stack

After an application or reviewed model-runtime publish, review and merge the
GitOps digest pull request. Argo CD syncs the new immutable image digest. The
AI model version and checksum are recorded in the artifact manifest and image
label.

To remove the stack, remove the Application entries from Git, merge, then delete
both Application objects with their resource finalizers:

```sh
kubectl --context oracle-k3s -n argocd delete application disease-prediction-dev
kubectl --context proxmox-k3s -n argocd delete application disease-prediction-ai-dev
```

Check that the Deployments, Services, and HTTPRoute are gone before
removing the ExternalSecrets or their Vault values. The model and parser assets
are part of the immutable AI runtime image.
