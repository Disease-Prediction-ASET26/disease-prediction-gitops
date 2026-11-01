# Argo CD

Argo CD watches the GitOps repository's `main` branch. It is installed by Helmfile, while the root Application and its child application configuration live in checked-in Kubernetes files.

## Check status and view changes

```bash
kubectl -n argocd get applications,appprojects
kubectl -n argocd describe application oracle-root
```

After merging a change, Argo CD syncs it and repairs drift. Review pending changes in the Argo CD UI or use the Argo CD CLI if installed. Automated pruning is disabled, so removing a file does not automatically delete the live object.

## Private recovery and bootstrap

The local `admin` account and anonymous access are disabled in the checked-in
Helm values. Before Authelia OIDC is ready, or if SSO needs recovery, use the
CLI's core mode with a trusted kubeconfig. Core mode talks directly to the
Kubernetes API and bypasses Argo CD's server login:

```bash
argocd --core app list
argocd --core app sync oracle-root
```

Do not enable a password-based admin account as a routine recovery method.

## Access through Authelia

After SSO is configured, open [`https://argocd.pocket-doc.app`](https://argocd.pocket-doc.app) and choose Authelia. Sign in to Authelia with your account and complete its second factor. Argo CD's local `admin` login and anonymous access are disabled. Members of the existing Authelia `admins` group receive Argo CD administrator permissions; other authenticated users receive no Argo CD permissions by default.

Accounts in the existing `admins` group are administrators in Argo CD. No additional group is needed. Wait for the `authelia-users` ExternalSecret to become Ready and restart Authelia after changing group membership. Do not put the group mapping in Argo CD's default policy, since that would grant every authenticated user administrator access.

The Argo CD CLI uses the same OIDC flow:

```bash
argocd login argocd.pocket-doc.app --sso --grpc-web
```

The browser callback uses `http://localhost:8085/auth/callback`. Keep the CLI callback local; do not publish that hostname or port. For emergency recovery with a trusted kubeconfig, use Argo CD core mode (`argocd login --core`) or restore the checked-in Helmfile configuration through the normal review workflow. Do not leave the local admin account enabled as a recovery method.

## Enable SSO and publish the route

Create the OIDC secrets listed in the [Authelia runbook](authelia.md#prepare-the-oci-vault-secrets) before merging the SSO change. Wait for the relevant ExternalSecrets, then check that Authelia rolled out:

```bash
kubectl -n auth-system wait --for=condition=Ready externalsecret/authelia-core-secrets --timeout=5m
kubectl -n argocd wait --for=condition=Ready externalsecret/argocd-oidc-client --timeout=5m
kubectl -n auth-system rollout status deployment/authelia
```

Apply the checked-in Argo CD Helmfile values from the GitOps repository after reviewing the diff:

```bash
helmfile diff --diff-args "--allow-unreleased" --suppress-secrets
helmfile apply --interactive --diff-args "--allow-unreleased" --suppress-secrets
kubectl -n argocd rollout status deployment/argocd-server
```

The route and proxy are in `auth-system`; the Argo CD Application that manages
them is `argocd-route` in `argocd`. The root Kustomization labels `auth-system`
as eligible for public routes. The route Application is intentionally
manual-sync. On a new cluster, publish it only after OIDC is configured and the
OIDC ExternalSecret is Ready. In this cluster it has already been manually
synced:

```bash
kubectl get namespace auth-system --show-labels
argocd --core app sync argocd-route
argocd --core app wait argocd-route
```

The route is served by the internal Gateway and points to a small, unprivileged
proxy in `auth-system`, which forwards to the ClusterIP `argocd-server` Service.
Keeping the route outside the Argo CD namespace lets Traefik watch it without
read access to Argo CD's Kubernetes Secrets. TLS terminates at Cloudflare; the
proxy connects to Argo CD's HTTP service port inside the cluster. Argo CD native
OIDC is the authentication boundary, so this route deliberately does not add the
generic Traefik ForwardAuth Middleware. The Argo CD service has no NodePort or
LoadBalancer.

## Route OIDC back-channel inside the cluster

The internal path uses the public OIDC issuer but sends Argo CD's server-side
requests directly to Traefik's private HTTPS listener. Prepare the Cloudflare
Origin CA certificate and Vault secrets as described in the
[Authelia runbook](authelia.md#prepare-the-internal-oidc-certificate), then
merge the GitOps changes for the TLS Gateway listener and route.

Wait for External Secrets to create the TLS Secret and for the Gateway listener
to be programmed before applying the Argo CD Helmfile values:

```bash
kubectl -n auth-system wait --for=condition=Ready externalsecret/authelia-origin-tls --timeout=5m
kubectl -n traefik-system wait --for=condition=Programmed gateway/oracle-public --timeout=5m
kubectl -n auth-system get httproute authelia -o yaml
```

The HTTPRoute status must show the `websecure` parent as accepted. Then review
and apply Helmfile from the GitOps repository:

```bash
helmfile diff --diff-args "--allow-unreleased" --suppress-secrets
helmfile apply --interactive --diff-args "--allow-unreleased" --suppress-secrets
kubectl -n argocd rollout status deployment/argocd-server
kubectl -n argocd exec deploy/argocd-server -- getent ahostsv4 auth.pocket-doc.app
```

The final command should return Traefik's ClusterIP (`10.43.66.80`). Complete a
browser SSO login, then remove any temporary Cloudflare exception for Oracle's
public egress IP and OIDC paths. If login fails, restore the previous Helmfile
values and apply them before troubleshooting; the public Cloudflare route stays
available as a recovery path.

## Sync and roll back

Normal updates come from reviewed Git changes. If you need to sync immediately after a merge, use the Argo CD UI. To roll back an application, revert its image digest in Git and merge the change. Do not use a mutable image tag.

## Delete an application

Delete an individual child Application through Argo CD with cascading deletion enabled. Back up persistent data first. The full root and cluster teardown steps are in [Kubernetes operations](kubernetes.md#destroy-the-gitops-managed-resources) and the [Helmfile guide](helmfile.md#remove-the-argo-cd-release).
