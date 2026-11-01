# Authelia login and passkeys

Authelia provides a shared login portal for approved routes under
`pocket-doc.app`. The configured portal is at
[`https://auth.pocket-doc.app`](https://auth.pocket-doc.app). The first factor
is a local account and password; WebAuthn passkeys are the second factor.
Passwordless passkey login and TOTP are disabled. Future protected workload
routes can use the Traefik ForwardAuth middleware. Argo CD uses its native
OpenID Connect integration so the browser and CLI receive real Argo CD sessions
from Authelia.

## How it is deployed

- The Authelia image is pinned to `ghcr.io/authelia/authelia:4.39.28` and runs
  as one ARM64 replica in `auth-system`.
- Account YAML and runtime secrets are synchronized from OCI Vault by an
  External Secrets controller scoped to `auth-system`.
- Authelia's OIDC provider signs tokens with a Vault-backed RSA key and a
  separate HMAC secret. Its Argo CD client secret is stored as a digest in
  Vault; the plaintext client secret is stored separately for Argo CD.
- Authelia uses a 1 GiB `local-path` PVC for SQLite state, including registered
  WebAuthn credentials. The file backend and single replica are intended for
  this single-node cluster, not horizontal scaling.
- Traefik serves the portal through Gateway API. Its ForwardAuth Middleware
  lives in `disease-prediction` and calls Authelia over the cluster network.
- Traefik's namespaced reader is bound in `auth-system` and includes read access
  to Secrets there. Keep this namespace limited to authentication components.
  Traefik has no matching read permission in `argocd`, so it cannot read the
  Argo CD OIDC client Secret.
- The Authelia Service uses Traefik native load balancing so requests go to its
  ClusterIP; direct Traefik-to-pod IP connections are unavailable on this
  cluster.
- Traefik limits pod-originated web traffic to `cloudflared`; Kubernetes
  NetworkPolicy does not restrict node-originated traffic. Its trusted
  forwarded-header range is the K3s pod CIDR `10.42.0.0/16`; keep the
  NetworkPolicy and that CIDR aligned if the cluster network changes. See
  Authelia's [forwarded-header guidance](https://www.authelia.com/integration/proxies/forwarded-headers/).

The Middleware only enforces authentication and redirects unauthenticated
users to the portal. It does not configure application-specific SSO headers or
OIDC. Follow an application's own guide before enabling those features.
Traefik passes the original HTTPS scheme to Authelia using forwarded headers.
Its `trustForwardHeader` setting is paired with the entrypoint's trusted pod
range and the Cloudflared-only pod ingress policy; review this behavior when
upgrading Traefik beyond v3.

## Prepare the OCI Vault secrets

Create these nine secrets in the cluster's OCI Vault before applying the root
configuration on a new cluster. For an existing Authelia deployment, add the
four OIDC secrets before merging the SSO change. To enable Argo CD's internal
OIDC path, also create the two TLS secrets described below. Argo CD
automatically syncs the child Applications. Enter values through the OCI
Console or another secure secret-entry workflow. Do not put values in Git,
Terraform, shell arguments, chat, or logs.

| OCI Vault secret | Payload |
|---|---|
| `authelia-users` | Complete YAML user database, stored as the secret string |
| `authelia-session-secret` | Random string used to sign sessions |
| `authelia-storage-encryption-key` | Random key used to encrypt SQLite data |
| `authelia-reset-password-jwt-secret` | Random signing secret; required by Authelia even though password reset is disabled |
| `authelia-smtp` | JSON object described below |
| `authelia-oidc-hmac-secret` | Random 64+ character string used by the OIDC provider |
| `authelia-oidc-signing-key` | PEM-encoded RSA private key used to sign OIDC tokens |
| `authelia-argocd-client-secret-hash` | PBKDF2-SHA512 digest of the Argo CD OIDC client secret |
| `argocd-oidc-client-secret` | Plaintext secret paired with that digest, synced only into `argocd` |

Generate a password digest locally with the same pinned Authelia image. The
CLI prompts for the password without putting it in shell history:

```bash
docker run --rm -it ghcr.io/authelia/authelia:4.39.28 \
  authelia crypto hash generate argon2
```

Put the resulting digest in the complete user database YAML. Replace the
placeholders with the account details; never use a plain-text password:

```yaml
users:
  <username>:
    disabled: false
    displayname: '<display name>'
    password: '<argon2 digest>'
    email: '<account email>'
    groups:
      - admins
```

Create random session and encryption values locally with the pinned CLI. Use a
private terminal and transfer each output directly to OCI Vault:

```bash
docker run --rm ghcr.io/authelia/authelia:4.39.28 \
  authelia crypto rand --length 64 --charset alphanumeric
```

Repeat for session, storage, and reset-password JWT secrets. Do not reuse a
value for different purposes. The Authelia CLI and user-file format are documented in
the [password guide](https://www.authelia.com/reference/guides/passwords/) and
[secure-value guide](https://www.authelia.com/reference/guides/generating-secure-values/).

Generate the OIDC signing key and HMAC secret in a private temporary directory
outside the Git repository. Keep both files private. Enter the full PEM content
into OCI Vault as `authelia-oidc-signing-key`, and the HMAC file content as
`authelia-oidc-hmac-secret`:

```bash
umask 077
export AUTHELIA_SECRET_DIR="$(mktemp -d /dev/shm/authelia-oidc.XXXXXX)"
chmod 700 "$AUTHELIA_SECRET_DIR"
openssl rand -hex 48 > "$AUTHELIA_SECRET_DIR/authelia-oidc-hmac-secret"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$AUTHELIA_SECRET_DIR/authelia-oidc-signing-key.pem"
```

Generate the OIDC client secret and its matching digest together with the
pinned Authelia CLI. Store the **Random Password** output as
`argocd-oidc-client-secret` and the **Digest** output as
`authelia-argocd-client-secret-hash`:

```bash
docker run --rm ghcr.io/authelia/authelia:4.39.28 \
  authelia crypto hash generate pbkdf2 --variant sha512 --random \
  --random.length 72 --random.charset rfc3986
```

The command prints both values to the local terminal. Enter each directly in
OCI Vault; never paste them into Git, chat, or a command argument. Ensure the
`groups` list includes `admins` for each account that should administer Argo CD.
The existing `admins` group maps to Argo CD's administrator role. Authelia's
config template reads the PBKDF2 digest from a mounted file, while Argo CD gets
the plaintext value through its own namespace-scoped ESO controller.

## Prepare the internal OIDC certificate

In Cloudflare, open SSL/TLS → Origin Server → Create Certificate. Create a
Cloudflare Origin CA RSA certificate for exactly `auth.pocket-doc.app`. Store
its certificate PEM in OCI Vault secret `authelia-origin-tls-cert` and its
private key PEM in `authelia-origin-tls-key`. Do not put the private key in
Git or paste it into chat. External Secrets syncs these values into the
`auth-system/authelia-origin-tls` TLS Secret, which Traefik reads through a
narrow Gateway API `ReferenceGrant`. Create both Vault secrets before merging
the internal OIDC route change.

The Argo CD configuration trusts the public Cloudflare Origin RSA CA root
certificate for connections to the OIDC issuer. The root is public and is
checked in as `oidc.config.rootCA`; the private certificate key remains in OCI
Vault. The current root expires in 2029, so renew it before expiry and update
the checked-in root certificate when Cloudflare rotates its CA. The origin
certificate is used only by Argo CD's in-cluster back-channel. Browser access
continues to use Cloudflare's edge certificate.

The current deployment uses Authelia's SMTP notifier and requires an SMTP
server it can reach during startup. The `authelia-smtp` Vault secret must be a
JSON object with the fields below. If you do not have an SMTP provider, do not
enter placeholder values; change the checked-in notifier and secret wiring in a
reviewed Git change before deploying Authelia. Authelia requires exactly one
notification provider.

```json
{
  "address": "submission://smtp.example.net:587",
  "username": "<SMTP username>",
  "password": "<SMTP password>",
  "sender": "Authelia <auth@example.net>",
  "startup_check_address": "<address allowed by the SMTP provider>"
}
```

Use an SMTP endpoint on port 25, 465, or 587 with the matching `smtp://`,
`submissions://`, or `submission://` scheme. Authelia requires TLS for SMTP by
default and validates the server certificate. Do not disable TLS verification.
The startup-check address is checked against the SMTP server, but Authelia does
not actually send a message during that startup check. Treat the whole JSON
payload as a secret.
See the [SMTP configuration reference](https://www.authelia.com/configuration/notifications/smtp/)
for provider-specific address formats.

ESO creates `authelia-users`, `authelia-core-secrets`, and `authelia-smtp` in
`auth-system`. The Deployment requires these Kubernetes Secrets and the OIDC
values before it can start. Password changes and password resets are disabled
in the portal because the user database is read-only; update its hash through
OCI Vault instead. A separate ESO controller creates `argocd-oidc-client` in
the `argocd` namespace and is restricted to that namespace.

The ESO `controllerClass` setting is experimental. Before inviting users,
validate `external-secrets-auth` with a non-sensitive canary in `auth-system`,
using `oci-vault-auth` and the same process as
[the temporary canary](secrets.md#verify-with-a-temporary-canary). Use a
separate Vault canary secret for this controller and delete the temporary
ExternalSecret explicitly because Argo pruning is disabled.

## Install the Traefik CRD bundle

The Traefik chart skips CRDs. Before syncing the cluster root or any Traefik
CRD resource, install the versioned bundle through K3s. Follow
[Kubernetes operations](kubernetes.md#install-k3s-host-manifests), then verify:

```bash
kubectl get crd ingressroutes.traefik.io middlewares.traefik.io traefikservices.traefik.io
```

This is a spot check; use the wait command in Kubernetes operations to verify
all ten Traefik CRDs. The Gateway API CRDs and External Secrets CRDs must also
be established. See
[Kubernetes operations](kubernetes.md#k3s-host-managed-gateway-api-crds) and
[secret operations](secrets.md).

## Preview and deploy

From the GitOps repository root, render and review the manifests:

```bash
kubectl kustomize clusters/oracle
kubectl diff -k clusters/oracle
```

Merge the reviewed pull request only after the Vault values and Traefik CRD
bundle are ready. Argo CD creates the namespace-scoped ESO controllers, Vault
stores, Authelia portal, ForwardAuth Middleware, and Argo CD OIDC configuration.
The `argocd-route` Application is manual-sync. For a new deployment, follow the
[Argo CD SSO runbook](argocd.md#enable-sso-and-publish-the-route) to apply
Helmfile values and sync the route after the OIDC secret is Ready. The route is
already synced in the current cluster.

Check status without printing Kubernetes Secret data:

```bash
kubectl -n argocd get applications external-secrets-auth oci-auth-vault-store authelia authelia-forwardauth external-secrets-argocd-oidc argocd-oidc-vault-store argocd-route
kubectl -n auth-system get deployments,pods,services,secretstores,externalsecrets
kubectl -n argocd get secretstores,externalsecrets
kubectl -n auth-system get httproute authelia
kubectl -n traefik-system get gateway oracle-public
```

All ExternalSecrets and the SecretStore should become Ready; Authelia should be
Ready; and its HTTPRoute should be accepted and programmed. Check DNS and the
HTTPS portal:

```bash
dig auth.pocket-doc.app A
curl -I https://auth.pocket-doc.app/
```

Sign in with the account from `authelia-users`, then register a passkey when
prompted. Registration requires an HTTPS browser session and working SMTP
because Authelia sends a notification during WebAuthn registration. Passkey
login remains disabled, so the passkey is used as the second factor after the
account password. See the [WebAuthn configuration reference](https://www.authelia.com/configuration/second-factor/webauthn/).
Use the same canonical host, `auth.pocket-doc.app`, when accessing the portal.

## Protect an application route

Add the ForwardAuth filter to an app's `HTTPRoute` in the
`disease-prediction` namespace. Keep its existing backend and route matches:

```yaml
rules:
  - matches:
      - path:
          type: PathPrefix
          value: /
    filters:
      - type: ExtensionRef
        extensionRef:
          group: traefik.io
          kind: Middleware
          name: authelia-forwardauth
    backendRefs:
      - name: <app-service>
        port: <service-port>
```

The namespace must be allowed by the `oracle-public` Gateway. The application
must not also expose a direct public route, NodePort, or LoadBalancer that
bypasses Traefik. Render and review the `HTTPRoute` change, merge it, then check
its Gateway conditions and test a private browser session before public use.

The current Middleware is namespaced to `disease-prediction`. If an application
is placed in another namespace, add a namespaced Middleware there through its
reviewed app configuration and permit that resource in the appropriate
AppProject. Do not enable cross-namespace Middleware references cluster-wide
without reviewing the broader trust boundary.

## Rotate an account password or secret

To change an account password, generate a new Argon2 digest locally, update
the user database in OCI Vault, and wait for the `authelia-users` ExternalSecret
to become Ready. Then restart Authelia so it reads the updated read-only file:

```bash
kubectl -n auth-system rollout restart deployment/authelia
kubectl -n auth-system rollout status deployment/authelia
```

Rotate session, storage, JWT, and SMTP secrets through OCI Vault and confirm
ESO has synced them before restarting the Deployment. Rotating the storage
encryption key makes existing encrypted data unreadable; back up and migrate
that data before changing the key. Never print generated Kubernetes Secret
values to verify rotation.

## Back up the SQLite state

The PVC is `auth-system/authelia-data` on `local-path`. Take a quiesced archive
weekly and before VM replacement. The target is an RPO of seven days and an
RTO of two hours. Keep the three most recent weekly archives on an encrypted
off-VM device. The archive contains authentication state and must be handled
as sensitive data.

Argo CD self-heals the Deployment replica count, so scale it to zero through a
temporary reviewed Git change. Wait until the Authelia Pod is gone. Then find
the node-local PV path and create the archive on the VM:

```bash
kubectl -n auth-system get pvc authelia-data -o jsonpath='{.spec.volumeName}'
kubectl get pv <pv-name> -o jsonpath='{.spec.hostPath.path}'
```

Use the returned host path as `<pvc-path>` and substitute it below. Run this
after merging the temporary change that sets the Deployment to zero:

```bash
backup_name="authelia-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
backup_dir="$HOME/secure-authelia-backups"
volume_path='<pvc-path>'
umask 077
case "$volume_path" in
  /var/lib/rancher/k3s/storage/*) ;;
  *) echo "Unexpected local-path volume path" >&2; exit 1 ;;
esac
mkdir -p "$backup_dir"
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  "sudo tar -C '$volume_path' -czf '/tmp/$backup_name' . && sudo chown opc:opc '/tmp/$backup_name'"
scp -i "$HOME/.ssh/disease-prediction-oci.key" \
  "opc@oracle-k3s:/tmp/$backup_name" "$backup_dir/$backup_name"
ssh -i "$HOME/.ssh/disease-prediction-oci.key" opc@oracle-k3s \
  "sudo rm -f '/tmp/$backup_name'"
```

Keep `backup_dir` on an encrypted device, and after the archive is copied,
merge a reviewed change restoring `replicas: 1`.

Restore by scaling Authelia to zero through Git, confirming its replacement
PVC is Bound, copying the archive to `/tmp` on the VM, and extracting it into
the replacement PV directory with
`sudo tar -C '<pvc-path>' -xzf /tmp/<backup-name>`. Verify the PV path is under
`/var/lib/rancher/k3s/storage/` before extracting. Restore file ownership to
UID/GID 1000, then set the Deployment back to one replica through Git. Keep
the same storage encryption key when restoring an existing database.

Before real users register passkeys, take an initial archive and rehearse this
restore into a separate temporary PVC. Create and remove that PVC through
reviewed manifests. Record the result in the recovery notes. Until that restore
has been rehearsed, treat re-registering passkeys after storage loss as the
tested recovery path; the stated two-hour RTO is a target, not a measured result.

## Recovery and removal

The SQLite PVC uses node-local storage. A loss of the VM's boot volume can
remove registered passkeys and sessions. The account YAML and the encryption
key remain recoverable from OCI Vault; after a fresh Authelia database is
created, users may need to register their passkey again. See the
[cluster recovery runbook](recovery.md) before replacing the node.

To remove Authelia, first remove ForwardAuth filters from every application
route and sync those changes. Then remove the auth applications and
namespace-scoped secret resources through a reviewed Git change. Argo CD has
pruning disabled, so explicitly delete retained child Applications and their
resources. Deleting `auth-system` deletes the SQLite PVC and its contents.
Keep Vault values until Authelia and all protected routes have been removed.
See [secret operations](secrets.md#remove-eso) for cleaning up the dedicated
ESO controller.
