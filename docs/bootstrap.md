# Bootstrap the Oracle cluster

This guide assumes k3s is already installed and healthy on the Oracle VM. It does not create OCI resources or require a public app hostname.

## Prerequisites

- An administrator has a working, private `kubectl` context for this cluster (for example, over SSH).
- The k3s API is not exposed to the internet.
- k3s Secrets encryption at rest was enabled at initial installation.
- You can add a read-only deploy key to this private GitHub repository.

Keep the deploy key and kubeconfig outside the repository. Use the private cluster context for all commands below.

## Install Argo CD

Install the non-HA distribution pinned to Argo CD `v3.5.6` (the current stable release when this guide was written). The upstream release provides signed images and provenance; follow its release verification guidance if verifying artifacts before installation.

```powershell
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply --server-side --force-conflicts -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.6/manifests/install.yaml
kubectl -n argocd get pods
```

Wait for the Argo CD pods to become ready before continuing.

## Connect this private repository

Create a dedicated Ed25519 key pair outside this checkout. Add only the `.pub` key to this repository's **Settings → Deploy keys**, leaving write access disabled. Keep the private key in a protected local location and do not paste it into GitHub issues or commits.

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\disease-prediction-gitops" -C "argocd read-only gitops"
```

Create the Argo CD repository Secret from the private key file. The private key is sent to the cluster as a Kubernetes Secret; never put this command or key in a manifest committed to Git.

```powershell
kubectl create secret generic gitops-repository --namespace argocd --from-literal=type=git --from-literal=url=git@github.com:Disease-Prediction-ASET26/disease-prediction-gitops.git --from-file=sshPrivateKey="$env:USERPROFILE\.ssh\disease-prediction-gitops"
kubectl label secret gitops-repository --namespace argocd argocd.argoproj.io/secret-type=repository
```

The repository Secret grants Argo CD read access only. Rotate it by replacing the GitHub deploy key and Kubernetes Secret together. Keep SSH host-key verification enabled; do not configure Argo CD to skip host-key checks.

## Apply the root configuration

From a checkout of this repository, using the private cluster context:

```powershell
kubectl apply -k clusters/oracle
kubectl -n argocd get applications,appprojects
```

The root application reconciles this directory from `main`. The `oracle-apps` AppProject restricts future application definitions to this repository and the `argocd` / `disease-prediction` namespaces. Add child Applications only when the corresponding application manifests and image digests are ready.

## Access Argo CD privately

The Argo CD Service stays internal. With the private `kubectl` context active, run:

```powershell
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Open `https://localhost:8080` while the port-forward is running. If you use the initial admin account, retrieve its bootstrap password with the official Argo CD CLI and rotate it immediately. Do not expose the Argo CD Service through a public IP, NodePort, or unauthenticated tunnel.

## Security and deletion policy

- Keep SSH, kubeconfig, API credentials, Git private keys, and database credentials out of Git and Terraform state.
- Keep the API server and Argo CD UI reachable only through the documented private administration path.
- Automated sync and self-healing are enabled; automated pruning is disabled. Review any deletion, especially for persistent resources, and remove data only through a documented backup-aware procedure.
- Use immutable image digests in application manifests; do not deploy mutable `latest` tags.
- Use synthetic demo data until the project has approved privacy and operational requirements for real health data.

## Later: Cloudflare and Name.com

No domain is needed to provision the VM, install k3s, or bootstrap Argo CD. After the application name is selected, move DNS hosting for the Name.com domain to Cloudflare, verify existing records, and deploy a Cloudflare Tunnel that routes only the chosen application hostname to the frontend Service. Keep this step out of the initial cluster bootstrap.
