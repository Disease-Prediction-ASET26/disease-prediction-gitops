# Argo CD

Argo CD watches the GitOps repository's `main` branch. It is installed by Helmfile, while the root Application and its child application configuration live in checked-in Kubernetes files.

## Check status and view changes

```bash
kubectl -n argocd get applications,appprojects
kubectl -n argocd describe application oracle-root
```

After merging a change, Argo CD syncs it and repairs drift. Review pending changes in the Argo CD UI or use the Argo CD CLI if installed. Automated pruning is disabled, so removing a file does not automatically delete the live object.

## Access the UI privately

With Tailscale connected and the workstation kubeconfig configured, start a
local port-forward:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Open `https://localhost:8080`. Do not expose the service through a public IP, NodePort, or public tunnel.

Read the bootstrap password only when you are ready to sign in. Decode it from
the generated Kubernetes Secret:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o 'jsonpath={.data.password}' | base64 --decode
```

Sign in as `admin`, then change the password in Argo CD. Delete the bootstrap
Secret after the password has been changed:

```bash
kubectl -n argocd delete secret argocd-initial-admin-secret
```

Do not paste the password into Git, issues, or chat.

## Reset a lost admin password

The initial password Secret is not updated when you change the password. If
the current password is lost, remove the stored password hash and let Argo CD
generate a new initial password. This briefly restarts the API server:

```bash
kubectl -n argocd delete secret argocd-initial-admin-secret --ignore-not-found
kubectl -n argocd patch secret argocd-secret --type=json \
  -p='[{"op":"remove","path":"/data/admin.password"},{"op":"remove","path":"/data/admin.passwordMtime"}]'
kubectl -n argocd rollout restart deployment/argocd-server
kubectl -n argocd rollout status deployment/argocd-server
```

Read the newly generated password locally, sign in as `admin`, and change it
in Argo CD. Keep the password out of command history, Git, issues, and chat.

## Sync and roll back

Normal updates come from reviewed Git changes. If you need to sync immediately after a merge, use the Argo CD UI. To roll back an application, revert its image digest in Git and merge the change. Do not use a mutable image tag.

## Delete an application

Delete an individual child Application through Argo CD with cascading deletion enabled. Back up persistent data first. The full root and cluster teardown steps are in [Kubernetes operations](kubernetes.md#destroy-the-gitops-managed-resources) and the [Helmfile guide](helmfile.md#remove-the-argo-cd-release).
