# Bootstrap the Oracle cluster

This guide installs Argo CD and connects it to the GitOps repository. It does not create OCI resources or expose an application hostname.

## Before you start

- Follow [the private access guide](operations/access.md) and keep the SSH tunnel open.
- Install the pinned tools listed in [tool versions](operations/README.md#tool-versions).
- Confirm `kubectl get nodes` shows the Oracle node as `Ready`.
- This GitHub repository is public. Argo CD reads it over HTTPS, so no Git credential is needed.

## Install Argo CD with Helmfile

The Argo CD namespace is a checked-in manifest. Review it, then create it:

```powershell
kubectl diff -f platform/argocd/namespace.yaml
kubectl apply -f platform/argocd/namespace.yaml
```

Review the pinned chart release and values:

```powershell
helmfile diff --diff-args "--allow-unreleased" --suppress-secrets
```

Install it after reviewing the diff. Add `--interactive` to require confirmation:

```powershell
helmfile apply --interactive --diff-args "--allow-unreleased" --suppress-secrets
kubectl -n argocd get pods
```

Wait until the Argo CD pods are ready before continuing.

## Apply the checked-in cluster configuration

The root configuration contains the Argo CD projects, application namespace, and root Application. Preview and apply it once:

```powershell
kubectl diff -k clusters/oracle
kubectl apply -k clusters/oracle
kubectl -n argocd get applications,appprojects
```

The root Application follows `main`. After bootstrap, make changes in files, open a pull request, and merge after review. Argo CD then syncs the changes. App workloads are added only when their runnable ARM64 images and service contracts are ready.

## Open Argo CD privately

Use a second PowerShell window while the SSH tunnel is running:

```powershell
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Open `https://localhost:8080`. Keep the Argo CD UI private. Read the initial admin password and rotate it by following [the Argo CD guide](operations/argocd.md#access-the-ui-privately).

## Later: Cloudflare and Name.com

No domain is needed for this setup. After the application name is chosen, configure the Name.com domain to use Cloudflare DNS, then add a Cloudflare Tunnel route for the frontend. Keep the Kubernetes API, Argo CD, and application services private.
