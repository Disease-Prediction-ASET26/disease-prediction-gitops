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

After SSO is configured, open [`https://argocd.pocket-doc.app`](https://argocd.pocket-doc.app) and choose Authelia. Sign in to Authelia with your account and complete its second factor. Argo CD's local `admin` login and anonymous access are disabled. The `argocd-admins` Authelia group receives Argo CD administrator permissions; other authenticated users receive no Argo CD permissions by default.

Add `argocd-admins` to the account's `groups` list in the `authelia-users` Vault secret, then wait for its ExternalSecret to become Ready and restart Authelia. Do not put the group mapping in Argo CD's default policy, since that would grant every authenticated user administrator access.

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

Then update the `argocd` Namespace label and publish the route. The Argo CD
route Application is intentionally not automated:

```bash
kubectl apply -f platform/argocd/namespace.yaml
argocd app sync argocd-route --core
argocd app wait argocd-route --core
```

The route is served by the internal Gateway and points to the ClusterIP `argocd-server` Service. TLS terminates at Cloudflare; the Gateway uses the Argo CD server's HTTP service port inside the cluster. Argo CD native OIDC is the authentication boundary, so this route deliberately does not add the generic Traefik ForwardAuth Middleware. The private service has no NodePort or LoadBalancer.

## Sync and roll back

Normal updates come from reviewed Git changes. If you need to sync immediately after a merge, use the Argo CD UI. To roll back an application, revert its image digest in Git and merge the change. Do not use a mutable image tag.

## Delete an application

Delete an individual child Application through Argo CD with cascading deletion enabled. Back up persistent data first. The full root and cluster teardown steps are in [Kubernetes operations](kubernetes.md#destroy-the-gitops-managed-resources) and the [Helmfile guide](helmfile.md#remove-the-argo-cd-release).
